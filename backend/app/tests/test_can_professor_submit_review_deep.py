"""
Deep async-DB tests for `ApplicationService.can_professor_submit_review`.

Paired with `can_professor_review_application` (covered in #255). This
one also applies the time-window restriction: submission is only allowed
when `now` is between application_start_date and professor_review_end
(or the renewal equivalents for renewal applications).

Contract pinned (6 cases):
- Application not found ⇒ False.
- Wrong professor (assignment guard) ⇒ False.
- Wrong status (e.g., draft) ⇒ False.
- No review window configured ⇒ True (test-friendly fallback).
- Inside review window ⇒ True.
- Outside review window (past or future) ⇒ False.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _seed_config(
    db: AsyncSession,
    *,
    suffix: str,
    application_start_date: datetime | None = None,
    professor_review_end: datetime | None = None,
) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"cansub_{suffix}", name=f"CanSub type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"cansub_cfg_{suffix}",
        config_name=f"CanSub cfg {suffix}",
        academic_year=114,
        application_start_date=application_start_date or datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        professor_review_end=professor_review_end,
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
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-CANSUB-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor_id,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_application_not_found_returns_false(db: AsyncSession):
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_404")
    service = ApplicationService(db)
    assert await service.can_professor_submit_review(999_999, prof.id) is False


@pytest.mark.asyncio
async def test_wrong_professor_returns_false(db: AsyncSession):
    student = await _seed_user(db, role=UserRole.student, nycu_id="cansub_stu_wrong")
    prof_a = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_a")
    prof_b = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_b")
    cfg = await _seed_config(db, suffix="wrong_prof")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof_a.id,
        suffix="wrong_prof",
    )
    service = ApplicationService(db)
    assert await service.can_professor_submit_review(app.id, prof_b.id) is False


@pytest.mark.asyncio
async def test_wrong_status_returns_false(db: AsyncSession):
    """Drafts can't be reviewed — only submitted and under_review."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="cansub_stu_draft")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_draft")
    cfg = await _seed_config(db, suffix="draft")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.draft.value,
        professor_id=prof.id,
        suffix="draft",
    )
    service = ApplicationService(db)
    assert await service.can_professor_submit_review(app.id, prof.id) is False


@pytest.mark.asyncio
async def test_no_review_window_configured_returns_true(db: AsyncSession):
    """professor_review_end=None ⇒ no time restriction (test fallback)."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="cansub_stu_no_window")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_no_window")
    # No professor_review_end set ⇒ time check is bypassed.
    cfg = await _seed_config(db, suffix="no_window", professor_review_end=None)
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="no_window",
    )
    service = ApplicationService(db)
    assert await service.can_professor_submit_review(app.id, prof.id) is True


@pytest.mark.asyncio
async def test_inside_review_window_returns_true(db: AsyncSession):
    """now is between application_start and professor_review_end ⇒ True."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="cansub_stu_inside")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_inside")
    now = datetime.now(timezone.utc)
    cfg = await _seed_config(
        db,
        suffix="inside",
        application_start_date=now - timedelta(days=10),
        professor_review_end=now + timedelta(days=10),
    )
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="inside",
    )
    service = ApplicationService(db)
    assert await service.can_professor_submit_review(app.id, prof.id) is True


@pytest.mark.asyncio
async def test_outside_review_window_returns_false(db: AsyncSession):
    """now is past professor_review_end ⇒ False (the deadline guard)."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="cansub_stu_outside")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="cansub_prof_outside")
    now = datetime.now(timezone.utc)
    # Window has already closed (10 days ago).
    cfg = await _seed_config(
        db,
        suffix="outside",
        application_start_date=now - timedelta(days=30),
        professor_review_end=now - timedelta(days=10),
    )
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="outside",
    )
    service = ApplicationService(db)
    assert await service.can_professor_submit_review(app.id, prof.id) is False
