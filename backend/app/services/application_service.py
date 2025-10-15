"""
Application service for scholarship application management
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, desc
from sqlalchemy import func as sa_func
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AuthorizationError, BusinessLogicError, NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus, ProfessorReview, ProfessorReviewItem
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

        # Integrate file data from submitted_form_data.documents
        integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}

        return ApplicationResponse(
            id=application.id,
            app_id=application.app_id,
            user_id=application.user_id,
            student_id=self._get_student_id_from_user(user) if user else None,
            scholarship_type_id=application.scholarship_type_id,
            scholarship_subtype_list=application.scholarship_subtype_list or [],
            status=application.status,
            status_name=application.status_name,
            is_renewal=application.is_renewal,
            academic_year=application.academic_year,
            semester=self._convert_semester_to_string(application.semester),
            student_data=application.student_data or {},
            submitted_form_data=integrated_form_data,
            agree_terms=application.agree_terms,
            professor_id=application.professor_id,
            reviewer_id=application.reviewer_id,
            final_approver_id=application.final_approver_id,
            review_score=application.review_score,
            review_comments=application.review_comments,
            rejection_reason=application.rejection_reason,
            submitted_at=application.submitted_at,
            reviewed_at=application.reviewed_at,
            approved_at=application.approved_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            meta_data=application.meta_data,
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
        """
        Generate sequential application ID with database locking

        Args:
            academic_year: Academic year (e.g., 113 for 民國113年)
            semester: Semester enum value ('first', 'second', 'yearly' or None)

        Returns:
            str: Sequential application ID (e.g., 'APP-113-1-00001')

        Format: APP-{academic_year}-{semester_code}-{sequence:05d}
        - semester_code: '1' for first, '2' for second, '0' for yearly/None
        """
        from app.models.application_sequence import ApplicationSequence

        # Handle None semester (for yearly scholarships)
        if semester is None:
            semester = "yearly"

        # Use database lock to ensure thread-safe sequence generation
        from sqlalchemy import and_, select

        stmt = (
            select(ApplicationSequence)
            .where(
                and_(
                    ApplicationSequence.academic_year == academic_year,
                    ApplicationSequence.semester == semester,
                )
            )
            .with_for_update()
        )

        result = await self.db.execute(stmt)
        seq_record = result.scalar_one_or_none()

        # Create sequence record if it doesn't exist
        if not seq_record:
            seq_record = ApplicationSequence(academic_year=academic_year, semester=semester, last_sequence=0)
            self.db.add(seq_record)
            await self.db.flush()  # Flush to get the record in the session

        # Increment sequence
        seq_record.last_sequence += 1
        sequence_num = seq_record.last_sequence

        # Commit the sequence increment immediately to release the lock
        await self.db.commit()

        # Format and return app_id
        app_id = ApplicationSequence.format_app_id(academic_year, semester, sequence_num)
        logger.debug(
            f"Generated app_id: {app_id} (academic_year={academic_year}, "
            f"semester={semester}, sequence={sequence_num})"
        )

        return app_id

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

    async def _get_user_and_student_data(self, user_id: int, student_code: str) -> Tuple[User, Dict[str, Any]]:
        """Get user and fetch student data from external API"""
        # Get user
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one()

        # Get student data from external API
        logger.debug(f"Fetching student data for student_code={student_code}")
        student_snapshot = await self.student_service.get_student_snapshot(student_code)
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

        # Determine main scholarship type from scholarship type code
        main_scholarship_type = application_data.scholarship_type.upper()

        # Determine sub scholarship type from selected subtypes (use first one if any)
        scholarship_subtype_list = application_data.scholarship_subtype_list or []
        sub_scholarship_type = "GENERAL"  # Default
        if scholarship_subtype_list:
            sub_scholarship_type = scholarship_subtype_list[0].upper()

        # Create application
        application = Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=scholarship.id,
            scholarship_configuration_id=config.id,
            scholarship_name=config.config_name or scholarship.name,
            amount=config.amount,
            scholarship_subtype_list=scholarship_subtype_list,
            sub_type_selection_mode=sub_type_selection_mode,
            main_scholarship_type=main_scholarship_type,
            sub_scholarship_type=sub_scholarship_type,
            is_renewal=False,  # New applications are never renewals
            academic_year=academic_year,
            semester=semester,
            student_data=student_snapshot,
            submitted_form_data=application_data.form_data.dict() if application_data.form_data else {},
            agree_terms=application_data.agree_terms or False,
            status="draft" if is_draft else "submitted",
        )

        if not is_draft:
            application.submitted_at = datetime.utcnow()

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

        # Get user and student data
        user, student_snapshot = await self._get_user_and_student_data(user_id, student_code)

        # Get and validate scholarship type and configuration
        scholarship, config = await self._get_scholarship_and_config(application_data)

        # Eligibility verification
        eligibility_service = EligibilityService(self.db)
        is_eligible, eligibility_errors = await eligibility_service.check_student_eligibility(
            student_data=student_snapshot, config=config, user_id=user.id
        )

        if not is_eligible:
            error_message = "Student is not eligible for this scholarship. " + "; ".join(eligibility_errors)
            raise ValidationError(error_message)

        # Create application instance using helper method
        application = await self._create_application_instance(
            user, student_snapshot, scholarship, config, application_data, is_draft
        )

        self.db.add(application)
        await self.db.commit()
        await self.db.refresh(application)

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
                selectinload(Application.professor_reviews),
            )
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one()

        logger.debug(f"Application created successfully: {application.app_id} with status: {application.status}")
        return await self._build_application_response(application, user)

    def _integrate_application_file_data(self, application: Application, user: User) -> Dict[str, Any]:
        """Integrate application file information into form data"""
        integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}

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
            status=application.status,
            status_name=application.status_name,
            is_renewal=application.is_renewal,
            academic_year=application.academic_year,
            semester=self._convert_semester_to_string(application.semester),
            student_data=application.student_data,
            submitted_form_data=integrated_form_data,
            agree_terms=application.agree_terms,
            professor_id=application.professor_id,
            reviewer_id=application.reviewer_id,
            final_approver_id=application.final_approver_id,
            review_score=application.review_score,
            review_comments=application.review_comments,
            rejection_reason=application.rejection_reason,
            submitted_at=application.submitted_at,
            reviewed_at=application.reviewed_at,
            approved_at=application.approved_at,
            created_at=application.created_at,
            updated_at=application.updated_at,
            meta_data=application.meta_data,
        )

    async def get_user_applications(self, user: User, status: Optional[str] = None) -> List[ApplicationListResponse]:
        """Get applications for a user"""
        stmt = (
            select(Application)
            .options(selectinload(Application.files), selectinload(Application.scholarship))
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
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}

            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token

                token_data = {"sub": str(user.id)}
                access_token = create_access_token(token_data)

                # 更新 submitted_form_data 中的 documents
                if "documents" in integrated_form_data:
                    existing_docs = integrated_form_data["documents"]
                    for existing_doc in existing_docs:
                        # 查找對應的文件記錄
                        matching_file = next(
                            (f for f in application.files if f.file_type == existing_doc.get("document_id")),
                            None,
                        )
                        if matching_file:
                            # 更新現有文件資訊
                            base_url = f"{settings.base_url}{settings.api_v1_str}"
                            existing_doc.update(
                                {
                                    "file_id": matching_file.id,
                                    "filename": matching_file.filename,
                                    "original_filename": matching_file.original_filename,
                                    "file_size": matching_file.file_size,
                                    "mime_type": matching_file.mime_type or matching_file.content_type,
                                    "file_path": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}?token={access_token}",
                                    "download_url": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}/download?token={access_token}",
                                    "is_verified": matching_file.is_verified,
                                    "object_name": matching_file.object_name,
                                }
                            )

            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=user.nycu_id if user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_type_zh=application.scholarship.name if application.scholarship else "未知獎學金",
                status=application.status,
                status_name=application.status_name,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
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
                selectinload(Application.reviews),
                selectinload(Application.professor_reviews),
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

        # 整合文件資訊到 submitted_form_data.documents
        if application.submitted_form_data and application.files:
            integrated_form_data = application.submitted_form_data.copy()

            # 生成文件訪問 token
            from app.core.config import settings
            from app.core.security import create_access_token

            token_data = {"sub": str(current_user.id)}
            access_token = create_access_token(token_data)

            # 更新 submitted_form_data 中的 documents
            if "documents" in integrated_form_data:
                existing_docs = integrated_form_data["documents"]
                for existing_doc in existing_docs:
                    # 查找對應的文件記錄
                    matching_file = next(
                        (f for f in application.files if f.file_type == existing_doc.get("document_id")),
                        None,
                    )
                    if matching_file:
                        # 更新現有文件資訊
                        base_url = f"{settings.base_url}{settings.api_v1_str}"
                        existing_doc.update(
                            {
                                "file_id": matching_file.id,
                                "filename": matching_file.filename,
                                "original_filename": matching_file.original_filename,
                                "file_size": matching_file.file_size,
                                "mime_type": matching_file.mime_type or matching_file.content_type,
                                "file_path": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}?token={access_token}",
                                "download_url": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}/download?token={access_token}",
                                "is_verified": matching_file.is_verified,
                                "object_name": matching_file.object_name,
                            }
                        )

            # 更新 application 的 submitted_form_data
            application.submitted_form_data = integrated_form_data

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

        # Extract student name and student number from student_data
        student_name = None
        student_no = None
        if application.student_data:
            student_name = application.student_data.get("std_cname")
            student_no = application.student_data.get("std_stdcode")

        # Get user information as fallback
        if not student_name or not student_no:
            if application.student:  # User loaded via relationship
                if not student_name:
                    student_name = application.student.name
                if not student_no:
                    student_no = application.student.nycu_id

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
            "sub_type_labels": sub_type_labels,
            "status": application.status,
            "status_name": application.status_name,
            "is_renewal": application.is_renewal,
            "academic_year": application.academic_year,
            "semester": self._convert_semester_to_string(application.semester),
            "student_data": application.student_data or {},
            "submitted_form_data": application.submitted_form_data or {},
            "agree_terms": application.agree_terms,
            "professor_id": application.professor_id,
            "reviewer_id": application.reviewer_id,
            "final_approver_id": application.final_approver_id,
            "review_score": application.review_score,
            "review_comments": application.review_comments,
            "rejection_reason": application.rejection_reason,
            "submitted_at": application.submitted_at,
            "reviewed_at": application.reviewed_at,
            "approved_at": application.approved_at,
            "created_at": application.created_at,
            "updated_at": application.updated_at,
            "meta_data": application.meta_data,
            "reviews": application.reviews or [],
            "professor_reviews": application.professor_reviews or [],
            # Additional display fields
            "scholarship_type": scholarship_type_name,
            "scholarship_type_zh": scholarship_type_zh,
            "scholarship_name": scholarship_name,
            "amount": amount,
            "currency": currency,
            "student_name": student_name,
            "student_no": student_no,
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

        await self.db.commit()
        await self.db.refresh(application)

        # Clone bank account proof document when saving draft or updating application
        # This ensures the document is available in the application
        logger.info(f"Cloning bank account proof document for application {application.app_id}")
        try:
            await self._clone_user_profile_documents(application, current_user)
        except Exception as e:
            logger.warning(f"Failed to clone bank account proof document for application {application.app_id}: {e}")
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
            except Exception as e:
                logger.warning(
                    f"Failed to re-clone fixed documents after subtype change for application {application.app_id}: {e}"
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
        if refresh_from_api and current_user.nycu_id:
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

        # 更新到資料庫
        application.student_data = current_student_data

        await self.db.commit()
        await self.db.refresh(application)

        return application

    async def submit_application(self, application_id: int, user: User) -> ApplicationResponse:
        """提交申請"""
        # Get application with relationships loaded
        stmt = (
            select(Application)
            .options(
                selectinload(Application.files),
                selectinload(Application.reviews),
                selectinload(Application.professor_reviews),
                selectinload(Application.scholarship),
            )
            .where(Application.id == application_id)
        )
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError(f"Application {application_id} not found")

        if not application.is_editable:
            raise ValidationError("Application cannot be submitted in current status")

        # 驗證所有必填欄位
        _ = ApplicationFormData(**application.submitted_form_data)

        # 處理銀行帳戶證明文件 clone（從個人資料複製到申請）
        await self._clone_user_profile_documents(application, user)

        # 更新狀態為已提交
        from app.utils.i18n import ScholarshipI18n

        application.status = ApplicationStatus.submitted.value
        application.status_name = ScholarshipI18n.get_application_status_text(ApplicationStatus.submitted.value)
        application.submitted_at = datetime.now(timezone.utc)
        application.updated_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(application, ["files", "reviews", "professor_reviews", "scholarship", "student"])

        # 發送自動化通知
        try:
            logger.info(f"=== STARTING EMAIL AUTOMATION for application {application.id} ===")

            # Extract student data from JSON field
            student_data = application.student_data or {}

            # Extract professor information from user profile
            professor_name = ""
            professor_email = ""
            if application.student:
                # Access user profile for advisor information
                user_profile_stmt = select(UserProfile).where(UserProfile.user_id == application.user_id)
                user_profile_result = await self.db.execute(user_profile_stmt)
                user_profile = user_profile_result.scalar_one_or_none()

                if user_profile:
                    professor_name = user_profile.advisor_name or ""
                    professor_email = user_profile.advisor_email or ""

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

        # 整合文件資訊到 submitted_form_data.documents
        integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}

        # 生成文件訪問 token
        from app.core.config import settings
        from app.core.security import create_access_token

        token_data = {"sub": str(user.id)}
        access_token = create_access_token(token_data)

        # 將 files 的完整資訊合併到 documents 中
        if application.files:
            integrated_documents = []
            for file in application.files:
                # 生成文件 URL
                base_url = f"{settings.base_url}{settings.api_v1_str}"
                file_path = f"{base_url}/files/applications/{application_id}/files/{file.id}?token={access_token}"
                download_url = (
                    f"{base_url}/files/applications/{application_id}/files/{file.id}/download?token={access_token}"
                )

                # 整合文件資訊
                integrated_document = {
                    "document_id": file.file_type,
                    "document_type": file.file_type,
                    "file_id": file.id,
                    "filename": file.filename,
                    "original_filename": file.original_filename,
                    "file_size": file.file_size,
                    "mime_type": file.mime_type or file.content_type,
                    "file_path": file_path,
                    "download_url": download_url,
                    "upload_time": file.uploaded_at.isoformat() if file.uploaded_at else None,
                    "is_verified": file.is_verified,
                    "object_name": file.object_name,
                }
                integrated_documents.append(integrated_document)

            # 更新 submitted_form_data 中的 documents
            if "documents" in integrated_form_data:
                # 如果已有 documents，合併文件資訊
                existing_docs = integrated_form_data["documents"]
                for existing_doc in existing_docs:
                    # 查找對應的文件記錄
                    matching_file = next(
                        (f for f in application.files if f.file_type == existing_doc.get("document_id")),
                        None,
                    )
                    if matching_file:
                        # 更新現有文件資訊
                        base_url = f"{settings.base_url}{settings.api_v1_str}"
                        existing_doc.update(
                            {
                                "file_id": matching_file.id,
                                "filename": matching_file.filename,
                                "original_filename": matching_file.original_filename,
                                "file_size": matching_file.file_size,
                                "mime_type": matching_file.mime_type or matching_file.content_type,
                                "file_path": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}?token={access_token}",
                                "download_url": f"{base_url}/files/applications/{application_id}/files/{matching_file.id}/download?token={access_token}",
                                "is_verified": matching_file.is_verified,
                                "object_name": matching_file.object_name,
                            }
                        )
            else:
                # 如果沒有 documents，創建新的
                integrated_form_data["documents"] = integrated_documents

        # Convert application to response model
        response_data = {
            "id": application.id,
            "app_id": application.app_id,
            "user_id": application.user_id,
            "student_id": self._get_student_id_from_user(user),
            "scholarship_type_id": application.scholarship_type_id,
            "scholarship_subtype_list": application.scholarship_subtype_list,
            "status": application.status,
            "status_name": application.status_name,
            "academic_year": application.academic_year,
            "semester": application.semester,
            "student_data": application.student_data,
            "submitted_form_data": integrated_form_data,  # 使用整合後的表單資料
            "agree_terms": application.agree_terms,
            "professor_id": application.professor_id,
            "reviewer_id": application.reviewer_id,
            "final_approver_id": application.final_approver_id,
            "review_score": application.review_score,
            "review_comments": application.review_comments,
            "rejection_reason": application.rejection_reason,
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
                    "reviewer_id": review.reviewer_id,
                    "reviewer_name": review.reviewer_name,
                    "score": review.score,
                    "comments": review.comments,
                    "reviewed_at": review.reviewed_at,
                }
                for review in application.reviews
            ],
            "professor_reviews": [
                {
                    "id": review.id,
                    "professor_id": review.professor_id,
                    "professor_name": review.professor_name,
                    "score": review.score,
                    "comments": review.comments,
                    "reviewed_at": review.reviewed_at,
                }
                for review in application.professor_reviews
            ],
        }

        return ApplicationResponse(**response_data)

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
            accessible_student_ids = current_user.get_accessible_student_ids("view_applications")
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
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}

            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token

                token_data = {"sub": str(current_user.id)}
                access_token = create_access_token(token_data)

                # 更新 submitted_form_data 中的 documents
                if "documents" in integrated_form_data:
                    existing_docs = integrated_form_data["documents"]
                    for existing_doc in existing_docs:
                        # 查找對應的文件記錄
                        matching_file = next(
                            (f for f in application.files if f.file_type == existing_doc.get("document_id")),
                            None,
                        )
                        if matching_file:
                            # 更新現有文件資訊
                            base_url = f"{settings.base_url}{settings.api_v1_str}"
                            existing_doc.update(
                                {
                                    "file_id": matching_file.id,
                                    "filename": matching_file.filename,
                                    "original_filename": matching_file.original_filename,
                                    "file_size": matching_file.file_size,
                                    "mime_type": matching_file.mime_type or matching_file.content_type,
                                    "file_path": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}?token={access_token}",
                                    "download_url": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}/download?token={access_token}",
                                    "is_verified": matching_file.is_verified,
                                    "object_name": matching_file.object_name,
                                }
                            )

            # Use eagerly loaded user (already loaded with selectinload)
            app_user = application.user

            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=app_user.nycu_id if app_user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_type_zh=application.scholarship.name if application.scholarship else None,
                status=application.status,
                status_name=application.status_name,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
                submitted_at=application.submitted_at,
                reviewed_at=application.reviewed_at,
                approved_at=application.approved_at,
                created_at=application.created_at,
                updated_at=application.updated_at,
                meta_data=application.meta_data,
            )

            response_applications.append(app_data)

        return response_applications

    async def update_application_status(
        self, application_id: int, user: User, status_update: ApplicationStatusUpdate
    ) -> ApplicationResponse:
        """Update application status (staff only)"""
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

        # Update status
        application.status = status_update.status
        application.reviewer_id = user.id

        from app.utils.i18n import ScholarshipI18n

        if status_update.status == ApplicationStatus.approved.value:
            application.approved_at = datetime.utcnow()
            application.status_name = ScholarshipI18n.get_application_status_text(ApplicationStatus.approved.value)
        elif status_update.status == ApplicationStatus.rejected.value:
            application.status_name = ScholarshipI18n.get_application_status_text(ApplicationStatus.rejected.value)
            if hasattr(status_update, "rejection_reason") and status_update.rejection_reason:
                application.rejection_reason = status_update.rejection_reason

        if hasattr(status_update, "comments") and status_update.comments:
            application.review_comments = status_update.comments

        application.reviewed_at = datetime.utcnow()

        await self.db.commit()

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
        from app.models.application import ProfessorReview, ProfessorReviewItem

        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()
        if not application:
            raise NotFoundError("Application", str(application_id))
        # Only the assigned professor can submit
        if application.professor_id != user.id:
            raise AuthorizationError("You are not the assigned professor for this application")

        # Create review record
        review = ProfessorReview(
            application_id=application_id,
            professor_id=user.id,
            recommendation=review_data.recommendation,
            review_status=review_data.review_status or "completed",
            reviewed_at=datetime.utcnow(),
        )
        self.db.add(review)
        await self.db.flush()  # Get the review ID

        # Create review items for each sub-type
        for item_data in review_data.items:
            review_item = ProfessorReviewItem(
                review_id=review.id,
                sub_type_code=item_data.sub_type_code,
                is_recommended=item_data.is_recommended,
                comments=item_data.comments,
            )
            self.db.add(review_item)

        await self.db.commit()

        # 觸發教授審查提交事件（會觸發自動化郵件規則）
        try:
            from app.services.email_automation_service import email_automation_service

            # Fetch student and scholarship info for email context
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
                    "review_result": review.review_status,
                    "review_date": review.reviewed_at.strftime("%Y-%m-%d")
                    if review.reviewed_at
                    else datetime.utcnow().strftime("%Y-%m-%d"),
                    "professor_recommendation": review.recommendation,
                    "college_name": application.college_name if hasattr(application, "college_name") else "",
                    "review_deadline": "",  # Add if available from scholarship config
                },
            )
        except Exception as e:
            logger.error(f"Failed to trigger professor review automation: {e}")

        # Return fresh copy with all relationships loaded
        return await self.get_application_by_id(application_id)

    async def upload_application_file_minio(
        self, application_id: int, user: User, file, file_type: str
    ) -> Dict[str, Any]:
        """Upload application file using MinIO"""
        # Verify application exists and user has access
        stmt = select(Application).where(Application.id == application_id)
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

        # Save file metadata to database
        file_record = ApplicationFile(
            application_id=application_id,
            filename=file.filename,  # Keep original filename for display
            original_filename=file.filename,  # Store original filename
            file_type=file_type,
            file_size=file_size,
            object_name=object_name,  # This is now UUID-based path
            uploaded_at=datetime.utcnow(),
            content_type=file.content_type or "application/octet-stream",
            mime_type=file.content_type or "application/octet-stream",
        )

        self.db.add(file_record)
        await self.db.commit()
        await self.db.refresh(file_record)

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
            accessible_student_ids = current_user.get_accessible_student_ids("view_applications")
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
            # 整合文件資訊到 submitted_form_data.documents
            integrated_form_data = application.submitted_form_data.copy() if application.submitted_form_data else {}

            if application.files:
                # 生成文件訪問 token
                from app.core.config import settings
                from app.core.security import create_access_token

                token_data = {"sub": str(current_user.id)}
                access_token = create_access_token(token_data)

                # 更新 submitted_form_data 中的 documents
                if "documents" in integrated_form_data:
                    existing_docs = integrated_form_data["documents"]
                    for existing_doc in existing_docs:
                        # 查找對應的文件記錄
                        matching_file = next(
                            (f for f in application.files if f.file_type == existing_doc.get("document_id")),
                            None,
                        )
                        if matching_file:
                            # 更新現有文件資訊
                            base_url = f"{settings.base_url}{settings.api_v1_str}"
                            existing_doc.update(
                                {
                                    "file_id": matching_file.id,
                                    "filename": matching_file.filename,
                                    "original_filename": matching_file.original_filename,
                                    "file_size": matching_file.file_size,
                                    "mime_type": matching_file.mime_type or matching_file.content_type,
                                    "file_path": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}?token={access_token}",
                                    "download_url": f"{base_url}/files/applications/{application.id}/files/{matching_file.id}/download?token={access_token}",
                                    "is_verified": matching_file.is_verified,
                                    "object_name": matching_file.object_name,
                                }
                            )

            # Use eagerly loaded user (already loaded with selectinload)
            app_user = application.user

            # 創建響應數據
            app_data = ApplicationListResponse(
                id=application.id,
                app_id=application.app_id,
                user_id=application.user_id,
                student_id=app_user.nycu_id if app_user else None,
                scholarship_type=application.scholarship.code if application.scholarship else None,
                scholarship_type_id=application.scholarship_type_id,
                scholarship_type_zh=application.scholarship.name if application.scholarship else None,
                status=application.status,
                status_name=application.status_name,
                academic_year=application.academic_year,
                semester=self._convert_semester_to_string(application.semester),
                student_data=application.student_data,
                submitted_form_data=integrated_form_data,  # 使用整合後的表單資料
                agree_terms=application.agree_terms,
                professor_id=application.professor_id,
                reviewer_id=application.reviewer_id,
                final_approver_id=application.final_approver_id,
                review_score=application.review_score,
                review_comments=application.review_comments,
                rejection_reason=application.rejection_reason,
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
        Soft delete an application

        Permission Control:
        - Students: Can only delete their own draft applications
        - Staff (professor/college/admin): Can delete any application (reason required)

        Args:
            application_id: ID of application to delete
            current_user: User performing the deletion
            reason: Reason for deletion (required for staff)

        Returns:
            Deleted application object
        """
        # Get application
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", application_id)

        # Check if already deleted
        if application.status == ApplicationStatus.deleted.value:
            raise ValidationError("Application is already deleted")

        # Check if user has permission to delete this application
        if current_user.role == UserRole.student:
            if application.user_id != current_user.id:
                raise AuthorizationError("You can only delete your own applications")
            # Students can only delete draft applications
            if application.status != ApplicationStatus.draft.value:
                raise ValidationError("Only draft applications can be deleted by students")
        elif current_user.role in [UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin]:
            # Staff can delete any application but must provide a reason
            if not reason:
                raise ValidationError("Deletion reason is required for staff users")
        else:
            raise AuthorizationError("You don't have permission to delete applications")

        # Perform soft delete
        application.status = ApplicationStatus.deleted.value
        application.deleted_at = datetime.now(timezone.utc)
        application.deleted_by_id = current_user.id
        application.deletion_reason = reason or "Student deleted draft application"

        await self.db.commit()
        await self.db.refresh(application)

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

        except Exception as e:
            logger.error(f"Failed to clone user profile documents for application {application.app_id}: {e}")
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
    async def get_professor_applications_paginated(
        self,
        professor_id: int,
        status_filter: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[List[ApplicationListResponse], int]:
        """Get paginated applications assigned to professor with total count"""
        try:
            # Build base query with ALL required filters (consistent with what will be returned)
            base_query = (
                select(Application)
                .options(
                    selectinload(Application.scholarship_configuration).selectinload(
                        ScholarshipConfiguration.scholarship_type
                    ),
                    selectinload(Application.professor_reviews),
                    selectinload(Application.student),
                )
                .join(Application.scholarship_configuration)
                .where(
                    # Only applications that require professor recommendation
                    Application.scholarship_configuration.has(
                        ScholarshipConfiguration.requires_professor_recommendation.is_(True)
                    ),
                    # Only applications assigned to this specific professor
                    Application.professor_id == professor_id,
                    # Only applications in valid statuses for professor viewing
                    Application.status.in_(
                        [
                            ApplicationStatus.submitted.value,
                            ApplicationStatus.under_review.value,
                            ApplicationStatus.pending_recommendation.value,
                            ApplicationStatus.recommended.value,
                            ApplicationStatus.approved.value,
                            ApplicationStatus.rejected.value,
                        ]
                    ),
                )
            )

            # Apply status filter to base query
            if status_filter == "pending":
                base_query = base_query.where(
                    Application.status.in_(
                        [
                            ApplicationStatus.submitted.value,
                            ApplicationStatus.pending_recommendation.value,
                            ApplicationStatus.under_review.value,  # Include under_review in pending
                        ]
                    )
                )
            elif status_filter == "completed":
                base_query = base_query.where(
                    Application.status.in_(
                        [
                            ApplicationStatus.recommended.value,
                            ApplicationStatus.approved.value,
                            ApplicationStatus.rejected.value,
                        ]
                    )
                )
            # "all" or None shows all applications (no additional status filter)

            # Get total count with same filters
            count_query = select(func.count()).select_from(base_query.subquery())
            count_result = await self.db.execute(count_query)
            total_count = count_result.scalar()

            # Apply pagination and get results
            offset = (page - 1) * size
            paginated_query = base_query.offset(offset).limit(size).order_by(desc(Application.created_at))

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
                        scholarship_type=app.main_scholarship_type.lower() if app.main_scholarship_type else "",
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
                        review_score=app.review_score,
                        review_comments=app.review_comments,
                        rejection_reason=app.rejection_reason,
                        submitted_at=app.submitted_at,
                        reviewed_at=app.reviewed_at,
                        approved_at=app.approved_at,
                        created_at=app.created_at,
                        updated_at=app.updated_at,
                        meta_data=app.meta_data,
                        # Display fields
                        student_name=app.student_data.get("std_cname", "") if app.student_data else "",
                        student_no=app.student_data.get("std_stdcode", "") if app.student_data else "",
                        days_waiting=None,  # Calculate if needed
                        professor=None,  # Professor info not needed in professor view
                        scholarship_configuration={
                            "requires_professor_recommendation": app.scholarship_configuration.requires_professor_recommendation
                            if app.scholarship_configuration
                            else False,
                            "requires_college_review": app.scholarship_configuration.requires_college_review
                            if app.scholarship_configuration
                            else False,
                            "config_name": app.scholarship_configuration.config_name
                            if app.scholarship_configuration
                            else None,
                        }
                        if app.scholarship_configuration
                        else None,
                    )
                )

            return responses, total_count

        except Exception as e:
            logger.error(f"Error fetching paginated professor applications: {e}")
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

            # Check if scholarship requires professor recommendation
            if not application.scholarship_configuration.requires_professor_recommendation:
                return False

            # Check if application is assigned to this specific professor
            if application.professor_id != professor_id:
                return False

            # Check application status - should be submitted or under review (or historical)
            if application.status not in [
                ApplicationStatus.submitted.value,
                ApplicationStatus.under_review.value,
                ApplicationStatus.pending_recommendation.value,
                ApplicationStatus.recommended.value,  # Allow viewing historical reviews
                ApplicationStatus.approved.value,
                ApplicationStatus.rejected.value,
            ]:
                return False

            return True

        except Exception as e:
            logger.error(f"Error checking professor review authorization: {e}")
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
            if application.status not in [
                ApplicationStatus.submitted.value,
                ApplicationStatus.under_review.value,
                ApplicationStatus.pending_recommendation.value,
            ]:
                return False

            now = datetime.now(timezone.utc)

            # Check professor review period for SUBMISSION (this is where time restriction applies)
            # Skip time restrictions if review periods are not configured (e.g., in test environment)
            if application.is_renewal:
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

        except Exception as e:
            logger.error(f"Error checking professor review submission authorization: {e}")
            return False

    async def get_professor_review(self, application_id: int, professor_id: int):
        """Get existing professor review"""
        try:
            stmt = (
                select(ProfessorReview)
                .options(
                    selectinload(ProfessorReview.items),
                    selectinload(ProfessorReview.application),
                )
                .where(
                    and_(
                        ProfessorReview.application_id == application_id,
                        ProfessorReview.professor_id == professor_id,
                    )
                )
            )

            result = await self.db.execute(stmt)
            review = result.scalar_one_or_none()

            if not review:
                return None

            from app.schemas.application import ProfessorReviewItemResponse, ProfessorReviewResponse

            return ProfessorReviewResponse(
                id=review.id,
                application_id=review.application_id,
                professor_id=review.professor_id,
                recommendation=review.recommendation,
                review_status=review.review_status,
                reviewed_at=review.reviewed_at,
                created_at=review.created_at,
                items=[
                    ProfessorReviewItemResponse(
                        id=item.id,
                        review_id=item.review_id,
                        sub_type_code=item.sub_type_code,
                        is_recommended=item.is_recommended,
                        comments=item.comments,
                        created_at=item.created_at,
                    )
                    for item in review.items
                ],
            )

        except Exception as e:
            logger.error(f"Error fetching professor review: {e}")
            raise

    async def get_professor_review_by_id(self, review_id: int):
        """Get professor review by its ID (for authorization checks)"""
        try:
            stmt = (
                select(ProfessorReview)
                .options(selectinload(ProfessorReview.items))
                .where(ProfessorReview.id == review_id)
            )

            result = await self.db.execute(stmt)
            review = result.scalar_one_or_none()

            if not review:
                return None

            from app.schemas.application import ProfessorReviewItemResponse, ProfessorReviewResponse

            return ProfessorReviewResponse(
                id=review.id,
                application_id=review.application_id,
                professor_id=review.professor_id,
                recommendation=review.recommendation,
                review_status=review.review_status,
                reviewed_at=review.reviewed_at,
                created_at=review.created_at,
                items=[
                    ProfessorReviewItemResponse(
                        id=item.id,
                        review_id=item.review_id,
                        sub_type_code=item.sub_type_code,
                        is_recommended=item.is_recommended,
                        comments=item.comments,
                        created_at=item.created_at,
                    )
                    for item in review.items
                ],
            )

        except Exception as e:
            logger.error(f"Error fetching professor review by ID {review_id}: {e}")
            raise

    async def submit_professor_review(self, application_id: int, professor_id: int, review_data: dict) -> dict:
        """Submit professor review for an application"""
        try:
            logger.info(f"Step 1: Checking existing review for app {application_id}, prof {professor_id}")
            # Check if review already exists
            existing_review = await self.get_professor_review(application_id, professor_id)
            if existing_review and existing_review.id > 0:  # ID > 0 means it's saved (not a new review template)
                # Update existing review
                logger.info(f"Found existing review {existing_review.id}, updating")
                return await self.update_professor_review(existing_review.id, review_data)

            logger.info("Step 2: Creating new professor review")
            # Create new professor review
            professor_review = ProfessorReview(
                application_id=application_id,
                professor_id=professor_id,
                recommendation=review_data.get("recommendation"),
                review_status="completed",
                reviewed_at=datetime.now(timezone.utc),
            )

            self.db.add(professor_review)
            logger.info("Step 3: Flushing to get review ID")
            await self.db.flush()  # Get the review ID
            logger.info(f"Created review with ID {professor_review.id}")

            # Create review items for each sub-type
            logger.info(f"Step 4: Creating {len(review_data.get('items', []))} review items")
            review_items = review_data.get("items", [])
            for item_data in review_items:
                review_item = ProfessorReviewItem(
                    review_id=professor_review.id,
                    sub_type_code=item_data.get("sub_type_code"),
                    is_recommended=item_data.get("is_recommended", False),
                    comments=item_data.get("comments"),
                )
                self.db.add(review_item)

            # Update application status
            logger.info("Step 5: Updating application status")
            stmt = select(Application).where(Application.id == application_id)
            result = await self.db.execute(stmt)
            application = result.scalar_one_or_none()

            if application:
                from app.utils.i18n import ScholarshipI18n

                logger.info("Step 6: Setting status to recommended")
                application.status = ApplicationStatus.recommended.value
                application.status_name = ScholarshipI18n.get_application_status_text(
                    ApplicationStatus.recommended.value
                )

            logger.info("Step 7: Committing transaction")
            await self.db.commit()

            # Return the created review
            logger.info("Step 8: Fetching created review to return")
            return await self.get_professor_review(application_id, professor_id)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error submitting professor review: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    async def update_professor_review(self, review_id: int, review_data: dict) -> dict:
        """Update an existing professor review"""
        try:
            # Get existing review
            stmt = (
                select(ProfessorReview)
                .options(selectinload(ProfessorReview.items))
                .where(ProfessorReview.id == review_id)
            )

            result = await self.db.execute(stmt)
            review = result.scalar_one_or_none()

            if not review:
                raise NotFoundError("Professor review not found")

            # Update review fields
            review.recommendation = review_data.get("recommendation", review.recommendation)
            review.review_status = "completed"
            review.reviewed_at = datetime.now(timezone.utc)

            # Update review items
            existing_items = {item.sub_type_code: item for item in review.items}
            new_items = review_data.get("items", [])

            for item_data in new_items:
                sub_type_code = item_data.get("sub_type_code")
                if sub_type_code in existing_items:
                    # Update existing item
                    existing_item = existing_items[sub_type_code]
                    existing_item.is_recommended = item_data.get("is_recommended", False)
                    existing_item.comments = item_data.get("comments")
                else:
                    # Create new item
                    new_item = ProfessorReviewItem(
                        review_id=review.id,
                        sub_type_code=sub_type_code,
                        is_recommended=item_data.get("is_recommended", False),
                        comments=item_data.get("comments"),
                    )
                    self.db.add(new_item)

            await self.db.commit()

            # Return updated review
            return await self.get_professor_review(review.application_id, review.professor_id)

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Error updating professor review: {e}")
            raise

    async def get_application_available_sub_types(self, application_id: int) -> List[dict]:
        """Get sub-types that the student actually applied for (not all possible sub-types)"""
        try:
            # Get application with scholarship type - use explicit join to avoid lazy loading
            stmt = (
                select(Application)
                .options(selectinload(Application.scholarship_configuration))
                .where(Application.id == application_id)
            )

            result = await self.db.execute(stmt)
            application = result.scalar_one_or_none()

            if not application:
                return []

            # Get the sub-types that the student actually applied for
            applied_sub_types = application.scholarship_subtype_list or []

            # If no specific sub-types or contains general, only show main scholarship (no sub-type selection)
            if not applied_sub_types or "general" in applied_sub_types or len(applied_sub_types) == 0:
                return []  # No sub-types to review for general applications

            # Get scholarship type with sub_type_configs relationship loaded properly
            from app.models.scholarship import ScholarshipType

            stmt = (
                select(ScholarshipType)
                .options(selectinload(ScholarshipType.sub_type_configs))
                .where(ScholarshipType.id == application.scholarship_type_id)
            )
            result = await self.db.execute(stmt)
            scholarship_type = result.scalar_one_or_none()

            if not scholarship_type:
                return []

            # Build translations from loaded sub_type_configs
            translations = {"zh": {}, "en": {}}

            # Get active sub-type configs that are already loaded
            active_configs = [config for config in scholarship_type.sub_type_configs if config.is_active]
            active_configs.sort(key=lambda x: x.display_order)

            for config in active_configs:
                translations["zh"][config.sub_type_code] = config.name
                translations["en"][config.sub_type_code] = config.name_en or config.name

            # Build response - only include sub-types that the student applied for
            sub_type_list = []

            for sub_type in applied_sub_types:
                if sub_type and sub_type != "general":  # Skip general
                    sub_type_list.append(
                        {
                            "value": sub_type,
                            "label": translations.get("zh", {}).get(sub_type, sub_type),
                            "label_en": translations.get("en", {}).get(sub_type, sub_type),
                            "is_default": False,
                        }
                    )

            return sub_type_list

        except Exception as e:
            logger.error(f"Error fetching application sub-types: {e}")
            raise

    async def get_professor_review_stats(self, professor_id: int) -> dict:
        """Get basic review statistics for a professor"""
        try:
            # Get applications in current review period - simplified approach to avoid column reference issues
            pending_query = select(func.count(Application.id)).where(
                Application.professor_id == professor_id,
                Application.status.in_(
                    [
                        ApplicationStatus.submitted.value,
                        ApplicationStatus.pending_recommendation.value,
                    ]
                ),
            )

            completed_query = select(func.count(ProfessorReview.id)).where(
                ProfessorReview.professor_id == professor_id,
                ProfessorReview.review_status == "completed",
            )

            # Execute queries
            pending_result = await self.db.execute(pending_query)
            completed_result = await self.db.execute(completed_query)

            pending_count = pending_result.scalar() or 0
            completed_count = completed_result.scalar() or 0

            # For overdue reviews, we'll use a simplified approach
            # In production, this would need proper review period configuration
            # For now, assume overdue = 0 (can be enhanced later)
            overdue_count = 0

            return {
                "pending_reviews": pending_count,
                "completed_reviews": completed_count,
                "overdue_reviews": overdue_count,
            }

        except Exception as e:
            logger.error(f"Error fetching professor stats: {e}")
            return {"pending_reviews": 0, "completed_reviews": 0, "overdue_reviews": 0}

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

        except Exception as e:
            logger.error(f"Error fetching available professors: {e}")
            raise

    async def assign_professor(self, application_id: int, professor_nycu_id: str, assigned_by: User) -> Application:
        """Assign professor to application with notification"""
        try:
            from app.core.exceptions import NotFoundError, ValidationError
            from app.models.application import ApplicationReview, ProfessorReview
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
                    selectinload(Application.professor_reviews).selectinload(ProfessorReview.professor),
                    selectinload(Application.professor_reviews).selectinload(ProfessorReview.items),
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

            # Check if scholarship requires professor review
            config = application.scholarship_configuration
            if not config or not config.requires_professor_recommendation:
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

            # Send email notification to professor
            if professor.email:
                try:
                    email_service = EmailService()
                    await email_service.send_to_professor(application, self.db)
                    logger.info(f"Email notification sent to professor {professor.nycu_id}")
                except Exception as e:
                    logger.error(f"Failed to send email to professor {professor.nycu_id}: {e}")

            # Create in-app notification
            try:
                notification_service = NotificationService(self.db)
                await notification_service.create_notification(
                    user_id=professor.id,
                    notification_type=NotificationType.professor_assignment,
                    data={
                        "title": "新的獎學金申請需要您的審查",
                        "message": f"申請編號 {application.app_id} 已指派給您進行教授推薦審查",
                        "application_id": application.id,
                        "app_id": application.app_id,
                        "student_name": application.student_data.get("std_cname")
                        if application.student_data
                        else "Unknown",
                        "scholarship_name": application.scholarship_name,
                        "assigned_by": assigned_by.name,
                    },
                    href=f"/professor/applications/{application.id}",
                    priority=NotificationPriority.high,
                    channels=[NotificationChannel.in_app, NotificationChannel.email],
                )
                logger.info(f"In-app notification created for professor {professor.nycu_id}")
            except Exception as e:
                logger.error(f"Failed to create notification for professor {professor.nycu_id}: {e}")

            # Log the assignment change
            if old_professor_id != professor.id:
                logger.info(
                    f"Professor assignment changed for application {application.app_id}: "
                    f"from professor_id={old_professor_id} to professor_id={professor.id} "
                    f"by user {assigned_by.nycu_id}"
                )

            return application

        except Exception as e:
            logger.error(f"Error assigning professor: {e}")
            await self.db.rollback()
            raise
