"""RenewalDistributionService — auto-approve renewals that have passed reviews.

Renewal applications, unlike general applications, do NOT go through the
college_ranking step. Once they have cleared the required review stages
(professor +/- college), administrators trigger this service to flip them
from `under_review` straight to `approved` with `review_stage =
quota_distributed`.

The terminal stage is configuration-driven via the renewal-specific flags
(`ScholarshipConfiguration.renewal_requires_professor_review` /
`renewal_requires_college_review`): a renewal only needs the review steps the
administrator enabled for renewals before auto-approval — possibly none.
"""

from typing import Dict, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration


class RenewalDistributionService:
    """Service that auto-approves renewal applications past their review stage."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _resolve_terminal_stages(self, scholarship_type_id: int, academic_year: int) -> List[ReviewStage]:
        """Return the review stage(s) at which a renewal becomes eligible
        for auto-approval, based on the configuration's renewal review flags
        (admin decides per configuration whether renewals need professor
        and/or college review).

        - renewal_requires_college_review = True    -> [college_reviewed]
        - only renewal_requires_professor_review    -> [professor_reviewed]
        - neither review required                   -> [student_submitted]

        When no configuration row exists we conservatively default to
        college_reviewed: matches the dominant pattern in this codebase and
        avoids accidentally promoting renewals after only a professor review.
        """
        config = await self.db.scalar(
            select(ScholarshipConfiguration).where(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
            )
        )
        if config is None:
            return [ReviewStage.college_reviewed]

        if bool(config.renewal_requires_college_review):
            return [ReviewStage.college_reviewed]
        if bool(config.renewal_requires_professor_review):
            return [ReviewStage.professor_reviewed]
        return [ReviewStage.student_submitted]

    async def auto_approve_passed_reviews(self, scholarship_type_id: int, academic_year: int) -> Dict[str, object]:
        """Auto-approve renewal applications past their terminal review stage.

        Matches:
            - is_renewal = True
            - status = under_review (or submitted when no review is required)
            - review_stage in terminal stages (per configuration)
            - scholarship_type_id / academic_year as supplied

        Side effects:
            - Updates matched applications:
                status = approved
                review_stage = quota_distributed
            - Commits the surrounding transaction.

        Returns:
            {
              "approved_count": int,
              "approved_ids": List[int],
            }
        """
        terminal_stages = await self._resolve_terminal_stages(
            scholarship_type_id=scholarship_type_id, academic_year=academic_year
        )

        # When no review step is required (terminal stage = student_submitted),
        # the renewal never left `submitted` — accept it alongside the
        # reviewed `under_review` rows.
        eligible_statuses = [ApplicationStatus.under_review]
        if ReviewStage.student_submitted in terminal_stages:
            eligible_statuses.append(ApplicationStatus.submitted)

        stmt = (
            update(Application)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(True),
                Application.status.in_(eligible_statuses),
                Application.review_stage.in_(terminal_stages),
            )
            .values(
                status=ApplicationStatus.approved,
                review_stage=ReviewStage.quota_distributed,
            )
            .returning(Application.id)
            .execution_options(synchronize_session="fetch")
        )
        result = await self.db.execute(stmt)
        approved_ids = [row[0] for row in result.all()]
        await self.db.commit()

        return {
            "approved_count": len(approved_ids),
            "approved_ids": approved_ids,
        }
