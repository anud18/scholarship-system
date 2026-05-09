"""
Regression tests for ReviewService.update_application_status — issue #182.

Before the fix, a single professor "approve" recommendation flipped
``application.status`` straight to ``approved``, even when the scholarship
configuration had ``requires_college_review=True``. That bypassed the
college step AND locked the student out of withdrawal (``withdraw`` only
accepts ``submitted`` / ``under_review``).

These tests pin the gating behavior in place: with college review required,
a professor "approve" must keep the app at ``under_review``; once college
also approves, status flips to ``approved``.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.review_service import ReviewService


def _val(x):
    """Normalise enum/string for stable equality assertions."""
    return x.value if hasattr(x, "value") else x


def _user(role: UserRole, suffix: str) -> User:
    return User(
        nycu_id=f"gating_{role.value}_{suffix}",
        name=f"Gating {role.value} {suffix}",
        email=f"gating_{role.value}_{suffix}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )


async def _seed_scholarship_and_config(db: AsyncSession, *, requires_college_review: bool) -> ScholarshipConfiguration:
    """Insert a minimal ScholarshipType + ScholarshipConfiguration pair."""
    stype = ScholarshipType(
        code=f"phd_test_{int(requires_college_review)}",
        name=f"PhD test ({'college' if requires_college_review else 'no-college'})",
        status="active",
    )
    db.add(stype)
    await db.commit()
    await db.refresh(stype)

    config = ScholarshipConfiguration(
        scholarship_type_id=stype.id,
        config_code=f"phd_test_cfg_{int(requires_college_review)}",
        config_name="PhD test config",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=requires_college_review,
        amount=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def _seed_app(db: AsyncSession, *, student: User, config: ScholarshipConfiguration) -> Application:
    app = Application(
        app_id=f"APP-GATING-{config.id}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=ApplicationStatus.submitted.value,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _seed_review(
    db: AsyncSession,
    *,
    application: Application,
    reviewer: User,
    sub_type_code: str,
    recommendation: str,
) -> None:
    review = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer.id,
        recommendation=recommendation,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    item = ApplicationReviewItem(
        review_id=review.id,
        sub_type_code=sub_type_code,
        recommendation=recommendation,
    )
    db.add(item)
    await db.commit()


# ---------------------------------------------------------------------------
# The bug fix — issue #182
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_professor_approve_keeps_status_under_review_when_college_required(db: AsyncSession):
    """The exact scenario from issue #182.

    Config: requires_professor_recommendation=True, requires_college_review=True.
    Action: a professor approves the only sub-type.
    Expected: status stays at under_review (NOT approved); review_stage=professor_reviewed.
    """
    student = _user(UserRole.student, "s")
    professor = _user(UserRole.professor, "p")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert (
        _val(final_status) == ApplicationStatus.under_review.value
    ), f"professor approve should not promote to approved when college review required; got {final_status}"
    # Identity-mapped — the object the test holds is the same one the service
    # mutated. We assert directly rather than db.refresh, because refresh would
    # revert the in-memory change back to the (still-uncommitted) DB row.
    assert _val(app.status) == ApplicationStatus.under_review.value
    assert _val(app.review_stage) == ReviewStage.professor_reviewed.value


@pytest.mark.asyncio
async def test_college_approve_after_professor_promotes_to_approved(db: AsyncSession):
    """Continuing #182 — once college also approves, status should flip to approved."""
    student = _user(UserRole.student, "s2")
    professor = _user(UserRole.professor, "p2")
    college = _user(UserRole.college, "c2")
    db.add_all([student, professor, college])
    await db.commit()
    for u in (student, professor, college):
        await db.refresh(u)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="approve")
    await _seed_review(db, application=app, reviewer=college, sub_type_code="default", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.approved.value
    assert _val(app.review_stage) == ReviewStage.college_reviewed.value


@pytest.mark.asyncio
async def test_professor_approve_promotes_to_approved_when_no_college_review(db: AsyncSession):
    """Pre-fix happy path must not regress.

    Config: requires_college_review=False.
    A professor approve should still flip status to approved immediately
    (there's no college step in the configured pipeline).
    """
    student = _user(UserRole.student, "s3")
    professor = _user(UserRole.professor, "p3")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=False)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.approved.value
    assert _val(app.review_stage) == ReviewStage.professor_reviewed.value


@pytest.mark.asyncio
async def test_full_reject_is_terminal_regardless_of_pipeline(db: AsyncSession):
    """All-rejected should still be terminal — no later role can rescue."""
    student = _user(UserRole.student, "s4")
    professor = _user(UserRole.professor, "p4")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="reject")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.rejected.value
