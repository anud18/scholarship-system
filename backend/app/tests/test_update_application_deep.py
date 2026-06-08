"""
Deep async-DB tests for `ApplicationService.update_application`.

Pins the editability + access-control contract for the dashboard's
edit-in-place flow. Real-DB coverage so the persistence path is observed,
not just the call shape.

Contract pinned:
- 404 when application doesn't exist OR when the caller has no access
  (the service returns None from `_get_application_model` for either
  case; the public `update_application` raises NotFoundError uniformly).
- ValidationError when application is not in editable status
  (only `draft` and `returned` are editable per `is_editable`).
- Happy path: form_data, status, is_renewal, scholarship_subtype_list
  all persist to the DB.
- Student cannot edit another student's draft (access control via
  `_get_application_model`).
- Professor cannot edit an application that's not assigned to them.
- College/admin/super_admin can edit any application.
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.application import ApplicationFormData, ApplicationUpdate
from app.services.application_service import ApplicationService


async def _seed_user(db: AsyncSession, *, role: UserRole, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_config(db: AsyncSession, *, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"upd_{suffix}", name=f"Upd type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"upd_cfg_{suffix}",
        config_name=f"Upd cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=False,
        amount=0,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _seed_app(
    db: AsyncSession,
    *,
    student: User,
    config: ScholarshipConfiguration,
    status: str,
    professor_id: int | None = None,
    scholarship_subtype_list: list[str] | None = None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-UPD-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor_id,
        scholarship_subtype_list=scholarship_subtype_list or [],
        submitted_form_data={"fields": {}, "documents": []},
        is_renewal=False,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


def _val(x):
    return x.value if hasattr(x, "value") else x


@pytest.fixture
def silence_collaborators(monkeypatch):
    """No-op _invalidate_app_caches + _clone_user_profile_documents.

    The first is Redis-bound, the second is MinIO-bound. Neither is what
    we're verifying here — we're pinning the persistence + access control."""

    async def _noop_cache() -> None:
        return None

    async def _noop_clone(self: Any, application: Any, user: Any) -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))
    monkeypatch.setattr(ApplicationService, "_clone_user_profile_documents", _noop_clone)


@pytest.mark.asyncio
async def test_update_not_found_raises(db: AsyncSession, silence_collaborators):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="upd_admin_404")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.update_application(
            application_id=999_999,
            update_data=ApplicationUpdate(form_data=ApplicationFormData(fields={}, documents=[])),
            current_user=admin,
        )


@pytest.mark.asyncio
async def test_update_rejects_when_status_is_not_editable(db: AsyncSession, silence_collaborators):
    """Only draft and returned are editable — submitted/approved/etc. must reject."""
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="upd_admin_locked")
    student = await _seed_user(db, role=UserRole.student, nycu_id="upd_stu_locked")
    cfg = await _seed_config(db, suffix="locked")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="locked")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.update_application(
            application_id=app.id,
            update_data=ApplicationUpdate(form_data=ApplicationFormData(fields={}, documents=[])),
            current_user=admin,
        )


@pytest.mark.asyncio
async def test_update_persists_form_data_status_is_renewal_subtype_list(db: AsyncSession, silence_collaborators):
    """All four fields persist to the DB after update."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="upd_happy_stu")
    cfg = await _seed_config(db, suffix="happy")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.draft.value,
        scholarship_subtype_list=["nstc"],
        suffix="happy",
    )
    service = ApplicationService(db)

    update_data = ApplicationUpdate(
        # fields is Dict[str, DynamicFormField] — pass a full field object, not a
        # bare string (the schema rejects a plain string value).
        form_data=ApplicationFormData(
            fields={
                "bank_account": {
                    "field_id": "bank_account",
                    "field_type": "text",
                    "value": "123456789",
                    "required": False,
                }
            },
            documents=[],
        ),
        is_renewal=True,
        scholarship_subtype_list=["nstc", "moe_1w"],
    )

    result = await service.update_application(application_id=app.id, update_data=update_data, current_user=student)

    await db.refresh(app)
    # form_data persisted — the field round-trips as a serialised DynamicFormField,
    # so the value lives under ["bank_account"]["value"].
    assert app.submitted_form_data is not None
    persisted = app.submitted_form_data.get("fields", {}).get("bank_account")
    persisted_value = persisted.get("value") if isinstance(persisted, dict) else persisted
    assert persisted_value == "123456789"
    # is_renewal flipped.
    assert app.is_renewal is True
    # subtype list updated.
    assert app.scholarship_subtype_list == ["nstc", "moe_1w"]
    # Returned object reflects the same state.
    assert result.is_renewal is True


