"""
Scholarship service for scholarship management
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.scholarship import ScholarshipType, ScholarshipRule, ScholarshipStatus
from app.models.student import Student
from app.schemas.scholarship import EligibleScholarshipResponse, RuleMessage

@dataclass
class RuleValidationResult:
    passed: bool
    rule_id: int
    rule_name: str
    rule_type: str
    message: str
    tag: Optional[str] = None
    message_en: Optional[str] = None
    sub_type: Optional[str] = None
    priority: int = 0
    is_warning: bool = False
    is_hard_rule: bool = False

async def get_active_scholarships(db: AsyncSession) -> List[ScholarshipType]:
    """Get all active scholarships"""
    result = await db.execute(
        select(ScholarshipType)
        .where(ScholarshipType.status == ScholarshipStatus.ACTIVE.value)
    )
    return result.scalars().all()

async def get_scholarship_rules(db: AsyncSession, scholarship_id: int) -> List[ScholarshipRule]:
    """Get all rules for a scholarship ordered by priority"""
    result = await db.execute(
        select(ScholarshipRule)
        .where(
            ScholarshipRule.scholarship_type_id == scholarship_id,
            ScholarshipRule.is_active == True
        )
        .order_by(ScholarshipRule.priority)
    )
    return result.scalars().all()

def separate_rules(rules: List[ScholarshipRule]) -> tuple[List[ScholarshipRule], Dict[str, List[ScholarshipRule]]]:
    """Separate rules into common rules and subtype-specific rules"""
    common_rules = []
    subtype_rules: Dict[str, List[ScholarshipRule]] = {}
    
    for rule in rules:
        if rule.sub_type:
            if rule.sub_type not in subtype_rules:
                subtype_rules[rule.sub_type] = []
            subtype_rules[rule.sub_type].append(rule)
        else:
            common_rules.append(rule)
    
    return common_rules, subtype_rules

async def get_field_value(student: Student, field_path: str) -> Any:
    """Get value from student object using dot notation field path"""
    obj = student
    for field in field_path.split('.'):
        # Map old field paths to new field names
        field_mapping = {
            "academicRecords.degree": "std_degree",
            "academicRecords.studyingStatus": "std_studingstatus",
            "academicRecords.schoolIdentity": "std_schoolid",
            "academicRecords.identity": "std_identity",
            "academicRecords.nationality": "std_nation",
            "academicRecords.termCount": "std_termcount",
            "academicRecords.enrollTypeCode": "std_enrollterm",  # Simplified mapping
            "studyingStatus": "std_studingstatus",
            "nationality": "std_nation",
            "schoolIdentity": "std_schoolid"
        }
        
        # Check if the full path is in the mapping
        if field_path in field_mapping:
            field = field_mapping[field_path]
            return getattr(obj, field, None)
        
        # Check if the current field is in the mapping
        if field in field_mapping:
            field = field_mapping[field]
        
        if hasattr(obj, field):
            obj = getattr(obj, field)
        else:
            return None
    return obj

def compare_values(value: str, expected_value: str, operator: str) -> bool:
    """Compare two values using the specified operator"""
    if operator == "==":
        return value == expected_value
    elif operator == "!=":
        return value != expected_value
    elif operator == ">=":
        try:
            return float(value) >= float(expected_value)
        except (ValueError, TypeError):
            return False
    elif operator == "<=":
        try:
            return float(value) <= float(expected_value)
        except (ValueError, TypeError):
            return False
    elif operator == "in":
        expected_values = [str(v).strip() for v in expected_value.split(",")]
        return value in expected_values
    elif operator == "not_in":
        expected_values = [str(v).strip() for v in expected_value.split(",")]
        return value not in expected_values
    return True  # Unknown operator

def create_validation_result(
    passed: bool,
    rule: ScholarshipRule,
    message: Optional[str] = None,
    message_en: Optional[str] = None
) -> RuleValidationResult:
    """Create a validation result object"""
    if passed:
        return RuleValidationResult(
            passed=True,
            rule_id=rule.id,
            rule_name=rule.rule_name,
            rule_type=rule.rule_type,
            tag=rule.tag,
            message="",
            message_en="",
            sub_type=rule.sub_type,
            is_warning=rule.is_warning,
            priority=rule.priority
        )
    
    msg = message or rule.message or f"Failed validation for {rule.rule_name}"
    msg_en = message_en or rule.message_en or f"Failed validation for {rule.rule_name}"
    
    return RuleValidationResult(
        passed=False,
        rule_id=rule.id,
        rule_name=rule.rule_name,
        rule_type=rule.rule_type,
        tag=rule.tag,
        message=msg,
        message_en=msg_en,
        sub_type=rule.sub_type,
        is_warning=rule.is_warning,
        priority=rule.priority
    )

async def validate_rule(student: Student, rule: ScholarshipRule) -> RuleValidationResult:
    """Validate a single rule against student data"""
    # Special handling for enrollType validation
    if rule.condition_field == "enrollTypeId":
        # For new model, we'll use a simplified approach
        # This might need adjustment based on actual requirements
        return create_validation_result(
            True,
            rule,
            "Enrollment type validation not implemented in new model"
        )
    
    # Normal validation for other fields
    field_value = await get_field_value(student, rule.condition_field)
    
    if field_value is None:
        return create_validation_result(
            False,
            rule,
            f"Field {rule.condition_field} not found"
        )
    
    # Compare values
    passed = compare_values(str(field_value), str(rule.expected_value), rule.operator)
    return create_validation_result(passed, rule)

async def validate_common_rules(
    student: Student,
    rules: List[ScholarshipRule],
) -> tuple[List[RuleValidationResult], List[RuleValidationResult], List[RuleValidationResult]]:
    """Validate common rules that apply to all subtypes"""
    passed_rules = []
    failed_rules = []
    warnings_rules = []
    for rule in rules:
        result = await validate_rule(student, rule)
        if result.is_warning and result.passed:
            warnings_rules.append(result)
        if not result.passed and not result.is_warning:
            failed_rules.append(result)
            # If it's a hard rule and validation failed, return immediately
            if rule.is_hard_rule:
                return [], failed_rules, warnings_rules
        else:
            passed_rules.append(result)
    
    # Return True if no hard rules failed, even if there are warning rules that failed
    return passed_rules, failed_rules, warnings_rules

async def validate_subtype_rules(
    student: Student,
    subtype: str,
    rules: List[ScholarshipRule],
) -> tuple[List[RuleValidationResult], List[RuleValidationResult], List[RuleValidationResult]]:
    """Validate rules for a specific subtype"""
    passed_rules = []
    failed_rules = []
    warnings_rules = []
    
    for rule in rules:
        result = await validate_rule(student, rule)
        if result.is_warning and result.passed:
            warnings_rules.append(result)
        if not result.passed and not result.is_warning:
            failed_rules.append(result)
        else:
            passed_rules.append(result)
    
    return passed_rules, failed_rules, warnings_rules

async def check_scholarship_basic_eligibility(
    student: Student,
    scholarship: ScholarshipType,
    db: AsyncSession
) -> bool:
    """Check basic eligibility for a scholarship"""
    # Check if scholarship is active
    if not scholarship.is_active:
        return False

    # Check if student is in whitelist if whitelist is enabled
    if scholarship.whitelist_enabled and student.id not in scholarship.whitelist_student_ids:
        return False

    return True

def create_eligibility_response(
    scholarship: ScholarshipType,
    eligible_sub_types: List[str],
    passed_rules: Optional[List[RuleValidationResult]] = None,
    failed_rules: Optional[List[RuleValidationResult]] = None,
    warnings_rules: Optional[List[RuleValidationResult]] = None
) -> EligibleScholarshipResponse:
    """Create a structured response for eligible scholarship, including rule validation details."""
    # Avoid mutable default arguments
    passed_rules = passed_rules or []
    failed_rules = failed_rules or []
    warnings_rules = warnings_rules or []

    def sort_by_priority(rules: List[RuleValidationResult]) -> List[RuleValidationResult]:
        return sorted(rules, key=lambda x: x.priority, reverse=False)

    sorted_passed = sort_by_priority(passed_rules)
    sorted_failed = sort_by_priority(failed_rules)
    sorted_warnings = sort_by_priority(warnings_rules)

    def to_rule_message(rule: RuleValidationResult) -> RuleMessage:
        return RuleMessage(
            rule_id=rule.rule_id,
            rule_name=rule.rule_name,
            rule_type=rule.rule_type,
            tag=rule.tag,
            message=rule.message,
            message_en=rule.message_en,
            sub_type=rule.sub_type,
            priority=rule.priority,
            is_warning=rule.is_warning,
            is_hard_rule=rule.is_hard_rule
        )

    return EligibleScholarshipResponse(
        id=scholarship.id,
        code=scholarship.code,
        eligible_sub_types=eligible_sub_types,
        name=scholarship.name,
        name_en=scholarship.name_en,
        category=scholarship.category,
        academic_year=scholarship.academic_year,
        semester=scholarship.semester.value,
        application_cycle=scholarship.application_cycle.value,
        description=scholarship.description,
        description_en=scholarship.description_en,
        amount=scholarship.amount,
        currency=scholarship.currency,
        application_start_date=scholarship.application_start_date,
        application_end_date=scholarship.application_end_date,
        professor_review_start=scholarship.professor_review_start,
        professor_review_end=scholarship.professor_review_end,
        college_review_start=scholarship.college_review_start,
        college_review_end=scholarship.college_review_end,
        sub_type_selection_mode=scholarship.sub_type_selection_mode.value,
        created_at=scholarship.created_at,
        passed=[to_rule_message(rule) for rule in sorted_passed],
        warnings=[to_rule_message(rule) for rule in sorted_warnings],
        errors=[to_rule_message(rule) for rule in sorted_failed]
    )

async def get_eligible_scholarships(
    student: Student, 
    db: AsyncSession,
    include_validation_details: bool = True
) -> List[EligibleScholarshipResponse]:
    """Get list of scholarships that student is eligible for"""
    
    # 預先加載所有需要的關係 (已移除舊的關係，現在使用扁平化結構)
    await db.refresh(student)
    
    # 獲取所有活躍的獎學金
    result = await db.execute(
        select(ScholarshipType)
        .where(ScholarshipType.status == ScholarshipStatus.ACTIVE.value)
    )
    scholarships = result.scalars().all()
    eligible_scholarships = []
    
    for scholarship in scholarships:
        # Check basic eligibility
        if not await check_scholarship_basic_eligibility(student, scholarship, db):
            continue
            
        # Get and separate rules
        rules = await get_scholarship_rules(db, scholarship.id)
        common_rules, subtype_rules = separate_rules(rules)

        # Validate common rules first
        passed_common, failed_common, warnings_common = await validate_common_rules(student, common_rules)

        # hard rule failed, skip
        if not passed_common:
            continue

        if failed_common:
            eligible_sub_types = []
        else:
            eligible_sub_types = scholarship.sub_type_list

        all_passed_rules = passed_common.copy()
        all_failed_rules = failed_common.copy()
        all_warnings_rules = warnings_common.copy()

        for subtype in eligible_sub_types:
            if subtype in subtype_rules:
                passed_subtype, failed_subtype, warnings_subtype = await validate_subtype_rules(
                    student, subtype, subtype_rules[subtype]
                )
                if failed_subtype:
                    eligible_sub_types.remove(subtype)

                all_passed_rules.extend(passed_subtype)
                all_failed_rules.extend(failed_subtype)
                all_warnings_rules.extend(warnings_subtype)

        eligible_scholarships.append(
            create_eligibility_response(
                scholarship, 
                eligible_sub_types,
                all_passed_rules,
                all_failed_rules,
                all_warnings_rules
            )
        )
    
    return eligible_scholarships
