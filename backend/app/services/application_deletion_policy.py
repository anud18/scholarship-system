"""
Admin hard-delete policy for applications.

An administrator may hard-delete an application at any point BEFORE it enters
the 配額分發 (quota distribution) stage. Once an allocation has been saved or
finalized for it, or it has been placed on a payment roster, the row is part of
the money trail and must be preserved.

"Entered distribution" is true when ANY of the following holds:
- ``review_stage`` is at/after ``quota_distribution``
- ``quota_allocation_status`` has been set by the distribution engine
- ``status`` is a distribution outcome (``approved`` / ``partial_approved``)
- a CollegeRankingItem for the application carries a saved allocation
  (``is_allocated`` / ``allocated_sub_type`` / status ``allocated``), or its
  ranking has ``distribution_executed``
- a PaymentRosterItem references the application
"""

from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.payment_roster import PaymentRosterItem

DELETE_BLOCKED_MESSAGE = "申請已進入分發階段，不可刪除"

DISTRIBUTION_REVIEW_STAGES: frozenset[str] = frozenset(
    {
        ReviewStage.quota_distribution.value,
        ReviewStage.quota_distributed.value,
        ReviewStage.roster_preparation.value,
        ReviewStage.roster_prepared.value,
        ReviewStage.roster_submitted.value,
        ReviewStage.completed.value,
        ReviewStage.archived.value,
    }
)

DISTRIBUTION_OUTCOME_STATUSES: frozenset[str] = frozenset(
    {
        ApplicationStatus.approved.value,
        ApplicationStatus.partial_approved.value,
    }
)

ALLOCATED_RANKING_ITEM_STATUS = "allocated"


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


async def find_distributed_application_ids(db: AsyncSession, application_ids: Iterable[int]) -> set[int]:
    """Return the subset of ``application_ids`` that have a saved/finalized
    allocation or a payment-roster entry (batch query, no per-row round trips)."""
    ids = list({int(app_id) for app_id in application_ids})
    if not ids:
        return set()

    ranking_stmt = (
        select(CollegeRankingItem.application_id)
        .join(CollegeRanking, CollegeRanking.id == CollegeRankingItem.ranking_id)
        .where(
            CollegeRankingItem.application_id.in_(ids),
            or_(
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocated_sub_type.isnot(None),
                CollegeRankingItem.status == ALLOCATED_RANKING_ITEM_STATUS,
                CollegeRanking.distribution_executed.is_(True),
            ),
        )
    )
    roster_stmt = select(PaymentRosterItem.application_id).where(PaymentRosterItem.application_id.in_(ids))

    ranking_hits = (await db.execute(ranking_stmt)).scalars().all()
    roster_hits = (await db.execute(roster_stmt)).scalars().all()
    return {*ranking_hits, *roster_hits}


def has_entered_distribution(application: Application, distributed_ids: set[int]) -> bool:
    """Pure check against the application row plus a pre-fetched id set from
    :func:`find_distributed_application_ids`."""
    if application.id in distributed_ids:
        return True
    if application.quota_allocation_status:
        return True
    if _enum_value(application.status) in DISTRIBUTION_OUTCOME_STATUSES:
        return True
    return _enum_value(application.review_stage) in DISTRIBUTION_REVIEW_STAGES


async def is_application_deletable(db: AsyncSession, application: Application) -> bool:
    """Single-application convenience wrapper used by the delete endpoint."""
    distributed_ids = await find_distributed_application_ids(db, [application.id])
    return not has_entered_distribution(application, distributed_ids)
