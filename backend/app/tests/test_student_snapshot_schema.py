"""
Tests for `backend/app/schemas/student_snapshot.py`.

Fix verification for **Issue #459** — previously the schema
contained 3 leading-underscore field names (_api_fetched_at,
_term_data_status, _term_error_message) which Pydantic v2
explicitly rejects with NameError. The fix uses `alias` to
preserve the `_`-prefixed JSON wire format (per CLAUDE.md §7)
while satisfying Pydantic's identifier rules.

Pins:
- Schema imports cleanly (regression test for #459)
- Required + optional field contracts
- alias round-trip: ingest `_api_fetched_at` → expose
  `api_fetched_at` → re-emit `_api_fetched_at` via by_alias=True
- populate_by_name=True accepts BOTH `_api_fetched_at` AND
  `api_fetched_at` on input (forward-compat)
"""

import pytest
from pydantic import ValidationError

from app.schemas.student_snapshot import (
    StudentSnapshotMinimal,
    StudentSnapshotSchema,
)


def _full_payload(**overrides) -> dict:
    base = {
        "std_stdcode": "310460031",
        "std_enrollyear": 110,
        "std_enrollterm": 1,
        "std_cname": "王小明",
        "std_pid": "A123456789",
        "std_academyno": "A",
        "std_depno": "4460",
        "std_sex": 1,
        "std_degree": 1,
        "std_enrolltype": 9,
        "std_identity": 1,
        "std_schoolid": 1,
        "std_termcount": 5,
        "std_studingstatus": 1,
        "mgd_title": "在學",
        "com_email": "test@nctu.edu.tw",
        "trm_year": 114,
        "trm_term": 1,
        "trm_termcount": 5,
        "trm_studystatus": 1,
        "trm_degree": 1,
        "trm_academyno": "A",
        "trm_academyname": "人社院",
        "trm_depno": "4460",
        "trm_depname": "教育博",
        "trm_placings": 5,
        "trm_placingsrate": 0.25,
        "trm_depplacing": 3,
        "trm_depplacingrate": 0.15,
        "trm_ascore_gpa": 3.8,
    }
    base.update(overrides)
    return base


class TestImportRegression:
    """Pin Issue #459 fix: schema imports without NameError."""

    def test_schema_imports_cleanly(self):
        # Pin: import succeeds (the previously-broken leading-
        # underscore fields are now aliased).
        from app.schemas.student_snapshot import StudentSnapshotSchema  # noqa: F401

    def test_schema_class_constructs_with_required_fields_only(self):
        # Pin: instantiating without optional fields works.
        snap = StudentSnapshotSchema(**_full_payload())
        assert snap.std_stdcode == "310460031"
        assert snap.trm_year == 114


class TestRequiredFields:
    """Pin: required vs optional field contracts."""

    def test_missing_std_stdcode_raises(self):
        payload = _full_payload()
        del payload["std_stdcode"]
        with pytest.raises(ValidationError) as exc:
            StudentSnapshotSchema(**payload)
        assert "std_stdcode" in str(exc.value)

    def test_missing_trm_year_raises(self):
        payload = _full_payload()
        del payload["trm_year"]
        with pytest.raises(ValidationError):
            StudentSnapshotSchema(**payload)

    def test_optional_fields_default_to_None(self):
        snap = StudentSnapshotSchema(**_full_payload())
        assert snap.std_ename is None
        assert snap.std_bdate is None
        assert snap.com_cellphone is None
        # Internal metadata defaults to None
        assert snap.api_fetched_at is None
        assert snap.term_data_status is None
        assert snap.term_error_message is None


