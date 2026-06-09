"""
Pure-function tests for `ScholarshipService` helpers.

These helpers wrap GPA coercion used by the eligibility path. Silent
bugs here would either over-validate (rejecting valid applications)
or under-validate (letting incomplete applications through to admin
queues).

1 helper covered (6 cases):
- `_safe_gpa_to_decimal` : type-tolerant Decimal coercion
"""

from decimal import Decimal

import pytest

from app.services.scholarship_service import ScholarshipService


@pytest.fixture
def service():
    """No DB I/O in the helpers — None session is fine."""
    return ScholarshipService(db=None)  # type: ignore[arg-type]


# ─── _safe_gpa_to_decimal ─────────────────────────────────────────────


def test_safe_gpa_string_to_decimal(service):
    """SIS sometimes returns GPA as a string — must coerce, not crash."""
    assert service._safe_gpa_to_decimal("3.85") == Decimal("3.85")


def test_safe_gpa_int_to_decimal(service):
    assert service._safe_gpa_to_decimal(4) == Decimal("4")


def test_safe_gpa_float_to_decimal(service):
    """Float → str → Decimal round-trip avoids the float precision trap."""
    assert service._safe_gpa_to_decimal(3.5) == Decimal("3.5")


def test_safe_gpa_already_decimal_passthrough(service):
    """Decimal in ⇒ same Decimal out (no spurious conversion)."""
    d = Decimal("3.95")
    assert service._safe_gpa_to_decimal(d) is d


def test_safe_gpa_unparseable_string_returns_zero(service):
    """Invalid string → exception caught → 0.0 (defensive default that
    won't accidentally let an applicant pass a GPA threshold)."""
    assert service._safe_gpa_to_decimal("not-a-gpa") == Decimal("0.0")


def test_safe_gpa_unexpected_type_returns_zero(service):
    """List / dict / None → 0.0 (logs a warning, returns the safe default)."""
    assert service._safe_gpa_to_decimal([3.5]) == Decimal("0.0")
    assert service._safe_gpa_to_decimal(None) == Decimal("0.0")
