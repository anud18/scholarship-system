"""RenewalDistributionService — auto-approve renewals that have passed reviews.

Renewal applications, unlike general applications, do NOT go through the
college_ranking step. Once they have cleared the required review stages
(professor +/- college), administrators trigger this service to flip them
from `under_review` straight to `approved` with `review_stage =
quota_distributed`.

The terminal stage is configuration-driven so scholarships that skip college
review (`ScholarshipConfiguration.requires_college_review = False`) only need
the professor review to finish before auto-approval.
"""

from typing import Dict, List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration
from app.services.manual_distribution_service import _norm_sub_type, load_rejected_subtype_map


class RenewalDistributionService:
    """Service that auto-approves renewal applications past their review stage."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _resolve_terminal_stages(self, scholarship_type_id: int, academic_year: int) -> List[ReviewStage]:
        """Return the review stage(s) at which a renewal becomes eligible
        for auto-approval, based on the configuration's review-flow flags.

        - requires_college_review = True (default) -> [college_reviewed]
        - requires_college_review = False          -> [professor_reviewed]

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
        requires_college = True
        if config is not None:
            # `requires_college_review` defaults to False at the column level
            # but the active scholarship configurations in this system have it
            # set explicitly; trust whatever the row says.
            requires_college = bool(getattr(config, "requires_college_review", True))

        if requires_college:
            return [ReviewStage.college_reviewed]
        return [ReviewStage.professor_reviewed]

    async def auto_approve_passed_reviews(self, scholarship_type_id: int, academic_year: int) -> Dict[str, object]:
        """Auto-approve renewal applications past their terminal review stage.

        Matches:
            - is_renewal = True
            - status = under_review
            - review_stage in terminal stages (per configuration)
            - scholarship_type_id / academic_year as supplied

        Applications whose sub_scholarship_type carries a reviewer reject
        (不同意) are excluded and reported as skipped — the rejection gate is
        unconditional across every distribution writer, and a rejected renewal
        can reach a terminal stage here via the admin 回發 override path.

        Side effects:
            - Updates matched applications:
                status = approved
                review_stage = quota_distributed
            - Commits the surrounding transaction.

        Returns:
            {
              "approved_count": int,
              "approved_ids": List[int],
              "skipped_rejected_ids": List[int],
            }
        """
        terminal_stages = await self._resolve_terminal_stages(
            scholarship_type_id=scholarship_type_id, academic_year=academic_year
        )

        candidate_filters = (
            Application.scholarship_type_id == scholarship_type_id,
            Application.academic_year == academic_year,
            Application.is_renewal.is_(True),
            Application.status == ApplicationStatus.under_review,
            Application.review_stage.in_(terminal_stages),
        )

        candidates = (
            await self.db.execute(select(Application.id, Application.sub_scholarship_type).where(*candidate_filters))
        ).all()
        rejected_map = await load_rejected_subtype_map(self.db, [app_id for app_id, _ in candidates])
        skipped_rejected_ids = [
            app_id for app_id, sub_type in candidates if _norm_sub_type(sub_type) in rejected_map.get(app_id, set())
        ]
        skipped_set = set(skipped_rejected_ids)

        approved_ids: List[int] = []
        approvable_ids = [app_id for app_id, _ in candidates if app_id not in skipped_set]
        if approvable_ids:
            stmt = (
                update(Application)
                .where(Application.id.in_(approvable_ids), *candidate_filters)
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
            "skipped_rejected_ids": skipped_rejected_ids,
        }
