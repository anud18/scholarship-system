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


# --- async helpers -----------------------------------------------------------

from app.models.application_sequence import ApplicationSequence  # noqa: E402,F401
from app.models.user import User  # noqa: E402
from app.models.user_profile import UserProfile  # noqa: E402
from app.services.application_builder import (  # noqa: E402
    assign_professor_from_profile,
    generate_app_id,
)


async def test_generate_app_id_creates_sequence_and_formats(db):
    app_id = await generate_app_id(db, 114, None)
    assert app_id == "APP-114-0-00001"

    app_id2 = await generate_app_id(db, 114, "yearly")
    assert app_id2 == "APP-114-0-00002"


async def test_generate_app_id_with_suffix_no_commit(db):
    app_id = await generate_app_id(db, 114, "first", suffix="U", commit=False)
    assert app_id == "APP-114-1-00001U"


async def test_assign_professor_sets_id_when_profile_matches(db):
    student = User(nycu_id="313554001", name="學生甲", role="student", user_type="student")
    professor = User(nycu_id="P001234", name="張教授", role="professor", user_type="employee")
    db.add_all([student, professor])
    await db.flush()

    db.add(UserProfile(user_id=student.id, advisor_nycu_id="P001234"))
    await db.flush()

    application = SimpleNamespace(professor_id=None)
    result = await assign_professor_from_profile(db, application, student.id)

    assert result is not None
    assert application.professor_id == professor.id


async def test_assign_professor_none_when_no_professor_account(db):
    student = User(nycu_id="313554002", name="學生乙", role="student", user_type="student")
    db.add(student)
    await db.flush()
    db.add(UserProfile(user_id=student.id, advisor_nycu_id="NOSUCH"))
    await db.flush()

    application = SimpleNamespace(professor_id=None)
    result = await assign_professor_from_profile(db, application, student.id)

    assert result is None
    assert application.professor_id is None


async def test_assign_professor_does_not_overwrite_existing(db):
    student = User(nycu_id="313554003", name="學生丙", role="student", user_type="student")
    db.add(student)
    await db.flush()

    application = SimpleNamespace(professor_id=999)
    result = await assign_professor_from_profile(db, application, student.id)

    assert result is None
    assert application.professor_id == 999
