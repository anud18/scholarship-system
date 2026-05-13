"""
Pure-function tests for `CollegeReviewService` static + pure helpers.

These run without DB and pin the helpers that downstream methods depend
on (semester normalization, role guards, roster-cycle math). A regression
here would silently misroute applications between semesters or grant
access to the wrong role.

Helpers covered (15 cases across 4 helpers):
- `_calculate_expected_periods(roster_cycle, academic_year)`: cycle →
  total-periods math.
- `_normalize_semester_value(semester)`: enum/str/None → canonical str
  or None.
- `_is_yearly_semester(semester)`: detect the yearly bucket from
  whichever form the caller passed.
- `_role_matches(role, *expected)`: role enum/string vs allow-list.
"""

from types import SimpleNamespace
from typing import Optional

import pytest

from app.services.college_review_service import CollegeReviewService

# ─── _calculate_expected_periods ────────────────────────────────────


@pytest.fixture
def service():
    return CollegeReviewService(db=None)  # type: ignore[arg-type]


def test_calculate_expected_periods_monthly_returns_12(service):
    from app.models.payment_roster import RosterCycle

    assert service._calculate_expected_periods(RosterCycle.MONTHLY, 114) == 12


def test_calculate_expected_periods_semi_yearly_returns_2(service):
    from app.models.payment_roster import RosterCycle

    assert service._calculate_expected_periods(RosterCycle.SEMI_YEARLY, 114) == 2


def test_calculate_expected_periods_yearly_returns_1(service):
    from app.models.payment_roster import RosterCycle

    assert service._calculate_expected_periods(RosterCycle.YEARLY, 114) == 1


def test_calculate_expected_periods_unknown_defaults_to_1(service):
    """An unrecognized roster_cycle (e.g. None / new enum variant) → 1."""
    assert service._calculate_expected_periods(None, 114) == 1
    assert service._calculate_expected_periods("garbage", 114) == 1


# ─── _normalize_semester_value ──────────────────────────────────────


def test_normalize_semester_none_returns_none():
    assert CollegeReviewService._normalize_semester_value(None) is None


def test_normalize_semester_yearly_normalizes_to_none():
    """'yearly' is the canonical no-semester marker → None."""
    assert CollegeReviewService._normalize_semester_value("yearly") is None
    assert CollegeReviewService._normalize_semester_value("Yearly") is None
    # Note: 'Semester.yearly' is the enum repr from str(Semester.yearly)
    # in older Python versions — also handled.
    assert CollegeReviewService._normalize_semester_value("Semester.yearly") is None


def test_normalize_semester_first_returns_first():
    """Canonical string form 'first' round-trips."""
    assert CollegeReviewService._normalize_semester_value("first") == "first"


def test_normalize_semester_second_with_prefix():
    """'Semester.second' enum-string repr normalizes to 'second'."""
    assert CollegeReviewService._normalize_semester_value("Semester.second") == "second"


def test_normalize_semester_invalid_returns_none():
    """Unrecognized values silently degrade to None — defensive default."""
    assert CollegeReviewService._normalize_semester_value("garbage") is None
    assert CollegeReviewService._normalize_semester_value("") is None
    assert CollegeReviewService._normalize_semester_value("none") is None


# ─── _is_yearly_semester ────────────────────────────────────────────


def test_is_yearly_semester_none_is_yearly():
    """None ⇒ yearly is the convention (no per-semester bucket)."""
    assert CollegeReviewService._is_yearly_semester(None) is True


def test_is_yearly_semester_explicit_yearly():
    assert CollegeReviewService._is_yearly_semester("yearly") is True
    assert CollegeReviewService._is_yearly_semester("Semester.yearly") is True


def test_is_yearly_semester_first_is_not_yearly():
    assert CollegeReviewService._is_yearly_semester("first") is False
    assert CollegeReviewService._is_yearly_semester("second") is False


# ─── _role_matches ──────────────────────────────────────────────────


def test_role_matches_enum_member_matches():
    """Enum-typed roles get .value extracted before comparison."""
    role = SimpleNamespace(value="admin")
    assert CollegeReviewService._role_matches(role, "admin", "super_admin") is True


def test_role_matches_string_matches():
    """Plain string role passes through compare directly."""
    assert CollegeReviewService._role_matches("college", "admin", "college") is True


def test_role_matches_returns_false_when_no_match():
    assert CollegeReviewService._role_matches("student", "admin", "super_admin") is False
    assert CollegeReviewService._role_matches(SimpleNamespace(value="student"), "admin", "college") is False
