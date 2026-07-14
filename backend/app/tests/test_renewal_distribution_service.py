"""Tests for RenewalDistributionService.

Verifies that renewal applications that have completed their required review
stages are auto-approved (status -> approved, review_stage -> quota_distributed),
while non-renewal and not-yet-reviewed applications are left untouched.

The "terminal" review stage is configuration-driven:
    - When ScholarshipConfiguration.requires_college_review = True:
        terminal stage is ReviewStage.college_reviewed
    - When requires_college_review = False:
        terminal stage is ReviewStage.professor_reviewed

These tests use the same conftest fixtures as the other renewal tests
(`db`, `test_user`, `test_scholarship`), plus a locally-built
ScholarshipConfiguration with `requires_college_review` set.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.services.renewal_distribution_service import RenewalDistributionService

CURRENT_ACADEMIC_YEAR = 114


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_config(
    scholarship_type_id: int,
    *,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
    requires_college_review: bool = True,
    config_code: str = "RDS-CFG",
) -> ScholarshipConfiguration:
    """Build a ScholarshipConfiguration row exposing the review flags
    used by RenewalDistributionService to decide the terminal stage.
    """
    return ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
        requires_professor_recommendation=True,
        requires_college_review=requires_college_review,
    )


async def _make_application(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    is_renewal: bool,
    status: ApplicationStatus,
    review_stage: ReviewStage,
    app_id_suffix: str,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> Application:
    """Insert an application with explicit (is_renewal, status, review_stage)."""
    app = Application(
        app_id=f"APP-{academic_year}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_subtype_list=["general"],
        sub_type_selection_mode="single",
        sub_scholarship_type="general",
        academic_year=academic_year,
        semester=None,
        status=status,
        review_stage=review_stage,
        is_renewal=is_renewal,
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_auto_approves_renewals_with_passed_reviews(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Two renewal applications, both already at `college_reviewed` and in
    `under_review`, should be auto-approved and advanced to `quota_distributed`.
    """
    # Configuration requires college review -> terminal stage is college_reviewed.
    config = _make_config(test_scholarship.id, requires_college_review=True)
    db.add(config)
    await db.commit()

    app_a = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
        app_id_suffix="00001",
    )
    app_b = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
        app_id_suffix="00002",
    )

    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    assert result["approved_count"] == 2
    assert set(result["approved_ids"]) == {app_a.id, app_b.id}

    # Verify the persisted state on both rows.
    refreshed = (
        (await db.execute(select(Application).where(Application.id.in_([app_a.id, app_b.id])).order_by(Application.id)))
        .scalars()
        .all()
    )
    assert len(refreshed) == 2
    for app in refreshed:
        assert app.status == ApplicationStatus.approved
        assert app.review_stage == ReviewStage.quota_distributed


@pytest.mark.asyncio
async def test_does_not_approve_non_renewal(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """A non-renewal (is_renewal=False) application at college_reviewed must be
    left in `under_review`."""
    config = _make_config(test_scholarship.id, requires_college_review=True)
    db.add(config)
    await db.commit()

    non_renewal = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=False,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
        app_id_suffix="00010",
    )

    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    assert result["approved_count"] == 0
    assert result["approved_ids"] == []

    refreshed = await db.scalar(select(Application).where(Application.id == non_renewal.id))
    assert refreshed.status == ApplicationStatus.under_review
    assert refreshed.review_stage == ReviewStage.college_reviewed


@pytest.mark.asyncio
async def test_does_not_approve_not_yet_reviewed(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """A renewal application still in `professor_review` (not yet at the
    terminal `college_reviewed` stage) must NOT be auto-approved."""
    config = _make_config(test_scholarship.id, requires_college_review=True)
    db.add(config)
    await db.commit()

    in_flight = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.professor_review,
        app_id_suffix="00020",
    )

    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    assert result["approved_count"] == 0
    assert result["approved_ids"] == []

    refreshed = await db.scalar(select(Application).where(Application.id == in_flight.id))
    assert refreshed.status == ApplicationStatus.under_review
    assert refreshed.review_stage == ReviewStage.professor_review


@pytest.mark.asyncio
async def test_skips_renewal_whose_subtype_was_rejected_in_review(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """A renewal at the terminal stage whose sub_scholarship_type carries a
    reviewer reject (不同意) must NOT be auto-approved — it stays under_review
    and is reported in skipped_rejected_ids (rejection gate, 回發 leak path)."""
    config = _make_config(test_scholarship.id, requires_college_review=True)
    db.add(config)
    await db.commit()

    rejected_app = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
        app_id_suffix="00030",
    )
    review = ApplicationReview(
        application_id=rejected_app.id,
        reviewer_id=test_user.id,
        recommendation="reject",
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    # Mixed case on purpose: the gate must normalize both sides.
    db.add(
        ApplicationReviewItem(review_id=review.id, sub_type_code="General", recommendation="reject", comments="不同意")
    )
    await db.commit()

    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    assert result["approved_count"] == 0
    assert result["skipped_rejected_ids"] == [rejected_app.id]

    refreshed = await db.scalar(select(Application).where(Application.id == rejected_app.id))
    assert refreshed.status == ApplicationStatus.under_review
    assert refreshed.review_stage == ReviewStage.college_reviewed
