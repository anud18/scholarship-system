"""Tests for RenewalDistributionService.

Verifies that renewal applications that have completed their required review
stages are auto-approved (status -> approved, review_stage -> quota_distributed),
while non-renewal and not-yet-reviewed applications are left untouched.

The "terminal" review stage is driven by the renewal-specific admin flags:
    - When ScholarshipConfiguration.renewal_requires_college_review = True:
        terminal stage is ReviewStage.college_reviewed
    - When only renewal_requires_professor_review = True:
        terminal stage is ReviewStage.professor_reviewed
    - When neither renewal review is required:
        terminal stage is ReviewStage.student_submitted (status may still
        be `submitted`)

These tests use the same conftest fixtures as the other renewal tests
(`db`, `test_user`, `test_scholarship`), plus a locally-built
ScholarshipConfiguration with the renewal review flags set.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
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
    renewal_requires_professor_review: bool = True,
    renewal_requires_college_review: bool = True,
    config_code: str = "RDS-CFG",
) -> ScholarshipConfiguration:
    """Build a ScholarshipConfiguration row exposing the renewal review
    flags used by RenewalDistributionService to decide the terminal stage.
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
        requires_college_review=True,
        renewal_requires_professor_review=renewal_requires_professor_review,
        renewal_requires_college_review=renewal_requires_college_review,
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
    # Configuration requires renewal college review -> terminal stage is college_reviewed.
    config = _make_config(test_scholarship.id, renewal_requires_college_review=True)
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
    config = _make_config(test_scholarship.id, renewal_requires_college_review=True)
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
    config = _make_config(test_scholarship.id, renewal_requires_college_review=True)
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
async def test_terminal_stage_professor_when_college_not_required_for_renewal(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """renewal_requires_college_review=False + renewal_requires_professor_review=True
    -> a renewal at `professor_reviewed` auto-approves. The GENERAL
    requires_college_review flag stays True to pin that renewals no longer
    follow the general-application flags."""
    config = _make_config(
        test_scholarship.id,
        renewal_requires_professor_review=True,
        renewal_requires_college_review=False,
    )
    db.add(config)
    await db.commit()

    renewal = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.professor_reviewed,
        app_id_suffix="00030",
    )

    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    assert result["approved_count"] == 1
    assert result["approved_ids"] == [renewal.id]

    refreshed = await db.scalar(select(Application).where(Application.id == renewal.id))
    assert refreshed.status == ApplicationStatus.approved
    assert refreshed.review_stage == ReviewStage.quota_distributed


@pytest.mark.asyncio
async def test_auto_approves_submitted_renewal_when_no_review_required(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Admin disabled BOTH renewal review steps -> a renewal that is merely
    `submitted` at `student_submitted` auto-approves without any reviewer."""
    config = _make_config(
        test_scholarship.id,
        renewal_requires_professor_review=False,
        renewal_requires_college_review=False,
    )
    db.add(config)
    await db.commit()

    renewal = await _make_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        is_renewal=True,
        status=ApplicationStatus.submitted,
        review_stage=ReviewStage.student_submitted,
        app_id_suffix="00040",
    )

    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    assert result["approved_count"] == 1
    assert result["approved_ids"] == [renewal.id]

    refreshed = await db.scalar(select(Application).where(Application.id == renewal.id))
    assert refreshed.status == ApplicationStatus.approved
    assert refreshed.review_stage == ReviewStage.quota_distributed


# Touched at import-time so unused-import linters don't strip the helper alias.
_ = datetime.now(timezone.utc)
