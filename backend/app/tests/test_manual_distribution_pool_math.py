"""Pool-math unit tests for ManualDistributionService (spec §6.1-6.3).

Covers the live shared-pool helpers: pool_total (matrix vs non-matrix),
consumers_count (the is_renewal partition), remaining (global), and
distributable_pool / _allowed_config_ids / _pick_config (own + linked).

These run under asyncio_mode=auto with the async `db` fixture from conftest.
All models are built directly (no API), so the suite is a focused unit on the
algorithm, not the endpoints.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService

# --------------------------------------------------------------------------- #
# Builders (return persisted rows; caller commits)
# --------------------------------------------------------------------------- #


async def _make_type(db: AsyncSession, *, code: str) -> ScholarshipType:
    st = ScholarshipType(code=code, name=f"Type {code}", description="t")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


async def _make_config(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    config_code: str,
    academic_year: int,
    quotas: dict,
    has_college_quota: bool = True,
    total_quota: int | None = None,
    shared_quota_sources: list | None = None,
) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=has_college_quota,
        total_quota=total_quota,
        quotas=quotas,
        shared_quota_sources=shared_quota_sources,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _make_user(db: AsyncSession, *, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"U {nycu_id}",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _make_application(
    db: AsyncSession,
    *,
    user_id: int,
    scholarship_type_id: int,
    academic_year: int,
    sub_scholarship_type: str,
    is_renewal: bool,
    status: ApplicationStatus,
    app_id: str,
    allocation_config_id: int | None = None,
) -> Application:
    app = Application(
        app_id=app_id,
        user_id=user_id,
        scholarship_type_id=scholarship_type_id,
        sub_type_selection_mode="single",
        sub_scholarship_type=sub_scholarship_type,
        academic_year=academic_year,
        semester=None,
        status=status,
        is_renewal=is_renewal,
        allocation_config_id=allocation_config_id,
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _make_ranking(
    db: AsyncSession, *, scholarship_type_id: int, sub_type_code: str, academic_year: int
) -> CollegeRanking:
    r = CollegeRanking(
        scholarship_type_id=scholarship_type_id,
        sub_type_code=sub_type_code,
        academic_year=academic_year,
        semester=None,
        ranking_name="R",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def _make_item(
    db: AsyncSession,
    *,
    ranking_id: int,
    application_id: int,
    rank: int,
    is_allocated: bool,
    allocated_sub_type: str | None,
    allocation_config_id: int | None,
) -> CollegeRankingItem:
    it = CollegeRankingItem(
        ranking_id=ranking_id,
        application_id=application_id,
        rank_position=rank,
        is_allocated=is_allocated,
        allocated_sub_type=allocated_sub_type,
        allocation_config_id=allocation_config_id,
        status="allocated" if is_allocated else "ranked",
    )
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return it


# --------------------------------------------------------------------------- #
# 2.1 pool_total
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pool_total_matrix_sums_colleges(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 15, "C": 12, "A": 8}},
        has_college_quota=True,
    )
    svc = ManualDistributionService(db)
    assert svc.pool_total(cfg, "nstc") == 35


@pytest.mark.asyncio
async def test_pool_total_non_matrix_scalar_then_total_quota(db: AsyncSession):
    st = await _make_type(db, code="simple")
    # scalar quotas[st] wins when present
    scalar_cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="simple_115",
        academic_year=115,
        quotas={"nstc": 20},
        has_college_quota=False,
        total_quota=99,
    )
    # falls back to total_quota when quotas has no scalar for st
    fallback_cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="simple_114",
        academic_year=114,
        quotas={},
        has_college_quota=False,
        total_quota=7,
    )
    svc = ManualDistributionService(db)
    assert svc.pool_total(scalar_cfg, "nstc") == 20
    assert svc.pool_total(fallback_cfg, "nstc") == 7


# --------------------------------------------------------------------------- #
# 2.2 consumers_count — is_renewal partition (spec §6.2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_consumers_general_winner_counted_once(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 10}},
    )
    user = await _make_user(db, nycu_id="s1")
    app = await _make_application(
        db,
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=False,
        status=ApplicationStatus.submitted,
        app_id="APP-115-0-00001",
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=app.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
    )
    svc = ManualDistributionService(db)
    assert await svc.consumers_count(cfg.id, "nstc") == 1


@pytest.mark.asyncio
async def test_consumers_renewal_counted_once_via_application_half(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 10}},
    )
    user = await _make_user(db, nycu_id="r1")
    renewal = await _make_application(
        db,
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-00002",
        allocation_config_id=cfg.id,
    )
    # College builds a ranking item for the renewal too, but is_allocated stays
    # False, so the CollegeRankingItem half must NOT pick it up.
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=renewal.id,
        rank=1,
        is_allocated=False,
        allocated_sub_type=None,
        allocation_config_id=None,
    )
    svc = ManualDistributionService(db)
    assert await svc.consumers_count(cfg.id, "nstc") == 1


@pytest.mark.asyncio
async def test_consumers_revoked_then_restored_renewal_not_double_counted(db: AsyncSession):
    """restore_allocation flips is_allocated=True on any item with an
    allocated_sub_type — including a renewal's item. The is_renewal==False
    guard on the ranking-item half is what keeps this from being counted
    twice (once as a winner, once as the approved-renewal application).
    """
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 10}},
    )
    user = await _make_user(db, nycu_id="r2")
    renewal = await _make_application(
        db,
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-00003",
        allocation_config_id=cfg.id,
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    # Restored renewal item: is_allocated=True with allocated_sub_type set.
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=renewal.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
    )
    svc = ManualDistributionService(db)
    # Counted ONCE (via the Application renewal half), not twice.
    assert await svc.consumers_count(cfg.id, "nstc") == 1


# --------------------------------------------------------------------------- #
# 2.3 remaining — global live (spec §6.2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_remaining_is_pool_total_minus_global_consumers(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5, "C": 5}},  # pool_total = 10
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    # 2 general winners
    for i in range(2):
        u = await _make_user(db, nycu_id=f"w{i}")
        a = await _make_application(
            db,
            user_id=u.id,
            scholarship_type_id=st.id,
            academic_year=115,
            sub_scholarship_type="nstc",
            is_renewal=False,
            status=ApplicationStatus.submitted,
            app_id=f"APP-115-0-1000{i}",
        )
        await _make_item(
            db,
            ranking_id=ranking.id,
            application_id=a.id,
            rank=i + 1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=cfg.id,
        )
    # 1 approved renewal
    ru = await _make_user(db, nycu_id="rw")
    await _make_application(
        db,
        user_id=ru.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-20000",
        allocation_config_id=cfg.id,
    )
    svc = ManualDistributionService(db)
    # 10 total - (2 winners + 1 renewal) = 7
    assert await svc.remaining(cfg, "nstc") == 7


# --------------------------------------------------------------------------- #
# 2.4 _allowed_config_ids — own ∪ linked-for-sub_type (spec §6.3, §7)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_allowed_config_ids_own_plus_linked_for_sub_type(db: AsyncSession):
    st = await _make_type(db, code="phd")
    prior = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 3}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}, "moe_1w": {"E": 4}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    # nstc is linked → own + prior
    assert await svc._allowed_config_ids(requesting, "nstc") == {requesting.id, prior.id}
    # moe_1w is NOT in the link's sub_types → own only
    assert await svc._allowed_config_ids(requesting, "moe_1w") == {requesting.id}


@pytest.mark.asyncio
async def test_allowed_config_ids_missing_target_config_ignored(db: AsyncSession):
    st = await _make_type(db, code="phd")
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        # phd_112 config does not exist → link silently dropped
        shared_quota_sources=[{"source_config_code": "phd_112", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    assert await svc._allowed_config_ids(requesting, "nstc") == {requesting.id}


# --------------------------------------------------------------------------- #
# 2.5 distributable_pool — own + linked, live remaining (spec §6.3, §7)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_distributable_pool_own_plus_linked(db: AsyncSession):
    st = await _make_type(db, code="phd")
    prior = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 3}},  # remaining 3
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},  # remaining 5
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    pool = await svc.distributable_pool(requesting, "nstc")
    # own first, then linked by descending academic_year
    assert pool == [
        {"config_id": requesting.id, "config_code": "phd_115", "academic_year": 115, "is_own": True, "remaining": 5},
        {"config_id": prior.id, "config_code": "phd_114", "academic_year": 114, "is_own": False, "remaining": 3},
    ]


@pytest.mark.asyncio
async def test_distributable_pool_revoking_source_winner_raises_borrower_remaining(db: AsyncSession):
    st = await _make_type(db, code="phd")
    prior = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 3}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    # One winner consuming the PRIOR config → prior remaining drops to 2.
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    u = await _make_user(db, nycu_id="bw")
    a = await _make_application(
        db,
        user_id=u.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=False,
        status=ApplicationStatus.submitted,
        app_id="APP-115-0-30000",
    )
    item = await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=a.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=prior.id,
    )
    svc = ManualDistributionService(db)
    before = {p["config_id"]: p["remaining"] for p in await svc.distributable_pool(requesting, "nstc")}
    assert before[prior.id] == 2  # 3 - 1 winner

    # Revoke the source winner → its slot frees → borrower's linked column rises.
    item.is_allocated = False
    item.allocated_sub_type = None
    item.allocation_config_id = None
    item.status = "ranked"
    await db.commit()

    after = {p["config_id"]: p["remaining"] for p in await svc.distributable_pool(requesting, "nstc")}
    assert after[prior.id] == 3  # restored live


@pytest.mark.asyncio
async def test_distributable_pool_cross_type_link(db: AsyncSession):
    phd = await _make_type(db, code="phd")
    direct = await _make_type(db, code="direct_phd")
    prior = await _make_config(
        db,
        scholarship_type_id=direct.id,
        config_code="direct_phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 2}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=phd.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        shared_quota_sources=[{"source_config_code": "direct_phd_114", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    pool = await svc.distributable_pool(requesting, "nstc")
    assert pool == [
        {"config_id": requesting.id, "config_code": "phd_115", "academic_year": 115, "is_own": True, "remaining": 5},
        {"config_id": prior.id, "config_code": "direct_phd_114", "academic_year": 114, "is_own": False, "remaining": 2},
    ]
