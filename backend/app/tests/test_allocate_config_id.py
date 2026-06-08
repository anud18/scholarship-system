"""allocate() writes item.allocation_config_id and validates against _allowed_config_ids."""

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


@pytest_asyncio.fixture
async def setup(db: AsyncSession):
    sch = ScholarshipType(code="al_phd", name="AL PhD", description="x")
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
        quotas={"nstc": {"A": 2}},
    )
    other = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=113,
        semester=None,
        config_name="phd113",
        config_code="phd_113",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        quotas={"nstc": {"A": 2}},
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
        quotas={"nstc": {"A": 3}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    db.add_all([prior, other, own])
    await db.commit()
    await db.refresh(own)
    await db.refresh(prior)
    await db.refresh(other)

    user = User(
        nycu_id="al_s",
        name="S",
        email="al_s@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    app = Application(
        app_id="APP-115-0-s",
        user_id=user.id,
        scholarship_type_id=sch.id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=115,
        semester=None,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_ranked,
        is_renewal=True,
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
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
    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app.id,
        rank_position=1,
        is_allocated=False,
        status="ranked",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"sch": sch, "own": own, "prior": prior, "other": other, "item": item}


@pytest.mark.asyncio
async def test_allocate_writes_linked_config_id(db: AsyncSession, setup):
    svc = ManualDistributionService(db)
    await svc.allocate(
        setup["sch"].id,
        115,
        "yearly",
        [{"ranking_item_id": setup["item"].id, "sub_type_code": "nstc", "allocation_config_id": setup["prior"].id}],
    )
    refreshed = (
        await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.id == setup["item"].id))
    ).scalar_one()
    assert refreshed.is_allocated is True
    assert refreshed.allocated_sub_type == "nstc"
    assert refreshed.allocation_config_id == setup["prior"].id


@pytest.mark.asyncio
async def test_allocate_rejects_disallowed_config(db: AsyncSession, setup):
    svc = ManualDistributionService(db)
    with pytest.raises(ValueError, match="phd_113"):
        await svc.allocate(
            setup["sch"].id,
            115,
            "yearly",
            [{"ranking_item_id": setup["item"].id, "sub_type_code": "nstc", "allocation_config_id": setup["other"].id}],
        )


@pytest_asyncio.fixture
async def oversub_setup(db: AsyncSession):
    """A round whose own config has a ZERO nstc pool, so allocating one item to
    it must be rejected by the §10 gate — which only sees the over-cap once it
    flushes the still-pending allocation write itself (autoflush is off)."""
    sch = ScholarshipType(code="al_phd_os", name="AL PhD OS", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    own = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester=None,
        config_name="os115",
        config_code="os_115",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        quotas={"nstc": {"A": 0}},
    )
    db.add(own)
    await db.commit()
    await db.refresh(own)

    user = User(
        nycu_id="os_s",
        name="S",
        email="os_s@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    app = Application(
        app_id="APP-115-0-os",
        user_id=user.id,
        scholarship_type_id=sch.id,
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
    db.add(app)
    await db.commit()
    await db.refresh(app)
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
    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app.id,
        rank_position=1,
        is_allocated=False,
        status="ranked",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"sch": sch, "own": own, "item": item}


@pytest.mark.asyncio
async def test_allocate_gate_rejects_oversubscription(db: AsyncSession, oversub_setup):
    # Disable autoflush so the over-cap allocation write stays PENDING through the
    # recount — only the gate's own first-line `await self.db.flush()` can make it
    # visible. This is the concurrency contract: the gate must not rely on autoflush.
    db.autoflush = False
    svc = ManualDistributionService(db)
    with pytest.raises(ValueError, match="配額超額"):
        await svc.allocate(
            oversub_setup["sch"].id,
            115,
            "yearly",
            [{"ranking_item_id": oversub_setup["item"].id, "sub_type_code": "nstc"}],
        )
