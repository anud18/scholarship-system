"""
Tests for default values in `app/schemas/application_field.py`.

Wave 6a26 covered the `validate_export_flag` model validator
(include_in_college_export only legal when field_type='text'). This
wave covers the OTHER pieces — defaults that gate admin form
behaviour and the ApplicationDocument schemas that share the module.

Non-obvious defaults pinned:

  - **ApplicationFieldBase.field_type defaults to TEXT** — most
    admin-created fields are free-text. Flipping the default would
    silently auto-classify new fields as select/checkbox.

  - **is_required=False** for ApplicationFieldBase (a new field is
    optional by default) vs **is_required=True** for
    ApplicationDocumentBase (a new document IS required by
    default — admin must opt-out). Pin the divergence side-by-side
    so a "unify these" refactor breaks loudly.

  - **ApplicationDocument defaults**: accepted_file_types=["PDF"],
    max_file_size="5MB", max_file_count=1. These are the system-
    wide safe-defaults that prevent admin error from accidentally
    accepting 100MB EXEs.

  - **export_column_label max_length=200** on both Base and Update.

13 cases.
"""

import pytest
from pydantic import ValidationError

from app.models.application_field import FieldType
from app.schemas.application_field import (
    ApplicationDocumentBase,
    ApplicationDocumentUpdate,
    ApplicationFieldBase,
    ApplicationFieldUpdate,
)

# ─── ApplicationFieldBase defaults ──────────────────────────────────


def _field_payload():
    return dict(
        scholarship_type="general",
        field_name="essay",
        field_label="申請動機",
    )


def test_field_type_defaults_to_text():
    # Pin: TEXT is the safest default (free-form input). Flipping
    # would surface as "select with no options".
    f = ApplicationFieldBase(**_field_payload())
    assert f.field_type == FieldType.TEXT.value


def test_field_is_required_defaults_false():
    # Pin: new fields are OPTIONAL by default — admin opts in to
    # required. Diverges from ApplicationDocument (required=True
    # by default). Pinned side-by-side so the divergence isn't
    # accidentally aligned.
    f = ApplicationFieldBase(**_field_payload())
    assert f.is_required is False


def test_field_display_order_defaults_zero():
    # Pin: 0 lets the admin add fields to the top of the form by
    # default. Flipping would auto-append to the bottom.
    f = ApplicationFieldBase(**_field_payload())
    assert f.display_order == 0


def test_field_is_active_defaults_true():
    # Pin: new fields render on the form by default. Flipping would
    # silently hide every newly-added field.
    f = ApplicationFieldBase(**_field_payload())
    assert f.is_active is True


def test_field_include_in_college_export_defaults_false():
    # Pin: most fields are NOT exported to the college roster.
    # Flipping would leak free-text student input (e.g. essays)
    # into the export Excel by default — privacy issue.
    f = ApplicationFieldBase(**_field_payload())
    assert f.include_in_college_export is False


def test_field_export_column_label_max_length_200():
    with pytest.raises(ValidationError):
        ApplicationFieldBase(
            **_field_payload(),
            field_type=FieldType.TEXT.value,
            include_in_college_export=True,
            export_column_label="x" * 201,
        )


def test_field_required_anchor_fields():
    # Pin: scholarship_type / field_name / field_label all required.
    with pytest.raises(ValidationError):
        ApplicationFieldBase(  # type: ignore[call-arg]
            scholarship_type="general",
            field_name="essay",
            # field_label missing
        )


# ─── ApplicationFieldUpdate PATCH ───────────────────────────────────


def test_field_update_export_column_label_max_length_200():
    # Pin: same 200 cap applies on Update. PATCH semantics — most
    # fields optional, but the bound is enforced when supplied.
    with pytest.raises(ValidationError):
        ApplicationFieldUpdate(export_column_label="x" * 201)


# ─── ApplicationDocumentBase defaults (DIVERGENT) ──────────────────


def _doc_payload():
    return dict(scholarship_type="general", document_name="成績單")


def test_document_is_required_defaults_true():
    # Pin: documents are REQUIRED by default (opposite of fields).
    # Most attachments are mandatory; admin opts-out for optional
    # documents (e.g. teacher recommendation).
    d = ApplicationDocumentBase(**_doc_payload())
    assert d.is_required is True


def test_document_accepted_file_types_defaults_pdf_only():
    # Pin: PDF-only by default. Flipping to allow .exe / .docm
    # would silently weaken the upload-validation surface.
    d = ApplicationDocumentBase(**_doc_payload())
    assert d.accepted_file_types == ["PDF"]


def test_document_max_file_size_defaults_5MB():
    # Pin: 5MB cap. Bumping silently changes infrastructure cost
    # (MinIO storage / proxy timeouts). Pin so a change forces
    # explicit review.
    d = ApplicationDocumentBase(**_doc_payload())
    assert d.max_file_size == "5MB"


def test_document_max_file_count_defaults_1():
    # Pin: single-file by default. Multi-file uploads need
    # explicit opt-in (e.g. transcript with multiple pages).
    d = ApplicationDocumentBase(**_doc_payload())
    assert d.max_file_count == 1


def test_document_required_anchor_fields():
    # Pin: scholarship_type + document_name required.
    with pytest.raises(ValidationError):
        ApplicationDocumentBase(  # type: ignore[call-arg]
            scholarship_type="general",
            # document_name missing
        )