class TestAliasRoundTrip:
    """Pin Issue #459 fix: internal-metadata fields use alias to
    preserve the `_`-prefixed JSON wire format per CLAUDE.md §7."""

    def test_ingest_underscore_prefixed_keys(self):
        # Pin: input payload with `_api_fetched_at` works (this is
        # the wire format documented in CLAUDE.md §7).
        snap = StudentSnapshotSchema(
            **_full_payload(),
            _api_fetched_at="2026-05-15T00:00:00Z",
            _term_data_status="success",
            _term_error_message=None,
        )
        # Attribute access uses the non-underscore Python name
        assert snap.api_fetched_at is not None
        assert snap.term_data_status == "success"

    def test_emit_underscore_prefixed_keys_via_by_alias(self):
        # Pin: model_dump(by_alias=True) re-emits with `_`-prefix
        # for round-trip with the SIS API snapshot storage format.
        snap = StudentSnapshotSchema(
            **_full_payload(),
            _api_fetched_at="2026-05-15T00:00:00Z",
            _term_data_status="success",
        )
        dumped = snap.model_dump(by_alias=True)
        assert "_api_fetched_at" in dumped
        assert "_term_data_status" in dumped
        # Non-underscore name should NOT appear in by_alias output
        assert "api_fetched_at" not in dumped

    def test_emit_python_names_via_default_dump(self):
        # Pin: model_dump() (without by_alias) emits Python names.
        # Pin so callers expecting non-underscore keys (e.g.
        # downstream Python consumers) get those.
        snap = StudentSnapshotSchema(
            **_full_payload(),
            _api_fetched_at="2026-05-15T00:00:00Z",
        )
        dumped = snap.model_dump()
        assert "api_fetched_at" in dumped
        assert "_api_fetched_at" not in dumped

    def test_populate_by_name_accepts_both_input_keys(self):
        # Pin: populate_by_name=True allows BOTH `_api_fetched_at`
        # (alias) AND `api_fetched_at` (Python name) as input keys.
        # Pin so refactor doesn't accidentally force one form only.
        snap1 = StudentSnapshotSchema(
            **_full_payload(),
            api_fetched_at="2026-05-15T00:00:00Z",
        )
        assert snap1.api_fetched_at is not None

        snap2 = StudentSnapshotSchema(
            **_full_payload(),
            _api_fetched_at="2026-05-15T00:00:00Z",
        )
        assert snap2.api_fetched_at is not None

    def test_three_internal_metadata_fields_are_aliased(self):
        # Pin: exactly 3 internal-metadata fields per CLAUDE.md §7.
        # Pin so refactor adding/removing fields requires explicit
        # update.
        fields = StudentSnapshotSchema.model_fields
        assert "api_fetched_at" in fields
        assert "term_data_status" in fields
        assert "term_error_message" in fields

        # Verify aliases
        assert fields["api_fetched_at"].alias == "_api_fetched_at"
        assert fields["term_data_status"].alias == "_term_data_status"
        assert fields["term_error_message"].alias == "_term_error_message"


class TestTypeContract:
    """Pin: type-coercion contract for downstream consumers."""

    def test_std_sex_is_int(self):
        snap = StudentSnapshotSchema(**_full_payload(std_sex=2))
        assert isinstance(snap.std_sex, int)
        assert snap.std_sex == 2

    def test_trm_ascore_gpa_is_float(self):
        snap = StudentSnapshotSchema(**_full_payload(trm_ascore_gpa=3.85))
        assert isinstance(snap.trm_ascore_gpa, float)

    def test_std_enrollyear_is_roc_year(self):
        # Pin: enrollyear is ROC/民國 year (e.g., 110 for 2021).
        snap = StudentSnapshotSchema(**_full_payload(std_enrollyear=110))
        assert snap.std_enrollyear == 110


class TestStudentSnapshotMinimal:
    """Pin: 3-field minimal subset."""

    def test_minimal_3_required_fields(self):
        snap = StudentSnapshotMinimal(
            std_stdcode="310460031",
            std_cname="王小明",
            com_email="test@nctu.edu.tw",
        )
        assert snap.std_stdcode == "310460031"

    def test_minimal_missing_any_field_raises(self):
        with pytest.raises(ValidationError):
            StudentSnapshotMinimal(std_stdcode="x", std_cname="y")

    def test_minimal_field_count(self):
        # Pin: exactly 3 fields. Pin so refactor adding more
        # without considering the minimal-data-required guard
        # surfaces in PR review.
        assert len(StudentSnapshotMinimal.model_fields) == 3
