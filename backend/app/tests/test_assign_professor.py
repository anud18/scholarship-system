"""
Unit tests for `ApplicationService.assign_professor`.

Pins the validation contract for the professor-assignment flow used by
admin and college-admin UIs. Multi-collaborator method (DB write + email
scheduling + in-app notification) — these tests focus on the validation
surface, which is the bug-prone part. Side effects (email + notification)
are exercised via a separate happy-path test with the collaborators
monkeypatched to no-ops so we can observe the persisted state without
fighting the React-Email render pipeline.

Pre-existing test references to this method: 0.

Contract pinned:
- 404 when application not found.
- 404 when professor nycu_id not found OR user is not role=professor.
- Student callers can only assign their own app (otherwise ValidationError).
- ValidationError if scholarship config has requires_professor_recommendation=false.
- College admin callers must share dept_code with the target professor.
- Happy path: application.professor_id updates to the new professor.id.
- Side-effect calls are guarded by try/except in production code, so a
  failing collaborator must not bubble up — but the assignment must still
  persist. We pin this with a monkeypatch that makes both collaborators
  raise.
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


async def _seed_user(
    db: AsyncSession,
    *,
    role: UserRole,
    name: str,
    nycu_id: str,
    dept_code: str | None = None,
    email: str | None = None,
    college_code: str | None = None,
) -> User:
    u = User(
        nycu_id=nycu_id,
        name=name,
        email=email or f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        dept_code=dept_code,
        # 學院 users are scoped to their own college (#1223 A). Bind one by
        # default so that gate PASSES and the assertion under test is the one
        # the test is actually named after.
        college_code=college_code if college_code is not None else ("C" if role == UserRole.college else None),
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_config(
    db: AsyncSession,
    *,
    requires_prof: bool,
    suffix: str,
) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"assign_{suffix}", name=f"Assign type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"assign_cfg_{suffix}",
        config_name=f"Assign cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=requires_prof,
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
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-ASSIGN-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=ApplicationStatus.submitted.value,
        student_data={"std_cname": student.name, "std_academyno": "C"},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.fixture
def silence_side_effects(monkeypatch):
    """Stop NotificationService.create_notification from doing real work.

    EmailService.schedule_email is patched too, but only as a tripwire: assignment
    must NOT send mail any more (professors are mailed on student submission only),
    so a call here means the removed email path came back.
    """

    async def _noop(*args: Any, **kwargs: Any) -> Any:
        return None

    async def _must_not_send(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("assign_professor must not schedule an email")

    from app.services.email_service import EmailService
    from app.services.notification_service import NotificationService

    monkeypatch.setattr(EmailService, "schedule_email", _must_not_send)
    monkeypatch.setattr(NotificationService, "create_notification", _noop)


@pytest.fixture
def raise_side_effects(monkeypatch):
    """Force the notification collaborator to raise — pins that assign_professor's
    try/except boundary keeps the DB write committed."""

    async def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("collaborator down — must not bubble")

    from app.services.notification_service import NotificationService

    monkeypatch.setattr(NotificationService, "create_notification", _boom)


@pytest.mark.asyncio
async def test_application_not_found_raises(db: AsyncSession, silence_side_effects):
    admin = await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="a_404app")
    professor = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="p_404app")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.assign_professor(application_id=999999, professor_nycu_id=professor.nycu_id, assigned_by=admin)


@pytest.mark.asyncio
async def test_professor_not_found_raises(db: AsyncSession, silence_side_effects):
    admin = await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="a_404prof")
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_404prof")
    cfg = await _seed_config(db, requires_prof=True, suffix="404prof")
    app = await _seed_app(db, student=student, config=cfg, suffix="404prof")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.assign_professor(
            application_id=app.id,
            professor_nycu_id="nonexistent_prof",
            assigned_by=admin,
        )


@pytest.mark.asyncio
async def test_non_professor_user_treated_as_not_found(db: AsyncSession, silence_side_effects):
    """A user with role=student under that nycu_id must not be assignable."""
    admin = await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="a_nonprof")
    student = await _seed_user(db, role=UserRole.student, name="Decoy", nycu_id="decoy_user")
    cfg = await _seed_config(db, requires_prof=True, suffix="nonprof")
    app = await _seed_app(db, student=student, config=cfg, suffix="nonprof")
    service = ApplicationService(db)

    # decoy_user exists but is a student, not professor — should 404.
    with pytest.raises(NotFoundError):
        await service.assign_professor(application_id=app.id, professor_nycu_id="decoy_user", assigned_by=admin)


@pytest.mark.asyncio
async def test_student_cannot_assign_other_students_app(db: AsyncSession, silence_side_effects):
    """A student caller can only assign on their own application."""
    student_a = await _seed_user(db, role=UserRole.student, name="A", nycu_id="stu_a")
    student_b = await _seed_user(db, role=UserRole.student, name="B", nycu_id="stu_b")
    professor = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="p_xstu", dept_code="CS")
    cfg = await _seed_config(db, requires_prof=True, suffix="xstu")
    app_of_a = await _seed_app(db, student=student_a, config=cfg, suffix="xstu")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.assign_professor(
            application_id=app_of_a.id,
            professor_nycu_id=professor.nycu_id,
            assigned_by=student_b,
        )


@pytest.mark.asyncio
async def test_validation_error_when_config_does_not_require_professor(db: AsyncSession, silence_side_effects):
    """If requires_professor_recommendation=False, assignment is not allowed."""
    admin = await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="a_noprof_cfg")
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_noprof_cfg")
    professor = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="p_noprof_cfg", dept_code="CS")
    cfg = await _seed_config(db, requires_prof=False, suffix="noprof_cfg")
    app = await _seed_app(db, student=student, config=cfg, suffix="noprof_cfg")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.assign_professor(
            application_id=app.id,
            professor_nycu_id=professor.nycu_id,
            assigned_by=admin,
        )


@pytest.mark.asyncio
async def test_college_cannot_assign_a_professor_to_another_colleges_application(
    db: AsyncSession, silence_side_effects
):
    """#1223 A: the dept_code rule compares the ASSIGNER to the PROFESSOR and says
    nothing about which college the APPLICATION belongs to.

    Pinned separately from the dept_code test so the two gates cannot mask each
    other — an earlier revision had the college gate firing first on an unbound
    fixture, which made the dept_code test pass for the wrong reason.
    """
    college = await _seed_user(
        db, role=UserRole.college, name="CS Admin", nycu_id="col_c_only", dept_code="CS", college_code="C"
    )
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_other_college")
    # Same dept as the assigner, so the dept_code rule would ALLOW this.
    cs_professor = await _seed_user(db, role=UserRole.professor, name="CS Prof", nycu_id="p_cs_ok", dept_code="CS")
    cfg = await _seed_config(db, requires_prof=True, suffix="xcollege")
    app = await _seed_app(db, student=student, config=cfg, suffix="xcollege")
    app.student_data = {"std_cname": student.name, "std_academyno": "E"}  # another college
    await db.commit()
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.assign_professor(
            application_id=app.id,
            professor_nycu_id=cs_professor.nycu_id,
            assigned_by=college,
        )


@pytest.mark.asyncio
async def test_college_admin_must_share_dept_with_professor(db: AsyncSession, silence_side_effects):
    """College admins can only assign professors in their own dept_code."""
    college = await _seed_user(db, role=UserRole.college, name="CS Admin", nycu_id="col_cs", dept_code="CS")
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_xdept")
    ee_professor = await _seed_user(db, role=UserRole.professor, name="EE Prof", nycu_id="p_ee", dept_code="EE")
    cfg = await _seed_config(db, requires_prof=True, suffix="xdept")
    app = await _seed_app(db, student=student, config=cfg, suffix="xdept")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.assign_professor(
            application_id=app.id,
            professor_nycu_id=ee_professor.nycu_id,
            assigned_by=college,
        )


@pytest.mark.asyncio
async def test_happy_path_admin_assigns_and_application_updated(db: AsyncSession, silence_side_effects):
    """Admin assigns a professor → application.professor_id is updated to that user's id."""
    admin = await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="a_happy")
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_happy")
    professor = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="p_happy", dept_code="CS")
    cfg = await _seed_config(db, requires_prof=True, suffix="happy")
    app = await _seed_app(db, student=student, config=cfg, suffix="happy")
    service = ApplicationService(db)

    result = await service.assign_professor(
        application_id=app.id,
        professor_nycu_id=professor.nycu_id,
        assigned_by=admin,
    )

    assert result.id == app.id
    assert result.professor_id == professor.id


@pytest.mark.asyncio
async def test_collaborator_failures_do_not_block_db_write(db: AsyncSession, raise_side_effects):
    """If NotificationService raises, the assignment must still be persisted —
    it's a best-effort side effect per the production try/except boundary.
    """
    admin = await _seed_user(db, role=UserRole.admin, name="Admin", nycu_id="a_collab_fail")
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_collab_fail")
    professor = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="p_collab_fail", dept_code="CS")
    cfg = await _seed_config(db, requires_prof=True, suffix="collab_fail")
    app = await _seed_app(db, student=student, config=cfg, suffix="collab_fail")
    service = ApplicationService(db)

    # Should NOT raise even though both collaborators throw.
    result = await service.assign_professor(
        application_id=app.id,
        professor_nycu_id=professor.nycu_id,
        assigned_by=admin,
    )
    assert result.professor_id == professor.id
