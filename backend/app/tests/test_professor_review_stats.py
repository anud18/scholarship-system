"""
Unit tests for `ApplicationService.get_professor_review_stats`.

Pins the fix from issue #218 (partial): the method previously queried the
placeholder `ProfessorReview` class (a `pass` stub from an unfinished
migration), which would 500 in production. The fix moves the query to the
unified ApplicationReview table.

These tests pin:
- completed_reviews counts ApplicationReview rows by reviewer.
- pending_reviews counts applications assigned to the professor in
  submitted/under_review that this reviewer has not reviewed yet.
- Reviewing an application removes it from pending and adds it to
  completed.
- A professor with nothing assigned gets all-zeros (NOT via fallback;
  via correct empty-count semantics).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.review import ApplicationReview
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_user(db: AsyncSession, *, role: UserRole, suffix: str) -> User:
    u = User(
        nycu_id=f"stats218_{role.value}_{suffix}",
        name=f"Stats218 {role.value} {suffix}",
        email=f"stats218_{role.value}_{suffix}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_scholarship_and_config(db: AsyncSession, *, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"stats218_{suffix}", name=f"Stats218 type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"stats218_cfg_{suffix}",
        config_name=f"Stats218 cfg {suffix}",
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
    professor: User | None,
    config: ScholarshipConfiguration,
    status: str,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-STATS218-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor.id if professor else None,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _seed_review(db: AsyncSession, *, application: Application, reviewer: User) -> ApplicationReview:
    r = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer.id,
        recommendation="approve",
        comments="seed",
        reviewed_at=_utcnow(),
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@pytest.mark.asyncio
async def test_stats_all_zero_when_professor_has_no_assignments(db: AsyncSession):
    """A fresh professor sees 0/0/0 — not via fallback but via real empty counts."""
    professor = await _seed_user(db, role=UserRole.professor, suffix="empty")

    service = ApplicationService(db)
    stats = await service.get_professor_review_stats(professor.id)

    assert stats == {"pending_reviews": 0, "completed_reviews": 0, "overdue_reviews": 0}


@pytest.mark.asyncio
async def test_stats_count_pending_for_assigned_unreviewed_apps(db: AsyncSession):
    """Apps assigned to this professor in submitted/under_review without a review row count as pending."""
    professor = await _seed_user(db, role=UserRole.professor, suffix="pending")
    student = await _seed_user(db, role=UserRole.student, suffix="pending")
    cfg = await _seed_scholarship_and_config(db, suffix="pending")

    await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        suffix="p1",
    )
    await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.under_review.value,
        suffix="p2",
    )

    service = ApplicationService(db)
    stats = await service.get_professor_review_stats(professor.id)

    assert stats["pending_reviews"] == 2
    assert stats["completed_reviews"] == 0


@pytest.mark.asyncio
async def test_stats_reviewed_app_moves_from_pending_to_completed(db: AsyncSession):
    """Once a professor submits a review, the app shifts pending → completed."""
    professor = await _seed_user(db, role=UserRole.professor, suffix="shift")
    student = await _seed_user(db, role=UserRole.student, suffix="shift")
    cfg = await _seed_scholarship_and_config(db, suffix="shift")

    app1 = await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        suffix="s1",
    )
    await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        suffix="s2",
    )

    # Professor reviews app1 only.
    await _seed_review(db, application=app1, reviewer=professor)

    service = ApplicationService(db)
    stats = await service.get_professor_review_stats(professor.id)

    assert stats["completed_reviews"] == 1, "review row counted as completed"
    assert stats["pending_reviews"] == 1, "reviewed app must not still count as pending"


@pytest.mark.asyncio
async def test_stats_ignore_other_professors_work(db: AsyncSession):
    """Reviews/assignments belonging to other professors do NOT leak into the result."""
    professor_a = await _seed_user(db, role=UserRole.professor, suffix="A")
    professor_b = await _seed_user(db, role=UserRole.professor, suffix="B")
    student = await _seed_user(db, role=UserRole.student, suffix="cross")
    cfg = await _seed_scholarship_and_config(db, suffix="cross")

    # Assigned to B, B has reviewed.
    app_b_reviewed = await _seed_app(
        db,
        student=student,
        professor=professor_b,
        config=cfg,
        status=ApplicationStatus.under_review.value,
        suffix="b-rev",
    )
    await _seed_review(db, application=app_b_reviewed, reviewer=professor_b)

    # Assigned to B, B hasn't reviewed.
    await _seed_app(
        db,
        student=student,
        professor=professor_b,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        suffix="b-pending",
    )

    service = ApplicationService(db)
    stats_a = await service.get_professor_review_stats(professor_a.id)

    assert stats_a == {"pending_reviews": 0, "completed_reviews": 0, "overdue_reviews": 0}

    stats_b = await service.get_professor_review_stats(professor_b.id)
    assert stats_b["completed_reviews"] == 1
    assert stats_b["pending_reviews"] == 1


@pytest.mark.asyncio
async def test_stats_skip_apps_not_in_submitted_or_under_review(db: AsyncSession):
    """Draft / approved / withdrawn / rejected apps don't count as pending — only submitted/under_review."""
    professor = await _seed_user(db, role=UserRole.professor, suffix="status")
    student = await _seed_user(db, role=UserRole.student, suffix="status")
    cfg = await _seed_scholarship_and_config(db, suffix="status")

    await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.draft.value,
        suffix="draft",
    )
    await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.approved.value,
        suffix="approved",
    )
    # One in scope:
    await _seed_app(
        db,
        student=student,
        professor=professor,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        suffix="submitted",
    )

    service = ApplicationService(db)
    stats = await service.get_professor_review_stats(professor.id)

    assert stats["pending_reviews"] == 1
