"""
Tests for `app.utils.academic_period` — Taiwan calendar arithmetic.

These pure functions decide WHICH academic year/semester an applicant
sees, and WHICH date range a payment roster covers. Off-by-one bugs
here cause:
- Students seeing 'last year's' scholarship list (wrong semester).
- Payment rosters missing months that should be included.
- Display strings showing wrong semester label on official documents.

The 7→8 month boundary is especially sensitive (matches NYCU's official
academic calendar — semester 1 starts in August, not September).

5 functions covered (22 cases):
- `calculate_academic_period_from_date`
- `get_current_academic_period`
- `get_academic_year_range`
- `format_academic_period`
- `get_roster_period_dates`
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.utils.academic_period import (
    calculate_academic_period_from_date,
    format_academic_period,
    get_academic_year_range,
    get_current_academic_period,
    get_roster_period_dates,
)

# ─── calculate_academic_period_from_date ─────────────────────────────


def test_calculate_period_august_is_first_semester_new_ay():
    """August 1st is the academic-year boundary — month=8 → first semester
    of the new ROC year. This is the most common 'is it next year yet?'
    confusion point."""
    result = calculate_academic_period_from_date(datetime(2025, 8, 1))
    assert result["academic_year"] == 114  # 2025 - 1911
    assert result["semester"] == "first"


def test_calculate_period_october_is_first_semester():
    """Oct ⇒ first semester of current ROC year."""
    result = calculate_academic_period_from_date(datetime(2025, 10, 15))
    assert result["academic_year"] == 114
    assert result["semester"] == "first"


def test_calculate_period_january_is_first_semester_previous_year():
    """January is still first semester (Aug-Jan window), but it belongs
    to the PREVIOUS ROC year because the AY started last August."""
    result = calculate_academic_period_from_date(datetime(2026, 1, 15))
    assert result["academic_year"] == 114  # AY started 2025/8
    assert result["semester"] == "first"


def test_calculate_period_february_is_second_semester():
    """Feb-Jul = second semester of the AY that started last August."""
    result = calculate_academic_period_from_date(datetime(2026, 3, 15))
    assert result["academic_year"] == 114
    assert result["semester"] == "second"


def test_calculate_period_july_is_second_semester():
    """End-of-semester boundary: July is second semester."""
    result = calculate_academic_period_from_date(datetime(2025, 7, 31))
    assert result["academic_year"] == 113  # AY113 = 2024/8 to 2025/7
    assert result["semester"] == "second"


def test_calculate_period_handles_tz_aware_input():
    """tzinfo is stripped — accepts UTC-aware datetimes from
    `datetime.now(timezone.utc)` calls without crashing."""
    result = calculate_academic_period_from_date(datetime(2025, 10, 15, tzinfo=timezone.utc))
    assert result["academic_year"] == 114
    assert result["semester"] == "first"


def test_calculate_period_none_uses_current_time():
    """Default None ⇒ datetime.now() (just verify it doesn't crash and
    returns the expected schema)."""
    result = calculate_academic_period_from_date(None)
    assert "academic_year" in result
    assert result["semester"] in ("first", "second")
    assert "western_year" in result


# ─── get_current_academic_period ─────────────────────────────────────


def test_get_current_period_delegates():
    """Just confirms the shape; the actual logic is tested above."""
    result = get_current_academic_period()
    assert isinstance(result["academic_year"], int)
    assert result["semester"] in ("first", "second")


# ─── get_academic_year_range ─────────────────────────────────────────


@patch("app.utils.academic_period.get_current_academic_period")
def test_year_range_includes_current_descending(mock_period):
    """Default include_current=True returns [current, current-1, ...]."""
    mock_period.return_value = {"academic_year": 114, "semester": "first", "western_year": 2025}
    assert get_academic_year_range(years_back=3) == [114, 113, 112, 111]


@patch("app.utils.academic_period.get_current_academic_period")
def test_year_range_exclude_current(mock_period):
    """include_current=False starts at current-1."""
    mock_period.return_value = {"academic_year": 114, "semester": "first", "western_year": 2025}
    assert get_academic_year_range(years_back=3, include_current=False) == [113, 112, 111]


@patch("app.utils.academic_period.get_current_academic_period")
def test_year_range_zero_back(mock_period):
    """years_back=0 with include_current=True ⇒ just [current]."""
    mock_period.return_value = {"academic_year": 114, "semester": "first", "western_year": 2025}
    assert get_academic_year_range(years_back=0) == [114]


# ─── format_academic_period ──────────────────────────────────────────


def test_format_period_chinese_first():
    assert format_academic_period(114, "first") == "114學年度第一學期"


def test_format_period_chinese_second():
    assert format_academic_period(114, "second", lang="zh") == "114學年度第二學期"


def test_format_period_chinese_yearly():
    """'yearly' (not a real semester) gets a '全年' label."""
    assert format_academic_period(114, "yearly") == "114學年度全年"


def test_format_period_chinese_unknown_semester_defaults_to_yearly():
    """Unknown semester value falls back to 全年 (defensive — don't show
    a half-formatted string)."""
    assert format_academic_period(114, "unknown_sem") == "114學年度全年"


def test_format_period_english_first():
    assert format_academic_period(114, "first", lang="en") == "AY 114 First Semester"


def test_format_period_english_yearly():
    """English yearly drops 'Semester'."""
    assert format_academic_period(114, "yearly", lang="en") == "AY 114 Yearly"


# ─── get_roster_period_dates ─────────────────────────────────────────


def test_roster_dates_yearly():
    """Yearly: 9月 to 8月 of following western year."""
    result = get_roster_period_dates(113, None, "yearly", "113")
    assert result["start_date"] == datetime(2024, 9, 1)
    assert result["end_date"] == datetime(2025, 8, 31)


def test_roster_dates_first_semester():
    """First semester: 8月-1月."""
    result = get_roster_period_dates(113, "first", "yearly", "113-1")
    assert result["start_date"] == datetime(2024, 8, 1)
    assert result["end_date"] == datetime(2025, 1, 31)


def test_roster_dates_second_semester():
    """Second semester: 2月-7月 of (western_year + 1)."""
    result = get_roster_period_dates(113, "second", "yearly", "113-2")
    assert result["start_date"] == datetime(2025, 2, 1)
    assert result["end_date"] == datetime(2025, 7, 31)


def test_roster_dates_monthly_handles_30_vs_31_days():
    """Monthly: extracts month from label '113-09' and computes correct
    last-day-of-month. September has 30 days, October 31."""
    result = get_roster_period_dates(113, None, "monthly", "113-09")
    assert result["start_date"] == datetime(2024, 9, 1)
    assert result["end_date"] == datetime(2024, 9, 30)

    result = get_roster_period_dates(113, None, "monthly", "113-10")
    assert result["end_date"] == datetime(2024, 10, 31)


def test_roster_dates_monthly_parse_failure_falls_back_to_yearly():
    """Malformed monthly label ⇒ yearly defaults (don't crash on bad input)."""
    result = get_roster_period_dates(113, None, "monthly", "no-dashes")
    assert result["start_date"] == datetime(2024, 9, 1)
    assert result["end_date"] == datetime(2025, 8, 31)


def test_roster_dates_semi_yearly_h2_is_march_to_august():
    """Semi-yearly H2: March to August of next western year."""
    result = get_roster_period_dates(113, None, "semi_yearly", "113-H2")
    assert result["start_date"] == datetime(2025, 3, 1)
    assert result["end_date"] == datetime(2025, 8, 31)
