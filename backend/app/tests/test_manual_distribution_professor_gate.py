"""Tests for the professor-approval gate on manual distribution.

Rule (用戶需求): 分發時一定要教授有同意「那個」子類型才能被分發到。
Enforced in ManualDistributionService._validate_allocations (called first by
allocate()), so a violation blocks the whole allocate() call before any mutation.

Exemptions:
  - renewal applications (續領豁免)
  - scholarships that don't require a professor recommendation step
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
) -> tuple[ManualDistributionService, int, int]:
    """Build a student + scholarship config + application + ranking item, and
    optionally a professor review approving the given sub-types.

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

    if approved_sub_types:
        review = ApplicationReview(
            application_id=app.id,
            reviewer_id=professor.id,
            recommendation="approve",
            reviewed_at=datetime.now(timezone.utc),
        )
        db.add(review)
        await db.commit()
        await db.refresh(review)
        for st in approved_sub_types:
            db.add(ApplicationReviewItem(review_id=review.id, sub_type_code=st, recommendation="approve"))
        await db.commit()

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="default",
        academic_year=YEAR,
        semester=SEM,
        total_applications=1,
        total_quota=5,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    item = CollegeRankingItem(ranking_id=ranking.id, application_id=app.id, rank_position=1)
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
async def test_allocate_blocked_for_subtype_professor_did_not_approve(db: AsyncSession):
    service, item_id, sch_id = await _setup(db, suffix="wrongsub", approved_sub_types=["nstc"])
    # Professor approved nstc only; allocating to moe_1w must be blocked.
    with pytest.raises(ValueError, match="教授"):
        await service._validate_allocations(
            sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "moe_1w"}]
        )


@pytest.mark.asyncio
async def test_allocate_blocked_when_no_professor_review(db: AsyncSession):
    service, item_id, sch_id = await _setup(db, suffix="noreview", approved_sub_types=None)
    with pytest.raises(ValueError, match="教授"):
        await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_allocate_exempts_renewal_application(db: AsyncSession):
    # Renewal app with no professor approval — must still be allocatable.
    service, item_id, sch_id = await _setup(db, suffix="renewal", is_renewal=True, approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_allocate_exempts_scholarship_without_professor_step(db: AsyncSession):
    # Scholarship that doesn't require professor recommendation — no gate.
    service, item_id, sch_id = await _setup(db, suffix="noprof", requires_prof=False, approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": "nstc"}])


@pytest.mark.asyncio
async def test_unallocate_is_never_blocked(db: AsyncSession):
    # sub_type_code=None means unallocate — must never be gated.
    service, item_id, sch_id = await _setup(db, suffix="unalloc", approved_sub_types=None)
    await service._validate_allocations(sch_id, YEAR, SEM, [{"ranking_item_id": item_id, "sub_type_code": None}])
