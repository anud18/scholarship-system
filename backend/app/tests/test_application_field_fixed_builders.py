"""
Pure-function tests for `ApplicationFieldService._create_fixed_*` builders.

These builders produce the "fixed" portion of every scholarship's
application form — the bank account field and required documents that
appear regardless of scholarship type. Bugs here either:
- Lock students out (wrong field_name breaks form-data lookup), or
- Display the wrong label / help_text — surface-level but visible noise.

3 builders covered (10 cases):
- `_create_fixed_bank_account_field`         : postal_account text input
- `_create_fixed_bank_statement_document`    : 存摺封面 file upload
- `_create_fixed_advisor_fields`             : 3-field group (name/email/id)
"""

import pytest

from app.services.application_field_service import ApplicationFieldService


@pytest.fixture
def service():
    return ApplicationFieldService(db=None)  # type: ignore[arg-type]


# ─── _create_fixed_bank_account_field ────────────────────────────────


def test_bank_account_field_required_keys_present(service):
    """Pin the minimum field-name set so form-data lookup logic depending
    on these keys won't break."""
    field = service._create_fixed_bank_account_field()
    for key in (
        "field_name",
        "field_label",
        "field_type",
        "is_required",
        "is_fixed",
        "max_length",
        "display_order",
    ):
        assert key in field, f"missing key: {key}"


def test_bank_account_field_canonical_field_name(service):
    """field_name must remain 'postal_account' — the rest of the codebase
    (form prefill, validation, export) uses this exact key. A rename here
    silently breaks every consumer."""
    field = service._create_fixed_bank_account_field()
    assert field["field_name"] == "postal_account"
    assert field["field_type"] == "text"
    assert field["is_required"] is True
    assert field["is_fixed"] is True


def test_bank_account_field_prefill_from_user_profile(service):
    """prefill_data['account_number'] flows into prefill_value; missing
    prefill (None) ⇒ empty string (don't propagate None into the JSX)."""
    field = service._create_fixed_bank_account_field(prefill_data={"account_number": "0001234567"})
    assert field["prefill_value"] == "0001234567"

    field_no_prefill = service._create_fixed_bank_account_field(prefill_data=None)
    assert field_no_prefill["prefill_value"] == ""


# ─── _create_fixed_bank_statement_document ───────────────────────────


def test_bank_statement_doc_accepts_pdf_and_images(service):
    """File type allowlist — these four extensions are what the form
    accepts. Adding more types is fine but removing PDF or any of the
    image types would break legitimate uploads."""
    doc = service._create_fixed_bank_statement_document()
    assert set(doc["accepted_file_types"]) == {"PDF", "JPG", "JPEG", "PNG"}
    assert doc["max_file_count"] == 1
    assert doc["max_file_size"] == "10MB"


def test_bank_statement_doc_is_fixed_and_required(service):
    doc = service._create_fixed_bank_statement_document()
    assert doc["is_fixed"] is True
    assert doc["is_required"] is True


def test_bank_statement_doc_existing_file_url_from_prefill(service):
    """If the user has a previously-uploaded photo, surface it via
    existing_file_url — frontend uses this to render a preview thumbnail
    so the student knows what they're replacing."""
    doc = service._create_fixed_bank_statement_document(prefill_data={"bank_document_photo_url": "https://x/photo.jpg"})
    assert doc["existing_file_url"] == "https://x/photo.jpg"


# ─── _create_fixed_advisor_fields ────────────────────────────────────


def test_advisor_fields_returns_three_fields(service):
    """Pin the count — advisor section is 3 fields (name, email, NYCU ID).
    Removing/adding a field changes the form layout for every renewal."""
    fields = service._create_fixed_advisor_fields()
    assert len(fields) == 3

    field_names = [f["field_name"] for f in fields]
    assert field_names == ["advisor_name", "advisor_email", "advisor_nycu_id"]


def test_advisor_fields_display_order_is_consecutive(service):
    """Display order increments by 1 from the start value."""
    fields = service._create_fixed_advisor_fields(display_order_start=10)
    assert [f["display_order"] for f in fields] == [10, 11, 12]


def test_advisor_fields_email_field_uses_email_type(service):
    """The email field's field_type='email' enables browser-side validation
    + the @ symbol in the keyboard layout on mobile. Pin so a typo to
    'text' doesn't silently break that UX."""
    fields = service._create_fixed_advisor_fields()
    email_field = next(f for f in fields if f["field_name"] == "advisor_email")
    assert email_field["field_type"] == "email"


def test_advisor_fields_prefill_each_field_separately(service):
    """Each field reads its own key from prefill_data — name, email,
    nycu_id are independent."""
    prefill = {"advisor_name": "Prof Wang", "advisor_email": "wang@nycu.edu.tw", "advisor_nycu_id": "EE0001"}
    fields = service._create_fixed_advisor_fields(prefill_data=prefill)

    expected = {
        "advisor_name": "Prof Wang",
        "advisor_email": "wang@nycu.edu.tw",
        "advisor_nycu_id": "EE0001",
    }
    for f in fields:
        assert f["prefill_value"] == expected[f["field_name"]]
