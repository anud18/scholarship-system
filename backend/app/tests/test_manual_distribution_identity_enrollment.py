"""
Tests for `_compute_application_identity` + `_format_enrollment_date`
on ManualDistributionService.

Wave 6q covered the OTHER pure helpers (_compute_term_count,
_sub_type_to_chinese, _get_renewal_sub_type). This wave fills:

  - **_compute_application_identity(app)**: builds the display
    string `"{academic_year}新申請"` for new apps and
    `"{academic_year}續領"` for renewals. The renewal branch
    additionally requires `previous_application_id` to be set —
    a renewal without a previous record reads as "新申請" for
    display.

  - **_format_enrollment_date(student_data)**: converts ROC year
    + term into "YYY.MM.01" (民國年.月.日). Term 1 → September,
    term 2 → February. Empty year returns empty string.

10 cases.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.manual_distribution_service import ManualDistributionService


@pytest.fixture
def service():
    db = MagicMock()
    return ManualDistributionService(db)


# ─── _compute_application_identity ──────────────────────────────────


def test_identity_new_application_label(service):
    # Pin: non-renewal → "{year}新申請" — the "new application"
    # signal in the distribution table.
    app = SimpleNamespace(is_renewal=False, previous_application_id=None, academic_year=114)
    assert service._compute_application_identity(app) == "114新申請"


def test_identity_renewal_with_previous_id_label(service):
    # Pin: renewal + previous_application_id → "{year}續領". The
    # second condition is critical — a renewal without a previous
    # record shouldn't claim "續領" because there's nothing to
    # continue from.
    app = SimpleNamespace(is_renewal=True, previous_application_id=42, academic_year=114)
    assert service._compute_application_identity(app) == "114續領"


def test_identity_renewal_without_previous_id_falls_through_to_new(service):
    # Pin: is_renewal=True BUT no previous_application_id → labeled
    # as new application. Defensive against legacy renewal records
    # that lost their previous-app FK.
    app = SimpleNamespace(is_renewal=True, previous_application_id=None, academic_year=114)
    assert service._compute_application_identity(app) == "114新申請"


def test_identity_academic_year_value_embedded(service):
    # Pin: the value is interpolated directly — pin against 113 to
    # confirm the f-string doesn't accidentally pin to a constant.
    app = SimpleNamespace(is_renewal=False, previous_application_id=None, academic_year=113)
    assert service._compute_application_identity(app) == "113新申請"


# ─── _format_enrollment_date ────────────────────────────────────────


def test_enrollment_date_term_1_is_september():
    # Pin: term 1 → "09" month. Documents NYCU's "first semester
    # starts in September" calendar convention.
    service = ManualDistributionService(MagicMock())
    out = service._format_enrollment_date({"std_enrollyear": 113, "std_enrollterm": 1})
    assert out == "113.09.01"


def test_enrollment_date_term_2_is_february():
    # Pin: term 2 → "02" month. (Second semester starts in
    # February of the next calendar year.)
    service = ManualDistributionService(MagicMock())
    out = service._format_enrollment_date({"std_enrollyear": 113, "std_enrollterm": 2})
    assert out == "113.02.01"


def test_enrollment_date_default_term_is_september():
    # Pin: when std_enrollterm is missing, default is 1 (September).
    # The .get(..., 1) fallback.
    service = ManualDistributionService(MagicMock())
    out = service._format_enrollment_date({"std_enrollyear": 113})
    assert out == "113.09.01"


def test_enrollment_date_empty_year_returns_empty_string(service):
    # Pin: enroll_year=0 (default) → empty string. Pin so callers
    # rendering this don't show "0.09.01".
    assert service._format_enrollment_date({}) == ""


def test_enrollment_date_explicit_zero_year_returns_empty(service):
    # Pin: same — explicit 0.
    assert service._format_enrollment_date({"std_enrollyear": 0, "std_enrollterm": 1}) == ""


def test_enrollment_date_unknown_term_uses_february_branch(service):
    # Pin: only term==1 is September; anything else is February
    # (no validation on term value).
    assert service._format_enrollment_date({"std_enrollyear": 113, "std_enrollterm": 9}) == "113.02.01"
