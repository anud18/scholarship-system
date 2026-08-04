"""
RenewalEligibilityService - determine which prior approved applications are
eligible to be renewed in the current academic year.

Architecture note:
    `renewal_application_start_date` / `renewal_application_end_date` live on
    `ScholarshipConfiguration` (one per ScholarshipType x academic_year x
    semester), NOT on `ScholarshipType`. To decide whether a prior approved
    application can be renewed *right now*, we look up the current-year
    configuration for that same scholarship_type and check its renewal window.

Eligibility rules (Phase 2, Section 7.1 of the renewal spec):
    1. The application belongs to `user_id`.
    2. Its `academic_year == current_academic_year - 1` (only previous-year
       cohorts may renew).
    3. Its `status == ApplicationStatus.approved`.
    4. The scholarship_type has a current-year ScholarshipConfiguration whose
       renewal_application window currently brackets `now`.
"""

from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration


class RenewalEligibilityService:
    """Service that identifies prior-year approved applications eligible for renewal."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_eligible_renewals(self, user_id: int, current_academic_year: int) -> List[Application]:
        """Return prior-year approved applications whose scholarship_type has an
        active renewal_application window in the current academic year.

        Args:
            user_id: The student's user id.
            current_academic_year: Academic year the student would be applying
                for (e.g. 114). Prior cohort is `current_academic_year - 1`.

        Returns:
            List of Application instances. Empty list when none qualify.
        """
        now = datetime.now(timezone.utc)
        prior_year = current_academic_year - 1

        # Join through ScholarshipConfiguration on (scholarship_type_id,
        # academic_year=current). The configuration row must have a non-null
        # renewal window bracketing `now`.
        stmt = (
            select(Application)
            .options(joinedload(Application.scholarship_type_ref))
            .join(
                ScholarshipConfiguration,
                ScholarshipConfiguration.scholarship_type_id == Application.scholarship_type_id,
            )
            .where(
                Application.user_id == user_id,
                Application.academic_year == prior_year,
                Application.status == ApplicationStatus.approved,
                ScholarshipConfiguration.academic_year == current_academic_year,
                ScholarshipConfiguration.is_active.is_(True),
                ScholarshipConfiguration.renewal_application_start_date.is_not(None),
                ScholarshipConfiguration.renewal_application_end_date.is_not(None),
                ScholarshipConfiguration.renewal_application_start_date <= now,
                ScholarshipConfiguration.renewal_application_end_date >= now,
            )
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().unique().all())
