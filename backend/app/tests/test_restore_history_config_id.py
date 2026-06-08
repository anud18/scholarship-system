"""restore_from_history reads allocation_config_id; _batch_load_previous_allocation_years returns config id."""

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
    sch = ScholarshipType(code="rh_phd", name="RH PhD", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    cfg = ScholarshipConfiguration(
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
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    user = User(
        nycu_id="rh_s",
        name="S",
        email="rh_s@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    app = Application(
        app_id="APP-115-0-rh",
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
    return {"sch": sch, "cfg": cfg, "item": item, "app": app}


@pytest.mark.asyncio
async def test_restore_writes_config_id(db: AsyncSession, setup):
    svc = ManualDistributionService(db)
    snapshot = {
        str(setup["item"].id): {
            "sub_type": "nstc",
            "allocation_config_id": setup["cfg"].id,
            "status": "allocated",
        }
    }
    result = await svc.restore_from_history(setup["sch"].id, 115, "yearly", snapshot)
    assert result["restored_count"] == 1
    refreshed = (
        await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.id == setup["item"].id))
    ).scalar_one()
    assert refreshed.is_allocated is True
    assert refreshed.allocation_config_id == setup["cfg"].id


@pytest.mark.asyncio
async def test_batch_load_previous_allocation_config(db: AsyncSession, setup):
    # Mark the existing item allocated to cfg as a "previous" slot.
    item = setup["item"]
    item.is_allocated = True
    item.allocated_sub_type = "nstc"
    item.allocation_config_id = setup["cfg"].id
    await db.commit()

    svc = ManualDistributionService(db)
    mapping = await svc._batch_load_previous_allocation_years([setup["app"].id])
    assert mapping == {setup["app"].id: setup["cfg"].id}
