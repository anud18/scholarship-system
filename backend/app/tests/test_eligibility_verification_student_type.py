"""
Tests for the remaining pure helpers on `EligibilityVerificationService`:

  - **_determine_student_type(student_data)**: Maps `std_degree` code
    to one of "phd" / "master" / "undergraduate". Critical because
    downstream rules branch on student_type (e.g., grad-only
    scholarships).

  - **_get_student_value_for_rule(student, field_name)**: Resolves a
    rule's field_name against the student data dict. Returns
    documented defaults for fields that need external-API enrichment
    (gpa=3.0, class_ranking=None, grade=None). Unknown field_name
    returns None.

Wave 6a43 covered other helpers on the same service. This wave
fills the gap for degree-code mapping + field-mapping.

11 cases.
"""

from unittest.mock import MagicMock

import pytest

from app.services.eligibility_verification_service import EligibilityVerificationService


@pytest.fixture
def service():
    # Constructor only needs the db handle for async DB ops; pure
    # helpers don't touch it.
    return EligibilityVerificationService(db=MagicMock())


# ─── _determine_student_type ────────────────────────────────────────


def test_student_type_degree_1_is_phd(service):
    # Pin: degree "1" → "phd". Documents NYCU SIS degree code
    # convention. Code "1" is the PhD bucket.
    assert service._determine_student_type({"std_degree": "1"}) == "phd"


def test_student_type_degree_2_is_master(service):
    # Pin: degree "2" → "master".
    assert service._determine_student_type({"std_degree": "2"}) == "master"


def test_student_type_other_codes_default_to_undergraduate(service):
    # Pin: anything other than "1" or "2" falls through to
    # undergraduate. Includes "3", "4", "B", etc. Conservative
    # default avoids accidentally elevating an undergrad into a
    # grad-only scholarship pool.
    for code in ["3", "4", "B", "0", "", "9"]:
        assert service._determine_student_type({"std_degree": code}) == "undergraduate"


def test_student_type_missing_degree_defaults_to_undergraduate(service):
    # Pin: missing std_degree key → undergraduate (the .get(..., "")
    # default falls through the elif chain).
    assert service._determine_student_type({}) == "undergraduate"


def test_student_type_none_degree_defaults_to_undergraduate(service):
    # Pin: explicit None for std_degree → undergraduate. Defensive
    # against API returning null degree code.
    assert service._determine_student_type({"std_degree": None}) == "undergraduate"


# ─── _get_student_value_for_rule ────────────────────────────────────


def test_field_gpa_returns_default_3_0(service):
    # Pin: gpa default is 3.0 — this is a TODO ("should be fetched
    # from external API") that the team still depends on as a
    # placeholder pre-rollout. Pin so any change forces an explicit
    # review (an unintended lift to 0.0 would silently fail all GPA
    # rules; a lift to 4.0 would silently pass all of them).
    assert service._get_student_value_for_rule({}, "gpa") == 3.0


def test_field_class_ranking_returns_none(service):
    # Pin: class_ranking placeholder — None. Rule engine must skip
    # this field when value is None (verified separately).
    assert service._get_student_value_for_rule({}, "class_ranking") is None


def test_field_grade_returns_none(service):
    # Pin: grade placeholder — None (calculated from enrollment).
    assert service._get_student_value_for_rule({}, "grade") is None


def test_field_completed_terms_reads_from_student_data(service):
    # Pin: completed_terms reads std_termcount with default 1.
    assert service._get_student_value_for_rule({"std_termcount": 5}, "completed_terms") == 5


def test_field_completed_terms_default_when_missing(service):
    # Pin: default 1 (not 0) — a fresh student has completed 1 term
    # by the time they apply.
    assert service._get_student_value_for_rule({}, "completed_terms") == 1


def test_field_student_id_reads_std_stdcode(service):
    # Pin: student_id rule maps to std_stdcode (the SIS roll-number),
    # NOT to internal app user_id. Rules that compare against the
    # SIS-side ID would silently fail otherwise.
    assert service._get_student_value_for_rule({"std_stdcode": "310460031"}, "student_id") == "310460031"


def test_field_student_id_missing_returns_empty_string(service):
    # Pin: missing std_stdcode → "" (the default in .get(..., "")).
    # The rule engine treats empty string as no-match.
    assert service._get_student_value_for_rule({}, "student_id") == ""


def test_field_department_reads_std_depno(service):
    # Pin: department maps to std_depno (the SIS department code,
    # not name). Rules comparing to department codes work; rules
    # comparing to localized names would silently fail.
    assert service._get_student_value_for_rule({"std_depno": "4460"}, "department") == "4460"


def test_field_unknown_returns_none(service):
    # Pin: unknown field_name → None via dict.get fallback. The
    # rule engine treats None as a soft-pass (rule cannot be
    # evaluated) — pin so rules referencing a typo'd field name
    # don't accidentally evaluate to a hardcoded value.
    assert service._get_student_value_for_rule({"std_stdcode": "x"}, "totally_unknown_field") is None
