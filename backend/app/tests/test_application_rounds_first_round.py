"""第一梯次 can restrict its sub-types too (多梯次申請 follow-up).

``scholarship_configurations.first_round_open_sub_types``: NULL = every sub-type
(existing configurations), a list = only those. One lookup,
``open_sub_types_for_round(n)``, answers every round.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.models.application import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import User, UserRole
from app.schemas.application import ApplicationUpdate
from app.services.application_service import ApplicationService
from app.services.scholarship_service import ScholarshipService
from app.tests.ranking_scope_helpers import add_application, make_config, make_scholarship, make_user

NOW = datetime.now(timezone.utc)
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
    scholarship = await make_scholarship(db, "first_round_scholarship")
    scholarship.sub_type_list = ["nstc", "moe_1w"]
    await db.commit()
    return scholarship


@pytest_asyncio.fixture
async def config(db, scholarship):
    config = await make_config(db, scholarship.id, code="fr_config")
    config.application_start_date, config.application_end_date = OPEN
    await db.commit()
    return config


@pytest_asyncio.fixture
async def admin(db):
    return await make_user(db, "fr_super", role=UserRole.super_admin)


async def _reload(db, config_id: int) -> ScholarshipConfiguration:
    stmt = (
        select(ScholarshipConfiguration)
        .where(ScholarshipConfiguration.id == config_id)
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one()


class TestEndpoint:
    async def test_saves_normalized_first_round_sub_types_and_resets_with_null(self, client, db, login, admin, config):
        login(admin)
        url = ROUNDS_URL.format(id=config.id)

        response = await client.put(url, json={"first_round_open_sub_types": [" NSTC ", "nstc"], "rounds": []})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["first_round_open_sub_types"] == ["nstc"]

        listing = await client.get(url)
        assert listing.json()["data"]["first_round_open_sub_types"] == ["nstc"]
        detail = await client.get(f"/api/v1/scholarship-configurations/configurations/{config.id}")
        assert detail.json()["data"]["first_round_open_sub_types"] == ["nstc"]

        response = await client.put(url, json={"first_round_open_sub_types": None, "rounds": []})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["first_round_open_sub_types"] is None

    async def test_rejects_unknown_sub_type(self, client, login, admin, config):
        login(admin)
        response = await client.put(
            ROUNDS_URL.format(id=config.id), json={"first_round_open_sub_types": ["xyz"], "rounds": []}
        )
        assert response.status_code == 400
        assert "第一梯次" in response.text and "xyz" in response.text

    async def test_rejects_empty_list(self, client, login, admin, config):
        login(admin)
        response = await client.put(
            ROUNDS_URL.format(id=config.id), json={"first_round_open_sub_types": [], "rounds": []}
        )
        assert response.status_code == 422
        assert "第一梯次至少需開放一個子類別" in response.text


class TestStudentPaths:
    async def test_existing_configuration_opens_every_sub_type_in_round_one(self, db, config):
        assert (await _reload(db, config.id)).open_sub_types_for_round(1) is None

    async def test_student_view_lists_only_round_one_sub_types(self, db, config):
        config.first_round_open_sub_types = ["nstc"]
        await db.commit()
        fields = ScholarshipService._application_round_fields(await _reload(db, config.id))
        assert fields["current_application_round"] == 1
        assert fields["open_sub_types"] == ["nstc"]

        offered, info = ScholarshipService._restrict_subtypes_to_round(
            [{"value": "nstc"}, {"value": "moe_1w"}],
            {"nstc": {"eligible": True}, "moe_1w": {"eligible": True}},
            fields["open_sub_types"],
        )
        assert [subtype["value"] for subtype in offered] == ["nstc"]
        assert info["moe_1w"]["closed_in_round"] is True

    async def test_draft_cannot_switch_to_a_sub_type_round_one_closed(self, db, scholarship, config):
        config.first_round_open_sub_types = ["nstc"]
        await db.commit()
        draft = await add_application(
            db, scholarship.id, "fr_d1", configuration_id=config.id, status=ApplicationStatus.draft
        )
        student = await db.get(User, draft.user_id)

        with pytest.raises(ValidationError, match="第一梯次僅開放申請：nstc"):
            await ApplicationService(db).update_application(
                draft.id, ApplicationUpdate(scholarship_subtype_list=["moe_1w"]), student
            )
