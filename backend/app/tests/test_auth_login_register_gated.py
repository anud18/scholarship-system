"""
Regression tests for the CRITICAL unauthenticated privilege-escalation chain:

    POST /auth/register (no auth, client-supplied `role`, incl. super_admin)
    + POST /auth/login (no password field at all — UserLogin has only `username`)
    = unauthenticated account creation + password-less token minting for any user.

Fix: both endpoints now 404 unless `settings.enable_mock_sso` is True, matching
the existing gate on /auth/mock-sso/* and /auth/dev-profiles/*. Real identities
come from Portal SSO (creates users directly, not via /auth/register) or from
the admin-gated POST /users (which reuses AuthService.register_user directly,
bypassing this HTTP endpoint) — so gating here does not affect any real flow.
"""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_register_is_404_when_mock_sso_disabled(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "enable_mock_sso", False)

    response = await client.post(
        "/api/v1/auth/register",
        json={"nycu_id": "attacker_created", "role": "super_admin"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_login_is_404_when_mock_sso_disabled(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "enable_mock_sso", False)

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin@nycu.edu.tw"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_register_and_login_still_work_when_mock_sso_enabled(client: AsyncClient, monkeypatch):
    """Dev/test convenience is preserved — only reachable deployments (staging/prod,
    which set ENABLE_MOCK_SSO=false) are closed off."""
    monkeypatch.setattr(settings, "enable_mock_sso", True)

    register_response = await client.post(
        "/api/v1/auth/register",
        json={"nycu_id": "dev_only_user", "role": "student"},
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"username": "dev_only_user"},
    )
    assert login_response.status_code == 200
    assert "access_token" in login_response.json()["data"]
