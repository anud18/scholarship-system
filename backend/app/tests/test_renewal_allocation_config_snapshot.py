"""Pin: create_renewal_from_previous snapshots Application.allocation_config_id
from the previous award's CollegeRankingItem.allocation_config_id; when the
prior slot is unresolved it falls back to the renewal's own
scholarship_configuration_id — an approved renewal is NEVER left NULL (spec §9),
which would inflate the §6.2 pool."""

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


@pytest_asyncio.fixture
async def renewal_setup(db):
    sch = ScholarshipType(code="ren_sch", name="Ren", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    consumed = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="REN-113",
        config_name="Ren 113",
        academic_year=113,
        semester=None,
        amount=50000,
    )
    prev_cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="REN-114",
        config_name="Ren 114",
        academic_year=114,
        semester=None,
        amount=50000,
    )
    db.add_all([consumed, prev_cfg])
    await db.commit()
    await db.refresh(consumed)
    await db.refresh(prev_cfg)

    user = User(
        nycu_id="ren_u",
        email="ren_u@u.edu",
        name="Ren U",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    def _prev(app_id, cfg):
        return Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=sch.id,
            scholarship_configuration_id=cfg.id,
            scholarship_subtype_list=["nstc"],
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            academic_year=114,
            semester=None,
            status=ApplicationStatus.approved,
            review_stage=ReviewStage.quota_distributed,
            agree_terms=True,
        )

    return {"sch": sch, "consumed": consumed, "prev_cfg": prev_cfg, "user": user, "_prev": _prev}


@pytest.mark.asyncio
async def test_renewal_snapshots_previous_slot_config(db, renewal_setup):
    prev = renewal_setup["_prev"]("APP-REN-PREV", renewal_setup["prev_cfg"])
    db.add(prev)
    await db.commit()
    await db.refresh(prev)

    ranking = CollegeRanking(
        scholarship_type_id=renewal_setup["sch"].id,
        sub_type_code="nstc",
        academic_year=114,
        semester=None,
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    db.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=prev.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=renewal_setup["consumed"].id,
            status="allocated",
        )
    )
    await db.commit()

    svc = ApplicationService(db)
    renewal = await svc.create_renewal_from_previous(
        previous=prev,
        current_user=renewal_setup["user"],
        target_academic_year=115,
        renewal_year=114,
    )
    await db.commit()
    await db.refresh(renewal)
    # snapshot copies the prior slot's consumed config
    assert renewal.allocation_config_id == renewal_setup["consumed"].id


@pytest.mark.asyncio
async def test_renewal_unresolved_slot_falls_back_to_own_config(db, renewal_setup):
    # previous app has NO allocated ranking item → unresolved
    prev = renewal_setup["_prev"]("APP-REN-PREV2", renewal_setup["prev_cfg"])
    db.add(prev)
    await db.commit()
    await db.refresh(prev)

    svc = ApplicationService(db)
    renewal = await svc.create_renewal_from_previous(
        previous=prev,
        current_user=renewal_setup["user"],
        target_academic_year=115,
        renewal_year=114,
    )
    await db.commit()
    await db.refresh(renewal)
    # never NULL: falls back to renewal's own scholarship_configuration_id
    assert renewal.allocation_config_id is not None
    assert renewal.allocation_config_id == prev.scholarship_configuration_id
