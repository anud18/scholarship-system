"""Regression tests for #1079.

`POST /auth/register` accepted a client-supplied `role` (including super_admin)
with no authentication, and `POST /auth/login` had no password field at all, so
`authenticate_user` minted a valid JWT for any known username — two unauthenticated
requests chained into full super_admin access.

The fix gates both endpoints behind `settings.enable_mock_sso` (404 when disabled),
matching the existing `/auth/mock-sso/*` and `/auth/dev-profiles/*` pattern.
`ENABLE_MOCK_SSO=false` on staging/production closes the exploit while local
dev/test (default True) keep working.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, UserType


class TestAuthRegisterLoginGated:
    async def test_register_returns_404_when_mock_sso_disabled(self, client: AsyncClient, monkeypatch):
        from app.core import config

        monkeypatch.setattr(config.settings, "enable_mock_sso", False)

        resp = await client.post(
            "/api/v1/auth/register",
            json={"nycu_id": "attacker_001", "role": "super_admin"},
        )
        assert resp.status_code == 404

    async def test_login_returns_404_when_mock_sso_disabled(self, client: AsyncClient, monkeypatch):
        from app.core import config

        monkeypatch.setattr(config.settings, "enable_mock_sso", False)

        resp = await client.post("/api/v1/auth/login", json={"username": "admin"})
        assert resp.status_code == 404

    async def test_register_still_works_when_mock_sso_enabled(self, client: AsyncClient, monkeypatch):
        """Local dev/test behavior is preserved (endpoint reachable when enabled)."""
        from app.core import config

        monkeypatch.setattr(config.settings, "enable_mock_sso", True)

        resp = await client.post(
            "/api/v1/auth/register",
            json={"nycu_id": "reg_enabled_001", "name": "Reg Enabled"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["nycu_id"] == "reg_enabled_001"

    async def test_login_still_works_when_mock_sso_enabled(self, client: AsyncClient, db: AsyncSession, monkeypatch):
        from app.core import config

        monkeypatch.setattr(config.settings, "enable_mock_sso", True)

        user = User(
            nycu_id="login_enabled_001",
            name="Login Enabled",
            email="login_enabled_001@nycu.edu.tw",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()

        resp = await client.post("/api/v1/auth/login", json={"username": "login_enabled_001"})
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"]
