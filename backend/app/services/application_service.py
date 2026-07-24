"""
Application service for scholarship application management
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc
from sqlalchemy import func as sa_func
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.cache import invalidate as cache_invalidate
from app.core.exceptions import AuthorizationError, BusinessLogicError, NotFoundError, ValidationError
from app.core.metrics import scholarship_applications_total, scholarship_reviews_total
from app.core.schema_validation import serialize_value
from app.models.audit_log import AuditAction, AuditLog
from app.models.application import Application, ApplicationStatus
from app.models.enums import REVIEWABLE_APPLICATION_STATUSES, ReviewStage, Semester
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole
from app.models.user_profile import UserProfile
from app.schemas.application import (
    ApplicationCreate,
    ApplicationFormData,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusUpdate,
    ApplicationUpdate,
    StudentDataSchema,
)
from app.services.eligibility_service import EligibilityService
from app.services.email_automation_service import email_automation_service
from app.services.email_service import EmailService
from app.services.minio_service import minio_service
from app.services.student_service import StudentService
from app.utils.phone_validation import (
    TAIWAN_MOBILE_MESSAGE,
    extract_contact_phone,
    is_valid_taiwan_mobile,
)

func: Any = sa_func

logger = logging.getLogger(__name__)


async def get_student_data_from_user(user: User) -> Optional[Dict[str, Any]]:
    """Get student data from external API using user's nycu_id"""
    if user.role != UserRole.student or not user.nycu_id:
        return None

    student_service = StudentService()
    return await student_service.get_student_basic_info(user.nycu_id)


