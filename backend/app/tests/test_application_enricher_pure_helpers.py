"""
Pure-function tests for `ApplicationEnricherService._is_student_data_missing`.

The enricher service decides whether to re-fetch student data from the
external SIS API when displaying applications to reviewers. If
`_is_student_data_missing` returns False (data looks OK) but actually
critical fields are absent, reviewers see incomplete cards. If it
returns True too eagerly, we burn SIS API calls and rate-limit budget.

Why so many field-name aliases? The student_data JSON snapshot lives
across multiple schema migrations:
- `nycu_id` / `std_stdcode` / `student_id` — three names for student ID
- `name` / `std_cname` / `student_name` — three names for name

Pinning the OR-chain so a future schema cleanup doesn't accidentally
drop one of the aliases used in old applications.

1 helper covered (10 cases).
"""

import pytest

from app.services.application_enricher_service import ApplicationEnricherService


@pytest.fixture
def service():
    return ApplicationEnricherService(db=None)  # type: ignore[arg-type]


def test_missing_when_data_is_none(service):
    """None/empty data ⇒ missing — short-circuit, don't crash on .get()."""
    assert service._is_student_data_missing(None) is True
    assert service._is_student_data_missing({}) is True


def test_present_with_canonical_nycu_id_and_name(service):
    """The canonical (newest schema) field names work."""
    data = {"nycu_id": "S12345", "name": "Alice"}
    assert service._is_student_data_missing(data) is False


def test_present_with_old_sis_field_names(service):
    """`std_stdcode` + `std_cname` is the original SIS API schema —
    old snapshots use this. Must still be recognized."""
    data = {"std_stdcode": "S12345", "std_cname": "張三"}
    assert service._is_student_data_missing(data) is False


def test_present_with_intermediate_schema(service):
    """The middle-generation schema used `student_id` + `student_name`."""
    data = {"student_id": "S12345", "student_name": "Bob"}
    assert service._is_student_data_missing(data) is False


def test_missing_when_only_id_no_name(service):
    """Need BOTH id and name — only id ⇒ missing."""
    assert service._is_student_data_missing({"nycu_id": "S1"}) is True


def test_missing_when_only_name_no_id(service):
    """Only name ⇒ missing."""
    assert service._is_student_data_missing({"name": "Alice"}) is True


def test_empty_string_treated_as_missing(service):
    """Empty string is falsy → missing. Don't pass empty-ID/empty-name
    through as 'present' just because the keys exist."""
    assert service._is_student_data_missing({"nycu_id": "", "name": ""}) is True
    assert service._is_student_data_missing({"nycu_id": "S1", "name": ""}) is True


def test_mixed_aliases_id_from_one_name_from_another(service):
    """nycu_id can come from the new schema and the name from the legacy
    SIS schema — common in partial-migration state."""
    assert service._is_student_data_missing({"nycu_id": "S1", "std_cname": "Alice"}) is False


def test_extra_fields_dont_affect_decision(service):
    """The decision only cares about id + name presence — other fields
    don't matter."""
    data = {"nycu_id": "S1", "name": "X", "trm_year": 113, "gpa": 3.5}
    assert service._is_student_data_missing(data) is False


def test_unrelated_field_only_returns_missing(service):
    """Data is populated but doesn't have id OR name fields under any alias
    ⇒ treat as missing (force re-fetch)."""
    data = {"trm_year": 113, "trm_term": 1}
    assert service._is_student_data_missing(data) is True
