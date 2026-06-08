"""get_quota_status rebuilt onto remaining()/distributable_pool() (spec §6.3, §17.1)."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService


@pytest_asyncio.fixture
async def setup(db: AsyncSession):
    sch = ScholarshipType(code="qs_phd", name="QS PhD", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    for code, name, order in [("nstc", "國科會", 1), ("moe_1w", "教育部", 2)]:
        db.add(
            ScholarshipSubTypeConfig(
                scholarship_type_id=sch.id,
                sub_type_code=code,
                name=name,
                display_order=order,
                is_active=True,
            )
        )
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
        quotas={"nstc": {"A": 3}, "moe_1w": {"A": 4}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    db.add_all([prior, own])
    await db.commit()
    await db.refresh(own)
    await db.refresh(prior)
    return {"sch": sch, "own": own, "prior": prior}


@pytest.mark.asyncio
async def test_quota_status_keys_by_config_and_subtracts_renewals(db: AsyncSession, setup):
    sch, own = setup["sch"], setup["own"]
    # An approved renewal consuming own config — must lower the displayed remaining.
    user = User(
        nycu_id="qs_r",
        name="R",
        email="qs_r@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    ren = Application(
        app_id="APP-115-0-r",
        user_id=user.id,
        scholarship_type_id=sch.id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=115,
        semester=None,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=True,
        allocation_config_id=own.id,
        agree_terms=True,
    )
    db.add(ren)
    await db.commit()

    svc = ManualDistributionService(db)
    status = await svc.get_quota_status(sch.id, 115, "yearly")

    assert status["nstc"]["display_name"] == "國科會"
    by_cfg = {c["config_id"]: c for c in status["nstc"]["by_config"]}
    # own nstc: total 3 − 1 renewal = 2 remaining
    assert by_cfg[own.id] == {
        "config_id": own.id,
        "config_code": "phd_115",
        "academic_year": 115,
        "is_own": True,
        "total": 3,
        "remaining": 2,
    }
    # linked phd_114 nstc: total 2, remaining 2
    assert by_cfg[setup["prior"].id]["total"] == 2
    assert by_cfg[setup["prior"].id]["remaining"] == 2
    assert by_cfg[setup["prior"].id]["is_own"] is False
    # moe_1w: own only, no linked column
    moe_cfgs = {c["config_id"] for c in status["moe_1w"]["by_config"]}
    assert moe_cfgs == {own.id}
