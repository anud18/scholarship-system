"""
Deep async-DB tests for `ApplicationService.delete_application`.

Pairs with the restore_application tests in #249 — this method is the
inverse. It branches between hard delete (drafts) and soft delete
(submitted), which is the highest-risk part of the contract: a regression
that hard-deletes a submitted application would lose review history and
audit trail forever.

Contract pinned:
- 404 if application not found.
- ValidationError if already deleted.
- Students:
  * Can only delete their own application (else AuthorizationError).
  * Can only delete drafts (else ValidationError).
- Staff (professor/college/admin/super_admin):
  * Must provide a deletion reason (else ValidationError).
  * Can delete any application.
- Draft applications: **hard delete** — row gone from DB.
- Submitted applications: **soft delete** — status='deleted', deleted_at
  + deleted_by_id + deletion_reason recorded; row still in DB.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
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
    st = ScholarshipType(code=f"del_{suffix}", name=f"Del type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"del_cfg_{suffix}",
        config_name=f"Del cfg {suffix}",
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
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-DEL-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


def _val(x):
    return x.value if hasattr(x, "value") else x


@pytest.fixture
def silence_collaborators(monkeypatch):
    """No-op _invalidate_app_caches (Redis) and minio_service.delete_file
    (network bound). The status flip and persistence are the parts under
    test here."""

    async def _noop_cache() -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))
    # The minio service is referenced inside the hard-delete branch.
    from app.services import application_service as svc_module

    monkeypatch.setattr(svc_module.minio_service, "delete_file", lambda *a, **k: None)


@pytest.mark.asyncio
async def test_delete_not_found_raises(db: AsyncSession, silence_collaborators):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="del_admin_404")
    service = ApplicationService(db)
    with pytest.raises(NotFoundError):
        await service.delete_application(application_id=999_999, current_user=admin, reason="seed")


@pytest.mark.asyncio
async def test_delete_already_deleted_raises_validation(db: AsyncSession, silence_collaborators):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="del_admin_dup")
    student = await _seed_user(db, role=UserRole.student, nycu_id="del_student_dup")
    cfg = await _seed_config(db, suffix="dup")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.deleted.value, suffix="dup")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.delete_application(application_id=app.id, current_user=admin, reason="seed")


@pytest.mark.asyncio
async def test_student_cannot_delete_another_students_app(db: AsyncSession, silence_collaborators):
    owner = await _seed_user(db, role=UserRole.student, nycu_id="del_owner")
    intruder = await _seed_user(db, role=UserRole.student, nycu_id="del_intruder")
    cfg = await _seed_config(db, suffix="xstu")
    app = await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.draft.value, suffix="xstu")
    service = ApplicationService(db)

    with pytest.raises(AuthorizationError):
        await service.delete_application(application_id=app.id, current_user=intruder)


@pytest.mark.asyncio
async def test_student_cannot_delete_submitted_app(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, nycu_id="del_stu_submitted")
    cfg = await _seed_config(db, suffix="stu_submit")
    app = await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="stu_submit"
    )
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.delete_application(application_id=app.id, current_user=student)


@pytest.mark.asyncio
async def test_staff_must_provide_reason(db: AsyncSession, silence_collaborators):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="del_admin_no_reason")
    student = await _seed_user(db, role=UserRole.student, nycu_id="del_stu_no_reason")
    cfg = await _seed_config(db, suffix="no_reason")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="no_reason")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.delete_application(application_id=app.id, current_user=admin)
    # Empty string also rejected.
    with pytest.raises(ValidationError):
        await service.delete_application(application_id=app.id, current_user=admin, reason="")


@pytest.mark.asyncio
async def test_draft_deletion_is_hard_delete(db: AsyncSession, silence_collaborators):
    """Drafts hard-delete: the row is gone from the DB after the call."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="del_hard_stu")
    cfg = await _seed_config(db, suffix="hard")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="hard")
    app_id = app.id
    service = ApplicationService(db)

    await service.delete_application(application_id=app_id, current_user=student)

    # Row is gone.
    remaining = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
    assert remaining is None, "draft delete must hard-delete the row"


@pytest.mark.asyncio
async def test_submitted_deletion_is_soft_delete(db: AsyncSession, silence_collaborators):
    """Submitted apps soft-delete: status flips, audit fields set, row preserved."""
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="del_soft_admin")
    student = await _seed_user(db, role=UserRole.student, nycu_id="del_soft_stu")
    cfg = await _seed_config(db, suffix="soft")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="soft")
    app_id = app.id
    service = ApplicationService(db)

    before = datetime.now(timezone.utc)
    await service.delete_application(application_id=app_id, current_user=admin, reason="compliance request")
    after = datetime.now(timezone.utc)

    # Row still in DB, with audit fields populated.
    persisted = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
    assert persisted is not None, "submitted delete must NOT hard-delete the row"
    assert _val(persisted.status) == ApplicationStatus.deleted.value
    assert persisted.deleted_at is not None
    assert before <= persisted.deleted_at <= after
    assert persisted.deleted_by_id == admin.id
    assert persisted.deletion_reason == "compliance request"


@pytest.mark.asyncio
async def test_staff_can_delete_submitted_with_reason(db: AsyncSession, silence_collaborators):
    """Positive flip-side of the no-reason test: staff with a reason succeeds."""
    for role, suffix in [
        (UserRole.professor, "prof"),
        (UserRole.college, "college"),
        (UserRole.admin, "admin"),
        (UserRole.super_admin, "super"),
    ]:
        staff = await _seed_user(db, role=role, nycu_id=f"del_ok_{suffix}")
        student = await _seed_user(db, role=UserRole.student, nycu_id=f"del_ok_stu_{suffix}")
        cfg = await _seed_config(db, suffix=f"ok_{suffix}")
        app = await _seed_app(
            db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix=f"ok_{suffix}"
        )
        service = ApplicationService(db)

        result = await service.delete_application(application_id=app.id, current_user=staff, reason=f"by {role.value}")
        assert _val(result.status) == ApplicationStatus.deleted.value
        assert result.deleted_by_id == staff.id
