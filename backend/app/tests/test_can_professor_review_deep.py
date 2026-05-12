"""
Deep async-DB tests for `ApplicationService.can_professor_review_application`.

Authorization helper guarding professor-side application views. Gets
called on every page load in the professor dashboard — a regression
would either expose applications to the wrong professor (security) or
hide them from the right professor (functional).

Contract pinned (5 cases):
- Application not found ⇒ False.
- Scholarship configuration doesn't require professor recommendation ⇒
  False (irrelevant to professor review queue).
- Assigned to a different professor ⇒ False (the assignment guard).
- Wrong application status (e.g., draft) ⇒ False.
- Happy path: assigned + requires-prof-rec + in {submitted, under_review,
  approved, partial_approved, rejected} ⇒ True.
"""

from datetime import datetime, timezone

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


async def _seed_config(db: AsyncSession, *, requires_prof: bool, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"canrev_{suffix}", name=f"CanRev type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"canrev_cfg_{suffix}",
        config_name=f"CanRev cfg {suffix}",
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
    status: str,
    professor_id: int | None = None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-CANREV-{suffix}",
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
    professor = await _seed_user(db, role=UserRole.professor, nycu_id="canrev_prof_404")
    service = ApplicationService(db)
    assert await service.can_professor_review_application(999_999, professor.id) is False


@pytest.mark.asyncio
async def test_returns_false_when_scholarship_does_not_require_professor(db: AsyncSession):
    student = await _seed_user(db, role=UserRole.student, nycu_id="canrev_stu_noprof")
    professor = await _seed_user(db, role=UserRole.professor, nycu_id="canrev_prof_noprof")
    cfg = await _seed_config(db, requires_prof=False, suffix="noprof")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=professor.id,
        suffix="noprof",
    )

    service = ApplicationService(db)
    assert await service.can_professor_review_application(app.id, professor.id) is False


@pytest.mark.asyncio
async def test_returns_false_when_assigned_to_different_professor(db: AsyncSession):
    student = await _seed_user(db, role=UserRole.student, nycu_id="canrev_stu_wrong_prof")
    professor_a = await _seed_user(db, role=UserRole.professor, nycu_id="canrev_prof_a")
    professor_b = await _seed_user(db, role=UserRole.professor, nycu_id="canrev_prof_b")
    cfg = await _seed_config(db, requires_prof=True, suffix="wrong_prof")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=professor_a.id,
        suffix="wrong_prof",
    )

    service = ApplicationService(db)
    # Professor B trying to access — must be False.
    assert await service.can_professor_review_application(app.id, professor_b.id) is False
    # Professor A (the assigned one) can.
    assert await service.can_professor_review_application(app.id, professor_a.id) is True


@pytest.mark.asyncio
async def test_returns_false_for_draft_application(db: AsyncSession):
    """Drafts aren't visible to the professor — only submitted+ statuses are."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="canrev_stu_draft")
    professor = await _seed_user(db, role=UserRole.professor, nycu_id="canrev_prof_draft")
    cfg = await _seed_config(db, requires_prof=True, suffix="draft")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.draft.value,
        professor_id=professor.id,
        suffix="draft",
    )

    service = ApplicationService(db)
    assert await service.can_professor_review_application(app.id, professor.id) is False


@pytest.mark.asyncio
async def test_returns_true_for_all_visible_statuses(db: AsyncSession):
    """The 5 visible statuses (submitted, under_review, approved,
    partial_approved, rejected) must each return True. This pins the
    historical-review path — a regression that excluded e.g. 'rejected'
    would silently hide already-decided applications from the professor."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="canrev_stu_visible")
    professor = await _seed_user(db, role=UserRole.professor, nycu_id="canrev_prof_visible")
    cfg = await _seed_config(db, requires_prof=True, suffix="visible")

    for status_value in [
        ApplicationStatus.submitted.value,
        ApplicationStatus.under_review.value,
        ApplicationStatus.approved.value,
        ApplicationStatus.partial_approved.value,
        ApplicationStatus.rejected.value,
    ]:
        app = await _seed_app(
            db,
            student=student,
            config=cfg,
            status=status_value,
            professor_id=professor.id,
            suffix=f"visible_{status_value}",
        )
        service = ApplicationService(db)
        assert (
            await service.can_professor_review_application(app.id, professor.id) is True
        ), f"status={status_value} should be visible to professor"
