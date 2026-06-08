"""
API endpoint tests for ScholarshipConfiguration CRUD operations

These exercise the real router mounted at
``/api/v1/scholarship-configurations`` whose CRUD routes live under the
``/configurations`` sub-path. Admin auth is provided by overriding the
``require_admin`` dependency (the standard FastAPI testing pattern used by the
other integration tests in this package) so we don't need real JWT tokens.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.main import app
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole, UserType

BASE = "/api/v1/scholarship-configurations/configurations"


# --------------------------------------------------------------------------- #
# Shared fixtures (module-level so both test classes can reuse them)
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def test_scholarship_type(db: AsyncSession) -> ScholarshipType:
    """Create a test scholarship type.

    ``is_active`` is now a read-only property derived from ``status`` and has no
    setter, so the active state is expressed via ``status``.
    """
    scholarship_type = ScholarshipType(
        code="test_endpoint_phd",
        name="Test Endpoint PhD Scholarship",
        description="Test scholarship for endpoint testing",
        status=ScholarshipStatus.active.value,
    )
    db.add(scholarship_type)
    await db.commit()
    await db.refresh(scholarship_type)
    return scholarship_type


@pytest_asyncio.fixture
async def test_admin_with_scholarship_access(db: AsyncSession, test_scholarship_type) -> User:
    """Create admin user with access to ``test_scholarship_type``."""
    admin = User(
        nycu_id="config_admin",
        email="config_admin@university.edu",
        name="Configuration Admin",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)

    # Grant access to scholarship type via the AdminScholarship link table.
    admin_scholarship = AdminScholarship(
        admin_id=admin.id,
        scholarship_id=test_scholarship_type.id,
    )
    db.add(admin_scholarship)
    await db.commit()

    return admin


@pytest_asyncio.fixture
async def authenticated_admin_client(client: AsyncClient, test_admin_with_scholarship_access) -> AsyncClient:
    """Yield a client whose ``require_admin`` dependency resolves to the admin
    that has scholarship access. The override is removed in teardown so the
    plain ``client`` used by the unauthorized/permission tests is unaffected.
    """

    async def override_admin():
        return test_admin_with_scholarship_access

    app.dependency_overrides[require_admin] = override_admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def valid_config_payload(test_scholarship_type):
    """Valid configuration payload for API testing."""
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


class TestScholarshipConfigurationEndpoints:
    """Test cases for ScholarshipConfiguration API endpoints"""

    @pytest.mark.asyncio
    async def test_create_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        test_scholarship_type,
        valid_config_payload,
    ):
        """Test successful configuration creation via API.

        The create endpoint returns only ``{id, config_code}``; the full record
        is verified by fetching it afterwards.
        """
        response = await authenticated_admin_client.post(BASE, json=valid_config_payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert data["data"]["config_code"] == valid_config_payload["config_code"]

        config_id = data["data"]["id"]
        get_response = await authenticated_admin_client.get(f"{BASE}/{config_id}")
        assert get_response.status_code == 200
        config_data = get_response.json()["data"]
        assert config_data["config_name"] == valid_config_payload["config_name"]
        assert config_data["config_code"] == valid_config_payload["config_code"]
        assert config_data["academic_year"] == valid_config_payload["academic_year"]
        assert config_data["amount"] == valid_config_payload["amount"]

    @pytest.mark.asyncio
    async def test_create_configuration_invalid_data(self, authenticated_admin_client: AsyncClient):
        """Test configuration creation with invalid/incomplete data.

        The endpoint accepts a free-form ``Dict`` body (no Pydantic validation),
        so a payload missing ``scholarship_type_id`` is rejected by the access
        check rather than by field validation -> 403.
        """
        invalid_payload = {
            "config_name": "",  # Empty name
            "academic_year": 50,  # Invalid year
            "amount": -1000,  # Negative amount
        }

        response = await authenticated_admin_client.post(BASE, json=invalid_payload)

        assert response.status_code == 403
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
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
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

        response = await authenticated_admin_client.get(f"{BASE}/{config.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["id"] == config.id
        assert data["data"]["config_name"] == "Test Get Configuration"

    @pytest.mark.asyncio
    async def test_get_nonexistent_configuration(self, authenticated_admin_client: AsyncClient):
        """Test retrieving non-existent configuration"""
        response = await authenticated_admin_client.get(f"{BASE}/99999")

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
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
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

        response = await authenticated_admin_client.put(f"{BASE}/{config.id}", json=update_payload)

        assert response.status_code == 200
        assert response.json()["success"] is True

        # The update endpoint returns only {id, config_code}; verify the changes
        # by re-fetching the configuration.
        get_response = await authenticated_admin_client.get(f"{BASE}/{config.id}")
        config_data = get_response.json()["data"]
        assert config_data["config_name"] == "Updated Configuration Name"
        assert config_data["amount"] == 45000

    @pytest.mark.asyncio
    async def test_delete_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test successful configuration deletion (deactivation)"""
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
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

        response = await authenticated_admin_client.delete(f"{BASE}/{config.id}")

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Soft delete -> the configuration is deactivated. Verify via re-fetch.
        get_response = await authenticated_admin_client.get(f"{BASE}/{config.id}")
        assert get_response.status_code == 200
        assert get_response.json()["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_duplicate_configuration_success(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test successful configuration duplication"""
        source_config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
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
            f"{BASE}/{source_config.id}/duplicate",
            json=duplicate_payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["config_code"] == "DUPLICATE-114-1"

        # The duplicate endpoint returns only {id, config_code}; verify the
        # inherited + overridden fields by fetching the new configuration.
        duplicate_id = data["data"]["id"]
        get_response = await authenticated_admin_client.get(f"{BASE}/{duplicate_id}")
        duplicate_data = get_response.json()["data"]
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
        configs_data = [
            {
                "academic_year": 113,
                "semester": Semester.first,
                "code": "LIST-113-1",
                "name": "List Test 113-1",
            },
            {
                "academic_year": 113,
                "semester": Semester.second,
                "code": "LIST-113-2",
                "name": "List Test 113-2",
            },
            {
                "academic_year": 114,
                "semester": Semester.first,
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

        # Filter by academic year
        response = await authenticated_admin_client.get(
            BASE,
            params={
                "scholarship_type_id": test_scholarship_type.id,
                "academic_year": 113,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 2  # Two configs for 113

        # Filter by semester
        response = await authenticated_admin_client.get(
            BASE,
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
        # No Authorization header -> require_admin -> get_current_user -> 401
        response = await client.get(BASE)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_insufficient_permissions(self, client: AsyncClient, db: AsyncSession, test_scholarship_type):
        """Test that users without proper permissions cannot access"""
        regular_user = User(
            nycu_id="regular",
            email="regular@university.edu",
            name="Regular User",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(regular_user)
        await db.commit()

        # Invalid/foreign token -> rejected before reaching the endpoint logic.
        client.headers.update({"Authorization": "Bearer mock_regular_token"})

        response = await client.get(BASE)
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
        response1 = await authenticated_admin_client.post(BASE, json=valid_config_payload)
        assert response1.status_code == 200

        # Attempt to create a duplicate for the same type/year/semester -> 409
        response2 = await authenticated_admin_client.post(BASE, json=valid_config_payload)

        assert response2.status_code == 409
        data = response2.json()
        assert data["success"] is False
        # The endpoint rejects the duplicate with a (localized) "already exists"
        # message; just confirm a message is returned.
        assert data.get("message")

    @pytest.mark.asyncio
    async def test_pagination_and_sorting(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Test pagination and sorting of configuration lists"""
        for year in [111, 112, 113, 114, 115]:
            config = ScholarshipConfiguration(
                scholarship_type_id=test_scholarship_type.id,
                academic_year=year,
                semester=Semester.first,
                config_name=f"Pagination Test {year}",
                config_code=f"PAGE-{year}-1",
                amount=30000,
                currency="TWD",
                is_active=True,
                created_by=test_admin_with_scholarship_access.id,
            )
            db.add(config)

        await db.commit()

        response = await authenticated_admin_client.get(
            BASE,
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
        create_response = await authenticated_admin_client.post(BASE, json=valid_config_payload)
        assert create_response.status_code == 200
        config_id = create_response.json()["data"]["id"]

        # Read configuration
        get_response = await authenticated_admin_client.get(f"{BASE}/{config_id}")
        assert get_response.status_code == 200

        # Update configuration
        update_payload = {"config_name": "Updated via Workflow", "amount": 55000}
        update_response = await authenticated_admin_client.put(f"{BASE}/{config_id}", json=update_payload)
        assert update_response.status_code == 200
        get_after_update = await authenticated_admin_client.get(f"{BASE}/{config_id}")
        assert get_after_update.json()["data"]["config_name"] == "Updated via Workflow"

        # Duplicate configuration
        duplicate_payload = {
            "academic_year": 114,
            "semester": "second",
            "config_code": "WORKFLOW-114-2",
            "config_name": "Workflow Duplicate",
        }
        duplicate_response = await authenticated_admin_client.post(
            f"{BASE}/{config_id}/duplicate",
            json=duplicate_payload,
        )
        assert duplicate_response.status_code == 200
        duplicate_id = duplicate_response.json()["data"]["id"]

        # List configurations to verify both exist
        list_response = await authenticated_admin_client.get(
            BASE,
            params={"scholarship_type_id": test_scholarship_type.id},
        )
        assert list_response.status_code == 200
        configs = list_response.json()["data"]
        assert len(configs) >= 2

        # Delete original configuration
        delete_response = await authenticated_admin_client.delete(f"{BASE}/{config_id}")
        assert delete_response.status_code == 200
        get_after_delete = await authenticated_admin_client.get(f"{BASE}/{config_id}")
        assert get_after_delete.json()["data"]["is_active"] is False

        # Verify duplicate still exists and is active
        get_duplicate_response = await authenticated_admin_client.get(f"{BASE}/{duplicate_id}")
        assert get_duplicate_response.status_code == 200
        assert get_duplicate_response.json()["data"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_persists_project_numbers_and_shared_quota_sources(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Create must persist the flattened project_numbers and the
        shared_quota_sources link, and the GET response must echo both
        (and no longer expose prior_quota_years)."""
        # Prior-year source config the link will point at.
        source = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
            config_name="Source 113",
            config_code="SRC-113-1",
            amount=40000,
            has_college_quota=True,
            quotas={"nstc": {"EE": 5}},
            is_active=True,
        )
        db.add(source)
        await db.commit()

        payload = {
            "scholarship_type_id": test_scholarship_type.id,
            "config_name": "Create With Pools",
            "config_code": "POOLS-114-1",
            "academic_year": 114,
            "semester": "first",
            "amount": 40000,
            "currency": "TWD",
            "project_numbers": {"nstc": "114R000001"},
            "shared_quota_sources": [{"source_config_code": "SRC-113-1", "sub_types": ["nstc"]}],
        }
        response = await authenticated_admin_client.post(BASE, json=payload)
        assert response.status_code == 200, response.text
        config_id = response.json()["data"]["id"]

        get_response = await authenticated_admin_client.get(f"{BASE}/{config_id}")
        body = get_response.json()["data"]
        assert body["project_numbers"] == {"nstc": "114R000001"}
        assert body["shared_quota_sources"] == [{"source_config_code": "SRC-113-1", "sub_types": ["nstc"]}]
        assert "prior_quota_years" not in body

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_shared_quota_source(
        self,
        authenticated_admin_client: AsyncClient,
        test_scholarship_type,
    ):
        """A link to a non-existent source config is rejected at create."""
        payload = {
            "scholarship_type_id": test_scholarship_type.id,
            "config_name": "Bad Link",
            "config_code": "BADLINK-114-1",
            "academic_year": 114,
            "semester": "first",
            "amount": 40000,
            "shared_quota_sources": [{"source_config_code": "NOPE-999", "sub_types": ["nstc"]}],
        }
        response = await authenticated_admin_client.post(BASE, json=payload)
        assert response.status_code == 400
        assert "NOPE-999" in response.json()["message"]
