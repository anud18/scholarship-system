"""
Pure-function tests for `ScholarshipService` helpers.

These helpers wrap GPA coercion, sub-type code extraction, and the
required-document check used by the application submission path.
Silent bugs here would either over-validate (rejecting valid
applications) or under-validate (letting incomplete applications
through to admin queues).

4 helpers covered (17 cases):
- `_safe_gpa_to_decimal`            : type-tolerant Decimal coercion
- `_extract_sub_type`               : code-substring → sub-type slug
- `_calculate_initial_priority`     : +100 renewal bonus
- `_validate_application_documents` : required_documents vs uploaded
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.scholarship_service import ScholarshipApplicationService, ScholarshipService


@pytest.fixture
def service():
    """No DB I/O in the helpers — None session is fine."""
    return ScholarshipService(db=None)  # type: ignore[arg-type]


@pytest.fixture
def app_service():
    return ScholarshipApplicationService(db=None)  # type: ignore[arg-type]


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


# ─── _extract_sub_type ────────────────────────────────────────────────


def test_extract_sub_type_nstc(app_service):
    assert app_service._extract_sub_type("PHD_NSTC_2024") == "nstc"


def test_extract_sub_type_moe_1w(app_service):
    assert app_service._extract_sub_type("phd_moe_1w") == "moe_1w"


def test_extract_sub_type_moe_2w(app_service):
    assert app_service._extract_sub_type("PHD_MOE_2W_2025") == "moe_2w"


def test_extract_sub_type_default_general(app_service):
    """Code without a recognized sub-type substring ⇒ 'general' (default
    track, matches the convention in CLAUDE.md §4 — sub-types are
    configuration-driven, not enum-constrained)."""
    assert app_service._extract_sub_type("undergrad_academic") == "general"
    assert app_service._extract_sub_type("") == "general"


# ─── _calculate_initial_priority ──────────────────────────────────────


def test_initial_priority_renewal_gets_bonus(app_service):
    """Renewal applications get +100 priority (they queue ahead of new apps)."""
    assert app_service._calculate_initial_priority(is_renewal=True, student_id=42) == 100


def test_initial_priority_new_application_is_zero(app_service):
    """Non-renewal starts at 0 (additional factors not yet implemented)."""
    assert app_service._calculate_initial_priority(is_renewal=False, student_id=42) == 0


# ─── _validate_application_documents ──────────────────────────────────


def _app(*, required_docs, uploaded_docs):
    """Duck-typed Application with just the attributes the helper reads."""
    return SimpleNamespace(
        scholarship_type=SimpleNamespace(required_documents=required_docs),
        files=[SimpleNamespace(document_type=d) for d in uploaded_docs],
    )


def test_validate_docs_all_present(app_service):
    app = _app(required_docs=["transcript", "bank"], uploaded_docs=["transcript", "bank"])
    ok, msg = app_service._validate_application_documents(app)
    assert ok is True
    assert "All required documents uploaded" in msg


def test_validate_docs_missing_one(app_service):
    """Missing docs are listed by name in the failure message — admins use
    this to know what to follow up on."""
    app = _app(required_docs=["transcript", "bank"], uploaded_docs=["transcript"])
    ok, msg = app_service._validate_application_documents(app)
    assert ok is False
    assert "bank" in msg
    assert "Missing required documents" in msg


def test_validate_docs_extra_uploads_dont_fail(app_service):
    """Uploading extras (beyond required) is fine — only missing matters."""
    app = _app(required_docs=["transcript"], uploaded_docs=["transcript", "bonus", "cover_letter"])
    ok, _ = app_service._validate_application_documents(app)
    assert ok is True


def test_validate_docs_none_required_is_ok(app_service):
    """No required docs configured ⇒ trivially valid (handles the edge
    case where scholarship_type.required_documents is None)."""
    app = SimpleNamespace(
        scholarship_type=SimpleNamespace(required_documents=None),
        files=[],
    )
    ok, _ = app_service._validate_application_documents(app)
    assert ok is True
