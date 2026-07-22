"""Tests for the review-reject gate on manual distribution.

Rule (用戶需求): 審核「不同意」的子類型，分發時絕不可被分發到 (rejection
gate, no exemptions — renewal or not, professor step or not). A sub-type the
professor merely has NOT approved (no review at all, or no verdict on that
sub-type) IS allocatable: the grid renders it as 未推薦 (same convention as
the 學院推薦 column) and the admin decides — one unreviewed application must
not strand the whole distribution (2026-07 staging fix; the former positive
professor-approval gate was removed).

The gate is enforced in ManualDistributionService._validate_allocations
(called first by allocate()), so a violation blocks the whole allocate() call
before any mutation. It additionally guards finalize() (rejects may arrive
after the allocation was saved) and restore_from_history() (a snapshot may
predate the reject).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, Semester
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService

YEAR = 114
SEM = Semester.first.value


async def _setup(
    db: AsyncSession,
    *,
    suffix: str,
    is_renewal: bool = False,
    requires_prof: bool = True,
    approved_sub_types: list[str] | None = None,
    rejected_sub_types: list[str] | None = None,
    is_finalized: bool = False,
    allocated_sub_type: str | None = None,
) -> tuple[ManualDistributionService, int, int]:
    """Build a student + scholarship config + application + ranking item, and
    optionally a professor review approving/rejecting the given sub-types.

    ``is_finalized`` / ``allocated_sub_type`` prepare a finalize()-ready state.
    Returns (service, ranking_item_id, scholarship_type_id).
    """
    student = User(
        nycu_id=f"gate_stu_{suffix}",
        name=f"Gate Stu {suffix}",
        email=f"gate_stu_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    professor = User(
        nycu_id=f"gate_prof_{suffix}",
        name=f"Gate Prof {suffix}",
        email=f"gate_prof_{suffix}@u.edu",
        user_type=UserType.employee,
        role=UserRole.professor,
    )
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    sch = ScholarshipType(code=f"gate_sch_{suffix}", name=f"Gate Sch {suffix}", status="active")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code=f"gate_cfg_{suffix}",
        config_name=f"Gate cfg {suffix}",
        academic_year=YEAR,
        semester=SEM,
        amount=30000,
        currency="TWD",
        is_active=True,
        requires_professor_recommendation=requires_prof,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    app = Application(
        app_id=f"APP-GATE-{suffix}",
        user_id=student.id,
        scholarship_type_id=sch.id,
        scholarship_configuration_id=cfg.id,
        sub_type_selection_mode="multiple",
        is_renewal=is_renewal,
        academic_year=YEAR,
        semester=Semester.first.value,
        review_stage=ReviewStage.college_ranked.value,
        status=ApplicationStatus.submitted.value,
        scholarship_subtype_list=["nstc", "moe_1w"],
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    if approved_sub_types or rejected_sub_types:
        if not approved_sub_types:
            overall = "reject"
        elif rejected_sub_types:
            overall = "partial_approve"
        else:
            overall = "approve"
        review = ApplicationReview(
            application_id=app.id,
            reviewer_id=professor.id,
            recommendation=overall,
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)
        for st in approved_sub_types or []:
            db.add(ApplicationReviewItem(review_id=review.id, sub_type_code=st, recommendation="approve"))
        for st in rejected_sub_types or []:
            db.add(
                ApplicationReviewItem(review_id=review.id, sub_type_code=st, recommendation="reject", comments="不同意")
            )
        await db.commit()

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="default",
        academic_year=YEAR,
        semester=SEM,
        total_applications=1,
        total_quota=5,
        is_finalized=is_finalized,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    item = CollegeRankingItem(ranking_id=ranking.id, application_id=app.id, rank_position=1)
    if allocated_sub_type:
        item.is_allocated = True
        item.allocated_sub_type = allocated_sub_type
        item.allocation_config_id = cfg.id
        item.status = "allocated"
    db.add(item)
    await db.commit()
    await db.refresh(item)

    return ManualDistributionService(db), item.id, sch.id


@pytest.mark.asyncio
async def test_allocate_allowed_when_professor_approved_that_subtype(db: AsyncSession):
    service, item_id, sch_id = await _setup(db, suffix="ok", approved_sub_types=["nstc"])
    # Allocating to the approved sub-type must pass validation (no raise).
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_allocate_allowed_for_subtype_professor_did_not_review(db: AsyncSession):
    service, item_id, sch_id = await _setup(db, suffix="wrongsub", approved_sub_types=["nstc"])
    # Professor approved nstc only; moe_1w has no verdict → shown as 未推薦
    # in the grid but still allocatable (no positive-approval gate).
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "moe_1w"}])


@pytest.mark.asyncio
async def test_allocate_allowed_when_no_professor_review(db: AsyncSession):
    # No professor review at all — must NOT block the distribution.
    service, item_id, sch_id = await _setup(db, suffix="noreview", approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_allocate_allows_renewal_without_professor_review(db: AsyncSession):
    # Renewal app with no professor approval — allocatable.
    service, item_id, sch_id = await _setup(db, suffix="renewal", is_renewal=True, approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_allocate_allows_scholarship_without_professor_step(db: AsyncSession):
    # Scholarship that doesn't require professor recommendation — allocatable.
    service, item_id, sch_id = await _setup(db, suffix="noprof", requires_prof=False, approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_unallocate_is_never_blocked(db: AsyncSession):
    # sub_type_code=None means unallocate — must never be gated.
    service, item_id, sch_id = await _setup(db, suffix="unalloc", approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": None}])


# --- Rejection gate (審核不同意 → 絕不可分發, no exemptions) ---


@pytest.mark.asyncio
async def test_allocate_blocked_when_professor_rejected_subtype(db: AsyncSession):
    service, item_id, sch_id = await _setup(
        db, suffix="rej", approved_sub_types=["nstc"], rejected_sub_types=["moe_1w"]
    )
    with pytest.raises(ValueError, match="不同意"):
        await service._validate_allocations(
            sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "moe_1w"}]
        )


@pytest.mark.asyncio
async def test_allocate_blocked_when_rejected_even_without_professor_step(db: AsyncSession):
    # Even without a professor-recommendation step, an explicit reject blocks.
    service, item_id, sch_id = await _setup(db, suffix="rejnoprof", requires_prof=False, rejected_sub_types=["nstc"])
    with pytest.raises(ValueError, match="不同意"):
        await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_allocate_blocked_when_rejected_for_renewal(db: AsyncSession):
    # An explicit reject blocks a renewal allocation too.
    service, item_id, sch_id = await _setup(db, suffix="rejrenew", is_renewal=True, rejected_sub_types=["nstc"])
    with pytest.raises(ValueError, match="不同意"):
        await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_finalize_blocked_when_allocated_subtype_rejected(db: AsyncSession):
    # A reject that arrives AFTER the allocation was saved must block finalize.
    service, _item_id, sch_id = await _setup(
        db,
        suffix="rejfin",
        rejected_sub_types=["nstc"],
        is_finalized=True,
        allocated_sub_type="nstc",
    )
    with pytest.raises(ValueError, match="不同意"):
        await service.finalize(sch_id, YEAR, SEM)


@pytest.mark.asyncio
async def test_allocate_blocked_when_rejected_with_mixed_case(db: AsyncSession):
    # Sub-type codes are free-form strings — the gate must normalize BOTH the
    # stored review code and the allocation input before comparing.
    service, item_id, sch_id = await _setup(db, suffix="rejcase", requires_prof=False, rejected_sub_types=["NSTC"])
    with pytest.raises(ValueError, match="不同意"):
        await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc "}])


@pytest.mark.asyncio
async def test_restore_allocation_blocked_when_subtype_rejected(db: AsyncSession):
    # A reviewer reject recorded while the application was suspended must not
    # be overridden by the admin restore (復發) path.
    service, item_id, sch_id = await _setup(
        db, suffix="rejreaffirm", rejected_sub_types=["nstc"], allocated_sub_type="nstc"
    )
    item = await db.get(CollegeRankingItem, item_id)
    app = await db.get(Application, item.application_id)
    app.quota_allocation_status = "suspended"
    await db.commit()
    with pytest.raises(ValueError, match="不同意"):
        await service.restore_allocation(app.id, admin_user_id=1)


@pytest.mark.asyncio
async def test_restore_skips_rejected_subtype(db: AsyncSession):
    # A history snapshot predating the reject must not re-allocate it.
    service, item_id, sch_id = await _setup(db, suffix="rejrestore", rejected_sub_types=["nstc"])
    result = await service.restore_from_history(
        sch_id,
        YEAR,
        SEM,
        {str(item_id): {"sub_type": "nstc", "allocation_config_id": None, "status": "allocated"}},
    )
    assert result["restored_count"] == 0
    assert result["skipped_rejected"] == 1
