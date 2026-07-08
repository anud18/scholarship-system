"""Unit tests for the shared application builder helpers.

These helpers are the single source of truth for logic that previously
drifted between the student self-submission path (ApplicationService)
and the batch import path (BatchImportService).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.services.application_builder import (
    FORCED_FIRST_PREFERENCE,
    build_submitted_application_values,
    derive_sub_scholarship_type,
    order_sub_type_preferences,
    validate_sub_type_for_submission,
)

# --- derive_sub_scholarship_type -------------------------------------------


def test_derive_sub_type_empty_list_returns_general():
    assert derive_sub_scholarship_type([]) == "general"
    assert derive_sub_scholarship_type(None) == "general"


def test_derive_sub_type_first_entry_lowercased():
    assert derive_sub_scholarship_type(["NSTC", "moe_1w"]) == "nstc"


# --- validate_sub_type_for_submission ---------------------------------------


def _scholarship_stub(sub_type_list):
    return SimpleNamespace(sub_type_list=sub_type_list)


def test_validate_rejects_general_when_real_sub_types_exist():
    with pytest.raises(ValidationError):
        validate_sub_type_for_submission(_scholarship_stub(["nstc", "moe_1w"]), "general")


def test_validate_accepts_real_sub_type_case_insensitive():
    validate_sub_type_for_submission(_scholarship_stub(["NSTC", "moe_1w"]), "nstc")


def test_validate_rejects_arbitrary_sub_type_when_none_defined():
    with pytest.raises(ValidationError):
        validate_sub_type_for_submission(_scholarship_stub([]), "nstc")


def test_validate_accepts_general_when_none_defined():
    validate_sub_type_for_submission(_scholarship_stub([]), "general")
    validate_sub_type_for_submission(_scholarship_stub(None), None)


# --- order_sub_type_preferences ---------------------------------------------


def test_order_forces_moe_1w_first():
    assert order_sub_type_preferences(["nstc", "moe_1w"]) == ["moe_1w", "nstc"]


def test_order_preserves_order_without_moe_1w():
    assert order_sub_type_preferences(["nstc", "moe_2w"]) == ["nstc", "moe_2w"]


def test_order_single_and_empty():
    assert order_sub_type_preferences(["moe_1w"]) == ["moe_1w"]
    assert order_sub_type_preferences([]) == []


def test_forced_first_preference_constant_matches_frontend():
    # Mirrors FORCED_FIRST_PREFERENCE in
    # frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx
    assert FORCED_FIRST_PREFERENCE == "moe_1w"


# --- build_submitted_application_values --------------------------------------


def test_build_submitted_values_uses_config_amount_and_name():
    scholarship = SimpleNamespace(name="博士生獎學金")
    config = SimpleNamespace(config_name="博士生獎學金 114學年", amount=40000)

    values = build_submitted_application_values(scholarship, config)

    assert values["status"] == "submitted"
    assert values["status_name"]  # non-empty i18n text
    assert values["review_stage"] == "student_submitted"
    assert values["amount"] == 40000
    assert values["scholarship_name"] == "博士生獎學金 114學年"
    assert isinstance(values["submitted_at"], datetime)
    assert values["submitted_at"].tzinfo == timezone.utc


def test_build_submitted_values_falls_back_to_scholarship_name():
    scholarship = SimpleNamespace(name="博士生獎學金")
    config = SimpleNamespace(config_name=None, amount=None)

    values = build_submitted_application_values(scholarship, config)

    assert values["scholarship_name"] == "博士生獎學金"
    assert values["amount"] is None
