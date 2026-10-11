"""
Pure-function tests for `ApplicationFieldService._create_fixed_*` builders.

These builders produce the "fixed" portion of every scholarship's
application form — the bank account field and required documents that
appear regardless of scholarship type. Bugs here either:
- Lock students out (wrong field_name breaks form-data lookup), or
- Display the wrong label / help_text — surface-level but visible noise.

3 builders covered (8 cases):
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


# ─── no per-user data ────────────────────────────────────────────────


def test_builders_carry_no_per_user_values(service):
    """The built items end up in the shared form-config cache, so they must
    never carry a profile value — that is how one student's 郵局帳號 and
    指導教授 reached every other student (#1443)."""
    items = [
        service._create_fixed_bank_account_field(),
        service._create_fixed_bank_statement_document(),
        *service._create_fixed_advisor_fields(),
    ]
    for item in items:
        assert "prefill_value" not in item
        assert "existing_file_url" not in item
