"""
Regression tests for ReviewService.assert_professor_review_unlocked — issue #64.

Once an application's review_stage advances to college_review (or any stage
beyond), professors must not be able to submit or update their reviews.
Admins / super_admins keep an escape hatch.
"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.application import Application
from app.models.enums import ReviewStage
from app.models.user import User, UserRole, UserType
from app.services.review_service import (
    LOCKED_STAGES_FOR_PROFESSOR_REVIEW,
    ReviewService,
    is_professor_review_locked,
)


def _make_user(role: UserRole, suffix: str) -> User:
    return User(
        nycu_id=f"reviewlock_{role.value}_{suffix}",
        name=f"Reviewlock {role.value} {suffix}",
        email=f"reviewlock_{role.value}_{suffix}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )


def test_lock_set_includes_all_post_college_stages():
    """Every stage from college_review onward must be in the lock set; earlier stages must not be."""
    expected_locked = {
        ReviewStage.college_review.value,
        ReviewStage.college_reviewed.value,
        ReviewStage.college_ranking.value,
        ReviewStage.college_ranked.value,
        ReviewStage.admin_review.value,
        ReviewStage.admin_reviewed.value,
        ReviewStage.quota_distribution.value,
        ReviewStage.quota_distributed.value,
        ReviewStage.roster_preparation.value,
        ReviewStage.roster_prepared.value,
        ReviewStage.roster_submitted.value,
        ReviewStage.completed.value,
        ReviewStage.archived.value,
    }
    assert LOCKED_STAGES_FOR_PROFESSOR_REVIEW == expected_locked
    # Sanity: editable stages must NOT be in the lock set
    for stage in (
        ReviewStage.student_draft,
        ReviewStage.student_submitted,
        ReviewStage.professor_review,
        ReviewStage.professor_reviewed,
    ):
        assert stage.value not in LOCKED_STAGES_FOR_PROFESSOR_REVIEW


def test_is_professor_review_locked_handles_string_stage():
    app = MagicMock(spec=Application)
    app.review_stage = "college_review"
    assert is_professor_review_locked(app) is True

    app.review_stage = "professor_reviewed"
    assert is_professor_review_locked(app) is False


def test_is_professor_review_locked_handles_enum_stage():
    app = MagicMock(spec=Application)
    app.review_stage = ReviewStage.admin_review
    assert is_professor_review_locked(app) is True

    app.review_stage = ReviewStage.student_submitted
    assert is_professor_review_locked(app) is False


@pytest.mark.asyncio
async def test_assert_unlocks_for_admin_even_when_stage_locked(db: AsyncSession):
    """Admin must bypass the lock — manual intervention escape hatch."""
    admin = _make_user(UserRole.admin, "a")
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    app = Application(
        app_id="APP-TEST-LOCK-ADMIN",
        user_id=admin.id,
        academic_year=114,
        scholarship_type_id=1,
        sub_type_selection_mode="single",
        review_stage=ReviewStage.college_review.value,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    service = ReviewService(db)
    # Should NOT raise
    await service.assert_professor_review_unlocked(app.id, admin)


@pytest.mark.asyncio
async def test_assert_raises_for_professor_when_stage_locked(db: AsyncSession):
    professor = _make_user(UserRole.professor, "p")
    db.add(professor)
    await db.commit()
    await db.refresh(professor)

    app = Application(
        app_id="APP-TEST-LOCK-PROF",
        user_id=professor.id,
        academic_year=114,
        scholarship_type_id=1,
        sub_type_selection_mode="single",
        review_stage=ReviewStage.college_reviewed.value,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    service = ReviewService(db)
    with pytest.raises(AuthorizationError):
        await service.assert_professor_review_unlocked(app.id, professor)


@pytest.mark.asyncio
async def test_assert_passes_when_stage_unlocked(db: AsyncSession):
    professor = _make_user(UserRole.professor, "p2")
    db.add(professor)
    await db.commit()
    await db.refresh(professor)

    app = Application(
        app_id="APP-TEST-UNLOCKED",
        user_id=professor.id,
        academic_year=114,
        scholarship_type_id=1,
        sub_type_selection_mode="single",
        review_stage=ReviewStage.professor_reviewed.value,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    service = ReviewService(db)
    # Should NOT raise (still in editable stage)
    await service.assert_professor_review_unlocked(app.id, professor)


@pytest.mark.asyncio
async def test_assert_raises_not_found_for_missing_application(db: AsyncSession):
    professor = _make_user(UserRole.professor, "p3")
    db.add(professor)
    await db.commit()
    await db.refresh(professor)

    service = ReviewService(db)
    with pytest.raises(NotFoundError):
        await service.assert_professor_review_unlocked(99999, professor)
