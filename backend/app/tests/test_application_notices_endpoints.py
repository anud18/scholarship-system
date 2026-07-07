"""Tests for the admin-editable 獎學金申請注意事項 endpoints.

GET  /api/v1/system-settings/application-notices — any authenticated user
PUT  /api/v1/system-settings/application-notices — admin only
"""

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.security import get_current_user
from app.main import app
from app.models.user import User
from app.schemas.application_notices import (
    APPLICATION_NOTICES_KEY,
    DEFAULT_APPLICATION_NOTICES,
    ApplicationNotices,
)


def _valid_payload() -> dict:
    return {
        "zh": {
            "items": [
                {"title": "申請資格", "content": "自訂資格說明"},
                {"title": "申請期限", "content": "自訂期限說明"},
            ],
            "important_notice": "自訂重要提醒",
        },
        "en": {
            "items": [
                {"title": "Eligibility", "content": "Custom eligibility"},
                {"title": "Deadline", "content": "Custom deadline"},
            ],
            "important_notice": "Custom important notice",
        },
    }


class TestApplicationNoticesSchema:
    def test_default_notices_are_valid_and_bilingual(self):
        assert len(DEFAULT_APPLICATION_NOTICES.zh.items) == 9
        assert len(DEFAULT_APPLICATION_NOTICES.en.items) == 9
        assert DEFAULT_APPLICATION_NOTICES.zh.items[0].title == "申請資格"
        assert DEFAULT_APPLICATION_NOTICES.zh.important_notice
        assert DEFAULT_APPLICATION_NOTICES.en.important_notice

    def test_rejects_empty_items_list(self):
        payload = _valid_payload()
        payload["zh"]["items"] = []
        with pytest.raises(ValidationError):
            ApplicationNotices.model_validate(payload)

    def test_rejects_blank_item_title(self):
        payload = _valid_payload()
        payload["zh"]["items"][0]["title"] = ""
        with pytest.raises(ValidationError):
            ApplicationNotices.model_validate(payload)

    def test_rejects_missing_locale(self):
        payload = _valid_payload()
        del payload["en"]
        with pytest.raises(ValidationError):
            ApplicationNotices.model_validate(payload)

    def test_rejects_overlong_content(self):
        payload = _valid_payload()
        payload["zh"]["items"][0]["content"] = "x" * 2001
        with pytest.raises(ValidationError):
            ApplicationNotices.model_validate(payload)


class TestApplicationNoticesEndpoints:
    @pytest.fixture(autouse=True)
    def _cleanup_overrides(self):
        yield
        app.dependency_overrides.pop(get_current_user, None)

    def _login(self, user: User):
        app.dependency_overrides[get_current_user] = lambda: user

    @pytest.mark.asyncio
    async def test_get_returns_defaults_when_unconfigured(self, client: AsyncClient, test_user: User):
        self._login(test_user)
        response = await client.get("/api/v1/system-settings/application-notices")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] == DEFAULT_APPLICATION_NOTICES.model_dump()

    @pytest.mark.asyncio
    async def test_put_requires_admin(self, client: AsyncClient, test_user: User):
        self._login(test_user)
        response = await client.put(
            "/api/v1/system-settings/application-notices",
            json=_valid_payload(),
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_update_roundtrip(self, client: AsyncClient, test_admin: User):
        self._login(test_admin)
        payload = _valid_payload()

        put_response = await client.put(
            "/api/v1/system-settings/application-notices",
            json=payload,
        )
        assert put_response.status_code == 200
        assert put_response.json()["success"] is True

        get_response = await client.get("/api/v1/system-settings/application-notices")
        assert get_response.status_code == 200
        assert get_response.json()["data"] == payload

    @pytest.mark.asyncio
    async def test_put_rejects_invalid_payload(self, client: AsyncClient, test_admin: User):
        self._login(test_admin)
        payload = _valid_payload()
        payload["zh"]["items"] = []
        response = await client.put(
            "/api/v1/system-settings/application-notices",
            json=payload,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_update_writes_audit_log(self, client: AsyncClient, test_admin: User, db):
        from sqlalchemy import select

        from app.models.system_setting import ConfigurationAuditLog

        self._login(test_admin)
        response = await client.put(
            "/api/v1/system-settings/application-notices",
            json=_valid_payload(),
        )
        assert response.status_code == 200

        result = await db.execute(
            select(ConfigurationAuditLog).where(ConfigurationAuditLog.setting_key == APPLICATION_NOTICES_KEY)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "CREATE"
        assert logs[0].changed_by == test_admin.id
