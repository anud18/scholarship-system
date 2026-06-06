"""
Tests for `ApplicationService._validate_sub_type_for_submission`.

Regression pin for the csphd0003 "申請類別 = general" bug: a PhD application
(scholarship type defines real sub-types nstc/moe_1w) was submitted carrying
the synthetic "general" category because the student never selected a sub-type
and both the frontend and backend silently defaulted to "general". A "general"
application matches no quota slot during manual distribution, so it must be
rejected at submission time.

The guard is a pure staticmethod — tested via SimpleNamespace bypass of
SQLAlchemy, no DB needed.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.schemas.application import ApplicationUpdate
from app.services.application_service import ApplicationService


def _scholarship(sub_type_list):
    return SimpleNamespace(sub_type_list=sub_type_list)


# ─── scholarships that define real sub-types: "general"/empty is rejected ───


def test_phd_general_submission_rejected():
    # The exact csphd0003 bug: nstc/moe_1w defined, "general" submitted.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "general")


def test_phd_none_submission_rejected():
    # Empty sub_scholarship_type collapses to "general" → rejected.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), None)


def test_sub_type_not_in_list_rejected():
    # Submitted a sub-type the scholarship doesn't define.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc"]), "moe_1w")


def test_error_message_lists_valid_sub_types():
    with pytest.raises(ValidationError) as exc:
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "general")
    msg = str(exc.value)
    assert "nstc" in msg and "moe_1w" in msg


# ─── valid submissions: no exception ───


def test_valid_concrete_sub_type_passes():
    # nstc is in the defined list → allowed.
    ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "nstc")


def test_general_scholarship_allows_general():
    # Scholarship whose only "sub-type" is the synthetic general → general ok.
    ApplicationService._validate_sub_type_for_submission(_scholarship(["general"]), "general")


def test_scholarship_without_sub_types_allows_general():
    # No sub-types defined at all → general is the correct category.
    ApplicationService._validate_sub_type_for_submission(_scholarship([]), "general")


def test_scholarship_with_none_sub_type_list_allows_general():
    # Defensive: sub_type_list may be None on older rows.
    ApplicationService._validate_sub_type_for_submission(_scholarship(None), "general")


def test_none_scholarship_is_skipped():
    # Defensive: scholarship relationship may be unloaded — skip, don't crash.
    ApplicationService._validate_sub_type_for_submission(None, "anything")


# ─── no real sub-types: arbitrary values are rejected (not silently stored) ───


def test_no_real_sub_types_rejects_arbitrary_value():
    # ["general"]-only scholarship must not accept a bogus sub-type string.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["general"]), "nstc")


def test_empty_sub_type_list_rejects_arbitrary_value():
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship([]), "garbage")


# ─── case-insensitive comparison (admin sub_type_list may not be lowercase) ───


def test_uppercase_sub_type_list_accepts_lowercase_submission():
    # Pin: sub_type_list=["NSTC"] must accept submitted "nstc" — sub-types are
    # stored lowercase, so a casing mismatch must NOT falsely reject.
    ApplicationService._validate_sub_type_for_submission(_scholarship(["NSTC", "MOE_1W"]), "nstc")


def test_uppercase_submission_against_lowercase_list_accepted():
    ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "NSTC")


# ─── _derive_sub_scholarship_type (shared by create + update) ───


def test_derive_first_entry_lowercased():
    assert ApplicationService._derive_sub_scholarship_type(["NSTC", "moe_1w"]) == "nstc"


def test_derive_empty_list_is_general():
    assert ApplicationService._derive_sub_scholarship_type([]) == "general"


def test_derive_none_is_general():
    assert ApplicationService._derive_sub_scholarship_type(None) == "general"


# ─── integration: update_application re-derives the scalar (regression) ───
#
# The csphd0003 fix is defeated if editing an application to pick a real
# sub-type leaves the denormalized sub_scholarship_type stale at "general",
# because submit_application's guard then rejects the corrected application.


@pytest.mark.asyncio
async def test_update_application_resyncs_sub_scholarship_type(db):
    # Seed: PhD-like scholarship with real sub-types + a draft owned by the user
    # that currently carries the "general" fallback (the bug state).
    user = User(
        nycu_id="csphd_edit",
        name="Edit Tester",
        email="csphd_edit@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    scholarship = ScholarshipType(
        code="phd_like",
        name="PhD-like",
        description="defines real sub-types",
        sub_type_list=["nstc", "moe_1w"],
    )
    db.add_all([user, scholarship])
    await db.commit()
    await db.refresh(user)
    await db.refresh(scholarship)

    application = Application(
        user_id=user.id,
        scholarship_type_id=scholarship.id,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=ApplicationStatus.draft.value,
        app_id="APP-114-0-09999",
        academic_year=114,
        semester=None,
        scholarship_subtype_list=["general"],
        sub_scholarship_type="general",
        student_data={"name": "Edit Tester"},
        submitted_form_data={"fields": {}, "documents": []},
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)

    service = ApplicationService(db)
    # Student edits the draft and picks nstc (sent uppercase to also prove
    # normalization end-to-end).
    await service.update_application(
        application.id,
        ApplicationUpdate(scholarship_subtype_list=["NSTC"]),
        user,
    )
    await db.refresh(application)

    # Scalar is re-derived from the list → guard will now accept it.
    assert application.scholarship_subtype_list == ["NSTC"]
    assert application.sub_scholarship_type == "nstc"
    ApplicationService._validate_sub_type_for_submission(scholarship, application.sub_scholarship_type)
