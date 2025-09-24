"""
Tests for Mock SSO functionality
"""

from fastapi.testclient import TestClient

from app.main import app
from app.models.user import UserRole

client = TestClient(app)


class TestMockSSO:
    """Test mock SSO functionality"""

    def test_get_mock_users_success(self):
        """Test retrieving mock users list"""
        response = client.get("/api/v1/auth/mock-sso/users")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert len(data["data"]) > 0

        # Check first user structure
        first_user = data["data"][0]
        assert "username" in first_user
        assert "email" in first_user
        assert "role" in first_user
        assert "description" in first_user

    def test_mock_sso_login_success(self):
        """Test successful mock SSO login with existing user from init_db"""
        # Attempt login with existing user from init_db
        response = client.post("/api/v1/auth/mock-sso/login", json={"username": "student001"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "user" in data["data"]
        assert data["data"]["user"]["role"] == "student"

    def test_mock_sso_login_invalid_user(self):
        """Test mock SSO login with invalid username"""
        response = client.post("/api/v1/auth/mock-sso/login", json={"username": "nonexistent_user"})

        assert response.status_code == 400

    def test_mock_sso_login_missing_username(self):
        """Test mock SSO login without username"""
        response = client.post("/api/v1/auth/mock-sso/login", json={})

        assert response.status_code == 400
        data = response.json()
        assert "Username is required" in data["detail"]

    def test_mock_users_contain_all_roles(self):
        """Test that mock users include all user roles"""
        response = client.get("/api/v1/auth/mock-sso/users")

        assert response.status_code == 200
        data = response.json()

        roles = set(user["role"] for user in data["data"])
        expected_roles = {
            UserRole.STUDENT.value,
            UserRole.PROFESSOR.value,
            UserRole.COLLEGE.value,
            UserRole.ADMIN.value,
            UserRole.SUPER_ADMIN.value,
        }

        assert roles >= expected_roles  # Contains all expected roles

    def test_mock_sso_disabled_in_production(self, monkeypatch):
        """Test that mock SSO is properly disabled when setting is False"""
        # Mock the settings to disable mock SSO
        from app.core import config

        monkeypatch.setattr(config.settings, "enable_mock_sso", False)

        response = client.get("/api/v1/auth/mock-sso/users")
        assert response.status_code == 404

        response = client.post("/api/v1/auth/mock-sso/login", json={"username": "student001"})
        assert response.status_code == 404