class ApplicationService:
    """Application management service"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.emailService = EmailService()
        self.student_service = StudentService()

    @staticmethod
    async def _invalidate_app_caches() -> None:
        """Invalidate dashboard + quota caches after an application status change.

        Best-effort: failures here never raise, so a Redis outage degrades to
        "cache shows stale stats up to TTL" not "request fails."
        """
        try:
            await cache_invalidate("dashboard:")
            await cache_invalidate("quota:")
        except Exception:  # noqa: BLE001
            logger.warning("cache invalidation failed (non-fatal)", exc_info=True)

    def _serialize_for_json(self, data: Any) -> Any:
        """Serialize data for JSON response"""
        if isinstance(data, Decimal):
            return float(data)
        elif isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, list):
            return [self._serialize_for_json(item) for item in data]
        elif isinstance(data, dict):
            return {k: self._serialize_for_json(v) for k, v in data.items()}
        return data

    def _get_student_id_from_user(self, user: User) -> Optional[str]:
        """
        Get student ID from user (using nycu_id)

        The student_id in our system is the user's nycu_id (string format)
        """
        if not user or not user.nycu_id:
            return None
        return user.nycu_id

    def _extract_student_fields(self, student_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract commonly used student fields from student_data snapshot.

        Converts raw API data into structured fields for ApplicationResponse.
        Prefers term data (trm_*) over basic data (std_*) when both available.
        """
        if not student_data:
            return {}

        return {
            # Basic info
            "student_name": student_data.get("std_cname"),
            "student_no": student_data.get("std_stdcode"),
            "student_name_en": student_data.get("std_ename"),
            "student_pid": student_data.get("std_pid"),
            "student_email": student_data.get("com_email"),
            "student_phone": student_data.get("com_cellphone"),
            # Academic org (prefer term data)
            "academy_code": student_data.get("trm_academyno") or student_data.get("std_academyno"),
            "academy_name": student_data.get("trm_academyname"),
            "department_code": student_data.get("trm_depno") or student_data.get("std_depno"),
            "department_name": student_data.get("trm_depname"),
            "degree": student_data.get("trm_degree") or student_data.get("std_degree"),
            "studying_status": student_data.get("std_studingstatus"),
            # Enrollment
            "enroll_year": student_data.get("std_enrollyear"),
            "enroll_term": student_data.get("std_enrollterm"),
            "enroll_type": student_data.get("std_enrolltype"),
            "term_count": student_data.get("trm_termcount") or student_data.get("std_termcount"),
            # Identity
            "student_nationality": student_data.get("std_nation"),
            "student_identity": student_data.get("std_identity"),
            "school_identity": student_data.get("std_schoolid"),
            "gender": student_data.get("std_sex"),
            "studying_status_name": student_data.get("mgd_title"),
            # Performance
            "gpa": student_data.get("trm_ascore_gpa"),
            "class_ranking": student_data.get("trm_placings"),
            "class_ranking_percent": student_data.get("trm_placingsrate"),
            "dept_ranking": student_data.get("trm_depplacing"),
            "dept_ranking_percent": student_data.get("trm_depplacingrate"),
        }

    def _normalize_submitted_form_data(self, form_data: dict) -> dict:
        """
        Normalize submitted_form_data to new format (with 'fields' and 'documents' keys)

        Old format (flat structure):
        {
          "postal_account": "1212312312",
          "advisor_name": null,
          "custom_fields": {"master_school_info": "交大資工所"}
        }

        New format (nested structure):
        {
          "fields": {
            "postal_account": {"field_id": "postal_account", "field_type": "text", "value": "1212312312", ...},
            "master_school_info": {"field_id": "master_school_info", "field_type": "text", "value": "交大資工所", ...},
            ...
          },
          "documents": [...]
        }
        """
        if not form_data:
            return {"fields": {}, "documents": []}

        # If already in new format (has 'fields' key), return as is
        if "fields" in form_data and isinstance(form_data.get("fields"), dict):
            return form_data

        # Convert old format to new format
        fields = {}
        documents = form_data.get("documents", [])

        for key, value in form_data.items():
            # Skip special keys
            if key in ["documents", "files", "agree_terms"]:
                continue

            # Handle custom_fields: merge them into fields
            if key == "custom_fields" and isinstance(value, dict):
                for custom_key, custom_value in value.items():
                    fields[custom_key] = {
                        "field_id": custom_key,
                        "field_type": "text",  # Default type
                        "value": custom_value,
                        "required": False,
                    }
                continue

            # Create field object for new format
            fields[key] = {
                "field_id": key,
                "field_type": "text",  # Default type
                "value": value,
                "required": False,
            }

        return {"fields": fields, "documents": documents}

    async def _build_application_response(
        self, application: Application, user: Optional[User] = None
    ) -> ApplicationResponse:
        """
        Build ApplicationResponse from Application model
        """
        # If user is not provided, try to load it from the relationship
        if not user and hasattr(application, "student") and application.student:
            user = application.student
        elif not user:
            # Load user from database
            stmt = select(User).where(User.id == application.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()

        # Normalize submitted_form_data to new format
        normalized_form_data = self._normalize_submitted_form_data(
            application.submitted_form_data.copy() if application.submitted_form_data else {}
        )

        # Extract student fields from student_data snapshot
        student_fields = self._extract_student_fields(application.student_data)

        return ApplicationResponse(
            id=application.id,
            app_id=application.app_id,
            user_id=application.user_id,
            student_id=self._get_student_id_from_user(user) if user else None,
            scholarship_type_id=application.scholarship_type_id,
            scholarship_subtype_list=application.scholarship_subtype_list or [],
            sub_scholarship_type=application.sub_scholarship_type,
            status=application.status,
            status_name=application.status_name,
            is_renewal=application.is_renewal,
            renewal_year=application.renewal_year,
            previous_application_id=application.previous_application_id,
            challenges_application_id=application.challenges_application_id,
            cancelled_due_to_application_id=application.cancelled_due_to_application_id,
            academic_year=application.academic_year,
            semester=self._convert_semester_to_string(application.semester),
            student_data=application.student_data or {},
            submitted_form_data=normalized_form_data,
            agree_terms=application.agree_terms or False,
            professor_id=application.professor_id,
            reviewer_id=application.reviewer_id,
            final_approver_id=application.final_approver_id,
            submitted_at=application.submitted_at,
            reviewed_at=application.reviewed_at,
            approved_at=application.approved_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            meta_data=application.meta_data,
            **student_fields,  # Spread extracted student fields
        )

    def _convert_semester_to_string(self, semester) -> Optional[str]:
        """
        Convert semester to string format for schema validation
        """
        if semester is None:
            return None

        # If it's already a string, return as is
        if isinstance(semester, str):
            return semester

        # If it's an enum or has a value attribute, get the value
        if hasattr(semester, "value"):
            return str(semester.value)

        # Otherwise convert to string
        return str(semester)

    async def _generate_app_id(self, academic_year: int, semester: Optional[str]) -> str:
        """Generate sequential application ID (delegates to application_builder)."""
        from app.services.application_builder import generate_app_id

        return await generate_app_id(self.db, academic_year, semester)

    async def _validate_student_eligibility(
        self,
        student_data: Dict[str, Any],
        scholarship_type: str,
        application_data: ApplicationCreate,
    ) -> None:
        """Validate student eligibility for scholarship"""
        # Get scholarship type configuration
        stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()

        if not scholarship:
            raise NotFoundError("Scholarship type", scholarship_type)

        if not scholarship.is_active:
            raise ValidationError("Scholarship type is not active")

        if not scholarship.is_application_period:
            raise ValidationError("Application period has ended")

        # Check student type eligibility
        eligible_types: List[str] = scholarship.eligible_student_types or []
        student_type = self.student_service.get_student_type_from_data(student_data)
        if eligible_types and student_type not in eligible_types:
            raise ValidationError(f"Student type {student_type} is not eligible for this scholarship")

        # Check whitelist eligibility
        # NOTE: This method is deprecated and no longer used in create_application
        # Whitelist checking is now handled by EligibilityService
        # This code is kept for backward compatibility with tests
        nycu_id = student_data.get("std_stdcode", "")
        if scholarship.whitelist_enabled and nycu_id:
            # Get configuration to check whitelist (using first available config)
            stmt = (
                select(ScholarshipConfiguration)
                .where(
                    ScholarshipConfiguration.scholarship_type_id == scholarship.id,
                    ScholarshipConfiguration.is_active,
                )
                .limit(1)
            )
            result = await self.db.execute(stmt)
            config = result.scalar_one_or_none()

            if config and not config.is_student_in_whitelist(nycu_id):
                raise ValidationError("您不在此獎學金的白名單內，僅限預先核准的學生申請")

        # All validation requirements (ranking, term count, etc.) are now handled by scholarship rules
        # No hardcoded validation logic needed here

        # Note: Check for existing applications is now handled at the API endpoint level
        # where user_id is available from the authenticated user context

    async def _get_user_and_student_data(
        self, user_id: int, student_code: str, academic_year: int, semester: Optional[Semester]
    ) -> Tuple[User, Dict[str, Any]]:
        """Get user and fetch student data from external API"""
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one()

        # Convert semester enum to string for API call
        semester_str = None
        if semester:
            semester_str = semester.value  # "first" or "second"

        # Get student data from external API with term data
        logger.debug(
            f"Fetching student data for student_code={student_code}, year={academic_year}, semester={semester_str}"
        )
        student_snapshot = await self.student_service.get_student_snapshot(
            student_code, academic_year=str(academic_year), semester=semester_str
        )
        logger.debug(f"Student snapshot: {student_snapshot}")

        return user, student_snapshot

    async def _get_scholarship_and_config(
        self, application_data: ApplicationCreate
    ) -> Tuple[ScholarshipType, "ScholarshipConfiguration"]:
        """Get and validate scholarship type and configuration"""
        # Get scholarship type
        stmt = select(ScholarshipType).where(ScholarshipType.code == application_data.scholarship_type)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one()

        # Get the specific configuration that the student is eligible for
        from app.models.scholarship import ScholarshipConfiguration

        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.id == application_data.configuration_id
        )
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if not config:
            raise ValueError(f"Configuration with id {application_data.configuration_id} not found")

        # Verify the configuration belongs to the scholarship type
        if config.scholarship_type_id != scholarship.id:
            raise ValueError(
                f"Configuration {application_data.configuration_id} does not belong to scholarship type {application_data.scholarship_type}"
            )

        return scholarship, config

    @staticmethod
    def _derive_sub_scholarship_type(scholarship_subtype_list: Optional[List[str]]) -> str:
        """Delegates to application_builder (shared with batch import)."""
        from app.services.application_builder import derive_sub_scholarship_type

        return derive_sub_scholarship_type(scholarship_subtype_list)

    @staticmethod
    def _validate_sub_type_for_submission(scholarship: ScholarshipType, sub_scholarship_type: Optional[str]) -> None:
        """Delegates to application_builder (shared with batch import)."""
        from app.services.application_builder import validate_sub_type_for_submission

        validate_sub_type_for_submission(scholarship, sub_scholarship_type)

    async def _create_application_instance(
        self,
        user: User,
        student_snapshot: Dict[str, Any],
        scholarship: ScholarshipType,
        config: "ScholarshipConfiguration",
        application_data: ApplicationCreate,
        is_draft: bool,
    ) -> Application:
        """Create the application instance with all data"""
        academic_year = config.academic_year
        semester = config.semester  # This can be None for yearly scholarships
        logger.debug(f"Using config {config.id}: academic_year={academic_year}, semester={semester}")

        # Generate sequential application ID
        app_id = await self._generate_app_id(academic_year, semester)
        logger.debug(f"Generated app_id: {app_id}")

        # Determine sub_type_selection_mode from scholarship configuration
        sub_type_selection_mode = SubTypeSelectionMode.single  # Default
        if scholarship.sub_type_selection_mode:
            sub_type_selection_mode = scholarship.sub_type_selection_mode

        # Determine sub scholarship type from selected subtypes (use first one if any)
        scholarship_subtype_list = application_data.scholarship_subtype_list or []
        sub_scholarship_type = self._derive_sub_scholarship_type(scholarship_subtype_list)

        # Submitting (not a draft) requires a concrete sub-type when the
        # scholarship defines real ones — drafts may stay incomplete.
        if not is_draft:
            self._validate_sub_type_for_submission(scholarship, sub_scholarship_type)

        from app.models.enums import ApplicationStatus
        from app.services.application_builder import build_submitted_application_values
        from app.utils.i18n import ScholarshipI18n

        submitted_values = build_submitted_application_values(scholarship, config)

        if is_draft:
            status = ApplicationStatus.draft.value
            status_name = ScholarshipI18n.get_application_status_text(status)
        else:
            status = submitted_values["status"]
            status_name = submitted_values["status_name"]

        # Create application
        application = Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=scholarship.id,
            scholarship_configuration_id=config.id,
            scholarship_name=submitted_values["scholarship_name"],
            amount=submitted_values["amount"],
            scholarship_subtype_list=scholarship_subtype_list,
            # Ordered sub-type preference list (志願序). The distribution service
            # reads this first; without it, allocation falls back to selection
            # order. The frontend computes the order (MOE/moe_1w forced first).
            sub_type_preferences=application_data.sub_type_preferences,
            sub_type_selection_mode=sub_type_selection_mode,
            sub_scholarship_type=sub_scholarship_type,
            is_renewal=False,  # New applications are never renewals
            academic_year=academic_year,
            semester=semester,
            student_data=student_snapshot,
            submitted_form_data=application_data.form_data.dict() if application_data.form_data else {},
            agree_terms=application_data.agree_terms or False,
            status=status,
            status_name=status_name,
        )

        if not is_draft:
            application.submitted_at = submitted_values["submitted_at"]
            application.review_stage = submitted_values["review_stage"]

        return application

    async def create_application(
        self,
        user_id: int,
        student_code: str,  # User's nycu_id for fetching student data
        application_data: ApplicationCreate,
        is_draft: bool = False,
    ) -> ApplicationResponse:
        """Create a new application (draft or submitted)"""
        logger.debug(
            f"Starting application creation for user_id={user_id}, student_code={student_code}, is_draft={is_draft}"
        )
        logger.debug(f"Application data received: {application_data.dict(exclude_none=True)}")

        # Get and validate scholarship type and configuration first
        # (needed to determine academic_year and semester for student snapshot)
        scholarship, config = await self._get_scholarship_and_config(application_data)

        # Get user and student data with term information
        user, student_snapshot = await self._get_user_and_student_data(
            user_id, student_code, config.academic_year, config.semester
        )

        # Eligibility verification
        eligibility_service = EligibilityService(self.db)
        is_eligible, eligibility_errors = await eligibility_service.check_student_eligibility(
            student_data=student_snapshot, config=config, user_id=user.id
        )

        if not is_eligible:
            error_message = "Student is not eligible for this scholarship. " + "; ".join(eligibility_errors)
            raise ValidationError(error_message)

        # 直接提交（非草稿）時驗證聯絡電話格式；草稿允許暫存未完成的號碼。
        if not is_draft and application_data.form_data:
            self._enforce_contact_phone_format(application_data.form_data.fields)

        # Create application instance using helper method
        application = await self._create_application_instance(
            user, student_snapshot, scholarship, config, application_data, is_draft
        )

        self.db.add(application)
        await self.db.commit()
        await self.db.refresh(application)

        # Business metric: count the application by the status it was
        # created in (draft for save-as-draft, submitted for direct
        # submission). Mirrors what _submit also emits so dashboards can
        # decompose the total either way (issue #159).
        scholarship_applications_total.labels(status=application.status).inc()

        # Clone fixed documents (like bank account proof) for both draft and submitted applications
        # This ensures that fixed documents are available for preview and progress calculation
        try:
            await self._clone_user_profile_documents(application, user)
        except Exception as e:
            # Don't fail the entire application creation if document cloning fails
            logger.warning(
                f"Failed to clone fixed documents for application {application.app_id}: {e}",
                exc_info=True,
            )

        # Load relationships for response
        stmt = (
            select(Application)
            .where(Application.id == application.id)
            .options(
                selectinload(Application.files),
                selectinload(Application.reviews),
                selectinload(Application.scholarship),
            )
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one()

        logger.debug(f"Application created successfully: {application.app_id} with status: {application.status}")

        # Trigger email automation for directly-submitted applications (non-draft)
        if not is_draft:
            try:
                logger.info(f"=== STARTING EMAIL AUTOMATION for application {application.app_id} ===")
                user_profile_stmt = select(UserProfile).where(UserProfile.user_id == application.user_id)
                user_profile_result = await self.db.execute(user_profile_stmt)
                advisor_profile = user_profile_result.scalar_one_or_none()

                student_data = application.student_data or {}
                professor_name = advisor_profile.advisor_name or "" if advisor_profile else ""
                professor_email = advisor_profile.advisor_email or "" if advisor_profile else ""

                application_data_for_email = {
                    "id": application.id,
                    "app_id": application.app_id,
                    "student_data": student_data,
                    "student_name": student_data.get("std_cname", ""),
                    "student_email": student_data.get("com_email", ""),
                    "professor_name": professor_name,
                    "professor_email": professor_email,
                    "scholarship_type": getattr(application.scholarship, "name", "") if application.scholarship else "",
                    "scholarship_type_id": application.scholarship_type_id,
                    "submit_date": application.submitted_at.strftime("%Y-%m-%d") if application.submitted_at else "",
                }
                await email_automation_service.trigger_application_submitted(
                    self.db, application.id, application_data_for_email
                )
                logger.info(f"=== EMAIL AUTOMATION COMPLETED for application {application.app_id} ===")
            except Exception as e:
                logger.error(f"❌ Failed to trigger automated submission emails: {e}", exc_info=True)

        return await self._build_application_response(application, user)

    def _integrate_application_file_data(self, application: Application, user: User) -> Dict[str, Any]:
        """Integrate application file information into form data"""
        # 先標準化資料格式（將舊格式轉換為新格式）
        normalized_data = self._normalize_submitted_form_data(
            application.submitted_form_data.copy() if application.submitted_form_data else {}
        )

        integrated_form_data = normalized_data

        if not application.files:
            return integrated_form_data

        # Generate file access token
        from app.core.config import settings
        from app.core.security import create_access_token

        token_data = {"sub": str(user.id)}
        access_token = create_access_token(token_data)
        base_url = f"{settings.base_url}{settings.api_v1_str}"

        # Ensure documents array exists
        if "documents" not in integrated_form_data:
            integrated_form_data["documents"] = []

        # Create or update document records for each ApplicationFile
        for file in application.files:
            # Check if a record for this file already exists
            existing_doc = next(
                (
                    doc
                    for doc in integrated_form_data["documents"]
                    if doc.get("document_type") == file.file_type or doc.get("document_id") == file.file_type
                ),
                None,
            )

            # Create file information
            file_info = {
                "document_id": file.file_type,
                "document_type": file.file_type,
                "document_name": self._get_document_display_name(file.file_type),
                "file_id": file.id,
                "filename": file.filename,
                "original_filename": file.original_filename,
                "file_size": file.file_size,
                "mime_type": file.mime_type or file.content_type,
                "file_path": f"{base_url}/files/applications/{application.id}/files/{file.id}?token={access_token}",
                "download_url": f"{base_url}/files/applications/{application.id}/files/{file.id}/download?token={access_token}",
                "is_verified": file.is_verified,
                "object_name": file.object_name,
                "upload_time": file.uploaded_at.isoformat() if file.uploaded_at else None,
            }

            if existing_doc:
                # Update existing record
                existing_doc.update(file_info)
            else:
                # Add new record
                integrated_form_data["documents"].append(file_info)

        return integrated_form_data

    def _create_application_list_response(
        self, application: Application, user: User, integrated_form_data: Dict[str, Any]
    ) -> ApplicationListResponse:
        """Create ApplicationListResponse from application data"""
        return ApplicationListResponse(
            id=application.id,
            app_id=application.app_id,
            user_id=application.user_id,
            student_id=user.nycu_id if user else None,
            scholarship_type=application.scholarship.code if application.scholarship else None,
            scholarship_type_id=application.scholarship_type_id,
            scholarship_type_zh=application.scholarship.name if application.scholarship else None,
            scholarship_subtype_list=application.scholarship_subtype_list or [],
            sub_scholarship_type=application.sub_scholarship_type,
            status=application.status,
            status_name=application.status_name,
            review_stage=serialize_value(application.review_stage),
            is_renewal=application.is_renewal,
            renewal_year=application.renewal_year,
            previous_application_id=application.previous_application_id,
            challenges_application_id=application.challenges_application_id,
            cancelled_due_to_application_id=application.cancelled_due_to_application_id,
            academic_year=application.academic_year,
            semester=self._convert_semester_to_string(application.semester),
            student_data=application.student_data or {},
            submitted_form_data=integrated_form_data,
            agree_terms=application.agree_terms or False,
            professor_id=application.professor_id,
            reviewer_id=application.reviewer_id,
            final_approver_id=application.final_approver_id,
            submitted_at=application.submitted_at,
            reviewed_at=application.reviewed_at,
            approved_at=application.approved_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            meta_data=application.meta_data,
            requires_professor_recommendation=bool(
                application.scholarship_configuration
                and application.scholarship_configuration.requires_professor_review_for(bool(application.is_renewal))
            ),
            requires_college_review=bool(
                application.scholarship_configuration
                and application.scholarship_configuration.requires_college_review_for(bool(application.is_renewal))
            ),
            allow_college_view_distribution=bool(
                application.scholarship_configuration
                and application.scholarship_configuration.allow_college_view_distribution
            ),
        )

    async def get_user_applications(self, user: User, status: Optional[str] = None) -> List[ApplicationListResponse]:
        """Get applications for a user"""
        stmt = (
            select(Application)
            .options(
                selectinload(Application.files),
                selectinload(Application.scholarship),
                selectinload(Application.scholarship_configuration),
            )
            .where(Application.user_id == user.id)
        )

        if status:
            stmt = stmt.where(Application.status == status)
        else:
            # 預設不顯示已刪除的申請
            stmt = stmt.where(Application.status != ApplicationStatus.deleted.value)

        stmt = stmt.order_by(desc(Application.created_at))
        result = await self.db.execute(stmt)
        applications = result.scalars().all()

        response_list = []
        for application in applications:
            # Integrate file information into submitted_form_data.documents
            integrated_form_data = self._integrate_application_file_data(application, user)

            # Create response data
            app_data = self._create_application_list_response(application, user, integrated_form_data)
            response_list.append(app_data)

        return response_list

    async def get_student_dashboard_stats(self, user: User) -> Dict[str, Any]:
        """Get dashboard statistics for student"""
        # Count applications by status (排除已刪除的申請)
        stmt = (
            select(Application.status, func.count(Application.id).label("count"))
            .where(Application.user_id == user.id)
            .where(Application.status != ApplicationStatus.deleted.value)
            .group_by(Application.status)
        )

        result = await self.db.execute(stmt)
        status_counts = {}
        total_applications = 0

        for row in result:
            count_value = row[1]  # Access by index since count is the second column
            status_counts[row[0]] = count_value  # status is the first column
            total_applications += count_value

        # Get recent applications with files loaded (排除已刪除的申請)
        stmt = (
            select(Application)
            .options(selectinload(Application.files), selectinload(Application.scholarship))
            .where(Application.user_id == user.id)
            .where(Application.status != ApplicationStatus.deleted.value)
            .order_by(desc(Application.created_at))
            .limit(5)
        )

        result = await self.db.execute(stmt)
        recent_applications = result.scalars().all()

        # Convert to response models with integrated file data
        recent_applications_response = []
        for application in recent_applications:
            # 整合 application.files 進 submitted_form_data.documents（create-or-update，共用 helper）。
            integrated_form_data = self._integrate_application_file_data(application, user)

            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=user.nycu_id if user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_type_zh=application.scholarship.name if application.scholarship else "未知獎學金",
                scholarship_subtype_list=application.scholarship_subtype_list or [],
                sub_scholarship_type=application.sub_scholarship_type,
                status=application.status,
                status_name=application.status_name,
                is_renewal=application.is_renewal,
                renewal_year=application.renewal_year,
                previous_application_id=application.previous_application_id,
                challenges_application_id=application.challenges_application_id,
                cancelled_due_to_application_id=application.cancelled_due_to_application_id,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data or {},
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms or False,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data,
            )

            recent_applications_response.append(app_data)

        return {
            "total_applications": total_applications,
            "status_counts": status_counts,
            "recent_applications": recent_applications_response,
        }

    async def _get_application_model(self, application_id: int, current_user: User) -> Application | None:
        """Internal method to get raw Application model with access control

        Use this for operations that need to modify the application.
        For read-only operations that need the response format, use get_application_by_id instead.
        """
        stmt = (
            select(Application)
            .options(
                selectinload(Application.files),
                selectinload(Application.reviews).selectinload(ApplicationReview.reviewer),
                selectinload(Application.reviews).selectinload(ApplicationReview.items),
                selectinload(Application.scholarship_configuration).selectinload(
                    ScholarshipConfiguration.scholarship_type
                ),
                selectinload(Application.scholarship).selectinload(
                    ScholarshipType.sub_type_configs
                ),  # Preload scholarship with sub_type_configs for labels
                selectinload(Application.student),
            )
            .where(Application.id == application_id)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            return None

        # Check access permissions
        if current_user.role == UserRole.student:
            if application.user_id != current_user.id:
                return None
        elif current_user.role == UserRole.professor:
            if application.professor_id != current_user.id:
                return None
        elif current_user.role in [
            UserRole.college,
            UserRole.admin,
            UserRole.super_admin,
        ]:
            pass
        else:
            return None

        return application

    async def get_application_by_id(self, application_id: int, current_user: User):
        """Get application by ID with proper access control and formatted response"""
        # Use internal method to get the application model
        application = await self._get_application_model(application_id, current_user)

        if not application:
            return None

        # 整合 application.files 的檔案參照進 submitted_form_data.documents。
        # 使用共用 helper（其他讀取路徑也用它）：它會「create-or-update」——把尚未
        # 出現在 documents[] 的已上傳檔案「補進去」。先前這裡的 inline 迴圈只更新
        # 已存在的 doc，所以以 documents:[] 存的草稿在重開時會掉光所有上傳檔案。
        integrated_form_data = self._integrate_application_file_data(application, current_user)

        # Construct ApplicationResponse with additional display fields
        from app.schemas.application import ApplicationResponse

        # Get scholarship type information for display
        scholarship_type_name = None
        scholarship_type_zh = None
        scholarship_name = None
        amount = application.amount
        currency = "TWD"

        if application.scholarship_configuration and application.scholarship_configuration.scholarship_type:
            scholarship_type_name = application.scholarship_configuration.scholarship_type.code
            scholarship_type_zh = application.scholarship_configuration.scholarship_type.name
            scholarship_name = application.scholarship_configuration.config_name
            amount = application.scholarship_configuration.amount
            currency = application.scholarship_configuration.currency or "TWD"
        elif application.scholarship:  # Fallback for batch import applications without scholarship_configuration
            scholarship_type_name = application.scholarship.code
            scholarship_type_zh = application.scholarship.name
            scholarship_name = application.scholarship.name

        # Extract student fields from student_data snapshot
        student_fields = self._extract_student_fields(application.student_data)

        # Get user information as fallback for student_name and student_no
        if not student_fields.get("student_name") and application.student:
            student_fields["student_name"] = application.student.name
        if not student_fields.get("student_no") and application.student:
            student_fields["student_no"] = application.student.nycu_id

        # 郵局帳號 lives on the student's UserProfile (student self-service and
        # batch import both write it there — never into submitted_form_data).
        from app.models.user_profile import UserProfile

        profile_result = await self.db.execute(select(UserProfile).where(UserProfile.user_id == application.user_id))
        student_profile = profile_result.scalar_one_or_none()
        postal_account = student_profile.account_number if student_profile else None

        # Build sub_type labels from scholarship.sub_type_configs
        sub_type_labels = {}
        if application.scholarship and hasattr(application.scholarship, "sub_type_configs"):
            for config in application.scholarship.sub_type_configs:
                if config.is_active:
                    sub_type_labels[config.sub_type_code] = {
                        "zh": config.name,
                        "en": config.name_en or config.name,
                    }

        # Build ApplicationResponse with all the original fields plus display fields
        response_data = {
            # Original Application fields
            "id": application.id,
            "app_id": application.app_id,
            "user_id": application.user_id,
            "student_id": application.student.nycu_id if application.student else None,
            "scholarship_type_id": application.scholarship_type_id,
            "scholarship_subtype_list": application.scholarship_subtype_list or [],
            "sub_scholarship_type": application.sub_scholarship_type,
            "sub_type_labels": sub_type_labels,
            "status": application.status,
            "status_name": application.status_name,
            "review_stage": serialize_value(application.review_stage),
            "is_renewal": application.is_renewal,
            "renewal_year": application.renewal_year,
            "previous_application_id": application.previous_application_id,
            "challenges_application_id": application.challenges_application_id,
            "cancelled_due_to_application_id": application.cancelled_due_to_application_id,
            "academic_year": application.academic_year,
            "semester": self._convert_semester_to_string(application.semester),
            "student_data": application.student_data or {},
            "submitted_form_data": integrated_form_data,
            "agree_terms": application.agree_terms,
            "professor_id": application.professor_id,
            "reviewer_id": application.reviewer_id,
            "final_approver_id": application.final_approver_id,
            "submitted_at": application.submitted_at,
            "reviewed_at": application.reviewed_at,
            "approved_at": application.approved_at,
            "created_at": application.created_at,
            "updated_at": application.updated_at,
            "meta_data": application.meta_data,
            "reviews": (
                []
                if current_user.role == UserRole.student
                else [
                    {
                        "id": review.id,
                        "application_id": review.application_id,
                        "reviewer_id": review.reviewer_id,
                        "recommendation": review.recommendation,
                        "comments": review.comments,
                        "reviewed_at": review.reviewed_at,
                        "created_at": review.created_at,
                        "reviewer_name": review.reviewer.name if review.reviewer else None,
                        "reviewer_role": review.reviewer.role if review.reviewer else None,
                    }
                    for review in (application.reviews or [])
                ]
            ),
            "professor_review_items": (
                []
                if current_user.role == UserRole.student
                else [
                    {
                        "sub_type_code": item.sub_type_code,
                        "recommendation": item.recommendation,
                        "comments": item.comments,
                    }
                    for review in (application.reviews or [])
                    if review.reviewer
                    and (review.reviewer.role.value if hasattr(review.reviewer.role, "value") else review.reviewer.role)
                    == "professor"
                    for item in (review.items or [])
                ]
            ),
            # Additional display fields
            "scholarship_type": scholarship_type_name,
            "scholarship_type_zh": scholarship_type_zh,
            "scholarship_name": scholarship_name,
            "amount": amount,
            "currency": currency,
            "postal_account": postal_account,
            **student_fields,  # Spread extracted student fields
            # Workflow configuration flags
            "requires_professor_recommendation": bool(
                application.scholarship_configuration
                and application.scholarship_configuration.requires_professor_review_for(bool(application.is_renewal))
            ),
            "requires_college_review": bool(
                application.scholarship_configuration
                and application.scholarship_configuration.requires_college_review_for(bool(application.is_renewal))
            ),
            "allow_college_view_distribution": bool(
                application.scholarship_configuration
                and application.scholarship_configuration.allow_college_view_distribution
            ),
        }

        return ApplicationResponse(**response_data)

    async def update_application(
        self, application_id: int, update_data: ApplicationUpdate, current_user: User
    ) -> Application:
        """更新申請資料"""

        # 取得申請 (use internal method to get the model for modification)
        application = await self._get_application_model(application_id, current_user)
        if not application:
            raise NotFoundError(f"Application {application_id} not found")

        # 檢查是否可以編輯
        if not application.is_editable:
            raise ValidationError("Application cannot be edited in current status")

        # Store old subtype list for comparison
        old_subtype_list = application.scholarship_subtype_list.copy() if application.scholarship_subtype_list else []

        # 更新表單資料
        if update_data.form_data:
            # Serialize form data to handle datetime objects properly
            application.submitted_form_data = self._serialize_for_json(update_data.form_data.dict())

        # 更新狀態
        if update_data.status:
            application.status = update_data.status

        # 更新續領申請標識
        if update_data.is_renewal is not None:
            application.is_renewal = update_data.is_renewal

        # 更新子項目列表（如果提供）
        if update_data.scholarship_subtype_list is not None:
            application.scholarship_subtype_list = update_data.scholarship_subtype_list
            # Keep the denormalized scalar in sync with the list, otherwise an
            # edit that picks a real sub-type (e.g. nstc) leaves a stale "general"
            # scalar — which submit_application's guard would then reject, blocking
            # the very correction the student is making.
            application.sub_scholarship_type = self._derive_sub_scholarship_type(update_data.scholarship_subtype_list)

        # 更新志願序（如果提供）— persist the ordered preference list so the
        # distribution service uses it instead of falling back to selection order.
        if update_data.sub_type_preferences is not None:
            application.sub_type_preferences = update_data.sub_type_preferences

        await self.db.commit()
        await self.db.refresh(application)
        if update_data.status:
            await self._invalidate_app_caches()

        # Clone bank account proof document when saving draft or updating application
        # This ensures the document is available in the application
        logger.info(f"Cloning bank account proof document for application {application.app_id}")
        try:
            await self._clone_user_profile_documents(application, current_user)
        except Exception:
            logger.warning(
                f"Failed to clone bank account proof document for application {application.app_id}", exc_info=True
            )
            import traceback

            traceback.print_exc()

        # Check if subtype list changed and re-clone fixed documents if necessary
        new_subtype_list = application.scholarship_subtype_list.copy() if application.scholarship_subtype_list else []
        if old_subtype_list != new_subtype_list:
            logger.info(
                f"Subtype list changed from {old_subtype_list} to {new_subtype_list}, re-cloning fixed documents"
            )
            try:
                await self._clone_user_profile_documents(application, current_user)
            except Exception:
                logger.warning(
                    "Failed to re-clone fixed documents after subtype change for application %s",
                    application.app_id,
                    exc_info=True,
                )

        return application

    async def update_student_data(
        self,
        application_id: int,
        student_data_update: StudentDataSchema,
        current_user: User,
        refresh_from_api: bool = False,
    ) -> Application:
        """更新申請中的學生資料

        Args:
            application_id: 申請ID
            student_data_update: 要更新的學生資料
            current_user: 當前用戶
            refresh_from_api: 是否重新從外部API獲取基本學生資料
        """

        # 取得申請 (use internal method to get the model for modification)
        application = await self._get_application_model(application_id, current_user)
        if not application:
            raise NotFoundError(f"Application {application_id} not found")

        # 檢查權限
        if current_user.role not in [
            UserRole.admin,
            UserRole.super_admin,
            UserRole.college,
        ]:
            if application.user_id != current_user.id:
                raise AuthorizationError("You can only update your own application data")

        # 檢查是否可以編輯
        if application.status not in [
            ApplicationStatus.draft.value,
            ApplicationStatus.returned.value,
        ]:
            raise ValidationError("Cannot update student data for submitted applications")

        # 獲取當前學生資料
        current_student_data = application.student_data or {}

        # 如果需要，重新從外部API獲取基本學生資料
        if refresh_from_api:
            if not current_user.nycu_id or not current_user.nycu_id.strip():
                raise ValidationError("Student NYCU ID is required to refresh data from API")

            fresh_api_data = await self.student_service.get_student_snapshot(current_user.nycu_id)
            if fresh_api_data:
                # 合併API資料，但保留用戶輸入的資料
                current_student_data.update(fresh_api_data)

        # 合併用戶更新的資料
        update_dict = student_data_update.model_dump(exclude_none=True)
        for field, value in update_dict.items():
            if field in ["financial_info", "supervisor_info"]:
                # 對於嵌套對象，進行深度合併
                if value:
                    if field not in current_student_data:
                        current_student_data[field] = {}
                    current_student_data[field].update(value)
            else:
                # 對於普通欄位，直接更新
                current_student_data[field] = value

        # 更新到資料庫。current_student_data may be the SAME dict reference
        # as application.student_data (line 1165's `or {}` only branches when
        # student_data is falsy), so plain `=` assignment doesn't change the
        # column's object identity. SQLAlchemy's default JSON change detection
        # compares identity, not contents, so without flag_modified() the
        # in-place mutations above would be silently dropped on commit.
        from sqlalchemy.orm.attributes import flag_modified

        application.student_data = current_student_data
        flag_modified(application, "student_data")

        await self.db.commit()
        await self.db.refresh(application)

        return application

    def _enforce_contact_phone_format(self, form_fields: Optional[Dict[str, Any]]) -> None:
        """Reject a submission whose contact_phone is present but not a TW mobile.

        The number must be pure digits starting with 09 and 10 digits long.
        Empty/absent values are deferred to the required-field check so forms
        without a contact_phone field keep submitting unchanged.
        """
        phone = extract_contact_phone(form_fields)
        if phone is None or phone == "":
            return
        if not is_valid_taiwan_mobile(phone):
            raise ValidationError(TAIWAN_MOBILE_MESSAGE)

    async def submit_application(self, application_id: int, user: User) -> ApplicationResponse:
        """提交申請"""
        # Get application with relationships loaded
        stmt = (
            select(Application)
            .options(
                selectinload(Application.files),
                selectinload(Application.reviews).selectinload(ApplicationReview.reviewer),
                selectinload(Application.scholarship),
            )
            .where(Application.id == application_id)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError(f"Application {application_id} not found")

        if not application.is_editable:
            allowed_statuses = [ApplicationStatus.draft.value, ApplicationStatus.returned.value]
            raise ValidationError(
                f"Application cannot be submitted in current status '{application.status.value}'. "
                f"Only applications with status {', '.join(repr(s) for s in allowed_statuses)} can be submitted."
            )

        # 驗證所有必填欄位
        _ = ApplicationFormData(**application.submitted_form_data)

        # 驗證聯絡電話格式（台灣手機，09 開頭共十碼純數字）
        self._enforce_contact_phone_format((application.submitted_form_data or {}).get("fields"))

        # A draft can only be submitted once it carries a concrete sub-type
        # for scholarships that define real ones (the "general" fallback maps
        # to no quota slot at distribution time).
        self._validate_sub_type_for_submission(application.scholarship, application.sub_scholarship_type)

        # 處理銀行帳戶證明文件 clone（從個人資料複製到申請）
        await self._clone_user_profile_documents(application, user)

        # 更新狀態為已提交
        from app.utils.i18n import ScholarshipI18n

        application.status = ApplicationStatus.submitted
        application.status_name = ScholarshipI18n.get_application_status_text(ApplicationStatus.submitted.value)
        # Advance the workflow stage off student_draft so reviewers no longer
        # see "學生編輯中" on a submitted application (it now awaits professor review).
        application.review_stage = ReviewStage.student_submitted.value
        application.submitted_at = datetime.now(timezone.utc)
        application.updated_at = datetime.now(timezone.utc)

        # Business metric: increment submitted counter so the Scholarship
        # System Overview dashboard panel for new submissions starts
        # reflecting real KPIs (issue #159).
        scholarship_applications_total.labels(status=ApplicationStatus.submitted.value).inc()

        # Load user profile once (reused for auto-assign professor and email notification)
        user_profile_stmt = select(UserProfile).where(UserProfile.user_id == application.user_id)
        user_profile_result = await self.db.execute(user_profile_stmt)
        advisor_profile = user_profile_result.scalar_one_or_none()

        # 自動分配指導教授：根據 UserProfile 的 advisor_nycu_id 查找教授帳號
        from app.services.application_builder import assign_professor_from_profile

        await assign_professor_from_profile(self.db, application, application.user_id, profile=advisor_profile)

        await self.db.commit()
        await self._invalidate_app_caches()

        # Re-query with eager loading to avoid MissingGreenlet on expired attributes
        stmt = (
            select(Application)
            .options(
                selectinload(Application.files),
                selectinload(Application.reviews).selectinload(ApplicationReview.reviewer),
                selectinload(Application.scholarship),
            )
            .where(Application.id == application.id)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one()

        # 發送自動化通知
        try:
            logger.info(f"=== STARTING EMAIL AUTOMATION for application {application.id} ===")

            # Extract student data from JSON field
            student_data = application.student_data or {}

            # Extract professor information from user profile
            professor_name = ""
            professor_email = ""
            if application.student and advisor_profile:
                professor_name = advisor_profile.advisor_name or ""
                professor_email = advisor_profile.advisor_email or ""

            # Prepare application data for email automation
            application_data = {
                "id": application.id,
                "app_id": application.app_id,
                "student_data": student_data,  # Pass complete student_data JSON
                "student_name": student_data.get("std_cname", ""),  # Extract from student_data
                "student_email": student_data.get("com_email", ""),  # Extract from student_data
                "professor_name": professor_name,  # From user profile
                "professor_email": professor_email,  # From user profile
                "scholarship_type": getattr(application.scholarship, "name", "") if application.scholarship else "",
                "scholarship_type_id": application.scholarship_type_id,
                "submit_date": application.submitted_at.strftime("%Y-%m-%d") if application.submitted_at else "",
            }
            logger.info(f"Application data prepared: {application_data}")

            # Trigger email automation for application submission
            logger.info("Calling email_automation_service.trigger_application_submitted()...")
            await email_automation_service.trigger_application_submitted(self.db, application.id, application_data)
            logger.info(f"=== EMAIL AUTOMATION COMPLETED for application {application.id} ===")
        except Exception as e:
            logger.error(f"❌ Failed to trigger automated submission emails: {e}", exc_info=True)

        # 整合 application.files 進 submitted_form_data.documents（create-or-update，共用 helper）。
        # 僅用於 response（不寫回 DB），與 get_application_by_id 一致；避免以 documents:[] 存的草稿送出後掉檔。
        integrated_form_data = self._integrate_application_file_data(application, user)

        # Convert application to response model
        response_data = {
            "id": application.id,
            "app_id": application.app_id,
            "user_id": application.user_id,
            "student_id": self._get_student_id_from_user(user),
            "scholarship_type_id": application.scholarship_type_id,
            "scholarship_subtype_list": application.scholarship_subtype_list,
            "sub_scholarship_type": application.sub_scholarship_type,
            "status": application.status,
            "status_name": application.status_name,
            "is_renewal": application.is_renewal,
            "renewal_year": application.renewal_year,
            "previous_application_id": application.previous_application_id,
            "challenges_application_id": application.challenges_application_id,
            "cancelled_due_to_application_id": application.cancelled_due_to_application_id,
            "academic_year": application.academic_year,
            "semester": application.semester,
            "student_data": application.student_data,
            "submitted_form_data": integrated_form_data,  # 使用整合後的表單資料
            "agree_terms": application.agree_terms,
            "professor_id": application.professor_id,
            "reviewer_id": application.reviewer_id,
            "final_approver_id": application.final_approver_id,
            "submitted_at": application.submitted_at,
            "reviewed_at": application.reviewed_at,
            "approved_at": application.approved_at,
            "created_at": application.created_at,
            "updated_at": application.updated_at,
            "meta_data": application.meta_data,
            # 移除獨立的 files 欄位
            "reviews": [
                {
                    "id": review.id,
                    "application_id": review.application_id,
                    "reviewer_id": review.reviewer_id,
                    "recommendation": review.recommendation,
                    "comments": review.comments,
                    "reviewed_at": review.reviewed_at,
                    "created_at": review.created_at,
                    "reviewer_name": review.reviewer.name if review.reviewer else None,
                    "reviewer_role": review.reviewer.role if review.reviewer else None,
                }
                for review in application.reviews
            ],
        }

        return ApplicationResponse(**response_data)

    async def _get_accessible_student_ids(self, professor: User, permission: str = "view_applications") -> List[int]:
        """Student IDs this professor may access, queried async-safely.

        The former User.get_accessible_student_ids traversed the lazy
        professor_relationships collection, which raises MissingGreenlet
        under an AsyncSession (issue #1130) — query the rows explicitly.
        """
        from app.models.professor_student import ProfessorStudentRelationship

        stmt = select(ProfessorStudentRelationship).where(
            ProfessorStudentRelationship.professor_id == professor.id,
            ProfessorStudentRelationship.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        return [rel.student_id for rel in result.scalars().all() if rel.has_permission(permission)]

    async def get_applications_for_review(
        self,
        current_user: User,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        scholarship_type: Optional[str] = None,
    ) -> List[ApplicationListResponse]:
        """Get applications for review with proper access control"""
        # Build query based on user role
        query = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.scholarship),
            selectinload(Application.student),  # Eagerly load student to avoid N+1 queries
        )

        if current_user.role == UserRole.professor:
            # Filter applications to only those from accessible students
            accessible_student_ids = await self._get_accessible_student_ids(current_user)
            if accessible_student_ids:
                query = query.where(Application.user_id.in_(accessible_student_ids))
            else:
                # No accessible students, return empty result
                return []
        elif current_user.role in [
            UserRole.college,
            UserRole.admin,
            UserRole.super_admin,
        ]:
            # College, Admin, and Super Admin can see all applications
            pass
        else:
            # Other roles cannot review applications
            return []

        # Apply filters
        if status:
            query = query.where(Application.status == status)
        if scholarship_type:
            # Get scholarship type ID for filtering
            stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
            result = await self.db.execute(stmt)
            scholarship = result.scalar_one_or_none()
            if scholarship:
                query = query.where(Application.scholarship_type_id == scholarship.id)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Execute query
        result = await self.db.execute(query)
        applications = result.scalars().all()

        # Convert to response models
        response_applications = []
        for application in applications:
            # 整合 application.files 進 submitted_form_data.documents（create-or-update，共用 helper）。
            # 與 get_application_by_id 一致：把尚未出現在 documents[] 的已上傳檔案補進去（審核列表才不會掉檔）。
            integrated_form_data = self._integrate_application_file_data(application, current_user)

            # Use eagerly loaded student (already loaded with selectinload)
            app_user = application.student

            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=app_user.nycu_id if app_user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_type_zh=application.scholarship.name if application.scholarship else None,
                scholarship_subtype_list=application.scholarship_subtype_list or [],
                sub_scholarship_type=application.sub_scholarship_type,
                status=application.status,
                status_name=application.status_name,
                is_renewal=application.is_renewal,
                renewal_year=application.renewal_year,
                previous_application_id=application.previous_application_id,
                challenges_application_id=application.challenges_application_id,
                cancelled_due_to_application_id=application.cancelled_due_to_application_id,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data or {},
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms or False,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data,
            )

            response_applications.append(app_data)

        return response_applications

    # G16 (#978): legal staff transitions for PATCH /applications/{id}/status.
    # Anything outside this table needs an admin/super_admin override WITH a
    # written reason (and the endpoint's audit row records old→new+reason).
    # `draft` and `deleted` are never reachable through this endpoint — drafts
    # belong to the student flow, deletion to the delete endpoints.
    _STAFF_STATUS_TRANSITIONS: Dict[str, set] = {
        ApplicationStatus.submitted.value: {
            ApplicationStatus.under_review.value,
            ApplicationStatus.pending_documents.value,
            ApplicationStatus.returned.value,
            ApplicationStatus.approved.value,
            ApplicationStatus.partial_approved.value,
            ApplicationStatus.rejected.value,
            ApplicationStatus.cancelled.value,
            ApplicationStatus.manual_excluded.value,
        },
        ApplicationStatus.under_review.value: {
            ApplicationStatus.pending_documents.value,
            ApplicationStatus.returned.value,
            ApplicationStatus.approved.value,
            ApplicationStatus.partial_approved.value,
            ApplicationStatus.rejected.value,
            ApplicationStatus.cancelled.value,
            ApplicationStatus.manual_excluded.value,
        },
        ApplicationStatus.pending_documents.value: {
            ApplicationStatus.under_review.value,
            ApplicationStatus.returned.value,
            ApplicationStatus.approved.value,
            ApplicationStatus.partial_approved.value,
            ApplicationStatus.rejected.value,
            ApplicationStatus.cancelled.value,
        },
        # Forward movement out of `returned` happens via the student's own
        # resubmit; staff may only cancel.
        ApplicationStatus.returned.value: {ApplicationStatus.cancelled.value},
        # Reversing a final decision is an override-only operation.
        ApplicationStatus.approved.value: {ApplicationStatus.cancelled.value},
        ApplicationStatus.partial_approved.value: {ApplicationStatus.cancelled.value},
        ApplicationStatus.rejected.value: set(),
        ApplicationStatus.withdrawn.value: set(),
        ApplicationStatus.cancelled.value: set(),
        ApplicationStatus.manual_excluded.value: {ApplicationStatus.under_review.value},
        ApplicationStatus.cancelled_by_challenge.value: set(),
        ApplicationStatus.draft.value: set(),
        ApplicationStatus.deleted.value: set(),
    }

    async def update_application_status(
        self, application_id: int, user: User, status_update: ApplicationStatusUpdate
    ) -> ApplicationResponse:
        """Update application status (staff only).

        G16 (#978): transitions are validated against
        ``_STAFF_STATUS_TRANSITIONS``. An illegal transition is allowed only
        as an explicit admin/super_admin override carrying a written reason —
        previously ANY staff account could set ANY status (approved→draft,
        submitted→approved, …), making the review flow bypassable without a
        trace.
        """
        if not (
            user.has_role(UserRole.admin)
            or user.has_role(UserRole.college)
            or user.has_role(UserRole.professor)
            or user.has_role(UserRole.super_admin)
        ):
            raise AuthorizationError("Staff access required")

        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", str(application_id))

        # ── G16 transition gate ──────────────────────────────────────────
        old_status = application.status.value if hasattr(application.status, "value") else str(application.status)
        new_status = status_update.status
        if new_status != old_status:
            allowed = self._STAFF_STATUS_TRANSITIONS.get(old_status, set())
            if new_status not in allowed:
                is_admin = user.has_role(UserRole.admin) or user.has_role(UserRole.super_admin)
                override_reason = getattr(status_update, "comments", None) or getattr(
                    status_update, "rejection_reason", None
                )
                if new_status in (ApplicationStatus.draft.value, ApplicationStatus.deleted.value):
                    raise ValidationError(
                        f"狀態 '{new_status}' 不可經由狀態更新設定（draft 屬學生流程、deleted 屬刪除流程）"
                    )
                if not (is_admin and override_reason):
                    raise ValidationError(
                        f"不允許的狀態轉移：{old_status} → {new_status}。"
                        f"僅 admin 可強制覆寫，且必須附上理由（comments）。"
                    )
                logger.warning(
                    "Admin override status transition %s -> %s on application %s by user %s: %s",
                    old_status,
                    new_status,
                    application.app_id,
                    user.id,
                    override_reason,
                )

        # Update status
        application.status = status_update.status
        application.reviewer_id = user.id

        from app.utils.i18n import ScholarshipI18n

        if status_update.status == ApplicationStatus.approved.value:
            application.approved_at = datetime.now(timezone.utc)
            application.status_name = ScholarshipI18n.get_application_status_text(ApplicationStatus.approved.value)
        elif status_update.status == ApplicationStatus.rejected.value:
            # G16: a rejected application must not keep its approved_at —
            # otherwise「某期間核准清單」queries include later-rejected rows.
            application.approved_at = None
            application.status_name = ScholarshipI18n.get_application_status_text(ApplicationStatus.rejected.value)
        elif status_update.status in (ApplicationStatus.returned.value, ApplicationStatus.cancelled.value):
            application.approved_at = None

        # Persist the decision as an ApplicationReview row. G32 (#994): also
        # when NO comments were given — silent approvals/rejections previously
        # left no review row at all, so the deciding actor was untraceable
        # from the review data (only reviewer_id, overwritten by the next
        # status touch).
        if status_update.status in (
            ApplicationStatus.approved.value,
            ApplicationStatus.rejected.value,
        ) or (getattr(status_update, "comments", None) or getattr(status_update, "rejection_reason", None)):
            combined_comments = getattr(status_update, "comments", None) or getattr(
                status_update, "rejection_reason", None
            )
            recommendation = "approve" if status_update.status == ApplicationStatus.approved.value else "reject"
            # Upsert: admin may set status multiple times on the same application
            existing_stmt = select(ApplicationReview).where(
                ApplicationReview.application_id == application.id,
                ApplicationReview.reviewer_id == user.id,
            )
            existing_result = await self.db.execute(existing_stmt)
            existing_admin_review = existing_result.scalar_one_or_none()
            if existing_admin_review:
                existing_admin_review.recommendation = recommendation
                existing_admin_review.comments = combined_comments
                existing_admin_review.reviewed_at = datetime.now(timezone.utc)
            else:
                review = ApplicationReview(
                    application_id=application.id,
                    reviewer_id=user.id,
                    recommendation=recommendation,
                    comments=combined_comments,
                    reviewed_at=datetime.now(timezone.utc),
                )
                self.db.add(review)

        application.reviewed_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self._invalidate_app_caches()

        # Return fresh copy with all relationships loaded
        return await self.get_application_by_id(application_id, user)

    async def upload_application_file(self, application_id: int, user: User, file, file_type: str) -> Dict[str, Any]:
        """Upload file for application"""
        # Get application
        stmt = select(Application).where(and_(Application.id == application_id, Application.user_id == user.id))
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", str(application_id))

        if not application.is_editable:
            raise BusinessLogicError("Cannot upload files to application in current status")

        # For now, return a placeholder response
        # In a real implementation, this would handle file storage
        return {
            "message": "File upload functionality not yet implemented",
            "application_id": application_id,
            "file_type": file_type,
            "filename": getattr(file, "filename", "unknown"),
        }

    async def create_professor_review(self, application_id: int, user: User, review_data) -> ApplicationResponse:
        """Create a professor review record and notify college reviewers"""
        from app.models.enums import ReviewStage

        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        if not application:
            raise NotFoundError("Application", str(application_id))
        # Only the assigned professor can submit
        if application.professor_id != user.id:
            raise AuthorizationError("You are not the assigned professor for this application")

        # Calculate overall recommendation from items
        # all approve → 'approve', all reject → 'reject', mixed → 'partial_approve'
        item_recommendations = [item.recommendation for item in review_data.items]
        if all(r == "approve" for r in item_recommendations):
            overall_recommendation = "approve"
        elif all(r == "reject" for r in item_recommendations):
            overall_recommendation = "reject"
        else:
            overall_recommendation = "partial_approve"

        # Build combined comments from items
        combined_comments = (
            "\n".join(f"[{item.sub_type_code}] {item.comments}" for item in review_data.items if item.comments) or None
        )

        reviewed_at = datetime.now(timezone.utc)

        # Upsert: update existing review if professor already submitted one
        stmt_existing = select(ApplicationReview).where(
            ApplicationReview.application_id == application_id,
            ApplicationReview.reviewer_id == user.id,
        )
        result_existing = await self.db.execute(stmt_existing)
        review = result_existing.scalar_one_or_none()

        if review:
            review.recommendation = overall_recommendation
            review.comments = combined_comments
            review.reviewed_at = reviewed_at
            # Delete existing items and re-create
            from sqlalchemy import delete as sa_delete

            await self.db.execute(sa_delete(ApplicationReviewItem).where(ApplicationReviewItem.review_id == review.id))
            await self.db.flush()
        else:
            review = ApplicationReview(
                application_id=application_id,
                reviewer_id=user.id,
                recommendation=overall_recommendation,
                comments=combined_comments,
                reviewed_at=reviewed_at,
            )
            self.db.add(review)
            await self.db.flush()  # Get the review ID

        # Create per-sub-type review items
        for item_data in review_data.items:
            review_item = ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=item_data.sub_type_code,
                recommendation=item_data.recommendation,
                comments=item_data.comments,
            )
            self.db.add(review_item)

        # Advance review_stage to professor_reviewed
        application.review_stage = ReviewStage.professor_reviewed.value
        application.updated_at = datetime.now(timezone.utc)

        await self.db.commit()

        # Business metric: count professor review actions for the
        # Scholarship System Overview dashboard. Action is derived from
        # the overall recommendation so dashboards can split approve vs
        # reject (issue #159).
        scholarship_reviews_total.labels(
            reviewer_type="professor",
            action=str(overall_recommendation) if overall_recommendation else "unknown",
        ).inc()

        # 觸發教授審查提交事件（會觸發自動化郵件規則）
        try:
            stmt_student = select(User).where(User.id == application.user_id)
            result_student = await self.db.execute(stmt_student)
            student = result_student.scalar_one_or_none()

            stmt_scholarship = select(ScholarshipType).where(ScholarshipType.id == application.scholarship_type_id)
            result_scholarship = await self.db.execute(stmt_scholarship)
            scholarship = result_scholarship.scalar_one_or_none()

            await email_automation_service.trigger_professor_review_submitted(
                db=self.db,
                application_id=application.id,
                review_data={
                    "app_id": application.app_id,
                    "student_name": student.name if student else "Unknown",
                    "professor_name": user.name,
                    "professor_email": user.email,
                    "scholarship_type": scholarship.name if scholarship else "Unknown",
                    "scholarship_type_id": application.scholarship_type_id,
                    "review_result": overall_recommendation,
                    "review_date": reviewed_at.strftime("%Y-%m-%d"),
                    "professor_recommendation": overall_recommendation,
                    "college_name": "",
                    "review_deadline": "",
                },
            )
        except Exception:
            logger.exception("Failed to trigger professor review automation")

        # Return fresh copy with all relationships loaded
        return await self.get_application_by_id(application_id, user)

    async def _get_document_max_file_count(self, application: Application, file_type: str) -> Optional[int]:
        """Configured file-count limit of the document slot an upload targets.

        Dynamic documents use the admin-configured 文件名稱 as their file_type,
        so the slot is the ApplicationDocument row matching the application's
        scholarship code + that name. Returns None when no configuration
        exists (fixed types like bank_account_proof, or legacy data)."""
        from app.models.application_field import ApplicationDocument

        stmt = (
            select(ApplicationDocument.max_file_count)
            .join(ScholarshipType, ScholarshipType.code == ApplicationDocument.scholarship_type)
            .where(
                ScholarshipType.id == application.scholarship_type_id,
                ApplicationDocument.document_name == file_type,
                ApplicationDocument.is_active.is_(True),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

    async def upload_application_file_minio(
        self, application_id: int, user: User, file, file_type: str
    ) -> Dict[str, Any]:
        """Upload application file using MinIO"""
        # Verify application exists and user has access. FOR UPDATE serializes
        # concurrent uploads to the same application (double-click, second tab,
        # the admin dialog's parallel uploads): the replace-stale-rows logic
        # below is SELECT→DELETE→INSERT and two interleaved requests would
        # otherwise both miss each other's rows and re-create duplicates.
        stmt = select(Application).where(Application.id == application_id).with_for_update()
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", str(application_id))

        # Check upload permissions based on role
        if user.role == UserRole.student:
            # Students can only upload to their own applications
            if application.user_id != user.id:
                raise AuthorizationError("Cannot upload files to other students' applications")
        elif user.role == UserRole.professor:
            # Professors can upload files to their students' applications
            if not user.can_access_student_data(application.user_id, "upload_documents"):
                raise AuthorizationError("Cannot upload files - no access to this student's data")
        elif user.role in [UserRole.college, UserRole.admin, UserRole.super_admin]:
            # College, Admin, and Super Admin can upload to any application
            pass
        else:
            # Other roles are not allowed to upload
            raise AuthorizationError("Upload access denied")

        # Upload file to MinIO
        object_name, file_size = await minio_service.upload_file(file, application_id, file_type)

        # Import ApplicationFile here to avoid circular imports
        from app.models.application import ApplicationFile

        # When the APPLICANT re-uploads a document it must REPLACE the previous
        # records, not append: repeated draft saves used to send the same file
        # once per save, and the stale rows surfaced in the college export as
        # 「成績 1..N」copies of one file. A single-file slot (max_file_count
        # <= 1, the admin default) replaces every row of its type — swapping to
        # a differently-named file must not leave the old one behind, since no
        # per-file delete endpoint exists. Multi-file slots can only match on
        # the original filename. Staff (professor/college/admin) uploads keep
        # append semantics: they attach supplements and must never silently
        # destroy the student's possibly-verified documents.
        stale_object_names = []
        is_applicant_upload = user.role == UserRole.student and application.user_id == user.id
        if is_applicant_upload:
            max_file_count = await self._get_document_max_file_count(application, file_type)
            stale_stmt = select(ApplicationFile).where(
                ApplicationFile.application_id == application_id,
                ApplicationFile.file_type == file_type,
            )
            if max_file_count is None or max_file_count > 1:
                stale_stmt = stale_stmt.where(ApplicationFile.original_filename == file.filename)
            stale_result = await self.db.execute(stale_stmt)
            for stale_file in stale_result.scalars().all():
                if stale_file.object_name and stale_file.object_name != object_name:
                    # Deleted from MinIO only AFTER the commit below succeeds — a
                    # failed commit must not leave surviving DB rows pointing at
                    # already-deleted objects.
                    stale_object_names.append(stale_file.object_name)
                await self.db.delete(stale_file)

        # Save file metadata to database
        file_record = ApplicationFile(
            application_id=application_id,
            filename=file.filename,  # Keep original filename for display
            original_filename=file.filename,  # Store original filename
            file_type=file_type,
            file_size=file_size,
            object_name=object_name,  # This is now UUID-based path
            uploaded_at=datetime.now(timezone.utc),
            content_type=file.content_type or "application/octet-stream",
            mime_type=file.content_type or "application/octet-stream",
        )

        self.db.add(file_record)
        await self.db.commit()
        await self.db.refresh(file_record)

        # Replaced rows are durably gone; now drop their objects. to_thread
        # because the MinIO client is synchronous network I/O; delete_file
        # logs and returns False on failure (an orphaned object is harmless).
        for stale_object_name in stale_object_names:
            await asyncio.to_thread(minio_service.delete_file, stale_object_name)

        return {
            "success": True,
            "message": "File uploaded successfully",
            "data": {
                "file_id": file_record.id,
                "filename": file_record.filename,
                "file_type": file_record.file_type,
                "file_size": file_record.file_size,
                "uploaded_at": file_record.uploaded_at.isoformat(),
            },
        }

    async def search_applications(self, search_criteria: Dict[str, Any]) -> List[Application]:
        """搜尋申請"""
        query = select(Application)

        # 動態添加搜尋條件
        for field, value in search_criteria.items():
            if field.startswith("student."):
                # 搜尋學生資料
                json_path = field.replace("student.", "")
                query = query.filter(Application.student_data[json_path].astext == str(value))
            elif field.startswith("form."):
                # 搜尋表單資料
                json_path = field.replace("form.", "")
                query = query.filter(Application.submitted_form_data[json_path].astext == str(value))
            else:
                # 一般欄位搜尋
                query = query.filter(getattr(Application, field) == value)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_applications(
        self,
        current_user: User,
        skip: int = 0,
        limit: int = 100,
        status: Optional[str] = None,
        scholarship_type: Optional[str] = None,
    ) -> List[ApplicationListResponse]:
        """Get applications with proper access control"""
        # Build query based on user role
        query = select(Application).options(
            selectinload(Application.files),
            selectinload(Application.scholarship),
            selectinload(Application.student),  # Eagerly load student to avoid N+1 queries
        )

        if current_user.role == UserRole.student:
            # Students can only see their own applications
            query = query.where(Application.user_id == current_user.id)
        elif current_user.role == UserRole.professor:
            # Filter applications to only those from accessible students
            accessible_student_ids = await self._get_accessible_student_ids(current_user)
            if accessible_student_ids:
                query = query.where(Application.user_id.in_(accessible_student_ids))
            else:
                # No accessible students, return empty result
                return []
        elif current_user.role in [
            UserRole.college,
            UserRole.admin,
            UserRole.super_admin,
        ]:
            # College, Admin, and Super Admin can see all applications
            pass
        else:
            # Other roles cannot see any applications
            return []

        # Apply filters
        if status:
            query = query.where(Application.status == status)
        if scholarship_type:
            query = query.where(Application.scholarship_type == scholarship_type)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        # Execute query
        result = await self.db.execute(query)
        applications = result.scalars().all()

        # Convert to response models
        response_applications = []
        for application in applications:
            # 整合 application.files 進 submitted_form_data.documents（create-or-update，共用 helper）。
            # 與 get_application_by_id 一致：把尚未出現在 documents[] 的已上傳檔案補進去。
            integrated_form_data = self._integrate_application_file_data(application, current_user)

            # Use eagerly loaded student (already loaded with selectinload)
            app_user = application.student

            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=app_user.nycu_id if app_user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_type_zh=application.scholarship.name if application.scholarship else None,
                scholarship_subtype_list=application.scholarship_subtype_list or [],
                sub_scholarship_type=application.sub_scholarship_type,
                status=application.status,
                status_name=application.status_name,
                is_renewal=application.is_renewal,
                renewal_year=application.renewal_year,
                previous_application_id=application.previous_application_id,
                challenges_application_id=application.challenges_application_id,
                cancelled_due_to_application_id=application.cancelled_due_to_application_id,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data or {},
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms or False,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data,
            )

            response_applications.append(app_data)

        return response_applications

    async def delete_application(
        self, application_id: int, current_user: User, reason: Optional[str] = None
    ) -> Application:
        """
        Delete an application (hard delete for drafts, soft delete for submitted applications)

        Permission Control:
        - Students: Can only delete their own draft applications
        - Staff (professor/college/admin): Can delete any application (reason required)

        Deletion Behavior:
        - Draft applications: Permanently deleted from database (hard delete)
        - Submitted applications: Status set to 'deleted' (soft delete)

        Args:
            application_id: ID of application to delete
            current_user: User performing the deletion
            reason: Reason for deletion (required for staff)

        Returns:
            Deleted application object
        """
        # Get application with files relationship loaded
        stmt = select(Application).options(selectinload(Application.files)).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", application_id)

        # Check if already deleted
        if application.status == ApplicationStatus.deleted:
            raise ValidationError("Application is already deleted")

        # Check if user has permission to delete this application
        if current_user.role == UserRole.student:
            if application.user_id != current_user.id:
                raise AuthorizationError("You can only delete your own applications")
            # Students can only delete draft applications
            if application.status != ApplicationStatus.draft:
                raise ValidationError("Only draft applications can be deleted by students")
        elif current_user.role in [UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin]:
            # Staff can delete any application but must provide a reason
            if not reason:
                raise ValidationError("Deletion reason is required for staff users")
        else:
            raise AuthorizationError("You don't have permission to delete applications")

        # Determine deletion type based on application status
        is_draft = application.status == ApplicationStatus.draft

        if is_draft:
            # Hard delete for draft applications
            logger.info(f"Performing hard delete for draft application {application.app_id}")

            # Delete associated files from MinIO. delete_file() never raises —
            # it swallows errors internally and returns False (issue #982 /
            # G20: the old try/except was dead code and the bool was ignored,
            # so failures orphaned objects with no trace).
            deleted_files_count = 0
            orphaned_objects = []
            if application.files:
                for app_file in application.files:
                    if app_file.object_name:
                        if minio_service.delete_file(app_file.object_name):
                            deleted_files_count += 1
                            logger.info(f"Deleted file from MinIO: {app_file.object_name}")
                        else:
                            orphaned_objects.append(app_file.object_name)
                            logger.error(
                                "MinIO deletion failed for %s (application %s) — object orphaned",
                                app_file.object_name,
                                application.app_id,
                            )

            if orphaned_objects:
                # Leave a queryable trace so the orphans can be swept later —
                # DB deletion proceeds regardless (storage cleanup must not
                # block the user-facing operation).
                self.db.add(
                    AuditLog.create_log(
                        user_id=current_user.id,
                        action=AuditAction.delete.value,
                        resource_type="application",
                        resource_id=str(application.id),
                        description=(
                            f"MinIO cleanup incomplete for {application.app_id}: "
                            f"{len(orphaned_objects)} orphaned object(s)"
                        ),
                        status="failed",
                        meta_data={"app_id": application.app_id, "orphaned_objects": orphaned_objects},
                    )
                )

            logger.info(f"Deleted {deleted_files_count} files from MinIO for application {application.app_id}")

            # Delete from database (cascade will delete related ApplicationFile records)
            await self.db.delete(application)
            await self.db.commit()
            await self._invalidate_app_caches()

            logger.info(f"Hard deleted draft application {application.app_id} from database")
            return application

        else:
            # Soft delete for submitted applications
            logger.info(f"Performing soft delete for submitted application {application.app_id}")

            application.status = ApplicationStatus.deleted
            application.deleted_at = datetime.now(timezone.utc)
            application.deleted_by_id = current_user.id
            application.deletion_reason = reason or "Application deleted"

            await self.db.commit()
            await self.db.refresh(application)
            await self._invalidate_app_caches()

            logger.info(f"Soft deleted application {application.app_id}")
            return application

    async def restore_application(self, application_id: int, current_user: User) -> Application:
        """
        Restore a deleted application to draft status

        Permission Control:
        - Students: Can only restore their own deleted applications
        - Staff (professor/college/admin): Can restore any application

        Args:
            application_id: ID of application to restore
            current_user: User performing the restoration

        Returns:
            Restored application object
        """
        # Get application with eagerly loaded relationships
        stmt = (
            select(Application)
            .options(
                selectinload(Application.reviews),
            )
            .where(Application.id == application_id)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", application_id)

        # Check if already deleted
        if application.status != ApplicationStatus.deleted:
            raise ValidationError("Only deleted applications can be restored")

        # Check if user has permission to restore this application
        if current_user.role == UserRole.student:
            if application.user_id != current_user.id:
                raise AuthorizationError("You can only restore your own applications")
        elif current_user.role not in [UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin]:
            raise AuthorizationError("You don't have permission to restore applications")

        # Restore application to appropriate status based on submission history
        # If the application was previously submitted, restore it to under_review status
        # so it will appear in the college review list
        if application.submitted_at:
            # Application was previously submitted - restore to under_review
            application.status = ApplicationStatus.under_review
        else:
            # Application was never submitted - restore to draft
            application.status = ApplicationStatus.draft

        # Clear deletion metadata
        application.deleted_at = None
        application.deleted_by_id = None
        application.deletion_reason = None

        await self.db.commit()
        await self.db.refresh(application)
        await self._invalidate_app_caches()

        return application

    async def withdraw_application(self, application_id: int, current_user: User) -> Application:
        """Withdraw a submitted application back to draft status"""
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", application_id)

        if current_user.role == UserRole.student and application.user_id != current_user.id:
            raise AuthorizationError("You can only withdraw your own applications")

        if application.status not in [ApplicationStatus.submitted, ApplicationStatus.under_review]:
            raise ValidationError("Only submitted or under-review applications can be withdrawn")

        from app.models.enums import ReviewStage

        application.status = ApplicationStatus.draft
        # review_stage is NOT NULL on the column (20251028_add_review_stage_to_applications
        # set nullable=False); set it back to the canonical draft stage to mirror the
        # status transition rather than leaving the column null and tripping a 500.
        application.review_stage = ReviewStage.student_draft.value
        application.professor_id = None
        application.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(application)
        await self._invalidate_app_caches()

        return application

    async def _clone_user_profile_documents(self, application: Application, user: User):
        """
        Clone all fixed documents from user profile to application-specific paths
        在申請提交或儲存草稿時，將個人資料中的固定文件複製到申請專屬路徑
        支援：銀行文件、其他固定文件
        """
        from sqlalchemy import select

        from app.models.application import ApplicationFile
        from app.services.user_profile_service import UserProfileService

        user_profile_service = UserProfileService(self.db)
        cloned_documents = []

        try:
            # 獲取用戶的個人資料
            user_profile = await user_profile_service.get_user_profile(user.id)

            if not user_profile:
                logger.debug(f"No user profile found for user {user.id}")
                return

            # 定義要複製的固定文件類型
            fixed_documents = [
                {
                    "file_type": "bank_account_proof",
                    "profile_field": "bank_document_photo_url",
                    "object_name_field": "bank_document_object_name",
                    "document_name": "存摺封面",
                }
                # 未來可以新增更多固定文件類型，例如：
                # {
                #     'file_type': 'id_card',
                #     'profile_field': 'id_card_photo_url',
                #     'object_name_field': 'id_card_object_name',
                #     'document_name': '身份證件'
                # }
            ]

            for doc_config in fixed_documents:
                # 獲取文件 URL
                doc_url = getattr(user_profile, doc_config["profile_field"], None)
                if not doc_url:
                    logger.debug(f"No {doc_config['file_type']} found for user {user.id}")
                    continue

                # Check if the document is already cloned to avoid duplication
                existing_file_stmt = select(ApplicationFile).where(
                    ApplicationFile.application_id == application.id,
                    ApplicationFile.file_type == doc_config["file_type"],
                )
                existing_file_result = await self.db.execute(existing_file_stmt)
                existing_file = existing_file_result.scalar_one_or_none()

                if existing_file:
                    logger.debug(
                        f"{doc_config['document_name']} already cloned for application {application.app_id}, skipping"
                    )
                    continue

                logger.info(f"Cloning {doc_config['document_name']} for application {application.app_id}")

                # 使用儲存的 object_name，如果沒有則從 URL 提取
                if hasattr(user_profile, doc_config["object_name_field"]):
                    source_object_name = getattr(user_profile, doc_config["object_name_field"], None)
                    if source_object_name:
                        filename = source_object_name.split("/")[-1]
                    else:
                        # 從 URL 提取
                        filename = doc_url.split("/")[-1].split("?")[0]
                        source_object_name = f"user-profiles/{user.id}/bank-documents/{filename}"
                else:
                    # 從 URL 提取（舊的邏輯作為備用）
                    filename = doc_url.split("/")[-1].split("?")[0]
                    source_object_name = f"user-profiles/{user.id}/bank-documents/{filename}"

                # 使用 MinIO 服務複製文件到申請路徑
                new_object_name = minio_service.clone_file_to_application(
                    source_object_name=source_object_name,
                    application_id=application.app_id,
                )

                logger.debug(f"File cloned from {source_object_name} to {new_object_name}")

                # 創建 ApplicationFile 記錄 - 與動態上傳文件相同處理
                application_file = ApplicationFile(
                    application_id=application.id,
                    file_type=doc_config["file_type"],
                    filename=filename,
                    original_filename=filename,
                    file_size=0,  # 大小會在實際使用時獲取
                    content_type="application/octet-stream",  # 會在實際使用時更新
                    object_name=new_object_name,
                    is_verified=True,  # 固定文件預設已驗證
                    uploaded_at=datetime.now(timezone.utc),
                )

                self.db.add(application_file)
                await self.db.flush()  # 確保獲得 application_file.id

                cloned_documents.append(
                    {
                        "file_type": doc_config["file_type"],
                        "document_name": doc_config["document_name"],
                        "file_id": application_file.id,
                        "object_name": new_object_name,
                    }
                )

            # 批量更新申請的 form_data
            if cloned_documents:
                form_data = application.submitted_form_data or {}

                # 生成文件訪問 URL
                from app.core.config import settings
                from app.core.security import create_access_token

                token_data = {"sub": str(user.id)}
                access_token = create_access_token(token_data)
                base_url = f"{settings.base_url}{settings.api_v1_str}"

                # 確保 documents 欄位存在
                if "documents" not in form_data:
                    form_data["documents"] = []

                # 更新或新增複製的文件資訊
                for cloned_doc in cloned_documents:
                    doc_info = {
                        "document_id": cloned_doc["file_type"],
                        "document_type": cloned_doc["file_type"],
                        "document_name": cloned_doc["document_name"],
                        "file_id": cloned_doc["file_id"],
                        "filename": cloned_doc["object_name"].split("/")[-1],
                        "original_filename": cloned_doc["object_name"].split("/")[-1],
                        "file_path": f"{base_url}/files/applications/{application.id}/files/{cloned_doc['file_id']}?token={access_token}",
                        "download_url": f"{base_url}/files/applications/{application.id}/files/{cloned_doc['file_id']}/download?token={access_token}",
                        "object_name": cloned_doc["object_name"],
                        "is_verified": True,
                        "upload_time": datetime.now(timezone.utc).isoformat(),
                    }

                    # 檢查是否已存在，如果存在則更新，否則新增
                    doc_found = False
                    for i, doc in enumerate(form_data["documents"]):
                        if doc.get("document_type") == cloned_doc["file_type"]:
                            form_data["documents"][i] = doc_info
                            doc_found = True
                            break

                    if not doc_found:
                        form_data["documents"].append(doc_info)

                # 更新申請的 form_data
                application.submitted_form_data = form_data

                # 提交資料庫變更
                await self.db.commit()
                await self.db.refresh(application)

                logger.info(
                    f"{len(cloned_documents)} documents successfully cloned and linked to application {application.app_id}"
                )

        except Exception:
            logger.exception(f"Failed to clone user profile documents for application {application.app_id}")
            # 不拋出異常，避免影響申請提交流程
            import traceback

            traceback.print_exc()

    def _get_document_display_name(self, file_type: str) -> str:
        """
        獲取文件類型的顯示名稱

        Args:
            file_type: 文件類型代碼

        Returns:
            文件顯示名稱
        """
        document_type_names = {
            "bank_account_proof": "存摺封面",
            "transcript": "成績單",
            "certificate": "證書",
            "recommendation_letter": "推薦信",
            "personal_statement": "個人陳述",
            "financial_statement": "財力證明",
            "other": "其他文件",
        }

        return document_type_names.get(file_type, file_type)

    # Professor Review Methods
    @staticmethod
    def _professor_reviewed(professor_id: int):
        """Correlated predicate: this professor authored an ApplicationReview for the row.

        Shared by the professor queue (:meth:`get_professor_applications_paginated`)
        and the dashboard badge (:meth:`get_professor_review_stats`) so the
        "has this professor reviewed?" split cannot drift between the two.
        """
        return Application.reviews.any(ApplicationReview.reviewer_id == professor_id)

    async def get_professor_applications_paginated(
        self,
        professor_id: int,
        status_filter: Optional[str] = None,
        page: int = 1,
        size: Optional[int] = None,
    ) -> tuple[List[ApplicationListResponse], int]:
        """Get applications assigned to professor with total count.

        ``size=None`` (default) returns ALL matching applications;
        pass ``page``/``size`` for explicit pagination.
        """
        try:
            # Build base query with ALL required filters (consistent with what will be returned)
            base_query = (
                select(Application)
                .options(
                    selectinload(Application.scholarship_configuration).selectinload(
                        ScholarshipConfiguration.scholarship_type
                    ),
                    selectinload(Application.student),
                    selectinload(Application.reviews),
                )
                .join(Application.scholarship_configuration)
                .where(
                    # Only applications that require professor review — general
                    # applications follow requires_professor_recommendation,
                    # renewals follow the renewal-specific admin flag. The
                    # configuration is already joined above, so filter its
                    # columns directly instead of EXISTS subqueries.
                    or_(
                        and_(
                            Application.is_renewal.is_(False),
                            ScholarshipConfiguration.requires_professor_recommendation.is_(True),
                        ),
                        and_(
                            Application.is_renewal.is_(True),
                            ScholarshipConfiguration.renewal_requires_professor_review.is_(True),
                        ),
                    ),
                    # Only applications assigned to this specific professor
                    Application.professor_id == professor_id,
                    # Only applications in valid statuses for professor viewing
                    Application.status.in_(REVIEWABLE_APPLICATION_STATUSES),
                )
            )

            # Discriminate pending vs completed by whether THIS professor has
            # already recorded a review, NOT by Application.status.
            #
            # Status is unreliable here: a professor "approve" on a scholarship
            # that requires college review deliberately keeps status at
            # under_review (issue #182), so a status-based "pending" filter kept
            # showing applications the professor had already reviewed. The only
            # sound signal that the professor is done is the existence of an
            # ApplicationReview row authored by them.
            reviewed_by_me = self._professor_reviewed(professor_id)

            if status_filter == "pending":
                # 待審核 — assigned to me but I have not reviewed yet.
                base_query = base_query.where(~reviewed_by_me)
            elif status_filter == "completed":
                # 已完成 — assigned to me and I have already reviewed.
                base_query = base_query.where(reviewed_by_me)
            # "all" or None → 全部 = 待審核 + 已完成 (no review-existence filter)

            # Get total count with same filters
            count_query = select(func.count()).select_from(base_query.subquery())
            count_result = await self.db.execute(count_query)
            total_count = count_result.scalar()

            # Apply ordering, then pagination only when explicitly requested
            paginated_query = base_query.order_by(desc(Application.created_at))
            if size is not None:
                paginated_query = paginated_query.offset((page - 1) * size).limit(size)

            result = await self.db.execute(paginated_query)
            applications = result.unique().scalars().all()

            # Convert to response format - no additional filtering needed since SQL query is already correct
            responses = []
            for app in applications:
                # Get scholarship type information for display
                scholarship_type_zh = None
                if app.scholarship_configuration and app.scholarship_configuration.scholarship_type:
                    # Use name for Chinese display since name_zh doesn't exist
                    scholarship_type_zh = app.scholarship_configuration.scholarship_type.name

                # Create response with all required fields
                responses.append(
                    ApplicationListResponse(
                        id=app.id,
                        app_id=app.app_id,
                        user_id=app.user_id,
                        student_id=app.student_data.get("std_stdcode", "") if app.student_data else "",
                        scholarship_type_id=app.scholarship_type_id,
                        scholarship_type_zh=scholarship_type_zh or "未設定",
                        scholarship_name=app.scholarship_name or "",
                        amount=app.amount or 0,
                        currency=app.scholarship_configuration.currency if app.scholarship_configuration else "TWD",
                        scholarship_subtype_list=app.scholarship_subtype_list or [],
                        status=app.status,
                        status_name=app.status,  # Using status as status_name for now
                        is_renewal=app.is_renewal or False,
                        academic_year=app.academic_year or 0,
                        semester=app.semester.value if app.semester else None,
                        student_data=app.student_data or {},
                        submitted_form_data=app.submitted_form_data or {},
                        agree_terms=app.agree_terms or False,
                        professor_id=app.professor_id,
                        reviewer_id=app.reviewer_id,
                        final_approver_id=app.final_approver_id,
                        # Note: review_score, review_comments, rejection_reason removed
                        submitted_at=app.submitted_at,
                        reviewed_at=app.reviewed_at,
                        approved_at=app.approved_at,
                        created_at=app.created_at,
                        updated_at=app.updated_at,
                        meta_data=app.meta_data,
                        review_stage=serialize_value(app.review_stage),
                        # Display fields
                        student_name=app.student_data.get("std_cname", "") if app.student_data else "",
                        student_no=app.student_data.get("std_stdcode", "") if app.student_data else "",
                        days_waiting=None,  # Calculate if needed
                        professor=None,  # Professor info not needed in professor view
                        scholarship_configuration=(
                            {
                                "requires_professor_recommendation": (
                                    app.scholarship_configuration.requires_professor_review_for(bool(app.is_renewal))
                                    if app.scholarship_configuration
                                    else False
                                ),
                                "requires_college_review": (
                                    app.scholarship_configuration.requires_college_review_for(bool(app.is_renewal))
                                    if app.scholarship_configuration
                                    else False
                                ),
                                "config_name": (
                                    app.scholarship_configuration.config_name if app.scholarship_configuration else None
                                ),
                            }
                            if app.scholarship_configuration
                            else None
                        ),
                        # Professor-centric review status: has THIS professor
                        # recorded a review? Mirrors the pending/completed split.
                        has_professor_reviewed=any(review.reviewer_id == professor_id for review in app.reviews),
                    )
                )

            return responses, total_count

        except Exception:
            logger.exception("Error fetching paginated professor applications")
            raise

    async def can_professor_review_application(self, application_id: int, professor_id: int) -> bool:
        """Check if professor can view this application (no time restrictions for viewing)"""
        try:
            # Get the application
            stmt = (
                select(Application)
                .options(selectinload(Application.scholarship_configuration))
                .where(Application.id == application_id)
            )
            result = await self.db.execute(stmt)
            application = result.scalar_one_or_none()

            if not application or not application.scholarship_configuration:
                return False

            # Check if this application kind requires professor review
            # (renewals carry their own admin-configured flag)
            if not application.scholarship_configuration.requires_professor_review_for(bool(application.is_renewal)):
                return False

            # Check if application is assigned to this specific professor
            if application.professor_id != professor_id:
                return False

            # Check application status - should be submitted or under review (or historical).
            # application is loaded fresh from the DB, so status is the Enum MEMBER, not its
            # .value string — compare against members (matching the dominant convention in
            # this file). Comparing a member against .value strings always failed → the
            # method wrongly returned False for every status.
            if application.status not in [
                ApplicationStatus.submitted,
                ApplicationStatus.under_review,
                ApplicationStatus.approved,
                ApplicationStatus.partial_approved,
                ApplicationStatus.rejected,
            ]:
                return False

            return True

        except Exception:
            logger.exception("Error checking professor review authorization")
            return False

    async def can_professor_submit_review(self, application_id: int, professor_id: int) -> bool:
        """Check if professor can submit a review (with time restrictions)"""
        try:
            # Get the application with scholarship configuration
            stmt = (
                select(Application)
                .options(selectinload(Application.scholarship_configuration))
                .where(Application.id == application_id)
            )
            result = await self.db.execute(stmt)
            application = result.scalar_one_or_none()

            if not application or not application.scholarship_configuration:
                return False

            config = application.scholarship_configuration

            # Check if application is assigned to this specific professor
            if application.professor_id != professor_id:
                return False

            # Check application status - should be submitted or under review
            # Compare with both enum and string value for robustness
            valid_statuses = [
                ApplicationStatus.submitted,
                ApplicationStatus.submitted.value,
                ApplicationStatus.under_review,
                ApplicationStatus.under_review.value,
            ]
            if application.status not in valid_statuses:
                return False

            now = datetime.now(timezone.utc)

            # Check professor review period for SUBMISSION (this is where time restriction applies)
            # Skip time restrictions if review periods are not configured (e.g., in test environment)
            if application.is_renewal:
                # Renewal professor review must be enabled by the admin at all
                if not config.requires_professor_review_for(True):
                    logger.warning(
                        f"Professor review submission blocked: renewal professor review "
                        f"not required for config {config.id}"
                    )
                    return False

                # Check renewal review period
                renewal_start = config.renewal_professor_review_start
                renewal_end = config.renewal_professor_review_end

                if renewal_start and renewal_end:
                    if renewal_start.tzinfo is None:
                        renewal_start = renewal_start.replace(tzinfo=timezone.utc)
                    if renewal_end.tzinfo is None:
                        renewal_end = renewal_end.replace(tzinfo=timezone.utc)

                    if not (renewal_start <= now <= renewal_end):
                        logger.warning(
                            f"Professor review submission outside renewal period: {renewal_start} to {renewal_end}, now: {now}"
                        )
                        return False
                # If no renewal periods configured, allow review (useful for testing)
            else:
                # Check regular review period - from application start to professor review end
                # Professor can review from when student submits application until professor review deadline
                review_start = config.application_start_date  # Changed from professor_review_start
                review_end = config.professor_review_end

                if review_start and review_end:
                    if review_start.tzinfo is None:
                        review_start = review_start.replace(tzinfo=timezone.utc)
                    if review_end.tzinfo is None:
                        review_end = review_end.replace(tzinfo=timezone.utc)

                    if not (review_start <= now <= review_end):
                        logger.warning(
                            f"Professor review submission outside period: {review_start} to {review_end}, now: {now}"
                        )
                        return False
                # If no review periods configured, allow review (useful for testing)

            return True

        except Exception:
            logger.exception("Error checking professor review submission authorization")
            return False

    async def get_professor_review_stats(self, professor_id: int) -> dict:
        """Professor dashboard review stats from the unified ApplicationReview table.

        Previously queried the placeholder `ProfessorReview` class (a `pass`
        stub left over from an unfinished migration — issue #218), which
        would 500 in production on SQLAlchemy's unmapped-class check.
        The silent except handler masked it as `{0, 0, 0}` — itself a
        CLAUDE.md §1 violation.

        - completed_reviews: rows where reviewer_id = professor_id
        - pending_reviews: applications assigned to this professor in
          submitted/under_review where this reviewer has no review row yet
        - overdue_reviews: 0 (deadline tracking lives in deadline_checker;
          surfacing it here would require a join on
          ScholarshipConfiguration.professor_review_end_date)
        """
        pending_query = select(sa_func.count(Application.id)).where(
            Application.professor_id == professor_id,
            Application.status.in_(
                [
                    ApplicationStatus.submitted.value,
                    ApplicationStatus.under_review.value,
                ]
            ),
            ~self._professor_reviewed(professor_id),
        )

        completed_query = select(sa_func.count(ApplicationReview.id)).where(
            ApplicationReview.reviewer_id == professor_id
        )

        pending_count = (await self.db.execute(pending_query)).scalar() or 0
        completed_count = (await self.db.execute(completed_query)).scalar() or 0

        return {
            "pending_reviews": pending_count,
            "completed_reviews": completed_count,
            "overdue_reviews": 0,
        }

    async def get_application_available_sub_types(
        self, application_id: int, current_user: User
    ) -> List[Dict[str, Any]]:
        """Return sub-types the given user is authorized to review on this application.

        The shape matches the frontend's ``SubTypeOption`` interface
        (see ``frontend/components/professor-review-component.tsx:81``):
            ``{"value": str, "label": str, "label_en": str, "is_default": bool}``

        Filtering rules (additive — stricter as the role moves through the
        review chain):

        - All callers: only ``is_active=True`` sub-type configs that the
          applicant actually applied for (``Application.scholarship_subtype_list``).
          Reviewers must never see sub-types the student didn't request — and
          this keeps the form in sync with the submit-time permission check in
          ``ReviewService.get_reviewable_subtypes``.
        - ``professor``: returns every applied active sub-type.
        - ``college``: also excludes sub-types where any professor has
          recommended ``reject`` on the application.
        - ``admin`` / ``super_admin``: also excludes sub-types where any
          college reviewer has recommended ``reject``.

        The result is sorted by ``(display_order, sub_type_code)`` so the
        frontend list rendering is stable across calls.

        Raises ``NotFoundError`` when the application doesn't exist.
        """
        # Load application + its scholarship + that scholarship's sub-type configs
        # in one round trip so we can iterate ``application.scholarship.sub_type_configs``
        # without a lazy fetch on the AsyncSession.
        stmt = (
            select(Application)
            .where(Application.id == application_id)
            .options(selectinload(Application.scholarship).selectinload(ScholarshipType.sub_type_configs))
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        if application is None:
            raise NotFoundError(f"Application {application_id} not found")

        # Empty scholarship or no configured sub-types -> empty list.
        # The frontend already falls back to a synthetic "default" sub-type
        # in that case (FALLBACK_SUB_TYPE), so we don't need to return one.
        if not application.scholarship or not application.scholarship.sub_type_configs:
            return []

        # Only sub-types the applicant actually applied for. An empty applied
        # list (single-mode / "general" application) -> empty list, so the
        # frontend falls back to its single "default" recommendation form.
        # Normalized to match the lowercase/stripped convention used by
        # ReviewService.get_reviewable_subtypes (the submit-time gate).
        applied_codes = {
            code.lower().strip() for code in (application.scholarship_subtype_list or []) if isinstance(code, str)
        }
        active_configs = [
            c
            for c in application.scholarship.sub_type_configs
            if c.is_active and (c.sub_type_code or "").lower().strip() in applied_codes
        ]

        async def _rejected_by_role(role: UserRole) -> set[str]:
            """sub_type_codes rejected by any reviewer of the given role on this application."""
            stmt_rejected = (
                select(ApplicationReviewItem.sub_type_code)
                .join(ApplicationReview, ApplicationReviewItem.review_id == ApplicationReview.id)
                .join(User, ApplicationReview.reviewer_id == User.id)
                .where(
                    ApplicationReview.application_id == application_id,
                    User.role == role,
                    ApplicationReviewItem.recommendation == "reject",
                )
            )
            res = await self.db.execute(stmt_rejected)
            return set(res.scalars().all())

        # Professors see everything. College sees what professors didn't reject.
        # Admin sees what neither professors nor college rejected.
        excluded_codes: set[str] = set()
        if current_user.role != UserRole.professor:
            excluded_codes |= await _rejected_by_role(UserRole.professor)
        if current_user.role in (UserRole.admin, UserRole.super_admin):
            excluded_codes |= await _rejected_by_role(UserRole.college)

        available = [c for c in active_configs if c.sub_type_code not in excluded_codes]
        available.sort(key=lambda c: (c.display_order or 0, c.sub_type_code))

        return [
            {
                "value": c.sub_type_code,
                "label": c.name,
                "label_en": c.name_en or c.name,
                "is_default": c.sub_type_code == "default",
            }
            for c in available
        ]

    async def get_available_professors(self, user: User, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get professors based on user role:
        - College admin: only same dept_code
        - Admin/Super Admin: all professors
        """
        try:
            from app.models.user import UserRole

            query = select(User).where(User.role == UserRole.professor)

            # Filter by college for college admins
            if user.role == UserRole.college:
                query = query.where(User.dept_code == user.dept_code)

            # Add search filter
            if search:
                query = query.where(
                    or_(
                        User.name.ilike(f"%{search}%"),
                        User.nycu_id.ilike(f"%{search}%"),
                    )
                )

            # Order by name for consistent results
            query = query.order_by(User.name)

            result = await self.db.execute(query)
            professors = result.scalars().all()

            return [
                {
                    "nycu_id": prof.nycu_id,
                    "name": prof.name,
                    "dept_code": prof.dept_code,
                    "dept_name": prof.dept_name,
                    "email": prof.email,
                }
                for prof in professors
            ]

        except Exception:
            logger.exception("Error fetching available professors")
            raise

    async def assign_professor(self, application_id: int, professor_nycu_id: str, assigned_by: User) -> Application:
        """Assign professor to application with notification"""
        try:
            from app.core.exceptions import NotFoundError, ValidationError
            from app.models.notification import NotificationChannel, NotificationPriority, NotificationType
            from app.models.user import UserRole
            from app.services.email_service import EmailService
            from app.services.notification_service import NotificationService

            # Get application with all relationships loaded to avoid lazy loading
            stmt = (
                select(Application)
                .options(
                    selectinload(Application.scholarship_configuration),
                    selectinload(Application.reviews).selectinload(ApplicationReview.reviewer),
                    selectinload(Application.student),
                    selectinload(Application.professor),
                    selectinload(Application.reviewer),
                    selectinload(Application.final_approver),
                )
                .where(Application.id == application_id)
            )
            result = await self.db.execute(stmt)
            application = result.scalar_one_or_none()

            if not application:
                raise NotFoundError(f"Application {application_id} not found")

            # Check access permissions (similar to get_application_by_id logic)
            if assigned_by.role == UserRole.student:
                if application.user_id != assigned_by.id:
                    raise ValidationError("Access denied")

            # Get professor
            stmt = select(User).where(User.nycu_id == professor_nycu_id, User.role == UserRole.professor)
            result = await self.db.execute(stmt)
            professor = result.scalar_one_or_none()

            if not professor:
                raise NotFoundError(f"Professor with NYCU ID {professor_nycu_id} not found")

            # Check if this application kind requires professor review
            # (renewals carry their own admin-configured flag)
            config = application.scholarship_configuration
            if not config or not config.requires_professor_review_for(bool(application.is_renewal)):
                raise ValidationError("This scholarship does not require professor review")

            # Check permission for college admins
            if assigned_by.role == UserRole.college:
                if assigned_by.dept_code != professor.dept_code:
                    raise ValidationError("College admins can only assign professors from their own college")

            # Update application
            old_professor_id = application.professor_id
            application.professor_id = professor.id
            application.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(application)

            # Send email via React Email HTML system (scheduled_emails queue)
            if professor.email:
                try:
                    from app.core.config import settings
                    from app.services.frontend_email_renderer import render_email_via_frontend

                    student_name = application.student_data.get("std_cname") if application.student_data else "Unknown"
                    email_context = {
                        "app_id": application.app_id,
                        "student_name": student_name,
                        "scholarship_type": application.scholarship_name or "獎學金",
                        "professor_name": professor.name,
                        "professor_email": professor.email,
                        "submit_date": application.updated_at.strftime("%Y-%m-%d") if application.updated_at else "",
                        "system_url": getattr(settings, "FRONTEND_URL", "https://scholarship.nycu.edu.tw"),
                    }
                    html = await render_email_via_frontend(
                        frontend_url=getattr(settings, "INTERNAL_FRONTEND_URL", "http://frontend:3000"),
                        template_name="professor-review-request",
                        context=email_context,
                    )
                    email_service = EmailService()
                    await email_service.schedule_email(
                        db=self.db,
                        to=professor.email,
                        subject=f"審查通知 - {student_name} 的 {application.scholarship_name or '獎學金'} 申請",
                        body=f"申請編號 {application.app_id} 已指派給您進行教授推薦審查。",
                        scheduled_for=datetime.now(timezone.utc),
                        html_content=html,
                        template_key="professor_review_notification",
                        application_id=application.id,
                        scholarship_type_id=application.scholarship_type_id,
                        created_by_user_id=assigned_by.id,
                    )
                    logger.info(f"Scheduled HTML email to professor {professor.nycu_id}")
                except Exception:
                    logger.exception(f"Failed to send email to professor {professor.nycu_id}")

            # Create in-app notification (use info type which exists in DB enum)
            try:
                notification_service = NotificationService(self.db)
                await notification_service.create_notification(
                    user_id=professor.id,
                    notification_type=NotificationType.info,
                    data={
                        "title": "新的獎學金申請需要您的審查",
                        "message": f"申請編號 {application.app_id} 已指派給您進行教授推薦審查",
                        "application_id": application.id,
                        "app_id": application.app_id,
                        "student_name": (
                            application.student_data.get("std_cname") if application.student_data else "Unknown"
                        ),
                        "scholarship_name": application.scholarship_name,
                        "assigned_by": assigned_by.name,
                    },
                    href=f"/professor/applications/{application.id}",
                    priority=NotificationPriority.high,
                    channels=[NotificationChannel.in_app, NotificationChannel.email],
                )
                logger.info(f"In-app notification created for professor {professor.nycu_id}")
            except Exception:
                logger.exception(f"Failed to create notification for professor {professor.nycu_id}")

            # Log the assignment change
            if old_professor_id != professor.id:
                logger.info(
                    f"Professor assignment changed for application {application.app_id}: "
                    f"from professor_id={old_professor_id} to professor_id={professor.id} "
                    f"by user {assigned_by.nycu_id}"
                )

            return application

        except Exception:
            logger.exception("Error assigning professor")
            await self.db.rollback()
            raise

    # ------------------------------------------------------------------ #
    # Renewal & Challenge application factories
    # ------------------------------------------------------------------ #

    async def create_renewal_from_previous(
        self,
        previous: Application,
        current_user: User,
        target_academic_year: int,
        renewal_year: int,
    ) -> Application:
        """Create a renewal Application copying sub_type & key fields from a
        previous approved application.

        Caller is responsible for committing the surrounding transaction.
        """
        app_id = await self._generate_app_id(
            target_academic_year,
            previous.semester.value if previous.semester else None,
        )

        # Snapshot the config the prior award consumed so the renewal occupies
        # the same shared-pool slot (spec §9). Fall back to the renewal's own
        # scholarship_configuration_id when the prior slot is unresolved — an
        # approved renewal must NEVER be left NULL (would inflate §6.2 pool).
        from app.models.college_review import CollegeRankingItem

        prior_slot_config_id = await self.db.scalar(
            select(CollegeRankingItem.allocation_config_id)
            .where(
                CollegeRankingItem.application_id == previous.id,
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocation_config_id.isnot(None),
            )
            .order_by(CollegeRankingItem.id.desc())
            .limit(1)
        )
        allocation_config_id = prior_slot_config_id or previous.scholarship_configuration_id

        new_app = Application(
            app_id=app_id,
            user_id=current_user.id,
            scholarship_type_id=previous.scholarship_type_id,
            scholarship_configuration_id=previous.scholarship_configuration_id,
            allocation_config_id=allocation_config_id,
            scholarship_subtype_list=[previous.sub_scholarship_type] if previous.sub_scholarship_type else [],
            sub_scholarship_type=previous.sub_scholarship_type,
            sub_type_selection_mode=previous.sub_type_selection_mode,
            is_renewal=True,
            renewal_year=renewal_year,
            previous_application_id=previous.id,
            academic_year=target_academic_year,
            semester=previous.semester,
            status=ApplicationStatus.draft,
            review_stage=ReviewStage.student_draft,
            agree_terms=False,
        )
        self.db.add(new_app)
        await self.db.flush()
        return new_app

    async def create_challenge_from_renewal(
        self,
        renewal: Application,
        current_user: User,
        target_sub_type: str,
    ) -> Application:
        """Create a challenge Application linked to an approved renewal.

        The challenge targets a different sub_type than the renewal and
        runs in the same academic_year + semester. Caller commits.
        """
        app_id = await self._generate_app_id(
            renewal.academic_year,
            renewal.semester.value if renewal.semester else None,
        )
        new_app = Application(
            app_id=app_id,
            user_id=current_user.id,
            scholarship_type_id=renewal.scholarship_type_id,
            scholarship_configuration_id=renewal.scholarship_configuration_id,
            scholarship_subtype_list=[target_sub_type],
            sub_scholarship_type=target_sub_type,
            sub_type_selection_mode=renewal.sub_type_selection_mode,
            is_renewal=False,
            challenges_application_id=renewal.id,
            academic_year=renewal.academic_year,
            semester=renewal.semester,
            status=ApplicationStatus.draft,
            review_stage=ReviewStage.student_draft,
            agree_terms=False,
        )
        self.db.add(new_app)
        await self.db.flush()
        return new_app
