"""
Pydantic validator tests for `app/schemas/application.py`.

These validators are the **last server-side gate** before form payloads
reach the application service / DB. Bugs cause:

- `DynamicFormField.validate_value_type`: wrong-type form data passes
  through → DB stores junk, downstream rendering crashes
- `ApplicationFormData.validate_required_fields`: SECURITY-ADJACENT —
  required field bypass means student submits empty mandatory fields,
  application enters review queue with missing bank account / contact,
  payment day fails silently
- `ApplicationFormData` min/max + min_length/max_length: validation_rules
  bypass means OCR/scoring services receive out-of-range values that
  cascade into downstream errors
- `ApplicationCreate.validate_sub_type_preferences`: duplicate sub-type
  preferences would crash quota allocation
- `ApplicationCreate.validate_preferences_match_subtype_list`:
  CRITICAL — preference list must be a permutation of the chosen
  sub-types; a mismatch causes ranking corruption (student appears in
  the wrong sub-type queue, displacing a real applicant)

4 validators covered (17 cases). No DB, pure Pydantic round-trip.
"""

import pytest
from pydantic import ValidationError

from app.schemas.application import (
    ApplicationCreate,
    ApplicationFormData,
    ApplicationUpdate,
    DynamicFormField,
)


# Reusable helper — a valid minimal DynamicFormField the way the form-builder
# would produce one.
def _field(field_id="bank_account", field_type="text", value="123", required=True, validation_rules=None):
    return DynamicFormField(
        field_id=field_id,
        field_type=field_type,
        value=value,
        required=required,
        validation_rules=validation_rules,
    )


# ─── DynamicFormField.validate_value_type ────────────────────────────


def test_select_field_accepts_string():
    """select field accepts a string (single-select)."""
    f = _field(field_type="select", value="option_a")
    assert f.value == "option_a"


def test_select_field_accepts_list():
    """select field accepts a list (multi-select)."""
    f = _field(field_type="select", value=["a", "b"])
    assert f.value == ["a", "b"]


def test_select_field_rejects_dict():
    """Pin: dict/other types in select fields raise. Defensive against a
    misconfigured form-builder shipping nested objects."""
    with pytest.raises(ValidationError) as exc:
        _field(field_type="select", value={"x": 1})
    assert "string or list" in str(exc.value)


def test_number_field_accepts_int_and_float():
    assert _field(field_type="number", value=42).value == 42
    assert _field(field_type="number", value=3.14).value == 3.14


def test_number_field_rejects_string():
    """SECURITY-adjacent: '5' as a string would silently coerce to len()
    in downstream comparators — pin so the rejection is explicit."""
    with pytest.raises(ValidationError) as exc:
        _field(field_type="number", value="42")
    assert "must be a number" in str(exc.value)


def test_text_field_skips_validation_for_unknown_type():
    """text/other types pass through without type-check (validation_rules
    handles their length checks). Pin so the validator doesn't become
    over-strict for new field types added via configuration."""
    f = _field(field_type="text", value="hello")
    assert f.value == "hello"


# ─── ApplicationFormData.validate_required_fields ────────────────────


def test_required_field_with_none_value_rejected():
    """SECURITY-ADJACENT: required + None → reject. Otherwise student
    submits an application with empty mandatory bank_account, downstream
    payment day fails silently."""
    with pytest.raises(ValidationError) as exc:
        ApplicationFormData(
            fields={"bank_account": _field(field_id="bank_account", value=None, required=True)},
        )
    assert "必填欄位 bank_account" in str(exc.value)


def test_required_field_with_empty_string_rejected():
    """Pin: empty string === missing for required fields. Matches the
    HTML form-empty semantics; otherwise the empty input slips past."""
    with pytest.raises(ValidationError) as exc:
        ApplicationFormData(
            fields={"contact_phone": _field(field_id="contact_phone", value="", required=True)},
        )
    assert "必填欄位 contact_phone" in str(exc.value)


def test_optional_field_with_none_value_accepted():
    """required=False → None / empty is OK."""
    data = ApplicationFormData(
        fields={"middle_name": _field(field_id="middle_name", value=None, required=False)},
    )
    assert data.fields["middle_name"].value is None


def test_number_field_min_max_validation_rules():
    """validation_rules min/max for number field — both bounds enforced."""
    # GPA 0–4.3 range
    rules = {"min": 0, "max": 4.3}
    # In-range OK
    data = ApplicationFormData(
        fields={"gpa": _field(field_id="gpa", field_type="number", value=3.5, validation_rules=rules)},
    )
    assert data.fields["gpa"].value == 3.5

    # Below min rejected
    with pytest.raises(ValidationError) as exc:
        ApplicationFormData(
            fields={"gpa": _field(field_id="gpa", field_type="number", value=-1, validation_rules=rules)},
        )
    assert "不可小於 0" in str(exc.value)

    # Above max rejected
    with pytest.raises(ValidationError) as exc:
        ApplicationFormData(
            fields={"gpa": _field(field_id="gpa", field_type="number", value=5.0, validation_rules=rules)},
        )
    assert "不可大於 4.3" in str(exc.value)


