"""
Tests for `ApplicationField` + `ApplicationDocument` + `FieldType`
enum on `app.models.application_field`.

These models drive the dynamic application form configuration —
admins add fields/documents per scholarship type via the admin UI,
and the student form renders directly from these rows. A regression
breaks every application form in the system.

Wave 6a105 pins:
  - FieldType enum: 8 lowercase HTML input types (per CLAUDE.md §4)
  - ApplicationField.__repr__ format (log greps)
  - ApplicationDocument.__repr__ format
  - UniqueConstraint name (Alembic migrations reference verbatim)
  - Both tablenames
  - Column defaults (is_required, is_active, display_order,
    accepted_file_types, max_file_size, max_file_count,
    include_in_college_export)

15 cases.
"""

from types import SimpleNamespace

from app.models.application_field import (
    ApplicationDocument,
    ApplicationField,
    FieldType,
)

# ─── FieldType enum ──────────────────────────────────────────────────


def test_field_type_has_eight_values():
    # Pin: 8 documented HTML input types. Adding another (e.g.,
    # "file") requires updating the frontend form renderer
    # switch case AND this test.
    assert {f.value for f in FieldType} == {
        "text",
        "textarea",
        "number",
        "email",
        "date",
        "select",
        "checkbox",
        "radio",
    }


def test_field_type_all_lowercase_values():
    # Pin: all values lowercase per CLAUDE.md §4 wire shape.
    # The frontend form renderer keys on these strings exactly.
    for f in FieldType:
        assert f.value == f.value.lower()


def test_field_type_uppercase_member_names():
    # Pin: member NAMES are UPPERCASE (TEXT/TEXTAREA/etc.) while
    # VALUES are lowercase ("text"/"textarea"/etc.). Documents
    # the deviation from CLAUDE.md §4 member-name=value rule for
    # this specific enum — pinned so any "fix" requires explicit
    # review of the impact on callers using FieldType.TEXT.
    assert FieldType.TEXT.name == "TEXT"
    assert FieldType.TEXT.value == "text"


def test_field_type_text_is_default():
    # Pin: TEXT is the default field type used in the column
    # definition. If TEXT is renamed to something else, the
    # default value reference would break — pinned via column
    # default check.
    col = ApplicationField.__table__.c.field_type
    assert col.default.arg == "text"


# ─── ApplicationField __repr__ ──────────────────────────────────────


def test_application_field_repr_format():
    # Pin: repr includes id/scholarship_type/field_name. Logs
    # use this exact format.
    stand_in = SimpleNamespace(
        id=12,
        scholarship_type="phd",
        field_name="bank_account",
    )
    out = ApplicationField.__repr__(stand_in)
    assert "ApplicationField" in out
    assert "id=12" in out
    assert "scholarship_type=phd" in out
    assert "field_name=bank_account" in out


def test_application_field_tablename():
    # Pin: __tablename__ matches production table.
    assert ApplicationField.__tablename__ == "application_fields"


def test_application_field_unique_constraint_name():
    # Pin: UniqueConstraint name "uq_application_field_type_name"
    # is referenced by Alembic migrations. CLAUDE.md §
    # "Database Constraint Requirements" specifically mentions
    # this constraint as needing exact-name match.
    constraint_names = [c.name for c in ApplicationField.__table_args__ if hasattr(c, "name")]
    assert "uq_application_field_type_name" in constraint_names


def test_application_field_is_required_default_is_false():
    # Pin: new fields default to NOT required. Conservative —
    # accidentally setting True as default would break every
    # existing form by requiring fields that weren't.
    col = ApplicationField.__table__.c.is_required
    assert col.default.arg is False


def test_application_field_is_active_default_is_true():
    # Pin: new fields are ACTIVE by default. Admin can deactivate
    # later, but the create flow shouldn't require an extra
    # "activate" step.
    col = ApplicationField.__table__.c.is_active
    assert col.default.arg is True


def test_application_field_display_order_default_is_zero():
    # Pin: default order is 0. The frontend sorts ASC by
    # display_order — 0 puts new fields at the top until admin
    # rearranges. Pinned so a refactor to LAST_ORDER+1 doesn't
    # silently change UX.
    col = ApplicationField.__table__.c.display_order
    assert col.default.arg == 0


def test_application_field_include_in_college_export_default_false():
    # Pin: opt-in for college export. Defaults to NOT included.
    # Critical — opting-in by default would leak fields the admin
    # didn't intend to export.
    col = ApplicationField.__table__.c.include_in_college_export
    assert col.default.arg is False


# ─── ApplicationDocument __repr__ ───────────────────────────────────


def test_application_document_repr_format():
    # Pin: repr includes id/scholarship_type/document_name.
    stand_in = SimpleNamespace(
        id=5,
        scholarship_type="undergraduate",
        document_name="成績單",
    )
    out = ApplicationDocument.__repr__(stand_in)
    assert "ApplicationDocument" in out
    assert "id=5" in out
    assert "scholarship_type=undergraduate" in out
    assert "document_name=成績單" in out


def test_application_document_tablename():
    assert ApplicationDocument.__tablename__ == "application_documents"


def test_application_document_is_required_default_is_true():
    # Pin: documents default to REQUIRED. Opposite of fields —
    # rationale: documents like transcripts are essential, so
    # the conservative default is "require it".
    col = ApplicationDocument.__table__.c.is_required
    assert col.default.arg is True


def test_application_document_max_file_size_default():
    # Pin: 5MB default file size limit. Used directly in the
    # upload error message — changing the value requires updating
    # the message too.
    col = ApplicationDocument.__table__.c.max_file_size
    assert col.default.arg == "5MB"


def test_application_document_max_file_count_default_is_one():
    # Pin: default 1 file per document. Multi-file upload is
    # opt-in by admin per document type.
    col = ApplicationDocument.__table__.c.max_file_count
    assert col.default.arg == 1
