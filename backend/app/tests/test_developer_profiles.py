"""
Tests for Developer Profile Service
Tests personalized developer authentication and profile management
"""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.main import app
from app.models.user import UserRole
from app.services.developer_profile_service import DeveloperProfile, DeveloperProfileManager, DeveloperProfileService

# Enable mock SSO for testing
settings.enable_mock_sso = True

client = TestClient(app)


class TestDeveloperProfileService:
    """Test the developer profile service functionality"""

    @pytest.mark.asyncio
    async def test_create_developer_user(self, db: AsyncSession):
        """Test creating a developer user"""
        service = DeveloperProfileService(db)

        profile = DeveloperProfile(
            developer_id="testdev",
            name="Test Developer Student",
            chinese_name="測試開發者學生",
            english_name="Test Dev Student",
            role=UserRole.student,
            email_domain="test.dev",
            custom_attributes={"gpa": 3.8, "major": "CS"},
        )

        user = await service.create_developer_user("testdev", profile)

        assert user.nycu_id == "dev_testdev_student"
        assert user.email == "dev_testdev_student@test.dev"
        assert user.name == "Test Developer Student"
        assert user.raw_data["chinese_name"] == "測試開發者學生"
        assert user.raw_data["english_name"] == "Test Dev Student"
        assert user.role == UserRole.student

    @pytest.mark.asyncio
    async def test_update_existing_developer_user(self, db: AsyncSession):
        """Test updating an existing developer user"""
        service = DeveloperProfileService(db)

        # Create initial user
        profile1 = DeveloperProfile(developer_id="testdev", name="Initial Name", role=UserRole.student)
        user1 = await service.create_developer_user("testdev", profile1)
        initial_id = user1.id

        # Update with new profile
        profile2 = DeveloperProfile(
            developer_id="testdev",
            name="Updated Name",
            chinese_name="更新名稱",
            role=UserRole.student,
        )
        user2 = await service.create_developer_user("testdev", profile2)

        assert user2.id == initial_id  # Same user, just updated
        assert user2.name == "Updated Name"

    @pytest.mark.asyncio
    async def test_get_developer_users(self, db: AsyncSession):
        """Test retrieving all users for a developer"""
        service = DeveloperProfileService(db)

        # Create multiple profiles for same developer
        profiles = [
            DeveloperProfile(developer_id="testdev", name="Student", role=UserRole.student),
            DeveloperProfile(developer_id="testdev", name="Professor", role=UserRole.professor),
            DeveloperProfile(developer_id="testdev", name="Admin", role=UserRole.admin),
        ]

        for profile in profiles:
            await service.create_developer_user("testdev", profile)

        users = await service.get_developer_users("testdev")

        assert len(users) == 3
        roles = {user.role for user in users}
        assert roles == {UserRole.student, UserRole.professor, UserRole.admin}

    @pytest.mark.asyncio
    async def test_delete_developer_user(self, db: AsyncSession):
        """Test deleting a specific developer user"""
        service = DeveloperProfileService(db)

        # Create user
        profile = DeveloperProfile(developer_id="testdev", name="Test User", role=UserRole.student)
        await service.create_developer_user("testdev", profile)

        # Delete user
        deleted = await service.delete_developer_user("testdev", UserRole.student)
        assert deleted is True

        # Verify deletion
        users = await service.get_developer_users("testdev")
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_delete_all_developer_users(self, db: AsyncSession):
        """Test deleting all users for a developer"""
        service = DeveloperProfileService(db)

        # Create multiple users
        profiles = [
            DeveloperProfile(developer_id="testdev", name="User1", role=UserRole.student),
            DeveloperProfile(developer_id="testdev", name="User2", role=UserRole.professor),
        ]

        for profile in profiles:
            await service.create_developer_user("testdev", profile)

        # Delete all
        deleted_count = await service.delete_all_developer_users("testdev")
        assert deleted_count == 2

        # Verify deletion
        users = await service.get_developer_users("testdev")
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_create_developer_test_suite(self, db: AsyncSession):
        """Test creating a complete test suite"""
        service = DeveloperProfileService(db)

        profiles = [
            DeveloperProfile(developer_id="testdev", name="Student", role=UserRole.student),
            DeveloperProfile(developer_id="testdev", name="Professor", role=UserRole.professor),
            DeveloperProfile(developer_id="testdev", name="Admin", role=UserRole.admin),
        ]

        users = await service.create_developer_test_suite("testdev", profiles)

        assert len(users) == 3
        nycu_ids = {user.nycu_id for user in users}
        expected = {"dev_testdev_student", "dev_testdev_professor", "dev_testdev_admin"}
        assert nycu_ids == expected

    @pytest.mark.asyncio
    async def test_get_all_developer_ids(self, db: AsyncSession):
        """Test getting all developer IDs"""
        service = DeveloperProfileService(db)

        # Create users for different developers
        profiles = [
            ("dev1", UserRole.student),
            ("dev2", UserRole.professor),
            ("dev1", UserRole.admin),  # dev1 has multiple profiles
        ]

        for dev_id, role in profiles:
            profile = DeveloperProfile(developer_id=dev_id, name=f"{dev_id} user", role=role)
            await service.create_developer_user(dev_id, profile)

        developer_ids = await service.get_all_developer_ids()

        assert set(developer_ids) == {"dev1", "dev2"}

    @pytest.mark.asyncio
    async def test_quick_setup_developer(self, db: AsyncSession):
        """Test quick setup functionality"""
        service = DeveloperProfileService(db)

        users = await service.quick_setup_developer("quickdev")

        assert len(users) == 3  # Student, Professor, Admin
        roles = {user.role for user in users}
        assert roles == {UserRole.student, UserRole.professor, UserRole.admin}

        # Verify names are properly set
        for user in users:
            assert "quickdev" in user.name.lower()
            assert user.raw_data["chinese_name"] is not None
            assert user.raw_data["english_name"] is not None


