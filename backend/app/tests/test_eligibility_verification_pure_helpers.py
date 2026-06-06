"""
Pure-helper tests for `EligibilityVerificationService` in
`app.services.eligibility_verification_service`.

These three helpers gate the eligibility-verification flow without
touching the DB:
- `_determine_student_type` maps degree codes → student type bucket
  ("phd" / "master" / "undergraduate"). Bug → wrong scholarship-type
  eligibility check (e.g., PhD-only scholarship opens to undergrads)
- `_get_student_value_for_rule` is the rule-engine field resolver.
  Bug → rules evaluate the wrong value or always-default
- `_check_academic_eligibility` runs the student-type allowlist check
  against ScholarshipType.eligible_student_types. Bug → bypass

These helpers run on EVERY application's eligibility check; subtle
regressions ripple to dozens of dashboards.

3 helpers (12 cases). Pure, no DB.
"""

import pytest

from app.models.scholarship import ScholarshipType
from app.services.eligibility_verification_service import EligibilityVerificationService


def _service() -> EligibilityVerificationService:
    """Construct without invoking __init__ (which requires a DB session).
    The pure helpers don't use self.db."""
    svc = object.__new__(EligibilityVerificationService)
    svc.db = None  # type: ignore[assignment]
    return svc


def _scholarship_type(**overrides) -> ScholarshipType:
    """Construct an in-memory ScholarshipType (no DB session)."""
    defaults = {
        "id": 1,
        "code": "TEST",
        "eligible_student_types": None,
    }
    defaults.update(overrides)
    # Construct via __init__ to get _sa_instance_state, then stuff __dict__
    # directly so vestigial/non-column keys are tolerated (bypasses descriptors).
    s = ScholarshipType()
    s.__dict__.update(defaults)
    return s


# ─── _determine_student_type ─────────────────────────────────────────


def test_student_type_phd_from_degree_1():
    """Pin: degree='1' → 'phd'. PhD students gate into PhD-only
    scholarships (NSTC, MOE 1-year, etc.)."""
    assert _service()._determine_student_type({"std_degree": "1"}) == "phd"


def test_student_type_master_from_degree_2():
    """Pin: degree='2' → 'master'."""
    assert _service()._determine_student_type({"std_degree": "2"}) == "master"


def test_student_type_undergraduate_default():
    """Pin: any other degree code → 'undergraduate'. Defensive default
    — covers degree='3' (bachelor's), missing field, empty string."""
    assert _service()._determine_student_type({"std_degree": "3"}) == "undergraduate"
    assert _service()._determine_student_type({"std_degree": ""}) == "undergraduate"
    assert _service()._determine_student_type({}) == "undergraduate"


# ─── _get_student_value_for_rule ─────────────────────────────────────


def test_rule_field_resolver_known_fields_mapping():
    """Pin: the field_mapping covers the 6 known rule fields. Pin all
    so a rule-engine refactor that renames a field surfaces here."""
    student = {"std_termcount": 4, "std_stdcode": "0856001", "std_depno": "4460"}
    svc = _service()

    assert svc._get_student_value_for_rule(student, "completed_terms") == 4
    assert svc._get_student_value_for_rule(student, "student_id") == "0856001"
    assert svc._get_student_value_for_rule(student, "department") == "4460"

    # GPA has a placeholder default until the external API is wired
    assert svc._get_student_value_for_rule(student, "gpa") == 3.0

    # class_ranking and grade are placeholders → None
    assert svc._get_student_value_for_rule(student, "class_ranking") is None
    assert svc._get_student_value_for_rule(student, "grade") is None


def test_rule_field_resolver_unknown_field_returns_none():
    """Pin: unknown field → None (not KeyError). Rule engine treats
    None as 'data unavailable' rather than crashing."""
    assert _service()._get_student_value_for_rule({}, "nonexistent_field") is None


def test_rule_field_resolver_completed_terms_default():
    """Pin: missing std_termcount → 1 (default first term). Defensive
    against incomplete student data — better to assume term 1 than
    crash the eligibility check."""
    assert _service()._get_student_value_for_rule({}, "completed_terms") == 1


def test_rule_field_resolver_student_id_empty_default():
    """Pin: missing std_stdcode → empty string. The downstream rule
    engine treats empty as 'fail' for any non-empty constraint."""
    assert _service()._get_student_value_for_rule({}, "student_id") == ""


# ─── _check_academic_eligibility ─────────────────────────────────────


@pytest.mark.asyncio
async def test_academic_eligibility_empty_student_data_fails():
    """Pin: empty student dict → (False, details with 'Missing student data')."""
    svc = _service()
    is_eligible, details = svc._check_academic_eligibility({}, _scholarship_type())
    # Empty student dict is falsy → fails
    assert is_eligible is False
    assert "Missing student data" in details["failures"]


@pytest.mark.asyncio
async def test_academic_eligibility_passes_when_type_in_allowlist():
    """Pin: student_type=phd + scholarship.eligible_student_types=['phd']
    → eligible. The student_type check is the primary gate."""
    svc = _service()
    student = {"std_degree": "1"}  # phd
    scholarship = _scholarship_type(eligible_student_types=["phd", "master"])
    is_eligible, details = svc._check_academic_eligibility(student, scholarship)
    assert is_eligible is True
    assert details["scores"]["student_type"] == "phd"


@pytest.mark.asyncio
async def test_academic_eligibility_fails_when_type_not_in_allowlist():
    """Pin: undergrad attempting PhD-only scholarship → fail with
    descriptive 'student_type_eligibility' check entry."""
    svc = _service()
    student = {"std_degree": "3"}  # undergraduate
    scholarship = _scholarship_type(eligible_student_types=["phd"])
    is_eligible, details = svc._check_academic_eligibility(student, scholarship)
    assert is_eligible is False
    assert any("Student type undergraduate not eligible" in f for f in details["failures"])
    # The check entry records both expected and actual types for debugging
    check_entries = [c for c in details["checks"] if c["check"] == "student_type_eligibility"]
    assert len(check_entries) == 1
    assert check_entries[0]["passed"] is False
    assert "phd" in check_entries[0]["details"]
    assert "undergraduate" in check_entries[0]["details"]


@pytest.mark.asyncio
async def test_academic_eligibility_no_type_restriction_allows_all():
    """Pin: scholarship without eligible_student_types restriction
    (None or empty) → student type check is skipped, eligibility
    passes on data-presence alone."""
    svc = _service()
    student = {"std_degree": "1"}
    scholarship = _scholarship_type(eligible_student_types=None)
    is_eligible, details = svc._check_academic_eligibility(student, scholarship)
    assert is_eligible is True
