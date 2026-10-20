"""Student-side guards around 申請梯次 (多梯次申請 audit follow-up).

- A student cannot flip ``is_renewal`` on their own application (that would skip the
  round's sub-type gate and rank them in the 續領 group).
- A draft submitted outside every application window is refused (it used to keep
  round 1 and skip the sub-type gate); a returned application still resubmits.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.application_round import ScholarshipApplicationRound
from app.models.user import User
from app.models.user_profile import UserProfile
from app.services.application_service import ApplicationService
from app.tests.ranking_scope_helpers import add_application, make_config, make_scholarship

NOW = datetime.now(timezone.utc)
OPEN = (NOW - timedelta(days=1), NOW + timedelta(days=5))
CLOSED = (NOW - timedelta(days=40), NOW - timedelta(days=30))
LATER = (NOW + timedelta(days=10), NOW + timedelta(days=20))


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


@pytest.fixture
def quiet_submit(monkeypatch):
    """Skip the MinIO document clone and the Redis cache flush submit performs."""

    async def _noop_clone(self, application, user):
        return None

    async def _noop_cache():
        return None

    monkeypatch.setattr(ApplicationService, "_clone_user_profile_documents", _noop_clone)
    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))


async def _submittable(db, scholarship_id: int, key: str, config_id: int, status=ApplicationStatus.draft):
    application = await add_application(db, scholarship_id, key, configuration_id=config_id, status=status)
    application.submitted_form_data = {"fields": {}, "documents": []}
    db.add(UserProfile(user_id=application.user_id, bank_document_photo_url="/files/passbook.jpg"))
    await db.commit()
    return application


async def _submit(client, db, login, application):
    login(await db.get(User, application.user_id))
    return await client.post(f"/api/v1/applications/{application.id}/submit")


class TestSubmitOutsideEveryWindow:
    @pytest_asyncio.fixture
    async def closed_config(self, db, scholarship):
        config = await make_config(db, scholarship.id, code="sg_closed")
        config.application_start_date, config.application_end_date = CLOSED
        await db.commit()
        db.add(
            ScholarshipApplicationRound(
                configuration_id=config.id,
                round_number=2,
                application_start_date=LATER[0],
                application_end_date=LATER[1],
                open_sub_types=["moe_1w"],
            )
        )
        await db.commit()
        return config

    async def test_draft_is_refused_between_rounds(self, client, db, login, quiet_submit, scholarship, closed_config):
        draft = await _submittable(db, scholarship.id, "sg_d1", closed_config.id)

        response = await _submit(client, db, login, draft)

        assert response.status_code == 400, response.text
        assert "目前非申請期間，無法送出申請" in response.text
        await db.refresh(draft)
        assert draft.status == ApplicationStatus.draft

    async def test_returned_application_still_resubmits(
        self, client, db, login, quiet_submit, scholarship, closed_config
    ):
        returned = await _submittable(
            db, scholarship.id, "sg_ret1", closed_config.id, status=ApplicationStatus.returned
        )

        response = await _submit(client, db, login, returned)

        assert response.status_code == 200, response.text
        await db.refresh(returned)
        assert returned.status == ApplicationStatus.submitted
        assert returned.application_round == 1

    async def test_dev_always_open_bypass_keeps_working(
        self, client, db, login, quiet_submit, monkeypatch, scholarship, closed_config
    ):
        from app.services import eligibility_service

        monkeypatch.setattr(eligibility_service, "application_period_bypassed", lambda: True)
        draft = await _submittable(db, scholarship.id, "sg_dev1", closed_config.id)

        response = await _submit(client, db, login, draft)

        assert response.status_code == 200, response.text
        await db.refresh(draft)
        assert draft.application_round == 1

    async def test_draft_submits_into_the_open_round(self, client, db, login, quiet_submit, scholarship, open_config):
        draft = await _submittable(db, scholarship.id, "sg_open1", open_config.id)

        response = await _submit(client, db, login, draft)

        assert response.status_code == 200, response.text
        await db.refresh(draft)
        assert draft.application_round == 1
