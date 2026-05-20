"""
Tests for `app/schemas/config_management.py`.

The schemas here back the admin /admin/config page where system
behaviour is tweaked at runtime (DB-driven feature flags, SMTP
config, API keys). The SECURITY-relevant default values are:

  - `is_sensitive=False` and `is_readonly=False` on
    ConfigurationItemSchema. A regression flipping either default
    would silently mark every new config sensitive (frontend masks
    the value, admins can't read what they set) or readonly (every
    new config locked from edit).
  - `force_recheck=False` on BankVerificationRequestSchema /
    BankVerificationBatchRequestSchema — re-verifying is rate-limited
    and slow; default must stay opt-in.
  - `requires_manual_review=False` on BankVerificationResultSchema —
    most verifications complete automatically; flipping the default
    would send every result to the manual-review queue.

Wave 6a51 covered the SECURITY-critical `sanitize_string_fields`
validator on BankVerificationResultSchema. This wave covers the
other schemas and their defaults.

20 cases pinning 10 schemas + their default-value invariants.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from app.models.system_setting import ConfigCategory, ConfigDataType
from app.schemas.config_management import (
    BankFieldComparisonSchema,
    BankVerificationBatchRequestSchema,
    BankVerificationBatchResultSchema,
    BankVerificationRequestSchema,
    BankVerificationResultSchema,
    ConfigurationBulkUpdateSchema,
    ConfigurationCategorySchema,
    ConfigurationCreateSchema,
    ConfigurationItemSchema,
    ConfigurationUpdateSchema,
    ConfigurationValidationResultSchema,
    ConfigurationValidationSchema,
)

# ─── ConfigurationItemSchema (read-side) ─────────────────────────────


def _item_kwargs():
    return dict(
        key="smtp.host",
        value="smtp.nycu.edu.tw",
        category=ConfigCategory.email,
        data_type=ConfigDataType.string,
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        updated_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )


def test_item_required_fields():
    # Pin: 6 required fields (key/value/category/data_type/created_at
    # /updated_at). Missing any would surface as a broken admin row.
    with pytest.raises(ValidationError):
        ConfigurationItemSchema(  # type: ignore[call-arg]
            key="x",
            value="y",
            category=ConfigCategory.email,
            # data_type missing
            created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
            updated_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        )


def test_item_is_sensitive_defaults_false():
    # Pin: most configs are NOT sensitive. Flipping the default would
    # mask every new config in the UI so admins can't read it back.
    obj = ConfigurationItemSchema(**_item_kwargs())
    assert obj.is_sensitive is False


def test_item_is_readonly_defaults_false():
    # Pin: most configs are editable. Flipping the default would lock
    # every new config from admin edit — silent permission downgrade.
    obj = ConfigurationItemSchema(**_item_kwargs())
    assert obj.is_readonly is False


def test_item_optional_metadata_fields():
    obj = ConfigurationItemSchema(**_item_kwargs())
    assert obj.description is None
    assert obj.validation_regex is None
    assert obj.default_value is None
    assert obj.last_modified_by is None


# ─── ConfigurationUpdateSchema / CreateSchema ───────────────────────


def test_update_requires_key_and_value():
    # Pin: both fields required. change_reason is optional for
    # backward-compat with old endpoints but recommended for audit.
    with pytest.raises(ValidationError):
        ConfigurationUpdateSchema(key="x")  # type: ignore[call-arg]


def test_update_value_accepts_any_type():
    # Pin: value is `Any` — admin UI may submit string/int/bool/dict
    # depending on the data_type of the underlying config. Don't
    # narrow this to str.
    obj = ConfigurationUpdateSchema(key="port", value=587)
    assert obj.value == 587


def test_create_data_type_defaults_to_string():
    # Pin: omitting data_type creates a string-typed config. This is
    # the safe fallback for free-form admin entries. A regression to
    # any other type would break form validation.
    obj = ConfigurationCreateSchema(
        key="my.config",
        value="hello",
        category=ConfigCategory.features,
    )
    assert obj.data_type == ConfigDataType.string


def test_create_defaults_for_flags():
    obj = ConfigurationCreateSchema(
        key="my.config",
        value="hello",
        category=ConfigCategory.features,
    )
    assert obj.is_sensitive is False
    assert obj.is_readonly is False


# ─── ConfigurationCategorySchema ────────────────────────────────────


def test_category_count_fields_default_zero():
    # Pin: total/sensitive/readonly counts default to 0. Frontend
    # displays them as badges — None would render "—" everywhere.
    obj = ConfigurationCategorySchema(
        category=ConfigCategory.email,
        display_name="Email",
        description="Email settings",
    )
    assert obj.total_count == 0
    assert obj.sensitive_count == 0
    assert obj.readonly_count == 0
    assert obj.configurations == []


# ─── ConfigurationBulkUpdateSchema ──────────────────────────────────


def test_bulk_update_requires_updates_list():
    # Pin: bulk update needs at least the updates list (can be empty
    # but the field must be present).
    with pytest.raises(ValidationError):
        ConfigurationBulkUpdateSchema()  # type: ignore[call-arg]


def test_bulk_update_carries_change_reason_for_all():
    # Pin: bulk change_reason applies to every individual update
    # without being repeated per-row. Optional, but pinned.
    b = ConfigurationBulkUpdateSchema(
        updates=[
            ConfigurationUpdateSchema(key="x", value="1"),
            ConfigurationUpdateSchema(key="y", value="2"),
        ],
        change_reason="Bulk policy update",
    )
    assert b.change_reason == "Bulk policy update"
    assert len(b.updates) == 2


# ─── ConfigurationValidationSchema / ResultSchema ───────────────────


def test_validation_request_required_fields():
    # Pin: key + value + data_type required. validation_regex is
    # optional (some types have no regex constraint).
    with pytest.raises(ValidationError):
        ConfigurationValidationSchema(  # type: ignore[call-arg]
            key="x",
            value="y",
            # data_type missing
        )


def test_validation_result_required_fields():
    with pytest.raises(ValidationError):
        ConfigurationValidationResultSchema(is_valid=True)  # type: ignore[call-arg]


def test_validation_result_suggested_value_optional():
    # Pin: suggested_value is optional — most "invalid" results have
    # no auto-correction.
    r = ConfigurationValidationResultSchema(is_valid=False, message="bad")
    assert r.suggested_value is None


# ─── BankVerificationRequestSchema ──────────────────────────────────


def test_verification_request_force_recheck_defaults_false():
    # Pin: force_recheck=False — re-verifying is slow + rate-limited.
    # Default must be opt-in. Flipping would silently spam the
    # external verification API.
    r = BankVerificationRequestSchema(application_id=1)
    assert r.force_recheck is False


def test_batch_verification_force_recheck_defaults_false():
    r = BankVerificationBatchRequestSchema(application_ids=[1, 2, 3])
    assert r.force_recheck is False


# ─── BankFieldComparisonSchema ──────────────────────────────────────


def test_field_comparison_required_fields():
    # Pin: all primary comparison fields required. They're all
    # rendered in the verification-review UI.
    with pytest.raises(ValidationError):
        BankFieldComparisonSchema(  # type: ignore[call-arg]
            field_name="account_number",
            form_value="123",
            ocr_value="123",
            # similarity_score missing
            is_match=True,
            confidence="high",
        )


def test_field_comparison_needs_manual_review_defaults_false():
    # Pin: most fields match cleanly; manual review is the
    # exception. Flipping would route every comparison to the manual
    # queue.
    c = BankFieldComparisonSchema(
        field_name="x",
        form_value="1",
        ocr_value="1",
        similarity_score=1.0,
        is_match=True,
        confidence="high",
    )
    assert c.needs_manual_review is False


# ─── BankVerificationResultSchema ───────────────────────────────────


def test_result_requires_manual_review_defaults_false():
    # Pin: top-level requires_manual_review=False. Most results auto-
    # complete; flipping the default would send every result to the
    # manual queue and overwhelm staff.
    r = BankVerificationResultSchema(
        success=True,
        application_id=1,
        verification_status="verified",
    )
    assert r.requires_manual_review is False


def test_result_dict_fields_default_empty():
    # Pin: comparisons/form_data/ocr_data default to {} so the
    # frontend can render the verification table without null checks.
    r = BankVerificationResultSchema(
        success=True,
        application_id=1,
        verification_status="verified",
    )
    assert r.comparisons == {}
    assert r.form_data == {}
    assert r.ocr_data == {}
    assert r.recommendations == []


# ─── BankVerificationBatchResultSchema ──────────────────────────────


def test_batch_result_summary_defaults_empty_dict():
    # Pin: summary defaults to {} so the batch endpoint can return an
    # empty result without forcing the caller to seed counters.
    b = BankVerificationBatchResultSchema(
        total_processed=0,
        successful_verifications=0,
        failed_verifications=0,
    )
    assert b.summary == {}
    assert b.results == {}
