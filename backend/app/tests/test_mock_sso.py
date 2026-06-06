"""
Tests for Mock SSO functionality
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, UserType


class TestMockSSO:
    """Test mock SSO functionality"""

    @pytest.fixture
    async def student001(self, db: AsyncSession) -> User:
        """Seed student001 user required by smoke SSO tests.

        The mock-sso/users endpoint queries the DB, and mock-sso/login looks
        up by nycu_id — both fail with an empty test DB without this fixture.
        """
        user = User(
            nycu_id="student001",
            name="Student 001",
            email="student001@nycu.edu.tw",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.mark.smoke
    async def test_get_mock_users_success(self, client: AsyncClient, student001: User):
        """Test retrieving mock users list"""
        response = await client.get("/api/v1/auth/mock-sso/users")

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

    @pytest.mark.smoke
    async def test_mock_sso_login_success(self, client: AsyncClient, student001: User):
        """Test successful mock SSO login with existing user from init_db"""
        response = await client.post("/api/v1/auth/mock-sso/login", json={"username": "student001"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert "user" in data["data"]
        assert data["data"]["user"]["role"] == "student"

    async def test_mock_sso_login_invalid_user(self, client: AsyncClient):
        """Test mock SSO login with invalid username"""
        response = await client.post("/api/v1/auth/mock-sso/login", json={"username": "nonexistent_user"})

        assert response.status_code == 400

    async def test_mock_sso_login_missing_username(self, client: AsyncClient):
        """Test mock SSO login without username"""
        response = await client.post("/api/v1/auth/mock-sso/login", json={})

        assert response.status_code == 400
        data = response.json()
        assert "NYCU ID is required" in data["message"]

    @pytest.fixture
    async def all_role_users(self, db: AsyncSession) -> None:
        """Seed one user per role so /mock-sso/users (which queries the DB)
        can return every role on the fresh per-test database."""
        for role in (
            UserRole.student,
            UserRole.professor,
            UserRole.college,
            UserRole.admin,
            UserRole.super_admin,
        ):
            db.add(
                User(
                    nycu_id=f"mock_{role.value}",
                    name=f"Mock {role.value}",
                    email=f"mock_{role.value}@nycu.edu.tw",
                    user_type=UserType.employee if role != UserRole.student else UserType.student,
                    role=role,
                )
            )
        await db.commit()

    async def test_mock_users_contain_all_roles(self, client: AsyncClient, all_role_users: None):
        """Test that mock users include all user roles"""
        response = await client.get("/api/v1/auth/mock-sso/users")

        assert response.status_code == 200
        data = response.json()

        roles = set(user["role"] for user in data["data"])
        expected_roles = {
            UserRole.student.value,
            UserRole.professor.value,
            UserRole.college.value,
            UserRole.admin.value,
            UserRole.super_admin.value,
        }

        assert roles >= expected_roles  # Contains all expected roles

    async def test_mock_sso_disabled_in_production(self, client: AsyncClient, monkeypatch):
        """Test that mock SSO is properly disabled when setting is False"""
        from app.core import config

        monkeypatch.setattr(config.settings, "enable_mock_sso", False)

        response = await client.get("/api/v1/auth/mock-sso/users")
        assert response.status_code == 404

        response = await client.post("/api/v1/auth/mock-sso/login", json={"username": "student001"})
        assert response.status_code == 404
