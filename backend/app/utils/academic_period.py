"""
Academic Period Utilities
Provides functions to dynamically determine current academic year and semester
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def calculate_academic_period_from_date(target_date: Optional[datetime] = None) -> Dict[str, any]:
    """
    Calculate academic year and semester from a given date

    Taiwan academic calendar rules:
    - Academic year starts in August
    - First semester: August - January (8-1月)
    - Second semester: February - July (2-7月)
    - ROC year = Western year - 1911

    Args:
        target_date: Date to calculate from (defaults to now in UTC)

    Returns:
        Dictionary with:
        - academic_year: int (ROC year, e.g., 114)
        - semester: str ('first' or 'second')
        - western_year: int (for reference)

    Examples:
        2025-10-15 -> {academic_year: 114, semester: 'first', western_year: 2025}
        2025-03-15 -> {academic_year: 113, semester: 'second', western_year: 2025}
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc)

    # Remove timezone info for easier month/year comparison
    if target_date.tzinfo is not None:
        target_date = target_date.replace(tzinfo=None)

    western_year = target_date.year
    month = target_date.month

    # Determine academic year and semester
    if month >= 8:  # August to December (8-12月) -> First semester of current ROC year
        roc_year = western_year - 1911
        semester = "first"
    elif month >= 2:  # February to July (2-7月) -> Second semester of previous ROC year
        roc_year = western_year - 1911 - 1  # Previous academic year
        semester = "second"
    else:  # January (1月) -> Still first semester of previous ROC year
        roc_year = western_year - 1911 - 1  # Previous academic year
        semester = "first"

    logger.info(
        f"Calculated academic period: AY{roc_year} {semester} semester " f"(from {target_date.strftime('%Y-%m-%d')})"
    )

    return {
        "academic_year": roc_year,
        "semester": semester,
        "western_year": western_year,
    }


def get_current_academic_period() -> Dict[str, any]:
    """
    Get current academic year and semester by calculating from current date

    Returns:
        Dictionary with:
        - academic_year: int (ROC year)
        - semester: str ('first' or 'second')
        - western_year: int (for reference)
    """
    return calculate_academic_period_from_date()


def get_academic_year_range(years_back: int = 3, include_current: bool = True) -> list[int]:
    """
    Get a list of academic years to query (for historical data)

    Args:
        years_back: Number of years to go back from current year
        include_current: Whether to include current academic year

    Returns:
        List of academic years in descending order (newest first)

    Example:
        If current year is 114 and years_back=3:
        Returns [114, 113, 112, 111] (if include_current=True)
        Returns [113, 112, 111] (if include_current=False)
    """
    current_period = get_current_academic_period()
    current_year = current_period["academic_year"]

    if include_current:
        return list(range(current_year, current_year - years_back - 1, -1))
    else:
        return list(range(current_year - 1, current_year - years_back - 1, -1))


def format_academic_period(academic_year: int, semester: str, lang: str = "zh") -> str:
    """
    Format academic period for display

    Args:
        academic_year: ROC academic year
        semester: 'first' or 'second'
        lang: Language code ('zh' or 'en')

    Returns:
        Formatted string

    Examples:
        (114, 'first', 'zh') -> "114學年度第一學期"
        (114, 'first', 'en') -> "AY 114 First Semester"
    """
    if lang == "en":
        semester_name = "First" if semester == "first" else "Second"
        return f"AY {academic_year} {semester_name} Semester"
    else:
        semester_name = "第一學期" if semester == "first" else "第二學期"
        return f"{academic_year}學年度{semester_name}"
