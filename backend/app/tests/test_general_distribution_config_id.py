"""execute_general_distribution rebuilt onto per-config pool + config-keyed release (spec §6.3, §12)."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService


async def _student(db, suffix):
    u = User(
        nycu_id=f"gd_{suffix}",
        name=f"S{suffix}",
        email=f"gd_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def setup(db: AsyncSession):
    sch = ScholarshipType(code="gd_phd", name="GD PhD", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    prior = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=114,
        semester=None,
        config_name="phd114",
        config_code="phd_114",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        quotas={"nstc": {"A": 1}},
    )
    own = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester=None,
        config_name="phd115",
        config_code="phd_115",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        quotas={"nstc": {"A": 2}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    db.add_all([prior, own])
    await db.commit()
    await db.refresh(own)
    await db.refresh(prior)
    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="nstc",
        academic_year=115,
        semester=None,
        is_finalized=True,
        ranking_status="finalized",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return {"sch": sch, "own": own, "prior": prior, "ranking": ranking}


async def _new_candidate(db, *, sch_id, ranking_id, rank, suffix):
    u = await _student(db, suffix)
    a = Application(
        app_id=f"APP-115-0-{suffix}",
        user_id=u.id,
        scholarship_type_id=sch_id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=115,
        semester=None,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_ranked,
        is_renewal=False,
        agree_terms=True,
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    item = CollegeRankingItem(
        ranking_id=ranking_id,
        application_id=a.id,
        rank_position=rank,
        is_allocated=False,
        status="ranked",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return a, item


@pytest.mark.asyncio
async def test_general_distribution_fills_own_then_linked(db: AsyncSession, setup):
    sch, own, prior, ranking = setup["sch"], setup["own"], setup["prior"], setup["ranking"]
    a1, i1 = await _new_candidate(db, sch_id=sch.id, ranking_id=ranking.id, rank=1, suffix="c1")
    a2, i2 = await _new_candidate(db, sch_id=sch.id, ranking_id=ranking.id, rank=2, suffix="c2")
    a3, i3 = await _new_candidate(db, sch_id=sch.id, ranking_id=ranking.id, rank=3, suffix="c3")

    svc = ManualDistributionService(db)
    await svc.execute_general_distribution(sch.id, 115)

    items = {
        it.application_id: it
        for it in (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking.id)))
        .scalars()
        .all()
    }
    # 2 own slots + 1 linked slot = 3 total; all three candidates get allocated.
    assigned = [items[a.id].allocation_config_id for a in (a1, a2, a3)]
    assert assigned.count(own.id) == 2
    assert assigned.count(prior.id) == 1
    assert all(items[a.id].is_allocated for a in (a1, a2, a3))
    assert all(items[a.id].allocation_config_id is not None for a in (a1, a2, a3))
