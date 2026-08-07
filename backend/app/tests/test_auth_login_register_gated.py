"""
Regression tests for issue #1079: privilege escalation prevention.

/auth/register is admin-only (requires authentication) — unauthenticated requests
must be rejected with 401, blocking anonymous privilege escalation.
/auth/login must return 404 when ENABLE_MOCK_SSO=false.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


class TestRegisterGated:
    def test_register_returns_401_without_auth(self, client):
        # /register requires get_current_user — unauthenticated requests must be rejected
        response = client.post(
            "/api/v1/auth/register",
            json={"nycu_id": "attacker", "name": "Attacker", "role": "super_admin"},
        )
        assert response.status_code == 401

    def test_register_returns_403_without_admin_role(self, client):
        # A valid non-admin token must be rejected with 403
        from app.main import app
        from app.core.security import get_current_user
        from app.models.user import User, UserRole

        fake_student = User()
        fake_student.__dict__.update(
            {
                "id": 99,
                "nycu_id": "student001",
                "name": "Student",
                "email": "s@test.com",
                "role": UserRole.student,
            }
        )

        async def override_student():
            return fake_student

        app.dependency_overrides[get_current_user] = override_student
        try:
            response = client.post(
                "/api/v1/auth/register",
                json={"nycu_id": "victim", "name": "Victim"},
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 403


class TestLoginGated:
    def test_login_returns_404_when_mock_sso_disabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "enable_mock_sso", False)
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin"},
        )
        assert response.status_code == 404

    def test_login_reachable_when_mock_sso_enabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "enable_mock_sso", True)
        with patch("app.services.auth_service.AuthService.login", new_callable=AsyncMock) as mock_login:
            mock_login.side_effect = Exception("no such user")
            response = client.post(
                "/api/v1/auth/login",
                json={"nycu_id": "nobody"},
            )
            assert response.status_code != 404
