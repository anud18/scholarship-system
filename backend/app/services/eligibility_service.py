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
        """Check if student is eligible for a scholarship configuration
        
        Note: This method no longer checks for existing applications as we want to show
        all scholarships the student meets the requirements for, regardless of application status.
        Application status is now checked separately.
        """
        
        reasons = []
        
        # Check if configuration is active and effective
        if not config.is_active:
            reasons.append("獎學金配置未啟用")
            return False, reasons
        
        if not config.is_effective:
            reasons.append("不在獎學金有效期間內")
            return False, reasons
        
        # Existing application check is moved to separate method
        # We want to show scholarships regardless of application status
        
        # Check application period (unless bypassed in dev mode)
        if not self._should_bypass_application_period():
            now = datetime.now(timezone.utc)
            
            # Check regular application period
            if config.application_start_date and config.application_end_date:
                # Handle timezone-aware and naive datetime comparison
                app_start = config.application_start_date
                if app_start.tzinfo is None:
                    app_start = app_start.replace(tzinfo=timezone.utc)
                    
                app_end = config.application_end_date
                if app_end.tzinfo is None:
                    app_end = app_end.replace(tzinfo=timezone.utc)
                
                if not (app_start <= now <= app_end):
                    # Check renewal application period if applicable
                    if config.renewal_application_start_date and config.renewal_application_end_date:
                        renewal_start = config.renewal_application_start_date
                        if renewal_start.tzinfo is None:
                            renewal_start = renewal_start.replace(tzinfo=timezone.utc)
                            
                        renewal_end = config.renewal_application_end_date
                        if renewal_end.tzinfo is None:
                            renewal_end = renewal_end.replace(tzinfo=timezone.utc)
                            
                        if not (renewal_start <= now <= renewal_end):
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
    
    async def get_detailed_eligibility_check(
        self, 
        student_data: Dict[str, Any], 
        config: ScholarshipConfiguration,
        user_id: Optional[int] = None
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Get detailed eligibility check with rule breakdown
        
        Returns:
            (is_eligible, reasons, details) where details contains:
            - passed: list of passed rules with their tags
            - warnings: list of warning rules
            - errors: list of failed hard rules
        
        Note: This method no longer checks for existing applications as we want to show
        all scholarships the student meets the requirements for, regardless of application status.
        Application status is now checked separately.
        """
        
        reasons = []
        details = {
            'passed': [],
            'warnings': [],
            'errors': []
        }
        
        # Check if configuration is active and effective
        if not config.is_active:
            reasons.append("獎學金配置未啟用")
            return False, reasons, details
        
        if not config.is_effective:
            reasons.append("不在獎學金有效期間內")
            return False, reasons, details
        
        # Existing application check is moved to separate method
        # We want to show scholarships regardless of application status
        
        # Check application period (unless bypassed in dev mode)
        if not self._should_bypass_application_period():
            now = datetime.now(timezone.utc)
            
            # Check regular application period
            if config.application_start_date and config.application_end_date:
                # Handle timezone-aware and naive datetime comparison
                app_start = config.application_start_date
                if app_start.tzinfo is None:
                    app_start = app_start.replace(tzinfo=timezone.utc)
                    
                app_end = config.application_end_date
                if app_end.tzinfo is None:
                    app_end = app_end.replace(tzinfo=timezone.utc)
                
                if not (app_start <= now <= app_end):
                    # Check renewal application period if applicable
                    if config.renewal_application_start_date and config.renewal_application_end_date:
                        renewal_start = config.renewal_application_start_date
                        if renewal_start.tzinfo is None:
                            renewal_start = renewal_start.replace(tzinfo=timezone.utc)
                            
                        renewal_end = config.renewal_application_end_date
                        if renewal_end.tzinfo is None:
                            renewal_end = renewal_end.replace(tzinfo=timezone.utc)
                            
                        if not (renewal_start <= now <= renewal_end):
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
        
        # Check scholarship rules with detailed breakdown
        rules_passed, rule_failures, rule_details = await self._check_scholarship_rules_detailed(
            student_data, config
        )
        if not rules_passed:
            reasons.extend(rule_failures)
        
        # Add rule details to response
        details.update(rule_details)
        
        # All checks passed if no reasons were added
        is_eligible = len(reasons) == 0
        
        return is_eligible, reasons, details
    
    async def _check_scholarship_rules(
        self, 
        student_data: Dict[str, Any], 
        config: ScholarshipConfiguration
    ) -> Tuple[bool, List[str]]:
        """Check student against scholarship rules"""
        
        failure_reasons = []
        
        # Get applicable rules for this scholarship configuration (exclude template rules)
        stmt = select(ScholarshipRule).filter(
            ScholarshipRule.scholarship_type_id == config.scholarship_type_id,
            ScholarshipRule.is_active == True,
            ScholarshipRule.is_template == False  # Exclude template rules from filtering
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
        
        # Track subtype eligibility - if any subtype has failed critical rules, exclude scholarship
        subtype_eligibility = {}  # subtype -> bool (True if eligible for this subtype)
        
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
            
            # Handle subtype rule tracking
            if rule.sub_type:
                if rule.sub_type not in subtype_eligibility:
                    subtype_eligibility[rule.sub_type] = True  # Start optimistic
                
                # For subtype rules, both hard rules and critical soft rules should prevent eligibility
                # Warning rules don't count as critical rules
                if not rule.is_warning:
                    if not rule_passed:
                        subtype_eligibility[rule.sub_type] = False
            
            if not rule_passed:
                if rule.is_hard_rule:
                    # Hard rules are mandatory - prevent showing scholarship
                    message = rule.message or f"不符合規則: {rule.rule_name}"
                    failure_reasons.append(message)
                elif rule.is_warning:
                    # Warning rules don't prevent eligibility but could be logged
                    logger.warning(f"Warning rule failed for student: {rule.rule_name}")
                else:
                    # Soft rules don't prevent eligibility - allow display but prevent application
                    pass  # Don't add to failure_reasons, allow scholarship to be shown
        
        # Check if scholarship has subtypes and if student is eligible for at least one
        # For subtypes: even soft rule failures should prevent subtype eligibility
        # Only if student is eligible for at least one subtype, show the scholarship
        has_subtypes = len(subtype_eligibility) > 0
        if has_subtypes:
            eligible_for_any_subtype = any(subtype_eligibility.values())
            if not eligible_for_any_subtype:
                # Student is not eligible for any subtype - prevent showing this scholarship
                failure_reasons.append("不符合任何子類型的申請資格")
        
        return len(failure_reasons) == 0, failure_reasons
    
    async def _check_scholarship_rules_detailed(
        self, 
        student_data: Dict[str, Any], 
        config: ScholarshipConfiguration
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """Check student against scholarship rules with detailed breakdown"""
        
        failure_reasons = []
        details = {
            'passed': [],
            'warnings': [],
            'errors': []
        }
        
        # Get applicable rules for this scholarship configuration (exclude template rules)
        stmt = select(ScholarshipRule).filter(
            ScholarshipRule.scholarship_type_id == config.scholarship_type_id,
            ScholarshipRule.is_active == True,
            ScholarshipRule.is_template == False  # Exclude template rules from filtering
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
        
        # Track subtype eligibility - if any subtype has failed critical rules, exclude scholarship
        subtype_eligibility = {}  # subtype -> bool (True if eligible for this subtype)
        subtype_critical_rules = {}  # subtype -> list of critical rules
        
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
            
            # Create rule detail object
            rule_detail = {
                'rule_id': rule.id,
                'rule_name': rule.rule_name,
                'rule_type': rule.rule_type,  # Add missing rule_type field
                'tag': rule.tag or 'general',
                'sub_type': getattr(rule, 'sub_type', None),
                'message': rule.message,
                'message_en': rule.message_en
            }
            
            # Handle subtype rule tracking
            if rule.sub_type:
                if rule.sub_type not in subtype_eligibility:
                    subtype_eligibility[rule.sub_type] = True  # Start optimistic
                    subtype_critical_rules[rule.sub_type] = []
                
                # For subtype rules, both hard rules and critical soft rules should prevent eligibility
                # Warning rules don't count as critical rules
                if not rule.is_warning:
                    if not rule_passed:
                        subtype_eligibility[rule.sub_type] = False
                        subtype_critical_rules[rule.sub_type].append(rule.rule_name)
            
            if rule_passed:
                # Rule passed - add to passed list
                details['passed'].append(rule_detail)
            else:
                if rule.is_hard_rule:
                    # Hard rules are mandatory - add to errors
                    message = rule.message or f"不符合規則: {rule.rule_name}"
                    failure_reasons.append(message)
                    details['errors'].append(rule_detail)
                elif rule.is_warning:
                    # Warning rules don't prevent eligibility but are shown as warnings
                    details['warnings'].append(rule_detail)
                    logger.warning(f"Warning rule failed for student: {rule.rule_name}")
                else:
                    # Soft rules don't prevent eligibility - allow display but prevent application
                    details['errors'].append(rule_detail)
                    # Don't add to failure_reasons - allow scholarship to be shown
        
        # Check if scholarship has subtypes and if student is eligible for at least one
        # For subtypes: even soft rule failures should prevent subtype eligibility
        # Only if student is eligible for at least one subtype, show the scholarship
        has_subtypes = len(subtype_eligibility) > 0
        if has_subtypes:
            eligible_for_any_subtype = any(subtype_eligibility.values())
            if not eligible_for_any_subtype:
                # Student is not eligible for any subtype - prevent showing this scholarship
                failure_reasons.append("不符合任何子類型的申請資格")
        
        # Post-process: Group subtype rule errors for unified presentation
        processed_details = self._process_subtype_rule_errors(details)
        
        return len(failure_reasons) == 0, failure_reasons, processed_details
    
    async def determine_required_student_api_type(
        self, 
        config: ScholarshipConfiguration
    ) -> str:
        """Determine which student API type is required based on scholarship rules
        
        Returns:
            "student" for basic API or "student_term" for term-specific API
        """
        
        # Get applicable rules for this scholarship configuration (exclude template rules)
        stmt = select(ScholarshipRule).filter(
            ScholarshipRule.scholarship_type_id == config.scholarship_type_id,
            ScholarshipRule.is_active == True,
            ScholarshipRule.is_template == False  # Exclude template rules from filtering
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
        
        # Check if any active rule requires student_term data
        for rule in rules:
            if not rule.is_active:
                continue
            
            # Skip rules that don't apply to initial applications
            if not rule.is_initial_enabled:
                continue
                
            # If any rule has rule_type == "student_term", we need the term-specific API
            if rule.rule_type == "student_term":
                return "student_term"
        
        # Default to basic student API
        return "student"
    
    async def get_application_status(
        self, 
        user_id: int, 
        config: ScholarshipConfiguration
    ) -> Dict[str, Any]:
        """Get application status for a specific scholarship configuration
        
        Returns:
            Dictionary with application status info:
            - has_application: bool - whether user has any application for this config
            - application_status: str - current application status (draft, submitted, etc.)
            - can_apply: bool - whether user can submit new/edit existing application
            - status_display: str - display text for frontend
        """
        
        # Check for any existing application
        active_statuses = [
            ApplicationStatus.DRAFT.value,
            ApplicationStatus.SUBMITTED.value,
            ApplicationStatus.UNDER_REVIEW.value,
            ApplicationStatus.PENDING_RECOMMENDATION.value,
            ApplicationStatus.RECOMMENDED.value,
            ApplicationStatus.APPROVED.value,
            ApplicationStatus.REJECTED.value,
            ApplicationStatus.RETURNED.value,
            ApplicationStatus.CANCELLED.value,
            ApplicationStatus.RENEWAL_PENDING.value,
            ApplicationStatus.RENEWAL_REVIEWED.value,
            ApplicationStatus.PROFESSOR_REVIEW.value,
            ApplicationStatus.WITHDRAWN.value
        ]
        
        # Handle semester comparison - use enum name for PostgreSQL compatibility
        # PostgreSQL stores enum as the name (FIRST, SECOND) not the value (first, second)
        if config.semester:
            # Use enum name for comparison
            semester_filter = Application.semester == config.semester.name
        else:
            # If no semester in config, check for NULL
            semester_filter = Application.semester.is_(None)
        
        stmt = select(Application).filter(
            and_(
                Application.user_id == user_id,
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.academic_year == config.academic_year,
                semester_filter,
                Application.status.in_(active_statuses)
            )
        )
        
        result = await self.db.execute(stmt)
        existing_application = result.scalar_one_or_none()
        
        if not existing_application:
            return {
                'has_application': False,
                'application_status': None,
                'can_apply': True,
                'status_display': '可申請',
                'application_id': None
            }
        
        status = existing_application.status
        
        # Determine if user can apply/edit
        can_apply = status in [
            ApplicationStatus.DRAFT.value,
            ApplicationStatus.RETURNED.value
        ]
        
        # Determine display status
        status_display_mapping = {
            ApplicationStatus.DRAFT.value: '草稿',
            ApplicationStatus.SUBMITTED.value: '已申請',
            ApplicationStatus.UNDER_REVIEW.value: '審核中',
            ApplicationStatus.PENDING_RECOMMENDATION.value: '待推薦',
            ApplicationStatus.RECOMMENDED.value: '已推薦',
            ApplicationStatus.APPROVED.value: '已核准',
            ApplicationStatus.REJECTED.value: '已拒絕',
            ApplicationStatus.RETURNED.value: '已退回',
            ApplicationStatus.CANCELLED.value: '已取消',
            ApplicationStatus.RENEWAL_PENDING.value: '續領待審',
            ApplicationStatus.RENEWAL_REVIEWED.value: '續領已審',
            ApplicationStatus.PROFESSOR_REVIEW.value: '教授審核中',
            ApplicationStatus.WITHDRAWN.value: '已撤回'
        }
        
        status_display = status_display_mapping.get(status, '未知狀態')
        
        return {
            'has_application': True,
            'application_status': status,
            'can_apply': can_apply,
            'status_display': status_display,
            'application_id': existing_application.id
        }
    
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
    
    def _process_subtype_rule_errors(self, details: Dict[str, Any]) -> Dict[str, Any]:
        """Process subtype rule errors - keep individual rule tags for display
        
        Return all error rules with their original tags so frontend can display them
        grouped by subtype along with passed rules.
        """
        # Simply return the details as-is, preserving all rule tags
        # The frontend will handle grouping by subtype
        return {
            'passed': details['passed'][:],  # Keep passed rules as-is
            'warnings': details['warnings'][:],  # Keep warnings as-is
            'errors': details['errors'][:]  # Keep all error rules with their original tags
        }
    
    async def _check_existing_applications(
        self, 
        user_id: int, 
        config: ScholarshipConfiguration, 
        student_data: Dict[str, Any]
    ) -> bool:
        """Check if user already has an application for this scholarship configuration
        
        Note: This check excludes DRAFT applications to allow students to see eligible 
        scholarships even when they have saved drafts. Only finalized applications
        (submitted or beyond) block eligibility.
        """
        
        # Get active applications (not cancelled, withdrawn, or rejected)
        # DRAFT status is excluded to allow students to see scholarships they have drafts for
        active_statuses = [
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
        
        # Handle semester comparison - use enum name for PostgreSQL compatibility
        # PostgreSQL stores enum as the name (FIRST, SECOND) not the value (first, second)
        if config.semester:
            # Use enum name for comparison
            semester_filter = Application.semester == config.semester.name
        else:
            # If no semester in config, check for NULL
            semester_filter = Application.semester.is_(None)
        
        stmt = select(Application).filter(
            and_(
                Application.user_id == user_id,
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.academic_year == config.academic_year,
                semester_filter,
                Application.status.in_(active_statuses)
            )
        )
        
        result = await self.db.execute(stmt)
        existing_application = result.scalar_one_or_none()
        
        # Return False if existing application found (not eligible)
        # Return True if no existing application (eligible)
        return existing_application is None