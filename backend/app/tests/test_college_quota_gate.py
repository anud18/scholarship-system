"""§10 per-college half of the quota gate.

Each college's cell of `quotas[sub_type]` is a HARD cap: allocate/finalize must
reject a round that over-fills one college even while the GLOBAL pool for that
(config, sub_type) still has slots free. Complements
test_allocate_config_id.py::test_allocate_gate_rejects_oversubscription, which
covers the global half.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.student import Academy
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService


async def _make_round(db: AsyncSession, *, code: str, quotas: dict, has_college_quota: bool, colleges: list[str]):
    """One finalized ranking with a ranked item per entry in `colleges`
    (the college code lands in the application's std_academyno snapshot)."""
    sch = ScholarshipType(code=code, name=code, description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    config = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester=None,
        config_name=f"{code}115",
        config_code=f"{code}_115",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=has_college_quota,
        quotas=quotas,
    )
    db.add(config)
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
    await db.refresh(config)
    await db.refresh(ranking)

    items = []
    for idx, college in enumerate(colleges):
        user = User(
            nycu_id=f"{code}_s{idx}",
            name=f"S{idx}",
            email=f"{code}_s{idx}@u.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        application = Application(
            app_id=f"APP-115-0-{code}{idx}",
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
            student_data={"std_academyno": college},
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)
        item = CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=application.id,
            rank_position=idx + 1,
            is_allocated=False,
            status="ranked",
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        items.append(item)

    return {"sch": sch, "config": config, "items": items}


def _allocations(items) -> list[dict]:
    return [{"ranking_item_id": item.id, "sub_type_code": "nstc"} for item in items]


@pytest_asyncio.fixture
async def matrix_round(db: AsyncSession):
    """A=1, B=2 → global pool 3, so two A students fit the pool but not the cell."""
    db.add(Academy(code="A", name="工學院"))
    await db.commit()
    return await _make_round(
        db,
        code="cq_matrix",
        quotas={"nstc": {"A": 1, "B": 2}},
        has_college_quota=True,
        colleges=["A", "A", "B"],
    )


@pytest.mark.asyncio
async def test_allocate_rejects_college_over_cap_while_pool_has_room(db: AsyncSession, matrix_round):
    svc = ManualDistributionService(db)
    a_items = matrix_round["items"][:2]

    with pytest.raises(ValueError, match="學院名額超額"):
        await svc.allocate(matrix_round["sch"].id, 115, "yearly", _allocations(a_items))

    # The global pool was never the problem: 2 of 3 slots used.
    assert await svc.remaining(matrix_round["config"], "nstc") == 1


@pytest.mark.asyncio
async def test_college_over_cap_message_names_the_college(db: AsyncSession, matrix_round):
    svc = ManualDistributionService(db)
    with pytest.raises(ValueError, match="工學院 已核配 2 人，超過該學院名額 1"):
        await svc.allocate(matrix_round["sch"].id, 115, "yearly", _allocations(matrix_round["items"][:2]))


@pytest.mark.asyncio
async def test_allocate_allows_one_per_college_cell(db: AsyncSession, matrix_round):
    svc = ManualDistributionService(db)
    one_a, _, one_b = matrix_round["items"]

    await svc.allocate(matrix_round["sch"].id, 115, "yearly", _allocations([one_a, one_b]))

    allocated = (
        (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.id.in_([one_a.id, one_b.id]))))
        .scalars()
        .all()
    )
    assert [item.is_allocated for item in allocated] == [True, True]


@pytest.mark.asyncio
async def test_allocate_rejects_college_absent_from_the_matrix(db: AsyncSession):
    """An unmapped 學院代碼 (or a snapshot with no std_academyno) has a cell of 0 —
    the same allocation auto-分發 refuses to make."""
    round_ = await _make_round(
        db,
        code="cq_unmapped",
        quotas={"nstc": {"A": 5}},
        has_college_quota=True,
        colleges=["ZZ"],
    )
    svc = ManualDistributionService(db)

    with pytest.raises(ValueError, match="學院名額超額"):
        await svc.allocate(round_["sch"].id, 115, "yearly", _allocations(round_["items"]))


@pytest.mark.asyncio
async def test_non_matrix_config_has_no_per_college_cap(db: AsyncSession):
    """simple/none configs carry a scalar pool only — the global gate is the only one."""
    round_ = await _make_round(
        db,
        code="cq_scalar",
        quotas={"nstc": 5},
        has_college_quota=False,
        colleges=["A", "A", "A"],
    )
    svc = ManualDistributionService(db)

    await svc.allocate(round_["sch"].id, 115, "yearly", _allocations(round_["items"]))

    assert await svc.remaining(round_["config"], "nstc") == 2
