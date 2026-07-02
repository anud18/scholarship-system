"""
Comprehensive scholarship service for scholarship management
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DEV_SCHOLARSHIP_SETTINGS, settings

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
        except Exception:
            logger.exception(f"Error converting GPA '{gpa}' to Decimal")
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
                            logger.warning("Student term API unavailable, continuing with basic data", exc_info=True)
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

            if is_eligible:
                # Build scholarship response with configuration data
                scholarship_type = config.scholarship_type

                # Whether the student already has a submitted-and-beyond
                # application for this configuration → hides it from the apply
                # flow (see spec). Computed only for eligible configs.
                already_submitted = False
                if user_id:
                    already_submitted = await eligibility_service.has_blocking_application(user_id, config)

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
                    "application_cycle": (
                        scholarship_type.application_cycle.value if scholarship_type.application_cycle else "semester"
                    ),
                    "sub_type_list": eligible_subtypes,  # Only eligible subtypes
                    "all_sub_type_list": scholarship_type.sub_type_list or [],  # All subtypes for reference
                    "subtype_eligibility": subtype_eligibility_info,  # Detailed eligibility per subtype
                    "sub_type_selection_mode": (
                        scholarship_type.sub_type_selection_mode.value
                        if scholarship_type.sub_type_selection_mode
                        else "single"
                    ),
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
                        # Hide already-submitted scholarships from the apply flow
                        "already_submitted": already_submitted,
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
