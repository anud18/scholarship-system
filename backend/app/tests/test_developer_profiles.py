"""
Tests for Developer Profile Service
Tests personalized developer authentication and profile management
"""

import pytest
from fastapi.testclient import TestClient
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
    async def test_create_developer_user(self, db_session: AsyncSession):
        """Test creating a developer user"""
        service = DeveloperProfileService(db_session)

        profile = DeveloperProfile(
            developer_id="testdev",
            full_name="Test Developer Student",
            chinese_name="測試開發者學生",
            english_name="Test Dev Student",
            role=UserRole.STUDENT,
            email_domain="test.dev",
            custom_attributes={"gpa": 3.8, "major": "CS"},
        )

        user = await service.create_developer_user("testdev", profile)

        assert user.username == "dev_testdev_student"
        assert user.email == "dev_testdev_student@test.dev"
        assert user.full_name == "Test Developer Student"
        assert user.chinese_name == "測試開發者學生"
        assert user.english_name == "Test Dev Student"
        assert user.role == UserRole.STUDENT
        assert user.is_active is True
        assert user.is_verified is True

    @pytest.mark.asyncio
    async def test_update_existing_developer_user(self, db_session: AsyncSession):
        """Test updating an existing developer user"""
        service = DeveloperProfileService(db_session)

        # Create initial user
        profile1 = DeveloperProfile(developer_id="testdev", full_name="Initial Name", role=UserRole.STUDENT)
        user1 = await service.create_developer_user("testdev", profile1)
        initial_id = user1.id

        # Update with new profile
        profile2 = DeveloperProfile(
            developer_id="testdev",
            full_name="Updated Name",
            chinese_name="更新名稱",
            role=UserRole.STUDENT,
        )
        user2 = await service.create_developer_user("testdev", profile2)

        assert user2.id == initial_id  # Same user, just updated
        assert user2.full_name == "Updated Name"
        assert user2.chinese_name == "更新名稱"

    @pytest.mark.asyncio
    async def test_get_developer_users(self, db_session: AsyncSession):
        """Test retrieving all users for a developer"""
        service = DeveloperProfileService(db_session)

        # Create multiple profiles for same developer
        profiles = [
            DeveloperProfile(developer_id="testdev", full_name="Student", role=UserRole.STUDENT),
            DeveloperProfile(developer_id="testdev", full_name="Professor", role=UserRole.PROFESSOR),
            DeveloperProfile(developer_id="testdev", full_name="Admin", role=UserRole.ADMIN),
        ]

        for profile in profiles:
            await service.create_developer_user("testdev", profile)

        users = await service.get_developer_users("testdev")

        assert len(users) == 3
        roles = {user.role for user in users}
        assert roles == {UserRole.STUDENT, UserRole.PROFESSOR, UserRole.ADMIN}

    @pytest.mark.asyncio
    async def test_delete_developer_user(self, db_session: AsyncSession):
        """Test deleting a specific developer user"""
        service = DeveloperProfileService(db_session)

        # Create user
        profile = DeveloperProfile(developer_id="testdev", full_name="Test User", role=UserRole.STUDENT)
        await service.create_developer_user("testdev", profile)

        # Delete user
        deleted = await service.delete_developer_user("testdev", UserRole.STUDENT)
        assert deleted is True

        # Verify deletion
        users = await service.get_developer_users("testdev")
        assert len(users) == 0

    @pytest.mark.asyncio
    async def test_delete_all_developer_users(self, db_session: AsyncSession):
        """Test deleting all users for a developer"""
        service = DeveloperProfileService(db_session)

        # Create multiple users
        profiles = [
            DeveloperProfile(developer_id="testdev", full_name="User1", role=UserRole.STUDENT),
            DeveloperProfile(developer_id="testdev", full_name="User2", role=UserRole.PROFESSOR),
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
    async def test_create_developer_test_suite(self, db_session: AsyncSession):
        """Test creating a complete test suite"""
        service = DeveloperProfileService(db_session)

        profiles = [
            DeveloperProfile(developer_id="testdev", full_name="Student", role=UserRole.STUDENT),
            DeveloperProfile(developer_id="testdev", full_name="Professor", role=UserRole.PROFESSOR),
            DeveloperProfile(developer_id="testdev", full_name="Admin", role=UserRole.ADMIN),
        ]

        users = await service.create_developer_test_suite("testdev", profiles)

        assert len(users) == 3
        usernames = {user.username for user in users}
        expected = {"dev_testdev_student", "dev_testdev_professor", "dev_testdev_admin"}
        assert usernames == expected

    @pytest.mark.asyncio
    async def test_get_all_developer_ids(self, db_session: AsyncSession):
        """Test getting all developer IDs"""
        service = DeveloperProfileService(db_session)

        # Create users for different developers
        profiles = [
            ("dev1", UserRole.STUDENT),
            ("dev2", UserRole.PROFESSOR),
            ("dev1", UserRole.ADMIN),  # dev1 has multiple profiles
        ]

        for dev_id, role in profiles:
            profile = DeveloperProfile(developer_id=dev_id, full_name=f"{dev_id} user", role=role)
            await service.create_developer_user(dev_id, profile)

        developer_ids = await service.get_all_developer_ids()

        assert set(developer_ids) == {"dev1", "dev2"}

    @pytest.mark.asyncio
    async def test_quick_setup_developer(self, db_session: AsyncSession):
        """Test quick setup functionality"""
        service = DeveloperProfileService(db_session)

        users = await service.quick_setup_developer("quickdev")

        assert len(users) == 3  # Student, Professor, Admin
        roles = {user.role for user in users}
        assert roles == {UserRole.STUDENT, UserRole.PROFESSOR, UserRole.ADMIN}

        # Verify names are properly set
        for user in users:
            assert "quickdev" in user.full_name.lower()
            assert user.chinese_name is not None
            assert user.english_name is not None


class TestDeveloperProfileManager:
    """Test the developer profile manager helper class"""

    def test_create_custom_profile(self):
        """Test creating a custom profile"""
        profile = DeveloperProfileManager.create_custom_profile(
            developer_id="testdev",
            role=UserRole.STUDENT,
            full_name="Custom Student",
            chinese_name="自定義學生",
            gpa=3.9,
            major="Computer Science",
        )

        assert profile.developer_id == "testdev"
        assert profile.role == UserRole.STUDENT
        assert profile.full_name == "Custom Student"
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
            assert profile.role == UserRole.STUDENT
            assert "testdev" in profile.full_name.lower()

    def test_create_staff_profiles(self):
        """Test creating staff profile suite"""
        profiles = DeveloperProfileManager.create_staff_profiles("testdev")

        assert len(profiles) == 3  # Professor, College, Admin

        roles = {p.role for p in profiles}
        expected_roles = {UserRole.PROFESSOR, UserRole.COLLEGE, UserRole.ADMIN}
        assert roles == expected_roles

        # Verify all have testdev in name
        for profile in profiles:
            assert "testdev" in profile.full_name.lower()


class TestDeveloperProfileAPI:
    """Test the developer profile API endpoints"""

    def test_get_all_developers(self):
        """Test getting all developer IDs via API"""
        response = client.get("/api/v1/auth/dev-profiles/developers")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)

    def test_quick_setup_developer_api(self):
        """Test quick setup via API"""
        response = client.post("/api/v1/auth/dev-profiles/apitest/quick-setup")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 3

        # Verify profiles were created
        profiles_response = client.get("/api/v1/auth/dev-profiles/apitest")
        assert profiles_response.status_code == 200
        profiles_data = profiles_response.json()
        assert profiles_data["data"]["count"] == 3

    def test_create_custom_profile_api(self):
        """Test creating custom profile via API"""
        custom_data = {
            "full_name": "API Test Student",
            "chinese_name": "API測試學生",
            "english_name": "API Test Student",
            "role": "student",
            "email_domain": "api.test",
            "custom_attributes": {"test_attribute": "test_value"},
        }

        response = client.post("/api/v1/auth/dev-profiles/apitest/create-custom", json=custom_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "dev_apitest_student" in data["data"]["username"]

    def test_create_student_suite_api(self):
        """Test creating student suite via API"""
        response = client.post("/api/v1/auth/dev-profiles/suitetest/student-suite")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 3

        # Verify student types
        created_profiles = data["data"]["created_profiles"]
        student_types = {p.get("student_type") for p in created_profiles}
        expected_types = {"undergraduate", "graduate", "phd"}
        assert student_types == expected_types

    def test_create_staff_suite_api(self):
        """Test creating staff suite via API"""
        response = client.post("/api/v1/auth/dev-profiles/stafftest/staff-suite")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["count"] == 3

    def test_get_developer_profiles_api(self):
        """Test getting developer profiles via API"""
        # Create some profiles first
        client.post("/api/v1/auth/dev-profiles/gettest/quick-setup")

        response = client.get("/api/v1/auth/dev-profiles/gettest")

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

    def test_delete_developer_profiles_api(self):
        """Test deleting developer profiles via API"""
        # Create profiles first
        client.post("/api/v1/auth/dev-profiles/deletetest/quick-setup")

        # Verify they exist
        get_response = client.get("/api/v1/auth/dev-profiles/deletetest")
        assert get_response.json()["data"]["count"] > 0

        # Delete them
        delete_response = client.delete("/api/v1/auth/dev-profiles/deletetest")

        assert delete_response.status_code == 200
        data = delete_response.json()
        assert data["success"] is True
        assert data["data"]["deleted_count"] > 0

        # Verify deletion
        get_response = client.get("/api/v1/auth/dev-profiles/deletetest")
        assert get_response.json()["data"]["count"] == 0

    def test_invalid_role_custom_profile(self):
        """Test creating custom profile with invalid role"""
        custom_data = {"full_name": "Test User", "role": "invalid_role"}

        response = client.post("/api/v1/auth/dev-profiles/errortest/create-custom", json=custom_data)

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "invalid" in data["detail"].lower()

    def test_missing_required_fields_custom_profile(self):
        """Test creating custom profile with missing required fields"""
        custom_data = {
            "role": "student"
            # Missing full_name
        }

        response = client.post("/api/v1/auth/dev-profiles/errortest/create-custom", json=custom_data)

        assert response.status_code == 400

    def test_developer_profile_authentication_flow(self):
        """Test complete authentication flow with developer profiles"""
        # Create a developer profile
        client.post("/api/v1/auth/dev-profiles/authtest/quick-setup")

        # Get the created profiles
        profiles_response = client.get("/api/v1/auth/dev-profiles/authtest")
        profiles = profiles_response.json()["data"]["profiles"]

        # Test login with the first profile
        test_username = profiles[0]["username"]

        login_response = client.post("/api/v1/auth/mock-sso/login", json={"username": test_username})

        assert login_response.status_code == 200
        login_data = login_response.json()
        assert login_data["success"] is True
        assert "access_token" in login_data["data"]

        # Test authenticated endpoint
        token = login_data["data"]["access_token"]
        auth_response = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})

        assert auth_response.status_code == 200
        user_data = auth_response.json()
        assert user_data["success"] is True
        assert user_data["data"]["username"] == test_username


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
                    response = client.get(endpoint) if endpoint.count("/") == 6 else client.post(endpoint)

                assert response.status_code == 404
                data = response.json()
                assert "disabled" in data["detail"].lower()

        finally:
            # Restore original setting
            settings.enable_mock_sso = original_setting
