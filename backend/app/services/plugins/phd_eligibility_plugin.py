"""
PhD Scholarship Eligibility Plugin

This plugin contains PhD-specific business logic for eligibility checking
and alternate promotion rules.

Key Rules:
1. Same college requirement
2. Same enrollment year/term (cohort matching)
3. Received months limit (default 36 months)
"""

import logging
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.payment_roster import PaymentRoster, PaymentRosterItem
from app.models.scholarship import ScholarshipConfiguration
from app.utils.application_helpers import get_college_code_from_data

logger = logging.getLogger(__name__)

# PhD scholarship type codes (can be configured from database in the future)
PHD_SCHOLARSHIP_CODES = ["phd_scholarship", "phd", "doctoral"]


def is_phd_scholarship(scholarship_config: ScholarshipConfiguration) -> bool:
    """
    Check if scholarship is PhD type by code

    Args:
        scholarship_config: Scholarship configuration

    Returns:
        True if PhD scholarship, False otherwise
    """
    if not scholarship_config or not scholarship_config.scholarship_type:
        return False

    scholarship_code = scholarship_config.scholarship_type.code
    if not scholarship_code:
        return False

    # Case-insensitive check
    return scholarship_code.lower() in PHD_SCHOLARSHIP_CODES


def check_phd_eligibility(
    db: Session, student_nycu_id: str, scholarship_config: ScholarshipConfiguration, max_months: int = 36
) -> Tuple[bool, Optional[str]]:
    """
    Check if student currently meets PhD scholarship eligibility

    This function is used during roster generation to verify that
    primary allocated students still meet the received months limit.

    Rule:
    - Must not have received more than max_months of scholarship

    Args:
        db: Database session
        student_nycu_id: Student NYCU ID
        scholarship_config: Scholarship configuration
        max_months: Maximum allowed months (default 36)

    Returns:
        (is_eligible, rejection_reason)
    """
    if not student_nycu_id:
        return (False, "缺少學號資訊")

    received_months = _calculate_received_months(db, student_nycu_id, scholarship_config)

    if received_months >= max_months:
        return (False, f"已領取 {received_months} 個月，超過上限 {max_months} 個月")

    logger.info(
        f"PhD eligibility check passed for student {student_nycu_id}: "
        f"received_months={received_months}/{max_months}"
    )

    return (True, None)


def check_phd_alternate_eligibility(
    db: Session,
    student_data: Dict[str, Any],
    original_student_data: Dict[str, Any],
    scholarship_config: ScholarshipConfiguration,
    max_months: int = 36,
) -> Tuple[bool, Optional[str]]:
    """
    Check if alternate student is eligible for PhD scholarship

    PhD-specific rules:
    1. Must be from same college
    2. Must be from same enrollment year/term (cohort)
    3. Must not have received more than max_months of scholarship

    Args:
        db: Database session
        student_data: Alternate student's data
        original_student_data: Original student's data (for comparison)
        scholarship_config: Scholarship configuration
        max_months: Maximum allowed months (default 36)

    Returns:
        (is_eligible, rejection_reason)
    """
    # Rule 1: Check same college
    alternate_college = get_college_code_from_data(student_data)
    original_college = get_college_code_from_data(original_student_data)

    if not alternate_college:
        return (False, "備取學生缺少學院資訊")

    if not original_college:
        logger.warning("Original student missing college code, skipping college check")
    elif alternate_college.upper() != original_college.upper():
        return (False, f"備取學生學院（{alternate_college}）與原學生學院（{original_college}）不符")

    # Rule 2: Check same enrollment year/term
    alternate_enroll_year = student_data.get("std_enrollyear")
    alternate_enroll_term = student_data.get("std_enrollterm")
    original_enroll_year = original_student_data.get("std_enrollyear")
    original_enroll_term = original_student_data.get("std_enrollterm")

    if not alternate_enroll_year or not alternate_enroll_term:
        return (False, "備取學生缺少入學年度或學期資訊")

    if not original_enroll_year or not original_enroll_term:
        logger.warning("Original student missing enrollment info, skipping cohort check")
    elif str(alternate_enroll_year) != str(original_enroll_year) or str(alternate_enroll_term) != str(
        original_enroll_term
    ):
        return (
            False,
            f"備取學生入學時間（{alternate_enroll_year}/{alternate_enroll_term}）"
            f"與原學生（{original_enroll_year}/{original_enroll_term}）不符",
        )

    # Rule 3: Check received months limit
    # Get student NYCU ID for querying historical rosters
    student_nycu_id = student_data.get("std_stdcode") or student_data.get("nycu_id")
    if not student_nycu_id:
        return (False, "備取學生缺少學號資訊")

    received_months = _calculate_received_months(db, student_nycu_id, scholarship_config)

    if received_months >= max_months:
        return (False, f"備取學生已領取 {received_months} 個月，超過上限 {max_months} 個月")

    logger.info(
        f"PhD eligibility check passed for student {student_nycu_id}: "
        f"college={alternate_college}, enroll={alternate_enroll_year}/{alternate_enroll_term}, "
        f"received_months={received_months}/{max_months}"
    )

    return (True, None)


def _calculate_received_months(db: Session, student_nycu_id: str, scholarship_config: ScholarshipConfiguration) -> int:
    """
    Calculate total months a student has received this scholarship

    Queries historical PaymentRosterItem records and counts months
    where the student was included (is_included=True).

    Args:
        db: Database session
        student_nycu_id: Student NYCU ID
        scholarship_config: Scholarship configuration

    Returns:
        Total months received
    """
    try:
        # Query all PaymentRosterItem for this student with this scholarship type
        roster_items = (
            db.query(PaymentRosterItem)
            .join(PaymentRoster, PaymentRosterItem.roster_id == PaymentRoster.id)
            .filter(
                and_(
                    PaymentRosterItem.student_id_number == student_nycu_id,
                    PaymentRosterItem.is_included.is_(True),
                    PaymentRoster.scholarship_configuration_id == scholarship_config.id,
                )
            )
            .all()
        )

        # Count unique academic_year + semester combinations
        # This handles both monthly and semester-based rosters
        unique_periods = set()
        for item in roster_items:
            roster = item.roster
            if roster:
                # Use academic_year + period_label as unique identifier
                period_key = f"{roster.academic_year}_{roster.period_label}"
                unique_periods.add(period_key)

        # For PhD scholarships, typically count by semester or year
        # Each unique period counts as 1 month (or adjust based on roster_cycle)
        # For more accurate counting, we'd need to parse period_label
        months_count = len(unique_periods)

        logger.info(
            f"Student {student_nycu_id} has received {months_count} periods "
            f"for scholarship_config {scholarship_config.id}"
        )

        return months_count

    except Exception as e:
        logger.error(f"Error calculating received months for student {student_nycu_id}: {e}")
        # In case of error, assume 0 months to allow promotion (fail open)
        return 0
