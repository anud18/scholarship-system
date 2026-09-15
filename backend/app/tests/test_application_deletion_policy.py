"""
Tests for app.services.application_deletion_policy — the admin hard-delete
gate: an application is deletable until it enters the 配額分發 stage.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterCycle, RosterTriggerType
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.services.application_deletion_policy import (
    find_distributed_application_ids,
    has_entered_distribution,
    is_application_deletable,
)


async def _seed_application(
    db: AsyncSession,
    user: User,
    scholarship: ScholarshipType,
    *,
    suffix: str,
    status: str = ApplicationStatus.submitted.value,
    review_stage: str = ReviewStage.student_submitted.value,
    quota_allocation_status: str | None = None,
    academic_year: int = 114,
) -> Application:
    application = Application(
        app_id=f"POL-{suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship.id,
        status=status,
        review_stage=review_stage,
        quota_allocation_status=quota_allocation_status,
        academic_year=academic_year,
        semester="first",
        sub_type_selection_mode="single",
        student_data={"std_cname": "測試", "std_stdcode": f"3104{suffix}"},
        created_at=datetime.now(timezone.utc),
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def _seed_ranking(
    db: AsyncSession, scholarship: ScholarshipType, *, distribution_executed: bool
) -> CollegeRanking:
    ranking = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        college_code="C",
        is_finalized=True,
        distribution_executed=distribution_executed,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return ranking


async def _seed_ranking_item(db: AsyncSession, ranking: CollegeRanking, application: Application, **overrides) -> None:
    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application.id,
        rank_position=1,
        **overrides,
    )
    db.add(item)
    await db.commit()


# ---------------------------------------------------------------------------
# Pure row-level checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.draft.value,
        ApplicationStatus.submitted.value,
        ApplicationStatus.under_review.value,
        ApplicationStatus.pending_documents.value,
        ApplicationStatus.rejected.value,
        ApplicationStatus.returned.value,
    ],
)
async def test_pre_distribution_statuses_are_deletable(db, test_user, test_scholarship, status):
    app = await _seed_application(db, test_user, test_scholarship, suffix=status[:6], status=status)
    assert has_entered_distribution(app, set()) is False
    assert await is_application_deletable(db, app) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "review_stage",
    [
        ReviewStage.professor_review.value,
        ReviewStage.professor_reviewed.value,
        ReviewStage.college_review.value,
        ReviewStage.college_ranked.value,
        ReviewStage.admin_reviewed.value,
    ],
)
async def test_review_stages_before_distribution_are_deletable(db, test_user, test_scholarship, review_stage):
    app = await _seed_application(db, test_user, test_scholarship, suffix=review_stage[:8], review_stage=review_stage)
    assert await is_application_deletable(db, app) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "review_stage",
    [
        ReviewStage.quota_distribution.value,
        ReviewStage.quota_distributed.value,
        ReviewStage.roster_preparation.value,
        ReviewStage.roster_submitted.value,
        ReviewStage.completed.value,
    ],
)
async def test_distribution_review_stages_block_delete(db, test_user, test_scholarship, review_stage):
    app = await _seed_application(db, test_user, test_scholarship, suffix=review_stage[:8], review_stage=review_stage)
    assert await is_application_deletable(db, app) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ApplicationStatus.approved.value, ApplicationStatus.partial_approved.value])
async def test_distribution_outcome_statuses_block_delete(db, test_user, test_scholarship, status):
    app = await _seed_application(db, test_user, test_scholarship, suffix=status[:6], status=status)
    assert await is_application_deletable(db, app) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("quota_status", ["allocated", "rejected", "waitlisted"])
async def test_quota_allocation_status_blocks_delete(db, test_user, test_scholarship, quota_status):
    """finalize() flips non-allocated rows to quota_allocation_status='rejected'
    while leaving status untouched — that row is still post-distribution."""
    app = await _seed_application(
        db, test_user, test_scholarship, suffix=quota_status[:6], quota_allocation_status=quota_status
    )
    assert await is_application_deletable(db, app) is False


# ---------------------------------------------------------------------------
# Ranking / roster lookups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_ranked_item_does_not_block(db, test_user, test_scholarship):
    """A college ranking (even finalized) without a saved allocation is pre-distribution."""
    app = await _seed_application(db, test_user, test_scholarship, suffix="ranked")
    ranking = await _seed_ranking(db, test_scholarship, distribution_executed=False)
    await _seed_ranking_item(db, ranking, app)

    assert await find_distributed_application_ids(db, [app.id]) == set()
    assert await is_application_deletable(db, app) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"is_allocated": True},
        {"allocated_sub_type": "nstc"},
        {"status": "allocated"},
    ],
)
async def test_saved_allocation_blocks_delete(db, test_user, test_scholarship, overrides):
    app = await _seed_application(db, test_user, test_scholarship, suffix="alloc")
    ranking = await _seed_ranking(db, test_scholarship, distribution_executed=False)
    await _seed_ranking_item(db, ranking, app, **overrides)

    assert await find_distributed_application_ids(db, [app.id]) == {app.id}
    assert await is_application_deletable(db, app) is False


@pytest.mark.asyncio
async def test_executed_ranking_blocks_delete(db, test_user, test_scholarship):
    app = await _seed_application(db, test_user, test_scholarship, suffix="exec")
    ranking = await _seed_ranking(db, test_scholarship, distribution_executed=True)
    await _seed_ranking_item(db, ranking, app)

    assert await is_application_deletable(db, app) is False


@pytest.mark.asyncio
async def test_roster_item_blocks_delete(db, test_user, test_admin, test_scholarship):
    app = await _seed_application(db, test_user, test_scholarship, suffix="roster")
    roster = PaymentRoster(
        roster_code="ROSTER-POLICY-1",
        scholarship_configuration_id=1,
        period_label="114-1",
        academic_year=114,
        roster_cycle=RosterCycle.YEARLY,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=test_admin.id,
    )
    db.add(roster)
    await db.commit()
    await db.refresh(roster)
    db.add(
        PaymentRosterItem(
            roster_id=roster.id,
            application_id=app.id,
            student_id_number="A123456789",
            student_name="測試",
            scholarship_name="Test",
            scholarship_amount=1000,
        )
    )
    await db.commit()

    assert await find_distributed_application_ids(db, [app.id]) == {app.id}
    assert await is_application_deletable(db, app) is False


@pytest.mark.asyncio
async def test_find_distributed_ids_is_batch_and_empty_safe(db, test_user, test_scholarship):
    assert await find_distributed_application_ids(db, []) == set()

    # One student may hold only one non-renewal application per (scholarship, year, semester).
    free = await _seed_application(db, test_user, test_scholarship, suffix="free", academic_year=113)
    taken = await _seed_application(db, test_user, test_scholarship, suffix="taken", academic_year=114)
    ranking = await _seed_ranking(db, test_scholarship, distribution_executed=False)
    await _seed_ranking_item(db, ranking, taken, allocated_sub_type="moe_1w")

    result = await find_distributed_application_ids(db, [free.id, taken.id, taken.id])
    assert result == {taken.id}
    assert has_entered_distribution(free, result) is False
    assert has_entered_distribution(taken, result) is True
