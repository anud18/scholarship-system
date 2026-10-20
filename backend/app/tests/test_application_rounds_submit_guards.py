"""Student-side guards around 申請梯次 (多梯次申請 audit follow-up).

- A student cannot flip ``is_renewal`` on their own application (that would skip the
  round's sub-type gate and rank them in the 續領 group).
"""

from datetime import datetime, timedelta, timezone

import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.user import User
from app.tests.ranking_scope_helpers import add_application, make_config, make_scholarship

NOW = datetime.now(timezone.utc)
OPEN = (NOW - timedelta(days=1), NOW + timedelta(days=5))


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
    scholarship = await make_scholarship(db, "submit_guard_scholarship")
    scholarship.sub_type_list = ["nstc", "moe_1w"]
    await db.commit()
    return scholarship


@pytest_asyncio.fixture
async def open_config(db, scholarship):
    config = await make_config(db, scholarship.id, code="sg_open")
    config.application_start_date, config.application_end_date = OPEN
    await db.commit()
    return config


async def test_student_cannot_mark_their_draft_as_renewal(client, db, login, scholarship, open_config):
    draft = await add_application(
        db, scholarship.id, "sg_r1", configuration_id=open_config.id, status=ApplicationStatus.draft
    )
    login(await db.get(User, draft.user_id))

    response = await client.put(f"/api/v1/applications/{draft.id}", json={"is_renewal": True, "agree_terms": True})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_renewal"] is False
    await db.refresh(draft)
    assert (await db.get(Application, draft.id)).is_renewal is False
