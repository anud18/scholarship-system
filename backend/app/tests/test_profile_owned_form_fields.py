"""
The 郵局帳號 and 指導教授 fields belong to the student's UserProfile, never to
`submitted_form_data` (#1443).

A shared form-config cache once prefilled every student's hidden fixed fields
with ONE student's profile, and the dynamic form saved those values into each
application. Review pages, roster generation and bank verification then read
another student's account and advisor. The student's own create/update paths
therefore strip those fields before persisting.

Covered here:
- `strip_profile_owned_fields` drops exactly the profile-owned ids, keeps
  everything else (including the wizard's own `account_number`), and does not
  mutate its input
- `update_application` persists the stripped form
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.application import ApplicationFormData, ApplicationUpdate
from app.services.application_service import (
    PROFILE_OWNED_FORM_FIELDS,
    ApplicationService,
    strip_profile_owned_fields,
)


def _field(field_id: str, value: str) -> dict:
    return {"field_id": field_id, "field_type": "text", "value": value, "required": False}


LEAKED = {
    "postal_account": _field("postal_account", "00000000000001"),
    "advisor_name": _field("advisor_name", "Someone Else"),
    "advisor_email": _field("advisor_email", "someone@example.edu"),
    "advisor_nycu_id": _field("advisor_nycu_id", "XX0000"),
}
OWN = {
    "account_number": _field("account_number", "00000000000002"),
    "contact_phone": _field("contact_phone", "0912345678"),
}


# ─── strip_profile_owned_fields ──────────────────────────────────────


def test_profile_owned_ids_are_the_postal_account_and_advisor_trio():
    assert PROFILE_OWNED_FORM_FIELDS == {"postal_account", "advisor_name", "advisor_email", "advisor_nycu_id"}


def test_strip_drops_profile_owned_fields_and_keeps_the_rest():
    form = {"fields": {**LEAKED, **OWN}, "documents": [{"document_id": "d1"}]}

    stripped = strip_profile_owned_fields(form)

    assert set(stripped["fields"]) == set(OWN)
    assert stripped["documents"] == [{"document_id": "d1"}]


def test_strip_does_not_mutate_its_input():
    form = {"fields": {**LEAKED, **OWN}, "documents": []}

    strip_profile_owned_fields(form)

    assert set(form["fields"]) == set(LEAKED) | set(OWN)


def test_strip_leaves_a_form_without_fields_untouched():
    assert strip_profile_owned_fields({"documents": []}) == {"documents": []}


# ─── update_application ──────────────────────────────────────────────


@pytest.fixture
def silence_collaborators(monkeypatch):
    """Redis cache invalidation and MinIO document cloning are not under test."""

    async def _noop_cache() -> None:
        return None

    async def _noop_clone(self: Any, application: Any, user: Any) -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))
    monkeypatch.setattr(ApplicationService, "_clone_user_profile_documents", _noop_clone)


async def _seed_draft(db: AsyncSession) -> tuple[User, Application]:
    student = User(
        nycu_id="pof_stu",
        name="Student",
        email="pof_stu@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    scholarship_type = ScholarshipType(code="pof_type", name="POF type", status="active")
    db.add_all([student, scholarship_type])
    await db.commit()

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code="pof_cfg",
        config_name="POF cfg",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=False,
        amount=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()

    application = Application(
        app_id="APP-POF-1",
        user_id=student.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        student_data={},
        status=ApplicationStatus.draft.value,
        scholarship_subtype_list=[],
        submitted_form_data={"fields": {}, "documents": []},
        is_renewal=False,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return student, application


@pytest.mark.asyncio
async def test_update_application_does_not_persist_profile_owned_fields(db: AsyncSession, silence_collaborators):
    student, application = await _seed_draft(db)
    service = ApplicationService(db)

    await service.update_application(
        application_id=application.id,
        update_data=ApplicationUpdate(form_data=ApplicationFormData(fields={**LEAKED, **OWN}, documents=[])),
        current_user=student,
    )

    result = await db.execute(select(Application).where(Application.id == application.id))
    persisted = result.scalar_one().submitted_form_data["fields"]
    assert set(persisted) == set(OWN)
    assert persisted["account_number"]["value"] == "00000000000002"
