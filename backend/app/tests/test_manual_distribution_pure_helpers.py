"""
Pure-function tests for `ManualDistributionService` helpers.

These helpers shape the data students/college reviewers see on the
manual-distribution UI. Silent bugs here mean wrong identity labels,
wrong term counts, or wrong enrollment dates on roster rows — student-
visible / auditor-visible noise.

5 helpers covered (16 cases total):
- `_compute_application_identity`        : "{year}新申請" vs "{year}續領"
- `_compute_term_count`                  : SIS trm_termcount → int | None
- `_get_renewal_sub_type`                : renewal app → Chinese display
- `_sub_type_to_chinese` (staticmethod)  : sub-type code → Chinese label
- `_format_enrollment_date`              : ROC date string from SIS
"""

from types import SimpleNamespace

import pytest

from app.services.manual_distribution_service import ManualDistributionService


@pytest.fixture
def service():
    """All tested helpers are pure (no DB), so we can hand it a None session."""
    return ManualDistributionService(db=None)  # type: ignore[arg-type]


def _app(*, academic_year=114, is_renewal=False, previous_application_id=None, sub_scholarship_type=None):
    return SimpleNamespace(
        academic_year=academic_year,
        is_renewal=is_renewal,
        previous_application_id=previous_application_id,
        sub_scholarship_type=sub_scholarship_type,
    )


# ─── _compute_application_identity ───────────────────────────────────


def test_application_identity_new_application(service):
    """Non-renewal ⇒ '{year}新申請'."""
    assert service._compute_application_identity(_app(academic_year=114, is_renewal=False)) == "114新申請"


def test_application_identity_renewal_with_previous_id(service):
    """Renewal flag + previous_application_id present ⇒ '{year}續領'."""
    app = _app(academic_year=113, is_renewal=True, previous_application_id=42)
    assert service._compute_application_identity(app) == "113續領"


def test_application_identity_renewal_without_previous_id_is_new(service):
    """is_renewal=True but no previous_application_id ⇒ still 新申請 — both
    conditions must hold (defensive against orphaned renewal flags)."""
    app = _app(academic_year=114, is_renewal=True, previous_application_id=None)
    assert service._compute_application_identity(app) == "114新申請"


# ─── _compute_term_count ──────────────────────────────────────────────


def test_term_count_integer_value(service):
    assert service._compute_term_count({"trm_termcount": 4}) == 4


def test_term_count_string_value_coerced(service):
    """SIS sometimes returns numerics as strings — must coerce."""
    assert service._compute_term_count({"trm_termcount": "6"}) == 6


def test_term_count_missing_key_returns_none(service):
    assert service._compute_term_count({}) is None


def test_term_count_unparseable_returns_none(service):
    """ValueError / TypeError on int(...) → None (no exception leaks)."""
    assert service._compute_term_count({"trm_termcount": "not-a-number"}) is None
    assert service._compute_term_count({"trm_termcount": [1, 2]}) is None


# ─── _sub_type_to_chinese (staticmethod) ─────────────────────────────


def test_sub_type_to_chinese_known_codes():
    assert ManualDistributionService._sub_type_to_chinese("nstc") == "國科會"
    assert ManualDistributionService._sub_type_to_chinese("moe_1w") == "教育部"
    assert ManualDistributionService._sub_type_to_chinese("moe_2w") == "教育部"


def test_sub_type_to_chinese_unknown_returns_input():
    """Unknown sub-types fall through unchanged — admins can add new
    sub-types via config without code changes (see CLAUDE.md §4)."""
    assert ManualDistributionService._sub_type_to_chinese("custom_new") == "custom_new"


# ─── _get_renewal_sub_type ────────────────────────────────────────────


def test_renewal_sub_type_not_a_renewal_returns_none(service):
    """Non-renewal ⇒ None (this helper only applies to renewals)."""
    app = _app(is_renewal=False, sub_scholarship_type="nstc")
    assert service._get_renewal_sub_type(app) is None


def test_renewal_sub_type_general_returns_none(service):
    """'general' is the no-special-track marker ⇒ None (don't display)."""
    app = _app(is_renewal=True, sub_scholarship_type="general")
    assert service._get_renewal_sub_type(app) is None


def test_renewal_sub_type_empty_returns_none(service):
    app = _app(is_renewal=True, sub_scholarship_type=None)
    assert service._get_renewal_sub_type(app) is None


def test_renewal_sub_type_maps_to_chinese(service):
    app = _app(is_renewal=True, sub_scholarship_type="nstc")
    assert service._get_renewal_sub_type(app) == "國科會"


# ─── _format_enrollment_date ──────────────────────────────────────────


def test_format_enrollment_date_term1_uses_september(service):
    """trm_term=1 corresponds to Sep enrollment (上學期)."""
    assert service._format_enrollment_date({"std_enrollyear": 112, "std_enrollterm": 1}) == "112.09.01"


def test_format_enrollment_date_term2_uses_february(service):
    """trm_term=2 corresponds to Feb enrollment (下學期)."""
    assert service._format_enrollment_date({"std_enrollyear": 113, "std_enrollterm": 2}) == "113.02.01"


def test_format_enrollment_date_missing_year_returns_empty(service):
    """No enroll year ⇒ '' (don't display a 0.09.01 placeholder)."""
    assert service._format_enrollment_date({}) == ""
    assert service._format_enrollment_date({"std_enrollyear": 0, "std_enrollterm": 1}) == ""