def test_text_field_min_length_max_length_validation_rules():
    """validation_rules min_length/max_length for text field."""
    rules = {"min_length": 3, "max_length": 10}
    # In-range OK
    data = ApplicationFormData(
        fields={"name": _field(field_id="name", value="王小明", validation_rules=rules)},
    )
    assert data.fields["name"].value == "王小明"

    # Too short rejected
    with pytest.raises(ValidationError) as exc:
        ApplicationFormData(
            fields={"name": _field(field_id="name", value="王", validation_rules=rules)},
        )
    assert "長度不可小於 3" in str(exc.value)

    # Too long rejected
    with pytest.raises(ValidationError) as exc:
        ApplicationFormData(
            fields={"name": _field(field_id="name", value="x" * 11, validation_rules=rules)},
        )
    assert "長度不可大於 10" in str(exc.value)


# ─── ApplicationCreate.validate_sub_type_preferences ──────────────────


def _form_data():
    """Minimal valid ApplicationFormData for ApplicationCreate tests."""
    return ApplicationFormData(fields={"bank_account": _field()})


def test_sub_type_preferences_empty_list_coerced_to_none():
    """Pin: [] → None. Otherwise downstream sees a truthy-but-empty list
    and treats 'no preferences set' as 'preferences set to nothing'."""
    app = ApplicationCreate(
        scholarship_type="undergraduate_freshman",
        configuration_id=1,
        scholarship_subtype_list=[],
        form_data=_form_data(),
        sub_type_preferences=[],
    )
    assert app.sub_type_preferences is None


def test_sub_type_preferences_none_passes_through():
    app = ApplicationCreate(
        scholarship_type="undergraduate_freshman",
        configuration_id=1,
        scholarship_subtype_list=[],
        form_data=_form_data(),
        sub_type_preferences=None,
    )
    assert app.sub_type_preferences is None


def test_sub_type_preferences_duplicates_rejected():
    """Pin: duplicates raise. Otherwise quota allocator double-counts."""
    with pytest.raises(ValidationError) as exc:
        ApplicationCreate(
            scholarship_type="phd",
            configuration_id=1,
            scholarship_subtype_list=["nstc", "moe_1w"],
            form_data=_form_data(),
            sub_type_preferences=["nstc", "nstc"],
        )
    assert "must not contain duplicates" in str(exc.value)


# ─── ApplicationCreate.validate_preferences_match_subtype_list ────────


def test_preferences_must_be_permutation_of_subtype_list():
    """CRITICAL: prefs must equal the set of selected sub-types.
    A mismatch means the student ranked something they didn't apply for
    → ranking allocator places them in the wrong sub-type queue,
    potentially displacing a legitimate applicant."""
    with pytest.raises(ValidationError) as exc:
        ApplicationCreate(
            scholarship_type="phd",
            configuration_id=1,
            scholarship_subtype_list=["nstc", "moe_1w"],
            form_data=_form_data(),
            sub_type_preferences=["nstc", "moe_2w"],  # moe_2w not selected!
        )
    assert "permutation" in str(exc.value)


def test_preferences_permutation_in_different_order_accepted():
    """The order is the preference — different order from the selection
    list is the whole point. Pin: not an error."""
    app = ApplicationCreate(
        scholarship_type="phd",
        configuration_id=1,
        scholarship_subtype_list=["nstc", "moe_1w"],
        form_data=_form_data(),
        sub_type_preferences=["moe_1w", "nstc"],  # different order
    )
    assert app.sub_type_preferences == ["moe_1w", "nstc"]


def test_preferences_none_with_subtypes_is_allowed():
    """Pin: prefs=None means 'no ranking expressed' — allowed even when
    sub-types are selected. The permutation check only fires when prefs
    are non-empty."""
    app = ApplicationCreate(
        scholarship_type="phd",
        configuration_id=1,
        scholarship_subtype_list=["nstc", "moe_1w"],
        form_data=_form_data(),
        sub_type_preferences=None,
    )
    assert app.sub_type_preferences is None


# ─── ApplicationUpdate.validate_sub_type_preferences ──────────────────


def test_update_sub_type_preferences_empty_coerced_to_none():
    """ApplicationUpdate shares the empty→None coercion (separate code path)."""
    upd = ApplicationUpdate(sub_type_preferences=[])
    assert upd.sub_type_preferences is None


def test_update_sub_type_preferences_duplicates_rejected():
    with pytest.raises(ValidationError) as exc:
        ApplicationUpdate(sub_type_preferences=["a", "a"])
    assert "must not contain duplicates" in str(exc.value)
