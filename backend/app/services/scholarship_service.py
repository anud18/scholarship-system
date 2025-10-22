"""
Comprehensive scholarship service for scholarship management
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import and_, asc, desc
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# Student model removed - student data now fetched from external API
from app.core.config import DEV_SCHOLARSHIP_SETTINGS, settings

# Import comprehensive scholarship system models
from app.models.application import (
    Application,
    ApplicationReview,
    ApplicationStatus,
    ProfessorReview,
    ProfessorReviewItem,
    ReviewStatus,
    ScholarshipMainType,
    ScholarshipSubType,
)

logger = logging.getLogger(__name__)


class ScholarshipService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def _safe_gpa_to_decimal(self, gpa: Union[str, int, float, Decimal]) -> Decimal:
        """Safely convert GPA to Decimal for comparison"""
        try:
            if isinstance(gpa, str):
                return Decimal(gpa)
            elif isinstance(gpa, (int, float)):
                return Decimal(str(gpa))
            elif isinstance(gpa, Decimal):
                return gpa
            else:
                logger.warning(f"Unexpected GPA type: {type(gpa)}, value: {gpa}")
                return Decimal("0.0")
        except Exception as e:
            logger.error(f"Error converting GPA '{gpa}' to Decimal: {e}")
            return Decimal("0.0")

    def _is_dev_mode(self) -> bool:
        """Check if running in development mode"""
        return settings.debug or settings.environment == "development"

    def _should_bypass_application_period(self) -> bool:
        """Check if should bypass application period in dev mode"""
        return self._is_dev_mode() and DEV_SCHOLARSHIP_SETTINGS.get("ALWAYS_OPEN_APPLICATION", False)

    def _should_bypass_whitelist(self) -> bool:
        """Check if should bypass whitelist in dev mode"""
        return self._is_dev_mode() and DEV_SCHOLARSHIP_SETTINGS.get("BYPASS_WHITELIST", False)

    async def get_eligible_scholarships(
        self, student_data: Dict[str, Any], user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get scholarships that the student is eligible for based on active configurations"""
        from app.services.eligibility_service import EligibilityService
        from app.services.scholarship_configuration_service import ScholarshipConfigurationService
        from app.services.student_service import StudentService

        config_service = ScholarshipConfigurationService(self.db)
        eligibility_service = EligibilityService(self.db)
        student_service = StudentService()

        # Get all active and effective configurations
        active_configs = await config_service.get_active_configurations()

        eligible_scholarships = []

        # Cache for student data by API type to avoid duplicate API calls
        student_data_cache = {
            "student": student_data,  # Start with the basic data provided
            "student_term": {},  # Cache for term-specific data
        }

        for config in active_configs:
            # First filter by application period - only show scholarships within their application period
            if not self._should_bypass_application_period() and not config.is_application_period:
                continue

            # Determine which student API type is required for this configuration
            required_api_type = await eligibility_service.determine_required_student_api_type(config)

            # Get appropriate student data based on rule requirements
            current_student_data = student_data  # Default to basic data

            if required_api_type == "student_term":
                # Create a cache key for this academic year and semester
                cache_key = f"{config.academic_year}_{config.semester.value if config.semester else 'yearly'}"

                if cache_key not in student_data_cache["student_term"]:
                    # Convert semester enum to string for API call
                    semester_str = config.semester.value if config.semester else "1"  # Default to first semester
                    academic_year_str = str(config.academic_year)

                    # Fetch term-specific data
                    student_code = student_data.get("std_stdcode")
                    if student_code:
                        try:
                            term_data = await student_service.get_student_term_info(
                                student_code, academic_year_str, semester_str
                            )
                            if term_data:
                                # Merge basic data with term-specific data
                                current_student_data = {**student_data, **term_data}
                                student_data_cache["student_term"][cache_key] = current_student_data
                            else:
                                logger.warning(
                                    f"Could not fetch term data for student {student_code}, AY{academic_year_str}, semester {semester_str}"
                                )
                                # Mark term data as not found (student has no data for this term)
                                current_student_data = {
                                    **student_data,
                                    "_term_data_status": "not_found",
                                    "_term_error_message": f"查無 {academic_year_str} 學年第 {semester_str} 學期的學期資料",
                                }
                                student_data_cache["student_term"][cache_key] = current_student_data
                        except Exception as e:
                            logger.warning(f"Student term API unavailable, continuing with basic data: {e}")
                            # Mark term data as API error (system issue)
                            current_student_data = {
                                **student_data,
                                "_term_data_status": "api_error",
                                "_term_error_message": f"學期資料 API 暫時無法使用: {str(e)}",
                            }
                            student_data_cache["student_term"][cache_key] = current_student_data
                    else:
                        logger.error("Student code not found in student data")
                        # Mark term data as unavailable due to missing student code
                        current_student_data = {
                            **student_data,
                            "_term_data_status": "missing_student_code",
                            "_term_error_message": "缺少學號資料，無法查詢學期資料",
                        }
                        student_data_cache["student_term"][cache_key] = current_student_data
                else:
                    # Use cached term data
                    current_student_data = student_data_cache["student_term"][cache_key]

            # Check if student meets eligibility with appropriate data and get detailed results
            (
                is_eligible,
                reasons,
                eligibility_details,
            ) = await eligibility_service.get_detailed_eligibility_check(current_student_data, config, user_id)

            # Always get application status if user_id is provided, regardless of eligibility
            application_status = {}
            if user_id:
                application_status = await eligibility_service.get_application_status(user_id, config)

            if is_eligible:
                # Build scholarship response with configuration data
                scholarship_type = config.scholarship_type

                # Filter sub_type_list based on student eligibility
                (
                    eligible_subtypes,
                    subtype_eligibility_info,
                ) = await self._filter_eligible_subtypes(
                    scholarship_type.sub_type_list or [],
                    eligibility_details,
                    scholarship_type,
                )

                scholarship_dict = {
                    "id": scholarship_type.id,
                    "configuration_id": config.id,  # Add configuration ID for application creation
                    "code": scholarship_type.code,
                    "name": config.config_name or scholarship_type.name,
                    "name_en": scholarship_type.name_en,
                    "description": config.description or scholarship_type.description,
                    "description_en": config.description_en or scholarship_type.description_en,
                    "academic_year": config.academic_year,
                    "semester": config.semester.value if config.semester else None,
                    "application_cycle": scholarship_type.application_cycle.value
                    if scholarship_type.application_cycle
                    else "semester",
                    "sub_type_list": eligible_subtypes,  # Only eligible subtypes
                    "all_sub_type_list": scholarship_type.sub_type_list or [],  # All subtypes for reference
                    "subtype_eligibility": subtype_eligibility_info,  # Detailed eligibility per subtype
                    "sub_type_selection_mode": scholarship_type.sub_type_selection_mode.value
                    if scholarship_type.sub_type_selection_mode
                    else "single",
                    # Configuration-specific data
                    "amount": config.amount,
                    "currency": config.currency,
                    "application_start_date": config.application_start_date,
                    "application_end_date": config.application_end_date,
                    "renewal_application_start_date": config.renewal_application_start_date,
                    "renewal_application_end_date": config.renewal_application_end_date,
                    "professor_review_start": config.professor_review_start,
                    "professor_review_end": config.professor_review_end,
                    "college_review_start": config.college_review_start,
                    "college_review_end": config.college_review_end,
                    "requires_professor_recommendation": config.requires_professor_recommendation,
                    "requires_college_review": config.requires_college_review,
                    "requires_interview": getattr(config, "requires_interview", False),
                    "requires_research_proposal": getattr(config, "requires_research_proposal", False),
                    # Eligibility info
                    "whitelist_enabled": scholarship_type.whitelist_enabled,
                    "whitelist_student_ids": config.whitelist_student_ids or {},
                    # Terms document
                    "terms_document_url": scholarship_type.terms_document_url,
                    # System data
                    "created_at": scholarship_type.created_at,
                    "config_version": config.version,
                    "config_code": config.config_code,
                }

                # Check quota availability
                (
                    quota_available,
                    quota_info,
                ) = await config_service.check_quota_availability(config, student_data.get("department_code"))

                scholarship_dict.update(
                    {
                        "quota_available": quota_available,
                        "quota_info": quota_info,
                        # Add rule evaluation results
                        "passed": eligibility_details.get("passed", []),
                        "warnings": eligibility_details.get("warnings", []),
                        "errors": eligibility_details.get("errors", []),
                        # Add application status information
                        "application_status": application_status.get("application_status"),
                        "can_apply": application_status.get("can_apply", True),
                        "status_display": application_status.get("status_display", "可申請"),
                        "has_application": application_status.get("has_application", False),
                        "application_id": application_status.get("application_id"),
                    }
                )

                eligible_scholarships.append(scholarship_dict)

        return eligible_scholarships

    async def _filter_eligible_subtypes(
        self,
        all_subtypes: List[str],
        eligibility_details: Dict[str, Any],
        scholarship_type,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Filter subtypes based on student eligibility and return detailed eligibility info

        Args:
            all_subtypes: List of all available subtypes for this scholarship
            eligibility_details: Detailed eligibility results from eligibility service
            scholarship_type: ScholarshipType instance for getting name translations

        Returns:
            Tuple of (eligible_subtypes_with_names_list, subtype_eligibility_info_dict)
        """
        if not all_subtypes:
            return [], {}

        # Get subtype name translations from database
        translations = await self._get_subtype_translations(scholarship_type.id)

        # Track which subtypes have failed rules (non-warning rules)
        subtype_failures = {}
        subtype_eligibility_info = {}

        # Check error rules to see which subtypes have critical failures
        for error_rule in eligibility_details.get("errors", []):
            sub_type = error_rule.get("sub_type")
            if sub_type:
                if sub_type not in subtype_failures:
                    subtype_failures[sub_type] = []
                    subtype_eligibility_info[sub_type] = {
                        "eligible": True,  # Start optimistic
                        "failed_rules": [],
                        "warning_rules": [],
                    }

                # Non-warning rules make subtype ineligible
                if not error_rule.get("is_warning", False):
                    subtype_eligibility_info[sub_type]["eligible"] = False
                    subtype_eligibility_info[sub_type]["failed_rules"].append(
                        {
                            "rule_name": error_rule.get("rule_name"),
                            "message": error_rule.get("message"),
                            "tag": error_rule.get("tag"),
                        }
                    )

        # Check warning rules for additional info
        for warning_rule in eligibility_details.get("warnings", []):
            sub_type = warning_rule.get("sub_type")
            if sub_type:
                if sub_type not in subtype_eligibility_info:
                    subtype_eligibility_info[sub_type] = {
                        "eligible": True,
                        "failed_rules": [],
                        "warning_rules": [],
                    }

                subtype_eligibility_info[sub_type]["warning_rules"].append(
                    {
                        "rule_name": warning_rule.get("rule_name"),
                        "message": warning_rule.get("message"),
                        "tag": warning_rule.get("tag"),
                    }
                )

        # For subtypes not mentioned in rules, assume they're eligible (no rules = no restrictions)
        for subtype in all_subtypes:
            if subtype not in subtype_eligibility_info:
                subtype_eligibility_info[subtype] = {
                    "eligible": True,
                    "failed_rules": [],
                    "warning_rules": [],
                }

        # Build eligible subtypes with proper names
        eligible_subtypes_with_names = []
        for subtype in all_subtypes:
            if subtype_eligibility_info.get(subtype, {}).get("eligible", True):
                eligible_subtypes_with_names.append(
                    {
                        "value": subtype,
                        "label": translations.get("zh", {}).get(subtype, subtype),
                        "label_en": translations.get("en", {}).get(subtype, subtype),
                        "is_default": subtype == "general",
                    }
                )

        # If no specific subtypes are eligible but we have a general one, add it
        if not eligible_subtypes_with_names and "general" not in all_subtypes:
            eligible_subtypes_with_names.append(
                {
                    "value": None,
                    "label": "通用",
                    "label_en": "General",
                    "is_default": True,
                }
            )

        return eligible_subtypes_with_names, subtype_eligibility_info

    async def _get_subtype_translations(self, scholarship_type_id: int) -> Dict[str, Dict[str, str]]:
        """Get subtype name translations from database"""
        from sqlalchemy import select

        from app.models.scholarship import ScholarshipSubTypeConfig

        translations = {"zh": {}, "en": {}}

        # Query active subtype configurations
        stmt = select(ScholarshipSubTypeConfig).filter(
            ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id,
            ScholarshipSubTypeConfig.is_active.is_(True),
        )
        result = await self.db.execute(stmt)
        configs = result.scalars().all()

        # Build translations from database
        for config in configs:
            translations["zh"][config.sub_type_code] = config.name
            translations["en"][config.sub_type_code] = config.name_en or config.name

        # Add default for general subtype if not configured
        if "general" not in translations["zh"]:
            translations["zh"]["general"] = "一般獎學金"
            translations["en"]["general"] = "General Scholarship"

        return translations


class ScholarshipApplicationService:
    """Comprehensive service for managing scholarship applications and workflows"""

    def __init__(self, db: Session):
        self.db = db

    # Application creation has been moved to ApplicationService with external API integration
    # def create_application(
    #     self,
    #     user_id: int,
    #     # student_id: int,  # Removed - student data now from external API
    #     scholarship_type_id: int,
    #     scholarship_type_code: str,
    #     semester: str,
    #     academic_year: str,
    #     application_data: Dict[str, Any],
    #     is_renewal: bool = False,
    #     previous_application_id: Optional[int] = None
    # ) -> Tuple[Application, str]:
    #     """Create a new scholarship application using existing schema"""
    #
    #     # Validate eligibility
    #     stmt = select(ScholarshipType).where(
    #         ScholarshipType.id == scholarship_type_id
    #     )
    #     result = await self.db.execute(stmt)
    #     scholarship_type = result.scalar_one_or_none()
    #
    #     if not scholarship_type:
    #         raise ValueError("Invalid scholarship type")
    #
    #     can_apply, error_msg = scholarship_type.can_student_apply(student_id, semester)
    #     if not can_apply:
    #         raise ValueError(error_msg)
    #
    #     # Check for existing application in the same semester
    #     stmt = select(Application).where(
    #         and_(
    #             Application.student_id == student_id,
    #             Application.scholarship_type_id == scholarship_type_id,
    #             Application.semester == semester,
    #             Application.status.notin_([ApplicationStatus.withdrawn.value, ApplicationStatus.rejected.value])
    #         )
    #     )
    #     result = await self.db.execute(stmt)
    #     existing_app = result.scalar_one_or_none()
    #
    #     if existing_app:
    #         raise ValueError("Student already has an active application for this scholarship in this semester")
    #
    #     # Generate application number using existing format
    #     app_number = self._generate_application_id(academic_year)
    #
    #     # Calculate priority score
    #     priority_score = self._calculate_initial_priority(is_renewal, student_id)
    #
    #     # Extract main and sub types from scholarship code
    #     main_type = self._extract_main_type(scholarship_type_code)
    #     sub_type = self._extract_sub_type(scholarship_type_code)
    #
    #     # Create application using existing schema
    #     application = Application(
    #         app_id=app_number,
    #         user_id=user_id,
    #         student_id=student_id,
    #         scholarship_type_id=scholarship_type_id,
    #         scholarship_type=scholarship_type_code,
    #         scholarship_name=scholarship_type.name,
    #         main_scholarship_type=main_type,
    #         sub_scholarship_type=sub_type,
    #         semester=semester,
    #         academic_year=academic_year,
    #         is_renewal=is_renewal,
    #         previous_application_id=previous_application_id,
    #         status=ApplicationStatus.draft.value,
    #         priority_score=priority_score,
    #         amount=application_data.get('requested_amount'),
    #         form_data=application_data
    #     )
    #
    #     self.db.add(application)
    #     await self.db.commit()
    #     await self.db.refresh(application)
    #
    #     return application, "Application created successfully"

    async def submit_application(self, application_id: int) -> Tuple[bool, str]:
        """Submit application for review"""
        stmt = select(Application).where(Application.id == application_id)
        result = await self.db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            return False, "Application not found"

        if application.status != ApplicationStatus.draft.value:
            return False, "Application is not in draft status"

        # Validate required documents
        validation_result = self._validate_application_documents(application)
        if not validation_result[0]:
            return False, validation_result[1]

        # Update application status
        application.status = ApplicationStatus.submitted.value
        application.submitted_at = datetime.now(timezone.utc)

        # Set review deadline (30 days from submission)
        application.review_deadline = datetime.now(timezone.utc) + timedelta(days=30)

        # Create initial review record
        self._create_initial_review(application)

        # If requires professor recommendation, create professor review
        if application.scholarship_type.requires_professor_recommendation:
            self._create_professor_review_request(application)

        await self.db.commit()
        return True, "Application submitted successfully"

    async def get_applications_by_priority(
        self,
        scholarship_type_id: Optional[int] = None,
        semester: Optional[str] = None,
        status: Optional[ApplicationStatus] = None,
        limit: int = 100,
    ) -> List["Application"]:
        """Get applications ordered by priority"""
        stmt = select(Application)

        if scholarship_type_id:
            stmt = stmt.where(Application.scholarship_type_id == scholarship_type_id)

        if semester:
            stmt = stmt.where(Application.semester == semester)

        if status:
            stmt = stmt.where(Application.status == status)

        # Note: priority_score removed - order by submission time and renewal status only
        # Order by renewal status (renewals first), then by submission time (earlier first)
        stmt = stmt.order_by(desc(Application.is_renewal), asc(Application.submitted_at)).limit(limit)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def process_renewal_applications_first(self, semester: str) -> Dict[str, int]:
        """Process renewal applications with higher priority"""

        # Get all submitted renewal applications for the semester
        # Note: priority_score removed - order by submission time
        stmt = (
            select(Application)
            .where(
                and_(
                    Application.semester == semester,
                    Application.is_renewal.is_(True),
                    Application.status == ApplicationStatus.submitted,
                )
            )
            .order_by(asc(Application.submitted_at))
        )
        result = await self.db.execute(stmt)
        renewal_apps = result.scalars().all()

        processed_count = 0
        approved_count = 0

        for app in renewal_apps:
            # Auto-approve if meets renewal criteria
            if self._meets_renewal_criteria(app):
                app.status = ApplicationStatus.approved
                app.decision_date = datetime.now(timezone.utc)
                approved_count += 1
            else:
                # Move to regular review process
                app.status = ApplicationStatus.under_review

            processed_count += 1

        await self.db.commit()

        return {"processed": processed_count, "auto_approved": approved_count}

    async def _generate_application_id(self, academic_year: str) -> str:
        """Generate unique application ID using existing format"""

        # Get count of applications for this year
        stmt = select(sa_func.count(Application.id)).where(Application.academic_year == academic_year)
        result = await self.db.execute(stmt)
        count = result.scalar()

        # Format: APP-{year}-{count+1:06d}
        return f"APP-{academic_year}-{count+1:06d}"

    def _extract_main_type(self, scholarship_code: str) -> str:
        """Extract main scholarship type from code"""
        code_upper = scholarship_code.upper()
        if "UNDERGRADUATE_FRESHMAN" in code_upper:
            return ScholarshipMainType.undergraduate_freshman.value
        elif "DIRECT_PHD" in code_upper:
            return ScholarshipMainType.direct_phd.value
        elif "PHD" in code_upper:
            return ScholarshipMainType.phd.value
        return ScholarshipMainType.phd.value  # Default

    def _extract_sub_type(self, scholarship_code: str) -> str:
        """Extract sub scholarship type from code"""
        code_upper = scholarship_code.upper()
        if "NSTC" in code_upper:
            return ScholarshipSubType.nstc.value
        elif "MOE_1W" in code_upper:
            return ScholarshipSubType.moe_1w.value
        elif "MOE_2W" in code_upper:
            return ScholarshipSubType.moe_2w.value
        return ScholarshipSubType.general.value  # Default

    def _calculate_initial_priority(self, is_renewal: bool, student_id: int) -> int:
        """Calculate initial priority score for application"""
        score = 0

        # Renewal applications get higher priority
        if is_renewal:
            score += 100

        # Add other priority factors here
        # - Academic performance
        # - Previous scholarship history
        # - Financial need assessment

        return score

    def _validate_application_documents(self, application: "Application") -> Tuple[bool, str]:
        """Validate that all required documents are uploaded"""

        required_docs = application.scholarship_type.required_documents or []
        uploaded_docs = [f.document_type for f in application.files if f.document_type]

        missing_docs = []
        for doc_type in required_docs:
            if doc_type not in uploaded_docs:
                missing_docs.append(doc_type)

        if missing_docs:
            return False, f"Missing required documents: {', '.join(missing_docs)}"

        return True, "All required documents uploaded"

    def _create_initial_review(self, application: "Application") -> "ApplicationReview":
        """Create initial review record for submitted application"""

        review = ApplicationReview(
            application_id=application.id,
            reviewer_id=1,  # System or default reviewer
            review_stage="initial_review",
            status=ReviewStatus.PENDING,
            due_date=application.review_deadline,
        )

        self.db.add(review)
        return review

    def _create_professor_review_request(self, application: "Application") -> "ProfessorReview":
        """Create professor review request"""

        # In a real implementation, this would determine the appropriate professor
        professor_id = 1  # Placeholder

        professor_review = ProfessorReview(
            application_id=application.id,
            professor_id=professor_id,
            review_type="recommendation",
            is_required=True,
            due_date=datetime.now(timezone.utc) + timedelta(days=14),
            status=ReviewStatus.PENDING,
        )

        self.db.add(professor_review)

        # Create standard review items
        review_items = [
            ("academic_performance", "Academic performance and achievements", 5),
            ("research_potential", "Research potential and capability", 5),
            ("overall_recommendation", "Overall recommendation", 5),
        ]

        for item_name, description, max_rating in review_items:
            review_item = ProfessorReviewItem(
                professor_review_id=professor_review.id,
                item_name=item_name,
                item_description=description,
                max_rating=max_rating,
                weight=1.0,
            )
            self.db.add(review_item)

        return professor_review

    def _meets_renewal_criteria(self, application: "Application") -> bool:
        """Check if renewal application meets auto-approval criteria"""

        # Implement renewal criteria logic
        # - Maintained minimum GPA
        # - No academic violations
        # - Satisfactory progress
        # - Complete required documents

        # For now, return True as placeholder
        return True


class ScholarshipQuotaService:
    """Service for managing scholarship quotas - simplified for existing schema"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_quota_status_by_type(
        self, main_scholarship_type: str, sub_scholarship_type: str, semester: str
    ) -> Dict[str, Any]:
        """Get quota status for a scholarship type combination"""

        # Count approved applications by type
        stmt = select(sa_func.count(Application.id)).where(
            and_(
                Application.main_scholarship_type == main_scholarship_type,
                Application.sub_scholarship_type == sub_scholarship_type,
                Application.semester == semester,
                Application.status == ApplicationStatus.approved.value,
            )
        )
        result = await self.db.execute(stmt)
        approved_count = result.scalar()

        # Get pending applications
        stmt = select(sa_func.count(Application.id)).where(
            and_(
                Application.main_scholarship_type == main_scholarship_type,
                Application.sub_scholarship_type == sub_scholarship_type,
                Application.semester == semester,
                Application.status.in_(
                    [
                        ApplicationStatus.submitted.value,
                        ApplicationStatus.under_review.value,
                    ]
                ),
            )
        )
        result = await self.db.execute(stmt)
        pending_count = result.scalar()

        # For now, use default quotas (these would come from configuration)
        default_quotas = {
            (ScholarshipMainType.phd.value, ScholarshipSubType.nstc.value): 50,
            (ScholarshipMainType.phd.value, ScholarshipSubType.general.value): 30,
            (ScholarshipMainType.direct_phd.value, ScholarshipSubType.nstc.value): 40,
            (
                ScholarshipMainType.undergraduate_freshman.value,
                ScholarshipSubType.general.value,
            ): 100,
        }

        total_quota = default_quotas.get((main_scholarship_type, sub_scholarship_type), 20)

        return {
            "main_type": main_scholarship_type,
            "sub_type": sub_scholarship_type,
            "semester": semester,
            "total_quota": total_quota,
            "total_used": approved_count,
            "total_available": total_quota - approved_count,
            "pending": pending_count,
            "usage_percent": (approved_count / total_quota * 100) if total_quota > 0 else 0,
        }

    async def process_applications_by_priority(
        self, main_scholarship_type: str, sub_scholarship_type: str, semester: str
    ) -> Dict[str, int]:
        """Process applications by priority within quota limits"""

        quota_status = self.get_quota_status_by_type(main_scholarship_type, sub_scholarship_type, semester)

        if quota_status["total_available"] <= 0:
            return {"processed": 0, "approved": 0, "message": "No remaining quota"}

        # Get applications ordered by priority (renewal first, then by submission time)
        # Note: priority_score removed from ordering
        stmt = (
            select(Application)
            .where(
                and_(
                    Application.main_scholarship_type == main_scholarship_type,
                    Application.sub_scholarship_type == sub_scholarship_type,
                    Application.semester == semester,
                    Application.status.in_(
                        [
                            ApplicationStatus.submitted.value,
                            ApplicationStatus.under_review.value,
                        ]
                    ),
                )
            )
            .order_by(
                desc(Application.is_renewal),  # Renewals first
                asc(Application.submitted_at),  # Then by submission time
            )
        )
        result = await self.db.execute(stmt)
        applications = result.scalars().all()

        processed_count = 0
        approved_count = 0
        remaining_quota = quota_status["total_available"]

        for app in applications:
            processed_count += 1

            if remaining_quota > 0:
                # Approve within quota
                app.status = ApplicationStatus.approved.value
                app.decision_date = datetime.now(timezone.utc)
                approved_count += 1
                remaining_quota -= 1
            else:
                # Reject due to quota limit
                # Note: rejection_reason moved to ApplicationReview model
                app.status = ApplicationStatus.rejected.value
                app.decision_date = datetime.now(timezone.utc)

                # Create ApplicationReview record to store rejection reason
                from app.models.application import ApplicationReview, ReviewStatus

                review = ApplicationReview(
                    application_id=app.id,
                    reviewer_id=1,  # System reviewer
                    review_stage="quota_processing",
                    review_status=ReviewStatus.REJECTED.value,
                    recommendation="reject",
                    decision_reason="Quota limit reached",
                    reviewed_at=datetime.now(timezone.utc),
                )
                self.db.add(review)

        await self.db.commit()

        return {
            "processed": processed_count,
            "approved": approved_count,
            "rejected": processed_count - approved_count,
            "remaining_quota": remaining_quota,
        }
