"""
Eligibility Service
Handles student eligibility checking for scholarship configurations
"""

from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, select
import logging

logger = logging.getLogger(__name__)

from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule
from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.core.config import DEV_SCHOLARSHIP_SETTINGS, settings


class EligibilityService:
    """Service for checking student eligibility for scholarships"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _is_dev_mode(self) -> bool:
        """Check if running in development mode"""
        return settings.debug or settings.environment == "development"
    
    def _should_bypass_whitelist(self) -> bool:
        """Check if should bypass whitelist in dev mode"""
        return (self._is_dev_mode() and 
                DEV_SCHOLARSHIP_SETTINGS.get("BYPASS_WHITELIST", False))
    
    def _should_bypass_application_period(self) -> bool:
        """Check if should bypass application period in dev mode"""
        return (self._is_dev_mode() and 
                DEV_SCHOLARSHIP_SETTINGS.get("ALWAYS_OPEN_APPLICATION", False))
    
    async def check_student_eligibility(
        self, 
        student_data: Dict[str, Any], 
        config: ScholarshipConfiguration,
        user_id: Optional[int] = None
    ) -> Tuple[bool, List[str]]:
        """Check if student is eligible for a scholarship configuration"""
        
        reasons = []
        
        # Check if configuration is active and effective
        if not config.is_active:
            reasons.append("獎學金配置未啟用")
            return False, reasons
        
        if not config.is_effective:
            reasons.append("不在獎學金有效期間內")
            return False, reasons
        
        # Check for existing application if user_id is provided
        if user_id:
            existing_app_eligible = await self._check_existing_applications(
                user_id, config, student_data
            )
            if not existing_app_eligible:
                reasons.append("已有相同學年學期的申請記錄")
                return False, reasons
        
        # Check application period (unless bypassed in dev mode)
        if not self._should_bypass_application_period():
            now = datetime.now(timezone.utc)
            
            # Check regular application period
            if config.application_start_date and config.application_end_date:
                if not (config.application_start_date <= now <= config.application_end_date):
                    # Check renewal application period if applicable
                    if config.renewal_application_start_date and config.renewal_application_end_date:
                        if not (config.renewal_application_start_date <= now <= config.renewal_application_end_date):
                            reasons.append("不在申請期間內")
                    else:
                        reasons.append("不在申請期間內")
        
        # Check whitelist if enabled (unless bypassed in dev mode)
        if config.scholarship_type.whitelist_enabled and not self._should_bypass_whitelist():
            student_id = student_data.get('std_stdcode', '')
            whitelist_ids = config.whitelist_student_ids or {}
            
            # Check if student is in whitelist
            if isinstance(whitelist_ids, dict):
                if student_id not in whitelist_ids:
                    reasons.append("未在白名單中")
            elif isinstance(whitelist_ids, list):
                if student_id not in whitelist_ids:
                    reasons.append("未在白名單中")
        
        # Category eligibility is now handled by scholarship rules
        # No hardcoded category checking needed
        
        # All eligibility requirements (GPA, year/grade, department, etc.) are now handled by scholarship rules
        # Check scholarship rules - this covers all types of requirements
        rules_passed, rule_failures = await self._check_scholarship_rules(
            student_data, config
        )
        if not rules_passed:
            reasons.extend(rule_failures)
        
        # All checks passed if no reasons were added
        is_eligible = len(reasons) == 0
        
        return is_eligible, reasons
    
    async def _check_scholarship_rules(
        self, 
        student_data: Dict[str, Any], 
        config: ScholarshipConfiguration
    ) -> Tuple[bool, List[str]]:
        """Check student against scholarship rules"""
        
        failure_reasons = []
        
        # Get applicable rules for this scholarship configuration
        stmt = select(ScholarshipRule).filter(
            ScholarshipRule.scholarship_type_id == config.scholarship_type_id,
            ScholarshipRule.is_active == True
        )
        
        # Filter by academic year and semester if specified
        if config.academic_year:
            stmt = stmt.filter(
                or_(
                    ScholarshipRule.academic_year.is_(None),  # Generic rules
                    ScholarshipRule.academic_year == config.academic_year
                )
            )
        
        if config.semester:
            stmt = stmt.filter(
                or_(
                    ScholarshipRule.semester.is_(None),  # Generic rules
                    ScholarshipRule.semester == config.semester
                )
            )
        
        result = await self.db.execute(stmt)
        rules = result.scalars().all()
        
        for rule in rules:
            # Skip inactive rules
            if not rule.is_active:
                continue
            
            # Check if rule applies to initial or renewal applications
            # For eligibility checking, we assume initial application
            if not rule.is_initial_enabled:
                continue
            
            # Check rule condition
            rule_passed = self._evaluate_rule(student_data, rule)
            
            if not rule_passed:
                if rule.is_hard_rule:
                    # Hard rules are mandatory
                    message = rule.message or f"不符合規則: {rule.rule_name}"
                    failure_reasons.append(message)
                elif rule.is_warning:
                    # Warning rules don't prevent eligibility but could be logged
                    logger.warning(f"Warning rule failed for student: {rule.rule_name}")
        
        return len(failure_reasons) == 0, failure_reasons
    
    def _evaluate_rule(self, student_data: Dict[str, Any], rule: ScholarshipRule) -> bool:
        """Evaluate a single rule against student data"""
        
        # Get the value from student data
        field_value = self._get_nested_field_value(student_data, rule.condition_field)
        expected_value = rule.expected_value
        
        # Handle different operators
        try:
            if rule.operator == ">=":
                return float(field_value) >= float(expected_value)
            elif rule.operator == "<=":
                return float(field_value) <= float(expected_value)
            elif rule.operator == ">":
                return float(field_value) > float(expected_value)
            elif rule.operator == "<":
                return float(field_value) < float(expected_value)
            elif rule.operator == "==":
                return str(field_value) == str(expected_value)
            elif rule.operator == "!=":
                return str(field_value) != str(expected_value)
            elif rule.operator == "in":
                # Expected value should be comma-separated list
                allowed_values = [v.strip() for v in expected_value.split(',')]
                return str(field_value) in allowed_values
            elif rule.operator == "not_in":
                # Expected value should be comma-separated list
                forbidden_values = [v.strip() for v in expected_value.split(',')]
                return str(field_value) not in forbidden_values
            elif rule.operator == "contains":
                return expected_value in str(field_value)
            elif rule.operator == "not_contains":
                return expected_value not in str(field_value)
            else:
                logger.warning(f"Unknown operator: {rule.operator}")
                return False
                
        except (ValueError, TypeError) as e:
            logger.error(f"Error evaluating rule {rule.rule_name}: {e}")
            return False
    
    def _get_nested_field_value(self, data: Dict[str, Any], field_path: str) -> Any:
        """Get value from nested dictionary using dot notation"""
        
        if '.' not in field_path:
            return data.get(field_path, '')
        
        parts = field_path.split('.')
        current_data = data
        
        for part in parts:
            if isinstance(current_data, dict):
                current_data = current_data.get(part, '')
            else:
                return ''
        
        return current_data
    
    async def _check_existing_applications(
        self, 
        user_id: int, 
        config: ScholarshipConfiguration, 
        student_data: Dict[str, Any]
    ) -> bool:
        """Check if user already has an application for this scholarship configuration"""
        
        # Get active applications (not cancelled, withdrawn, or rejected)
        active_statuses = [
            ApplicationStatus.DRAFT.value,
            ApplicationStatus.SUBMITTED.value,
            ApplicationStatus.UNDER_REVIEW.value,
            ApplicationStatus.PENDING_RECOMMENDATION.value,
            ApplicationStatus.RECOMMENDED.value,
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.RENEWAL_PENDING.value,
            ApplicationStatus.RENEWAL_REVIEWED.value,
            ApplicationStatus.PROFESSOR_REVIEW.value,
            ApplicationStatus.RETURNED.value  # Returned applications can still be edited
        ]
        
        # Convert semester enum to string value to avoid type mismatch
        # Database uses uppercase enum values (FIRST, SECOND) while Python enum uses lowercase (first, second)
        semester_value = None if config.semester is None else config.semester.value.upper()
        
        stmt = select(Application).filter(
            and_(
                Application.user_id == user_id,
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.academic_year == config.academic_year,
                Application.semester == semester_value,
                Application.status.in_(active_statuses)
            )
        )
        
        result = await self.db.execute(stmt)
        existing_application = result.scalar_one_or_none()
        
        # Return False if existing application found (not eligible)
        # Return True if no existing application (eligible)
        return existing_application is None