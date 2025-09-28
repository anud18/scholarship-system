"""
API endpoint tests for ScholarshipConfiguration CRUD operations
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole


class TestScholarshipConfigurationEndpoints:
    """Test cases for ScholarshipConfiguration API endpoints"""

    @pytest.fixture
    async def test_scholarship_type(self, db: AsyncSession):
        """Create a test scholarship type"""
        scholarship_type = ScholarshipType(
            code="test_endpoint_phd",
            name="Test Endpoint PhD Scholarship",
            description="Test scholarship for endpoint testing",
            category="doctoral",
            is_active=True,
            is_application_period=True,
            eligible_student_types=["doctoral"],
        )
        db.add(scholarship_type)
        await db.commit()
        await db.refresh(scholarship_type)
        return scholarship_type

    @pytest.fixture
    async def test_admin_with_scholarship_access(self, db: AsyncSession, test_scholarship_type):
        """Create admin user with scholarship access"""
        admin = User(
            email="config_admin@university.edu",
            username="config_admin",
            full_name="Configuration Admin",
            role=UserRole.admin,
            is_active=True,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        # Grant access to scholarship type
        admin_scholarship = AdminScholarship(
            user_id=admin.id,
            scholarship_type_id=test_scholarship_type.id,
            is_active=True,
        )
        db.add(admin_scholarship)
        await db.commit()

        return admin

    @pytest.fixture
    async def authenticated_admin_client(self, client: AsyncClient, test_admin_with_scholarship_access):
        """Create authenticated admin client"""
        # Mock authentication for testing - in real scenario would use proper auth
        # For now, we'll assume the client has proper authorization headers
        client.headers.update({"Authorization": "Bearer mock_admin_token"})
        return client

    @pytest.fixture
    def valid_config_payload(self, test_scholarship_type):
        """Valid configuration payload for API testing"""
        return {
            "scholarship_type_id": test_scholarship_type.id,
            "config_name": "API Test Configuration",
            "config_code": "API-TEST-113-1",
            "academic_year": 113,
            "semester": "first",
            "description": "Configuration created via API test",
            "amount": 40000,
            "currency": "TWD",
            "application_start_date": "2024-09-01T09:00:00",
            "application_end_date": "2024-10-15T23:59:59",
            "requires_professor_recommendation": True,
            "requires_college_review": False,
            "is_active": True,
            "version": "1.0",
        }

    @pytest.mark.asyncio
    async def test_create_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        test_scholarship_type,
        valid_config_payload,
    ):
        """Test successful configuration creation via API"""
        response = await authenticated_admin_client.post(
            "/api/v1/admin/scholarship-configurations/", json=valid_config_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

        config_data = data["data"]
        assert config_data["config_name"] == valid_config_payload["config_name"]
        assert config_data["config_code"] == valid_config_payload["config_code"]
        assert config_data["academic_year"] == valid_config_payload["academic_year"]
        assert config_data["amount"] == valid_config_payload["amount"]

    @pytest.mark.asyncio
    async def test_create_configuration_invalid_data(self, authenticated_admin_client: AsyncClient):
        """Test configuration creation with invalid data"""
        invalid_payload = {
            "config_name": "",  # Empty name
            "academic_year": 50,  # Invalid year
            "amount": -1000,  # Negative amount
        }

        response = await authenticated_admin_client.post(
            "/api/v1/admin/scholarship-configurations/", json=invalid_payload
        )

        assert response.status_code == 400
        data = response.json()
        assert data["success"] is False
        assert "message" in data

    @pytest.mark.asyncio
    async def test_get_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test successful configuration retrieval"""
        # Create a configuration first
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester="first",
            config_name="Test Get Configuration",
            config_code="GET-TEST-113-1",
            amount=35000,
            currency="TWD",
            is_active=True,
            created_by=test_admin_with_scholarship_access.id,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        response = await authenticated_admin_client.get(f"/api/v1/admin/scholarship-configurations/{config.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] == config.id
        assert data["data"]["config_name"] == "Test Get Configuration"

    @pytest.mark.asyncio
    async def test_get_nonexistent_configuration(self, authenticated_admin_client: AsyncClient):
        """Test retrieving non-existent configuration"""
        response = await authenticated_admin_client.get("/api/v1/admin/scholarship-configurations/99999")

        assert response.status_code == 404
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_update_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test successful configuration update"""
        # Create a configuration first
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester="first",
            config_name="Original Name",
            config_code="UPDATE-TEST-113-1",
            amount=30000,
            currency="TWD",
            is_active=True,
            created_by=test_admin_with_scholarship_access.id,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        update_payload = {
            "config_name": "Updated Configuration Name",
            "amount": 45000,
            "description": "Updated description",
        }

        response = await authenticated_admin_client.put(
            f"/api/v1/admin/scholarship-configurations/{config.id}", json=update_payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["config_name"] == "Updated Configuration Name"
        assert data["data"]["amount"] == 45000

    @pytest.mark.asyncio
    async def test_delete_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test successful configuration deletion (deactivation)"""
        # Create a configuration first
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester="first",
            config_name="To Delete Configuration",
            config_code="DELETE-TEST-113-1",
            amount=25000,
            currency="TWD",
            is_active=True,
            created_by=test_admin_with_scholarship_access.id,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        response = await authenticated_admin_client.delete(f"/api/v1/admin/scholarship-configurations/{config.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_duplicate_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test successful configuration duplication"""
        # Create source configuration
        source_config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester="first",
            config_name="Source Configuration",
            config_code="SOURCE-113-1",
            amount=32000,
            currency="TWD",
            description="Source description",
            is_active=True,
            created_by=test_admin_with_scholarship_access.id,
        )
        db.add(source_config)
        await db.commit()
        await db.refresh(source_config)

        duplicate_payload = {
            "academic_year": 114,
            "semester": "first",
            "config_code": "DUPLICATE-114-1",
            "config_name": "Duplicated Configuration",
        }

        response = await authenticated_admin_client.post(
            f"/api/v1/admin/scholarship-configurations/{source_config.id}/duplicate",
            json=duplicate_payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        duplicate_data = data["data"]
        assert duplicate_data["academic_year"] == 114
        assert duplicate_data["config_code"] == "DUPLICATE-114-1"
        assert duplicate_data["config_name"] == "Duplicated Configuration"
        assert duplicate_data["amount"] == 32000  # Should inherit from source
        assert duplicate_data["description"] == "Source description"  # Should inherit

    @pytest.mark.asyncio
    async def test_list_configurations_with_filters(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test listing configurations with various filters"""
        # Create multiple configurations
        configs_data = [
            {
                "academic_year": 113,
                "semester": "first",
                "code": "LIST-113-1",
                "name": "List Test 113-1",
            },
            {
                "academic_year": 113,
                "semester": "second",
                "code": "LIST-113-2",
                "name": "List Test 113-2",
            },
            {
                "academic_year": 114,
                "semester": "first",
                "code": "LIST-114-1",
                "name": "List Test 114-1",
            },
        ]

        for config_data in configs_data:
            config = ScholarshipConfiguration(
                scholarship_type_id=test_scholarship_type.id,
                academic_year=config_data["academic_year"],
                semester=config_data["semester"],
                config_name=config_data["name"],
                config_code=config_data["code"],
                amount=30000,
                currency="TWD",
                is_active=True,
                created_by=test_admin_with_scholarship_access.id,
            )
            db.add(config)

        await db.commit()

        # Test filtering by academic year
        response = await authenticated_admin_client.get(
            "/api/v1/admin/scholarship-configurations/",
            params={
                "scholarship_type_id": test_scholarship_type.id,
                "academic_year": 113,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2  # Two configs for 113

        # Test filtering by semester
        response = await authenticated_admin_client.get(
            "/api/v1/admin/scholarship-configurations/",
            params={
                "scholarship_type_id": test_scholarship_type.id,
                "academic_year": 113,
                "semester": "first",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["semester"] == "first"

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client: AsyncClient):
        """Test that unauthorized users cannot access endpoints"""
        # Test without authentication token
        response = await client.get("/api/v1/admin/scholarship-configurations/")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_insufficient_permissions(self, client: AsyncClient, db: AsyncSession, test_scholarship_type):
        """Test that users without proper permissions cannot access"""
        # Create user without admin privileges
        regular_user = User(
            email="regular@university.edu",
            username="regular",
            full_name="Regular User",
            role=UserRole.student,
            is_active=True,
        )
        db.add(regular_user)
        await db.commit()

        # Mock token for regular user
        client.headers.update({"Authorization": "Bearer mock_regular_token"})

        response = await client.get("/api/v1/admin/scholarship-configurations/")
        assert response.status_code in [401, 403]  # Unauthorized or Forbidden

    @pytest.mark.asyncio
    async def test_create_configuration_duplicate_prevention(
        self,
        authenticated_admin_client: AsyncClient,
        test_scholarship_type,
        valid_config_payload,
    ):
        """Test that duplicate configurations are prevented"""
        # Create first configuration
        response1 = await authenticated_admin_client.post(
            "/api/v1/admin/scholarship-configurations/", json=valid_config_payload
        )
        assert response1.status_code == 200

        # Attempt to create duplicate
        response2 = await authenticated_admin_client.post(
            "/api/v1/admin/scholarship-configurations/", json=valid_config_payload
        )

        assert response2.status_code == 400
        data = response2.json()
        assert data["success"] is False
        assert "already exists" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_pagination_and_sorting(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test pagination and sorting of configuration lists"""
        # Create multiple configurations with different academic years
        for year in [111, 112, 113, 114, 115]:
            config = ScholarshipConfiguration(
                scholarship_type_id=test_scholarship_type.id,
                academic_year=year,
                semester="first",
                config_name=f"Pagination Test {year}",
                config_code=f"PAGE-{year}-1",
                amount=30000,
                currency="TWD",
                is_active=True,
                created_by=test_admin_with_scholarship_access.id,
            )
            db.add(config)

        await db.commit()

        # Test getting all configurations - should be sorted by academic year desc
        response = await authenticated_admin_client.get(
            "/api/v1/admin/scholarship-configurations/",
            params={"scholarship_type_id": test_scholarship_type.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        configs = data["data"]
        assert len(configs) == 5

        # Verify sorting (should be descending by academic year)
        academic_years = [config["academic_year"] for config in configs]
        assert academic_years == sorted(academic_years, reverse=True)


class TestScholarshipConfigurationEndpointsIntegration:
    """Integration tests combining multiple endpoints"""

    @pytest.mark.asyncio
    async def test_complete_configuration_workflow(
        self,
        authenticated_admin_client: AsyncClient,
        test_scholarship_type,
        valid_config_payload,
    ):
        """Test complete CRUD workflow through API"""
        # Create configuration
        create_response = await authenticated_admin_client.post(
            "/api/v1/admin/scholarship-configurations/", json=valid_config_payload
        )
        assert create_response.status_code == 200
        config_id = create_response.json()["data"]["id"]

        # Read configuration
        get_response = await authenticated_admin_client.get(f"/api/v1/admin/scholarship-configurations/{config_id}")
        assert get_response.status_code == 200

        # Update configuration
        update_payload = {"config_name": "Updated via Workflow", "amount": 55000}
        update_response = await authenticated_admin_client.put(
            f"/api/v1/admin/scholarship-configurations/{config_id}", json=update_payload
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["config_name"] == "Updated via Workflow"

        # Duplicate configuration
        duplicate_payload = {
            "academic_year": 114,
            "semester": "second",
            "config_code": "WORKFLOW-114-2",
            "config_name": "Workflow Duplicate",
        }
        duplicate_response = await authenticated_admin_client.post(
            f"/api/v1/admin/scholarship-configurations/{config_id}/duplicate",
            json=duplicate_payload,
        )
        assert duplicate_response.status_code == 200
        duplicate_id = duplicate_response.json()["data"]["id"]

        # List configurations to verify both exist
        list_response = await authenticated_admin_client.get(
            "/api/v1/admin/scholarship-configurations/",
            params={"scholarship_type_id": test_scholarship_type.id},
        )
        assert list_response.status_code == 200
        configs = list_response.json()["data"]
        assert len(configs) >= 2

        # Delete original configuration
        delete_response = await authenticated_admin_client.delete(
            f"/api/v1/admin/scholarship-configurations/{config_id}"
        )
        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["is_active"] is False

        # Verify duplicate still exists and is active
        get_duplicate_response = await authenticated_admin_client.get(
            f"/api/v1/admin/scholarship-configurations/{duplicate_id}"
        )
        assert get_duplicate_response.status_code == 200
        assert get_duplicate_response.json()["data"]["is_active"] is True