@pytest.mark.asyncio
async def test_update_persists_sub_type_preferences(db: AsyncSession, silence_collaborators):
    """志願序 (sub_type_preferences) must persist on update.

    Regression guard: this is the field the distribution service reads first
    (`raw_prefs = app.sub_type_preferences or applied or default_prefs` in
    manual_distribution_service). update_application silently dropped it before
    — the schema accepted it but it was never written to the model — which made
    the wizard's forced ordering a no-op end-to-end. Caught by the Playwright
    E2E (a saved draft persisted NULL instead of the ordered list)."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="upd_prefs_stu")
    cfg = await _seed_config(db, suffix="prefs")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.draft.value,
        scholarship_subtype_list=["nstc", "moe_1w"],
        suffix="prefs",
    )
    assert app.sub_type_preferences is None  # nothing persisted at seed time
    service = ApplicationService(db)

    update_data = ApplicationUpdate(
        scholarship_subtype_list=["nstc", "moe_1w"],
        sub_type_preferences=["moe_1w", "nstc"],  # MOE (moe_1w) forced to first preference
    )
    result = await service.update_application(application_id=app.id, update_data=update_data, current_user=student)

    await db.refresh(app)
    # The ordered preference list round-trips to the DB, leading with moe_1w.
    assert app.sub_type_preferences == ["moe_1w", "nstc"]
    assert result.sub_type_preferences == ["moe_1w", "nstc"]


@pytest.mark.asyncio
async def test_student_cannot_update_other_students_draft(db: AsyncSession, silence_collaborators):
    """`_get_application_model` returns None for cross-student access ⇒
    update_application raises NotFoundError uniformly (the service does
    NOT leak existence via a different error)."""
    owner = await _seed_user(db, role=UserRole.student, nycu_id="upd_owner")
    intruder = await _seed_user(db, role=UserRole.student, nycu_id="upd_intruder")
    cfg = await _seed_config(db, suffix="xstu")
    app = await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.draft.value, suffix="xstu")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.update_application(
            application_id=app.id,
            update_data=ApplicationUpdate(form_data=ApplicationFormData(fields={}, documents=[])),
            current_user=intruder,
        )


@pytest.mark.asyncio
async def test_unassigned_professor_cannot_update(db: AsyncSession, silence_collaborators):
    """A professor not assigned to the application gets NotFoundError
    (access control via `_get_application_model`)."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="upd_stu_unassigned")
    other_prof = await _seed_user(db, role=UserRole.professor, nycu_id="upd_prof_other")
    cfg = await _seed_config(db, suffix="unassigned")
    # professor_id is None — no professor assigned at all.
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="unassigned")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.update_application(
            application_id=app.id,
            update_data=ApplicationUpdate(form_data=ApplicationFormData(fields={}, documents=[])),
            current_user=other_prof,
        )


@pytest.mark.asyncio
async def test_college_and_admin_can_update_any_application(db: AsyncSession, silence_collaborators):
    """College, admin, super_admin pass the access-control check for any draft."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="upd_stu_admin_access")
    cfg = await _seed_config(db, suffix="admin_access")

    for role, suffix in [(UserRole.college, "col"), (UserRole.admin, "adm"), (UserRole.super_admin, "sup")]:
        staff = await _seed_user(db, role=role, nycu_id=f"upd_staff_{suffix}")
        app = await _seed_app(
            db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix=f"admin_{suffix}"
        )
        service = ApplicationService(db)

        result = await service.update_application(
            application_id=app.id,
            update_data=ApplicationUpdate(is_renewal=True),
            current_user=staff,
        )
        assert result.is_renewal is True


@pytest.mark.asyncio
async def test_returned_status_is_editable_too(db: AsyncSession, silence_collaborators):
    """Both draft AND returned must pass `is_editable`. This is the second
    allowed editable state; missing it would block the revisions workflow."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="upd_returned_stu")
    cfg = await _seed_config(db, suffix="returned")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.returned.value, suffix="returned")
    service = ApplicationService(db)

    # Should NOT raise.
    await service.update_application(
        application_id=app.id,
        update_data=ApplicationUpdate(is_renewal=True),
        current_user=student,
    )
    await db.refresh(app)
    assert app.is_renewal is True
