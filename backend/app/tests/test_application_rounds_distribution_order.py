"""The admin distribution page orders by round group (多梯次申請 follow-up).

The college's ranking is kept as the college saved it; the distribution grid,
預設分發 and the release-chain waitlist order 續領 → 第一梯次 → 第二梯次 …, then the
college's rank. The grid numbers that order per college as 實際順位
(``effective_rank``); college-rejected rows get none and follow the ranked rows.
"""

import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.application import ApplicationStatus
from app.models.college_review import CollegeRankingItem
from app.services.manual_distribution_service import ManualDistributionService, _compute_suggestions
from app.tests.ranking_scope_helpers import (
    SEMESTER,
    SUB_TYPE,
    YEAR,
    add_application,
    insert_ranking,
    make_config,
    make_scholarship,
    make_user,
)


@pytest_asyncio.fixture
async def scholarship(db):
    return await make_scholarship(db, "distribution_order_scholarship")


@pytest_asyncio.fixture
async def config(db, scholarship):
    return await make_config(db, scholarship.id, code="dist_order_cfg")


@pytest_asyncio.fixture
async def college_user(db):
    return await make_user(db, "dist_order_eng", college_code="ENG")


@pytest_asyncio.fixture
async def eng_ranking(db, scholarship, config, college_user):
    """ENG's finalized ranking as the college saved it: a 補充匯入 第一梯次 student
    (c1_late) sits below a 第二梯次 one, and x_rej was marked 'N'."""
    apps = {
        "renewal": await add_application(db, scholarship.id, "r_ren", is_renewal=True, configuration_id=config.id),
        "first": await add_application(db, scholarship.id, "c1", configuration_id=config.id),
        "second": await add_application(db, scholarship.id, "c2", application_round=2, configuration_id=config.id),
        "first_late": await add_application(db, scholarship.id, "c1_late", configuration_id=config.id),
        "rejected": await add_application(db, scholarship.id, "x_rej", configuration_id=config.id),
    }
    ranking = await insert_ranking(
        db,
        scholarship.id,
        created_by=college_user.id,
        application_ids=[apps[key].id for key in ("renewal", "first", "second", "first_late", "rejected")],
        is_finalized=True,
    )
    await db.execute(
        update(CollegeRankingItem)
        .where(CollegeRankingItem.application_id == apps["rejected"].id)
        .values(college_rejected=True)
    )
    await db.commit()
    return ranking


async def test_grid_orders_by_round_group_and_numbers_effective_rank(db, scholarship, config, eng_ranking):
    sci_second = await add_application(
        db, scholarship.id, "s2", college_code="SCI", application_round=2, configuration_id=config.id
    )
    sci_first = await add_application(db, scholarship.id, "s1", college_code="SCI", configuration_id=config.id)
    await insert_ranking(
        db,
        scholarship.id,
        created_by=eng_ranking.created_by,
        college_code="SCI",
        application_ids=[sci_second.id, sci_first.id],
        is_finalized=True,
    )

    students = await ManualDistributionService(db).get_students_for_distribution(scholarship.id, YEAR, SEMESTER)

    rows = [(s["college_code"], s["student_id"], s["rank_position"], s["effective_rank"]) for s in students]
    assert rows == [
        ("ENG", "r_ren", 1, 1),
        ("ENG", "c1", 2, 2),
        ("ENG", "c1_late", 4, 3),
        ("ENG", "c2", 3, 4),
        ("ENG", "x_rej", 5, None),
        ("SCI", "s1", 2, 1),
        ("SCI", "s2", 1, 2),
    ]


async def test_auto_allocate_follows_the_displayed_order(db, scholarship, config, eng_ranking):
    students = await ManualDistributionService(db).get_students_for_distribution(scholarship.id, YEAR, SEMESTER)
    items = (
        (
            await db.execute(
                select(CollegeRankingItem)
                .options(selectinload(CollegeRankingItem.application))
                .where(CollegeRankingItem.ranking_id == eng_ranking.id)
            )
        )
        .scalars()
        .all()
    )

    suggestions = _compute_suggestions(
        unique_items=list(items),
        default_prefs=[SUB_TYPE],
        prev_alloc_configs={},
        allowed_configs_by_sub_type={SUB_TYPE: [config.id]},
        quota_tracker={(config.id, SUB_TYPE, "ENG"): 3},
        own_config_id=config.id,
    )

    allocated = {s["ranking_item_id"] for s in suggestions if s["sub_type_code"]}
    first_three = {s["ranking_item_id"] for s in students if s["effective_rank"] in (1, 2, 3)}
    assert allocated == first_three


async def test_waitlist_puts_first_round_ahead_of_a_better_ranked_second_round(db, scholarship, config, college_user):
    second = await add_application(
        db,
        scholarship.id,
        "w2",
        application_round=2,
        configuration_id=config.id,
        status=ApplicationStatus.under_review,
    )
    first = await add_application(
        db, scholarship.id, "w1", configuration_id=config.id, status=ApplicationStatus.under_review
    )
    await insert_ranking(
        db, scholarship.id, created_by=college_user.id, application_ids=[second.id, first.id], is_finalized=True
    )

    waitlist = await ManualDistributionService(db)._get_waitlist_candidates(scholarship.id, YEAR, SUB_TYPE, None)

    assert [item.application_id for item in waitlist] == [first.id, second.id]
