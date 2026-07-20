"""
Regression test for ManualDistributionService.finalize — issue #45.

Pre-fix:
  Non-allocated CollegeRankingItem rows triggered
    app.status = ApplicationStatus.rejected
  even though the application had passed review and only missed the
  quota cut. Students saw "已拒絕" in their portal — wrong.

Post-fix (commit 193fecf):
  Non-allocated branch sets only:
    item.status = "rejected"
    app.quota_allocation_status = "rejected"
    app.review_stage = ReviewStage.quota_distributed
  app.status is left untouched (typically remains "approved" or
  whatever it was before distribution).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, Semester
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService


def _make_user(suffix: str) -> User:
    return User(
        nycu_id=f"finalize_test_{suffix}",
        name=f"Finalize Test {suffix}",
        email=f"finalize_test_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )


@pytest.mark.asyncio
async def test_finalize_keeps_status_for_non_allocated_apps(db: AsyncSession):
    """The fix in #45: non-allocated app.status must NOT change."""
    # Two students that will end up in the same ranking
    user_a = _make_user("alloc")
    user_b = _make_user("noalloc")
    db.add_all([user_a, user_b])
    await db.commit()
    await db.refresh(user_a)
    await db.refresh(user_b)

    # ScholarshipType the ranking points at
    sch = ScholarshipType(
        code="finalize_test_sch",
        name="Finalize Test Scholarship",
        description="Fixture for #45 regression test",
    )
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    # Two applications, both pre-distribution at status=approved
    # (this is the realistic state — they passed review, awaiting quota cut)
    common_kwargs = dict(
        scholarship_type_id=sch.id,
        sub_type_selection_mode="single",
        is_renewal=False,
        academic_year=114,
        semester=Semester.first.value,
        review_stage=ReviewStage.college_ranked.value,
        status=ApplicationStatus.approved.value,
        scholarship_subtype_list=["general"],
        agree_terms=True,
    )
    app_a = Application(app_id="APP-114-1-FA001", user_id=user_a.id, **common_kwargs)
    app_b = Application(app_id="APP-114-1-FA002", user_id=user_b.id, **common_kwargs)
    db.add_all([app_a, app_b])
    await db.commit()
    await db.refresh(app_a)
    await db.refresh(app_b)

    # A finalized ranking with two items: one allocated, one not
    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="general",
        academic_year=114,
        semester=Semester.first.value,
        total_applications=2,
        total_quota=1,
        allocated_count=1,
        is_finalized=True,
        ranking_status="finalized",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    item_alloc = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_a.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="general",
    )
    item_noalloc = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_b.id,
        rank_position=2,
        is_allocated=False,
    )
    db.add_all([item_alloc, item_noalloc])
    await db.commit()

    # Act
    service = ManualDistributionService(db)
    await service.finalize(sch.id, 114, Semester.first.value)

    # Assert — allocated path
    await db.refresh(app_a)
    assert (
        app_a.status == ApplicationStatus.approved.value or app_a.status == ApplicationStatus.approved
    ), "allocated app status should be approved"
    assert app_a.quota_allocation_status == "allocated"
    assert app_a.sub_scholarship_type == "general"
    assert app_a.approved_at is not None

    # Assert — NON-allocated path (the regression target)
    await db.refresh(app_b)
    # Status must NOT have flipped to rejected
    rejected_value = ApplicationStatus.rejected.value
    assert app_b.status != rejected_value, (
        f"#45 regression: non-allocated app.status was '{app_b.status}', "
        "should remain 'approved' (its prior status) — old behavior stomped it to 'rejected'"
    )
    assert app_b.quota_allocation_status == "rejected"
    # review_stage advances regardless (workflow position, not user-facing status)
    review_stage_value = getattr(app_b.review_stage, "value", app_b.review_stage)
    assert review_stage_value == ReviewStage.quota_distributed.value

    # Ranking flagged as distributed
    await db.refresh(ranking)
    assert ranking.distribution_executed is True
    assert ranking.distribution_date is not None


@pytest.mark.asyncio
async def test_finalize_skips_unallocated_renewals(db: AsyncSession):
    """The fix in #1171: a funded renewal sitting unallocated in a ranking
    must keep quota_allocation_status='allocated' (owned by renewal import),
    not be downgraded to 'rejected' by matrix finalize."""
    user_renewal = _make_user("renewal")
    user_winner = _make_user("winner")
    db.add_all([user_renewal, user_winner])
    await db.commit()
    await db.refresh(user_renewal)
    await db.refresh(user_winner)

    sch = ScholarshipType(
        code="finalize_renewal_sch",
        name="Finalize Renewal Test Scholarship",
        description="Fixture for #1171 regression test",
    )
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    common_kwargs = dict(
        scholarship_type_id=sch.id,
        sub_type_selection_mode="single",
        academic_year=114,
        semester=Semester.first.value,
        review_stage=ReviewStage.college_ranked.value,
        status=ApplicationStatus.approved.value,
        scholarship_subtype_list=["general"],
        agree_terms=True,
    )
    # Renewal import leaves the renewal approved + allocated (#1132)
    app_renewal = Application(
        app_id="APP-114-1-FA003R",
        user_id=user_renewal.id,
        is_renewal=True,
        quota_allocation_status="allocated",
        **common_kwargs,
    )
    app_winner = Application(
        app_id="APP-114-1-FA004",
        user_id=user_winner.id,
        is_renewal=False,
        **common_kwargs,
    )
    db.add_all([app_renewal, app_winner])
    await db.commit()
    await db.refresh(app_renewal)
    await db.refresh(app_winner)

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="general",
        academic_year=114,
        semester=Semester.first.value,
        total_applications=2,
        total_quota=1,
        allocated_count=1,
        is_finalized=True,
        ranking_status="finalized",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    # Renewals auto-rank first (#71) but stay unallocated in the matrix
    item_renewal = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_renewal.id,
        rank_position=1,
        is_allocated=False,
    )
    item_winner = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_winner.id,
        rank_position=2,
        is_allocated=True,
        allocated_sub_type="general",
    )
    db.add_all([item_renewal, item_winner])
    await db.commit()

    service = ManualDistributionService(db)
    result = await service.finalize(sch.id, 114, Semester.first.value)

    # The renewal must be untouched: still approved + allocated
    await db.refresh(app_renewal)
    status_value = getattr(app_renewal.status, "value", app_renewal.status)
    assert status_value == ApplicationStatus.approved.value
    assert app_renewal.quota_allocation_status == "allocated", (
        "#1171 regression: finalize downgraded a funded renewal's "
        f"quota_allocation_status to '{app_renewal.quota_allocation_status}'"
    )

    # Its ranking item must not be marked rejected either
    await db.refresh(item_renewal)
    assert item_renewal.status != "rejected"

    # And it must not inflate the rejected tally
    assert result["rejected_count"] == 0
    assert result["approved_count"] == 1
