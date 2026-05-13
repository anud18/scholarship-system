"""
Pure-function tests for `RosterService` helpers.

Payment-roster generation drives the actual money flow — labels and
semester inferences feed into downstream financial-period grouping
that the finance team uses to issue payments. Silent bugs here cause
payments routed to the wrong semester or duplicate roster codes.

3 pure helpers covered (16 cases):
- `generate_period_label`            : RosterCycle + date → label string
- `_extract_semester_from_period`    : label → 'first' | 'second' | None
- `_serialize_verification_result`   : dict with enums/datetimes → JSON-safe
"""

import enum
from datetime import datetime

import pytest

from app.models.payment_roster import RosterCycle
from app.services.roster_service import RosterService


@pytest.fixture
def service():
    return RosterService(db=None)  # type: ignore[arg-type]


# ─── generate_period_label ───────────────────────────────────────────


def test_period_label_monthly(service):
    """Monthly cycle ⇒ YYYY-MM with zero-padded month."""
    assert service.generate_period_label(RosterCycle.MONTHLY, datetime(2025, 1, 15)) == "2025-01"
    assert service.generate_period_label(RosterCycle.MONTHLY, datetime(2025, 12, 1)) == "2025-12"


def test_period_label_semi_yearly_h1(service):
    """Jan–Jun ⇒ H1."""
    assert service.generate_period_label(RosterCycle.SEMI_YEARLY, datetime(2025, 1, 1)) == "2025-H1"
    assert service.generate_period_label(RosterCycle.SEMI_YEARLY, datetime(2025, 6, 30)) == "2025-H1"


def test_period_label_semi_yearly_h2(service):
    """Jul–Dec ⇒ H2 (Jul boundary case)."""
    assert service.generate_period_label(RosterCycle.SEMI_YEARLY, datetime(2025, 7, 1)) == "2025-H2"
    assert service.generate_period_label(RosterCycle.SEMI_YEARLY, datetime(2025, 12, 31)) == "2025-H2"


def test_period_label_yearly(service):
    """Yearly cycle ⇒ YYYY only."""
    assert service.generate_period_label(RosterCycle.YEARLY, datetime(2025, 5, 15)) == "2025"


def test_period_label_unsupported_cycle_raises(service):
    """Unsupported cycle ⇒ ValueError (no silent fallback to empty label,
    which would corrupt the roster_code uniqueness invariant)."""

    class _FakeCycle(enum.Enum):
        WEEKLY = "weekly"

    with pytest.raises(ValueError, match="Unsupported roster cycle"):
        service.generate_period_label(_FakeCycle.WEEKLY, datetime(2025, 1, 1))


# ─── _extract_semester_from_period ───────────────────────────────────


def test_extract_semester_h1_suffix(service):
    assert service._extract_semester_from_period("2025-H1") == "first"


def test_extract_semester_h2_suffix(service):
    assert service._extract_semester_from_period("2025-H2") == "second"


def test_extract_semester_monthly_summer_is_second(service):
    """Months 2–7 belong to the 'second' (spring/summer) semester."""
    assert service._extract_semester_from_period("2025-03") == "second"
    assert service._extract_semester_from_period("2025-07") == "second"


def test_extract_semester_monthly_fall_winter_is_first(service):
    """Months 8–12 and 1 (Jan, mid-year start) ⇒ 'first' (fall) semester."""
    assert service._extract_semester_from_period("2025-09") == "first"
    assert service._extract_semester_from_period("2025-01") == "first"


def test_extract_semester_yearly_label_returns_none(service):
    """Yearly label ('2025') has no semester info → None."""
    assert service._extract_semester_from_period("2025") is None


def test_extract_semester_unparseable_returns_none(service):
    """Non-integer month component falls back to None (silent — caller can
    treat None as 'unknown semester')."""
    assert service._extract_semester_from_period("2025-XX") is None


# ─── _serialize_verification_result ──────────────────────────────────


class _SampleStatus(enum.Enum):
    OK = "ok"


def test_serialize_verification_returns_none_for_empty(service):
    assert service._serialize_verification_result(None) is None
    # Truthy check inside helper — empty dict short-circuits to None.
    assert service._serialize_verification_result({}) is None


def test_serialize_verification_unwraps_enum_values(service):
    result = service._serialize_verification_result({"status": _SampleStatus.OK})
    assert result == {"status": "ok"}


def test_serialize_verification_isoformats_datetime(service):
    dt = datetime(2025, 6, 15, 12, 30, 45)
    result = service._serialize_verification_result({"checked_at": dt})
    assert result == {"checked_at": "2025-06-15T12:30:45"}


def test_serialize_verification_recurses_into_nested_dicts_and_lists(service):
    result = service._serialize_verification_result(
        {
            "checks": [{"status": _SampleStatus.OK, "ts": datetime(2025, 1, 1)}],
            "scalar": 42,
        }
    )
    assert result == {
        "checks": [{"status": "ok", "ts": "2025-01-01T00:00:00"}],
        "scalar": 42,
    }


def test_serialize_verification_preserves_primitives(service):
    """Strings/ints/floats/bools pass through unchanged."""
    result = service._serialize_verification_result({"a": 1, "b": "x", "c": 3.14, "d": True})
    assert result == {"a": 1, "b": "x", "c": 3.14, "d": True}
