"""
Regression tests for issue #1079: /auth/register and /auth/login must return 404
when ENABLE_MOCK_SSO=false, preventing unauthenticated privilege escalation.
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
    def test_register_returns_404_when_mock_sso_disabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "enable_mock_sso", False)
        response = client.post(
            "/api/v1/auth/register",
            json={"nycu_id": "attacker", "name": "Attacker", "role": "super_admin"},
        )
        assert response.status_code == 404

    def test_register_reachable_when_mock_sso_enabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "enable_mock_sso", True)
        with patch("app.services.auth_service.AuthService.register_user", new_callable=AsyncMock) as mock_reg:
            from app.models.user import User, UserRole
            from datetime import datetime

            fake_user = User()
            fake_user.__dict__.update(
                {
                    "id": 1,
                    "nycu_id": "test001",
                    "name": "Test User",
                    "email": "test@test.com",
                    "role": UserRole.student,
                    "created_at": datetime(2026, 1, 1),
                }
            )
            mock_reg.return_value = fake_user
            response = client.post(
                "/api/v1/auth/register",
                json={"nycu_id": "test001", "name": "Test User"},
            )
            assert response.status_code != 404


class TestLoginGated:
    def test_login_returns_404_when_mock_sso_disabled(self, client, monkeypatch):
        monkeypatch.setattr(settings, "enable_mock_sso", False)
        response = client.post(
            "/api/v1/auth/login",
            json={"nycu_id": "admin"},
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