class TestDeveloperProfileManager:
    """Test the developer profile manager helper class"""

    def test_create_custom_profile(self):
        """Test creating a custom profile"""
        profile = DeveloperProfileManager.create_custom_profile(
            developer_id="testdev",
            role=UserRole.student,
            name="Custom Student",
            chinese_name="自定義學生",
            gpa=3.9,
            major="Computer Science",
        )

        assert profile.developer_id == "testdev"
        assert profile.role == UserRole.student
        assert profile.name == "Custom Student"
        assert profile.chinese_name == "自定義學生"
        assert profile.custom_attributes["gpa"] == 3.9
        assert profile.custom_attributes["major"] == "Computer Science"

    def test_create_student_profiles(self):
        """Test creating student profile suite"""
        profiles = DeveloperProfileManager.create_student_profiles("testdev")

        assert len(profiles) == 3  # Freshman, Graduate, PhD

        student_types = {p.custom_attributes.get("student_type") for p in profiles}
        expected_types = {"undergraduate", "graduate", "phd"}
        assert student_types == expected_types

        # Verify all are students
        for profile in profiles:
            assert profile.role == UserRole.student
            assert "testdev" in profile.name.lower()

    def test_create_staff_profiles(self):
        """Test creating staff profile suite"""
        profiles = DeveloperProfileManager.create_staff_profiles("testdev")

        assert len(profiles) == 4  # two professors, one college reviewer, one super_admin

        roles = {p.role for p in profiles}
        expected_roles = {UserRole.professor, UserRole.college, UserRole.super_admin}
        assert roles == expected_roles

        # Verify all have testdev in name
        for profile in profiles:
            assert "testdev" in profile.name.lower()


