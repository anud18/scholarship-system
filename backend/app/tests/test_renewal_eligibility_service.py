"""
Tests for RenewalEligibilityService.

Verifies that prior approved applications are surfaced as renewal candidates
only when the corresponding ScholarshipConfiguration for the current academic
year is in its renewal_application_period window.

Architectural note: renewal_application_{start,end}_date live on
ScholarshipConfiguration (per academic_year + semester), NOT on
ScholarshipType. The service queries through the configuration of the
*current* academic year.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.services.renewal_eligibility_service import RenewalEligibilityService


def _config(
    scholarship_type_id: int,
    *,
    academic_year: int,
    in_renewal_period: bool,
    config_code: str,
) -> ScholarshipConfiguration:
    """Build a ScholarshipConfiguration with renewal-period dates set
    either to bracket `now` (active) or fully in the past (inactive).
    """
    now = datetime.now(timezone.utc)
    if in_renewal_period:
        start = now - timedelta(days=1)
        end = now + timedelta(days=7)
    else:
        # Renewal period closed a week ago
        start = now - timedelta(days=14)
        end = now - timedelta(days=7)

    return ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Test Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
        renewal_application_start_date=start,
        renewal_application_end_date=end,
    )


async def _make_prior_approved_application(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    prior_year: int,
    status: ApplicationStatus = ApplicationStatus.approved,
    app_id_suffix: str = "00001",
) -> Application:
    """Insert a prior-year application in the given status."""
    app = Application(
        app_id=f"APP-{prior_year}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_subtype_list=["general"],
        sub_type_selection_mode="single",
        sub_scholarship_type="general",
        academic_year=prior_year,
        semester=None,
        status=status,
        is_renewal=False,
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_returns_empty_when_no_prior_approved(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """A user with zero prior applications gets an empty list."""
    # Create an active renewal configuration for the current academic year so
    # the only thing missing is a prior approved application.
    config = _config(
        test_scholarship.id,
        academic_year=114,
        in_renewal_period=True,
        config_code="RE-114-NONE",
    )
    db.add(config)
    await db.commit()

    service = RenewalEligibilityService(db)
    result = await service.get_eligible_renewals(user_id=test_user.id, current_academic_year=114)

    assert result == []


@pytest.mark.asyncio
async def test_returns_prior_approved_when_in_renewal_period(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """User with 113 approved + 114 config inside renewal window -> 113 app is returned."""
    config = _config(
        test_scholarship.id,
        academic_year=114,
        in_renewal_period=True,
        config_code="RE-114-OPEN",
    )
    db.add(config)
    await db.commit()

    prior = await _make_prior_approved_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        prior_year=113,
    )

    service = RenewalEligibilityService(db)
    result = await service.get_eligible_renewals(user_id=test_user.id, current_academic_year=114)

    assert len(result) == 1
    assert result[0].id == prior.id
    assert result[0].academic_year == 113
    assert result[0].status == ApplicationStatus.approved


@pytest.mark.asyncio
async def test_excludes_rejected_prior(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """A rejected prior application must not surface as a renewal candidate."""
    config = _config(
        test_scholarship.id,
        academic_year=114,
        in_renewal_period=True,
        config_code="RE-114-REJ",
    )
    db.add(config)
    await db.commit()

    await _make_prior_approved_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        prior_year=113,
        status=ApplicationStatus.rejected,
    )

    service = RenewalEligibilityService(db)
    result = await service.get_eligible_renewals(user_id=test_user.id, current_academic_year=114)

    assert result == []


@pytest.mark.asyncio
async def test_excludes_when_not_in_renewal_period(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Prior application is approved, but the current-year config's renewal
    period is closed -> empty list."""
    config = _config(
        test_scholarship.id,
        academic_year=114,
        in_renewal_period=False,  # closed
        config_code="RE-114-CLOSED",
    )
    db.add(config)
    await db.commit()

    await _make_prior_approved_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        prior_year=113,
    )

    service = RenewalEligibilityService(db)
    result = await service.get_eligible_renewals(user_id=test_user.id, current_academic_year=114)

    assert result == []
