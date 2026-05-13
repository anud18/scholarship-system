"""
Pure-function tests for `ScholarshipConfigurationService` validators.

`validate_configuration_data` is the gate that admins hit when creating
or editing a scholarship configuration. Bugs let invalid configurations
through to the database — corrupting downstream eligibility checks and
roster generation that read these dates and amounts.

2 helpers covered (14 cases):
- `validate_configuration_data`     : required + range + date-pair checks
- `calculate_application_score`     : weighted criteria scoring
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.services.scholarship_configuration_service import ScholarshipConfigurationService


@pytest.fixture
def service():
    return ScholarshipConfigurationService(db=None)  # type: ignore[arg-type]


def _full_valid_config(**overrides):
    base = {
        "config_name": "test config",
        "config_code": "TEST_2024",
        "academic_year": 113,
        "amount": 50000,
    }
    base.update(overrides)
    return base


# ─── validate_configuration_data: required fields ────────────────────


def test_validate_returns_empty_list_for_valid_config(service):
    """Happy path — no errors when all required fields present."""
    assert service.validate_configuration_data(_full_valid_config()) == []


def test_validate_flags_missing_required(service):
    errors = service.validate_configuration_data({})
    # All 4 required fields should be flagged.
    for field in ("config_name", "config_code", "academic_year", "amount"):
        assert any(field in e for e in errors), f"missing field not flagged: {field}"


def test_validate_flags_empty_string_as_missing(service):
    """Empty string is falsy ⇒ flagged as missing — pin behavior so the
    common 'whitespace name' bug surfaces in admin UI."""
    errors = service.validate_configuration_data(_full_valid_config(config_name=""))
    assert any("config_name" in e for e in errors)


# ─── validate_configuration_data: academic year range ────────────────


def test_validate_rejects_academic_year_below_100(service):
    """ROC calendar year must be ≥ 100 (year 100 = AD 2011)."""
    errors = service.validate_configuration_data(_full_valid_config(academic_year=99))
    assert any("Taiwan calendar" in e for e in errors)


def test_validate_rejects_academic_year_above_200(service):
    """ROC year > 200 (= AD 2111) is almost certainly a mistake."""
    errors = service.validate_configuration_data(_full_valid_config(academic_year=201))
    assert any("Taiwan calendar" in e for e in errors)


def test_validate_accepts_boundary_years(service):
    """100 and 200 are the inclusive boundaries — admins can legitimately
    set 100 (early years) and 200 (far future planning)."""
    assert service.validate_configuration_data(_full_valid_config(academic_year=100)) == []
    assert service.validate_configuration_data(_full_valid_config(academic_year=200)) == []


# ─── validate_configuration_data: amount ─────────────────────────────


def test_validate_rejects_zero_or_negative_amount(service):
    """Amount must be > 0 — a 0 NTD scholarship is meaningless."""
    errors = service.validate_configuration_data(_full_valid_config(amount=0))
    # 0 is falsy → required-field check flags it too; pin that EITHER way
    # produces an error (so the admin can't accidentally save 0).
    assert any("amount" in e.lower() for e in errors)

    errors = service.validate_configuration_data(_full_valid_config(amount=-100))
    assert any("greater than 0" in e for e in errors)


# ─── validate_configuration_data: date-pair ordering ─────────────────


def test_validate_flags_inverted_date_pair_iso_strings(service):
    """If end_date <= start_date, flag the pair (don't silently accept
    a config where application_end is *before* application_start)."""
    cfg = _full_valid_config(
        application_start_date="2025-09-01T00:00:00",
        application_end_date="2025-08-01T00:00:00",
    )
    errors = service.validate_configuration_data(cfg)
    assert any("application_end_date" in e and "application_start_date" in e for e in errors)


def test_validate_flags_unparseable_date_string(service):
    cfg = _full_valid_config(
        application_start_date="not-a-date",
        application_end_date="2025-09-01T00:00:00",
    )
    errors = service.validate_configuration_data(cfg)
    assert any("Invalid date format" in e for e in errors)


def test_validate_accepts_correctly_ordered_dates(service):
    cfg = _full_valid_config(
        application_start_date="2025-08-01T00:00:00",
        application_end_date="2025-09-01T00:00:00",
    )
    assert service.validate_configuration_data(cfg) == []


def test_validate_accepts_datetime_objects_not_strings(service):
    """Pass datetime objects directly (some admin code paths do this) —
    should compare correctly without trying to parse them as strings."""
    cfg = _full_valid_config(
        application_start_date=datetime(2025, 8, 1),
        application_end_date=datetime(2025, 9, 1),
    )
    assert service.validate_configuration_data(cfg) == []


# ─── calculate_application_score ─────────────────────────────────────


def test_calculate_score_no_criteria_returns_zero(service):
    """No scoring_criteria configured ⇒ 0.0 (don't crash, return baseline)."""
    config = SimpleNamespace(scoring_criteria=None, get_scoring_criteria=lambda: {})
    assert service.calculate_application_score(config, {}) == 0.0


def test_calculate_score_weighted_normalization(service):
    """Two criteria, equal weights, scores 80/40 → normalized average 60.
    The function returns total_weighted/total_weight * 100 — sanity check
    the weighting math."""
    config = SimpleNamespace(
        scoring_criteria={"placeholder": "non-falsy"},
        get_scoring_criteria=lambda: {
            "gpa": {"weight": 1.0, "max_score": 100},
            "interview": {"weight": 1.0, "max_score": 100},
        },
    )
    app_data = {"score_gpa": 80, "score_interview": 40}
    result = service.calculate_application_score(config, app_data)
    # (80*1 + 40*1) / (1+1) * 100 = 6000 — yes, the implementation
    # multiplies the normalized fraction by 100 producing a >100 number
    # when raw scores are not on a 0-1 scale. Pinning current behavior so
    # any future fix is intentional.
    assert result == 6000.0


def test_calculate_score_caps_raw_score_at_max(service):
    """Raw score above max_score is capped — pinning the min() guard."""
    config = SimpleNamespace(
        scoring_criteria={"x": "y"},
        get_scoring_criteria=lambda: {"gpa": {"weight": 1.0, "max_score": 100}},
    )
    result = service.calculate_application_score(config, {"score_gpa": 999})
    # min(999, 100) * 1.0 / 1.0 * 100 = 10000.0
    assert result == 10000.0


def test_calculate_score_zero_total_weight_returns_zero(service):
    """If all weights are 0 (config bug), don't divide by zero — return 0.0."""
    config = SimpleNamespace(
        scoring_criteria={"x": "y"},
        get_scoring_criteria=lambda: {"gpa": {"weight": 0.0, "max_score": 100}},
    )
    assert service.calculate_application_score(config, {"score_gpa": 80}) == 0.0