@pytest.mark.integration
class TestDeveloperProfileAPI:
    """Test the developer profile API endpoints"""

    pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

    async def test_get_all_developers(self, client: AsyncClient):
        """Test getting all developer IDs via API"""
        response = await client.get("/api/v1/auth/dev-profiles/developers")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    async def test_quick_setup_developer_api(self, client: AsyncClient):
        """Test quick setup via API"""
        response = await client.post("/api/v1/auth/dev-profiles/apitest/quick-setup")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 3

        # Verify profiles were created
        profiles_response = await client.get("/api/v1/auth/dev-profiles/apitest")
        assert profiles_response.status_code == 200
        profiles_data = profiles_response.json()
        assert profiles_data["data"]["count"] == 3

    async def test_create_custom_profile_api(self, client: AsyncClient):
        """Test creating custom profile via API"""
        custom_data = {
            "full_name": "API Test Student",
            "chinese_name": "API測試學生",
            "english_name": "API Test Student",
            "role": "student",
            "email_domain": "api.test",
            "custom_attributes": {"test_attribute": "test_value"},
        }

        response = await client.post("/api/v1/auth/dev-profiles/apitest/create-custom", json=custom_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "dev_apitest_student" in data["data"]["username"]

    async def test_create_student_suite_api(self, client: AsyncClient):
        """Test creating student suite via API"""
        response = await client.post("/api/v1/auth/dev-profiles/suitetest/student-suite")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 3

        # Verify student types
        created_profiles = data["data"]["created_profiles"]
        student_types = {p.get("student_type") for p in created_profiles}
        expected_types = {"undergraduate", "graduate", "phd"}
        assert student_types == expected_types

    async def test_create_staff_suite_api(self, client: AsyncClient):
        """Test creating staff suite via API"""
        response = await client.post("/api/v1/auth/dev-profiles/stafftest/staff-suite")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 4

    async def test_get_developer_profiles_api(self, client: AsyncClient):
        """Test getting developer profiles via API"""
        # Create some profiles first
        await client.post("/api/v1/auth/dev-profiles/gettest/quick-setup")

        response = await client.get("/api/v1/auth/dev-profiles/gettest")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["developer_id"] == "gettest"
        assert data["data"]["count"] > 0

        # Verify profile structure
        profiles = data["data"]["profiles"]
        for profile in profiles:
            assert "username" in profile
            assert "email" in profile
            assert "role" in profile
            assert "full_name" in profile

    async def test_delete_developer_profiles_api(self, client: AsyncClient):
        """Test deleting developer profiles via API"""
        # Create profiles first
        await client.post("/api/v1/auth/dev-profiles/deletetest/quick-setup")

        # Verify they exist
        get_response = await client.get("/api/v1/auth/dev-profiles/deletetest")
        assert get_response.json()["data"]["count"] > 0

        # Delete them
        delete_response = await client.delete("/api/v1/auth/dev-profiles/deletetest")

        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["success"] is True
        assert data["data"]["deleted_count"] > 0

        # Verify deletion
        get_response = await client.get("/api/v1/auth/dev-profiles/deletetest")
        assert get_response.json()["data"]["count"] == 0

    async def test_invalid_role_custom_profile(self, client: AsyncClient):
        """Test creating custom profile with invalid role"""
        custom_data = {"full_name": "Test User", "role": "invalid_role"}

        response = await client.post("/api/v1/auth/dev-profiles/errortest/create-custom", json=custom_data)

        assert response.status_code in (400, 422)
        data = response.json()
        assert data["success"] is False

    async def test_missing_required_fields_custom_profile(self, client: AsyncClient):
        """Test creating custom profile with missing required fields"""
        custom_data = {
            "role": "student"
            # Missing full_name
        }

        response = await client.post("/api/v1/auth/dev-profiles/errortest/create-custom", json=custom_data)

        assert response.status_code in (400, 422)

    async def test_developer_profile_authentication_flow(self, client: AsyncClient):
        """Test complete authentication flow with developer profiles"""
        # Create a developer profile
        await client.post("/api/v1/auth/dev-profiles/authtest/quick-setup")

        # Get the created profiles
        profiles_response = await client.get("/api/v1/auth/dev-profiles/authtest")
        profiles = profiles_response.json()["data"]["profiles"]

        # Test login with the first profile
        test_username = profiles[0]["username"]

        login_response = await client.post("/api/v1/auth/mock-sso/login", json={"username": test_username})

        assert login_response.status_code == 200
        login_data = login_response.json()
        assert login_data["success"] is True
        assert "access_token" in login_data["data"]

        # Test authenticated endpoint
        token = login_data["data"]["access_token"]
        auth_response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

        assert auth_response.status_code == 200
        user_data = auth_response.json()
        assert user_data["success"] is True
        # User model exposes nycu_id (the `username` column was renamed); the
        # dev-profile "username" IS the nycu_id the mock-SSO login was made with.
        assert user_data["data"]["nycu_id"] == test_username


class TestProductionSafety:
    """Test that developer profiles are properly disabled in production"""

    def test_disabled_endpoints_when_mock_sso_disabled(self):
        """Test that endpoints return 404 when mock SSO is disabled"""
        # Temporarily disable mock SSO
        original_setting = settings.enable_mock_sso
        settings.enable_mock_sso = False

        try:
            endpoints = [
                "/api/v1/auth/dev-profiles/developers",
                "/api/v1/auth/dev-profiles/test",
                "/api/v1/auth/dev-profiles/test/quick-setup",
                "/api/v1/auth/dev-profiles/test/create-custom",
                "/api/v1/auth/dev-profiles/test/student-suite",
                "/api/v1/auth/dev-profiles/test/staff-suite",
            ]

            for endpoint in endpoints:
                if "create-custom" in endpoint:
                    response = client.post(endpoint, json={"full_name": "Test", "role": "student"})
                else:
                    response = client.get(endpoint) if endpoint.count("/") == 5 else client.post(endpoint)

                assert response.status_code == 404
                data = response.json()
                assert "disabled" in data["message"].lower()

        finally:
            # Restore original setting
            settings.enable_mock_sso = original_setting
