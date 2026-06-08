"""finalize() §10 lock gate — rejects oversubscription; snapshot re-keyed to allocation_config_id."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService


async def _student(db, suffix):
    u = User(
        nycu_id=f"fl_{suffix}",
        name=f"S{suffix}",
        email=f"fl_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _alloc_item(db, *, sch_id, app_id, ranking_id, cfg_id):
    item = CollegeRankingItem(
        ranking_id=ranking_id,
        application_id=app_id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg_id,
        status="allocated",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@pytest_asyncio.fixture
async def base(db: AsyncSession):
    sch = ScholarshipType(code="fl_phd", name="FL PhD", description="x")
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
        quotas={"nstc": {"A": 1}},
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
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
    return {"sch": sch, "cfg": cfg, "ranking": ranking}


async def _new_app(db, *, user, sch_id):
    a = Application(
        app_id=f"APP-115-0-{user.nycu_id}",
        user_id=user.id,
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
    return a


@pytest.mark.asyncio
async def test_finalize_rejects_oversubscription(db: AsyncSession, base):
    sch, cfg, ranking = base["sch"], base["cfg"], base["ranking"]
    u1 = await _student(db, "1")
    u2 = await _student(db, "2")
    a1 = await _new_app(db, user=u1, sch_id=sch.id)
    a2 = await _new_app(db, user=u2, sch_id=sch.id)
    await _alloc_item(db, sch_id=sch.id, app_id=a1.id, ranking_id=ranking.id, cfg_id=cfg.id)
    await _alloc_item(db, sch_id=sch.id, app_id=a2.id, ranking_id=ranking.id, cfg_id=cfg.id)

    svc = ManualDistributionService(db)
    with pytest.raises(ValueError, match="超額"):
        await svc.finalize(sch.id, 115, "yearly")


@pytest.mark.asyncio
async def test_finalize_at_cap_records_config_id_snapshot(db: AsyncSession, base):
    sch, cfg, ranking = base["sch"], base["cfg"], base["ranking"]
    u1 = await _student(db, "ok")
    a1 = await _new_app(db, user=u1, sch_id=sch.id)
    await _alloc_item(db, sch_id=sch.id, app_id=a1.id, ranking_id=ranking.id, cfg_id=cfg.id)

    svc = ManualDistributionService(db)
    result = await svc.finalize(sch.id, 115, "yearly")
    assert result["approved_count"] == 1

    hist = (
        (
            await db.execute(
                select(ManualDistributionHistory).where(ManualDistributionHistory.operation_type == "finalize")
            )
        )
        .scalars()
        .first()
    )
    snap = list(hist.allocations_snapshot.values())[0]
    assert snap["allocation_config_id"] == cfg.id
    assert "allocation_year" not in snap
