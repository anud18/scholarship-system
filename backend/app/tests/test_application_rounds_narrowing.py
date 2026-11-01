"""A round cannot stop opening a sub-type its submitted applications use (409).

Covers 第一梯次 (first_round_open_sub_types) and later rounds alike. Drafts and
renewals do not block: drafts are re-checked on submit, renewals inherit theirs.
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio

from app.models.application import ApplicationStatus
from app.models.application_round import ScholarshipApplicationRound
from app.models.user import UserRole
from app.tests.ranking_scope_helpers import add_application, make_config, make_scholarship, make_user

NOW = datetime.now(timezone.utc)
CLOSED = (NOW - timedelta(days=40), NOW - timedelta(days=30))
OPEN = (NOW - timedelta(days=1), NOW + timedelta(days=5))
ROUNDS_URL = "/api/v1/scholarship-configurations/configurations/{id}/application-rounds"


@pytest_asyncio.fixture
async def login():
    from app.core.security import get_current_user
    from app.main import app

    def _login(user) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def scholarship(db):
    scholarship = await make_scholarship(db, "narrowing_scholarship")
    scholarship.sub_type_list = ["nstc", "moe_1w"]
    await db.commit()
    return scholarship


@pytest_asyncio.fixture
async def config(db, scholarship):
    config = await make_config(db, scholarship.id, code="narrow_cfg")
    config.application_start_date, config.application_end_date = CLOSED
    await db.commit()
    db.add(
        ScholarshipApplicationRound(
            configuration_id=config.id,
            round_number=2,
            application_start_date=OPEN[0],
            application_end_date=OPEN[1],
            open_sub_types=["nstc", "moe_1w"],
        )
    )
    await db.commit()
    return config


@pytest_asyncio.fixture
async def admin(db, login):
    user = await make_user(db, "narrow_super", role=UserRole.super_admin)
    login(user)
    return user


def _body(first_round=None, second_round=("nstc", "moe_1w")):
    return {
        "first_round_open_sub_types": first_round,
        "rounds": [
            {
                "round_number": 2,
                "application_start_date": OPEN[0].isoformat(),
                "application_end_date": OPEN[1].isoformat(),
                "open_sub_types": list(second_round),
            }
        ],
    }


async def test_closing_a_used_sub_type_in_round_two_is_refused(client, db, admin, scholarship, config):
    for key in ("n1", "n2"):
        await add_application(
            db, scholarship.id, key, sub_type="moe_1w", application_round=2, configuration_id=config.id
        )

    response = await client.put(ROUNDS_URL.format(id=config.id), json=_body(second_round=("nstc",)))

    assert response.status_code == 409, response.text
    assert "第二梯次的moe_1w（2 件）" in response.text
    listing = await client.get(ROUNDS_URL.format(id=config.id))
    assert listing.json()["data"]["rounds"][0]["open_sub_types"] == ["nstc", "moe_1w"]


async def test_restricting_round_one_away_from_a_used_sub_type_is_refused(client, db, admin, scholarship, config):
    await add_application(db, scholarship.id, "n3", sub_type="nstc", configuration_id=config.id)

    response = await client.put(ROUNDS_URL.format(id=config.id), json=_body(first_round=["moe_1w"]))

    assert response.status_code == 409, response.text
    assert "第一梯次的nstc（1 件）" in response.text


async def test_drafts_and_renewals_do_not_block(client, db, admin, scholarship, config):
    await add_application(
        db, scholarship.id, "n4", sub_type="moe_1w", configuration_id=config.id, status=ApplicationStatus.draft
    )
    await add_application(db, scholarship.id, "n5", sub_type="moe_1w", configuration_id=config.id, is_renewal=True)
    await add_application(db, scholarship.id, "n6", sub_type="nstc", configuration_id=config.id)

    response = await client.put(ROUNDS_URL.format(id=config.id), json=_body(first_round=["nstc"]))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["first_round_open_sub_types"] == ["nstc"]
