"""
Tests for quota management functionality
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.college_mappings import get_all_colleges, is_valid_college_code
from app.core.security import require_admin, require_staff
from app.main import app
from app.models.application import Application
from app.models.enums import ApplicationStatus, QuotaManagementMode, Semester, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole, UserType


@pytest_asyncio.fixture
async def super_admin_user(db: AsyncSession) -> User:
    """Create a real super-admin user persisted in the test DB."""
    user = User(
        nycu_id="superadmin",
        name="Super Admin",
        email="superadmin@university.edu",
        user_type=UserType.employee,
        role=UserRole.super_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_db_user(db: AsyncSession) -> User:
    """Create a real (regular) admin user persisted in the test DB."""
    user = User(
        nycu_id="reguladmin",
        name="Regular Admin",
        email="reguladmin@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth_as(user: User):
    """Override admin/staff guards so endpoints resolve to the given user without a real JWT."""

    def _override() -> User:
        return user

    app.dependency_overrides[require_admin] = _override
    app.dependency_overrides[require_staff] = _override


def _make_config(scholarship_type_id: int, **overrides) -> ScholarshipConfiguration:
    """Build a ScholarshipConfiguration with all NOT NULL columns populated."""
    defaults = dict(
        scholarship_type_id=scholarship_type_id,
        academic_year=113,
        semester=None,
        config_name="Test Config",
        config_code=f"cfg-{scholarship_type_id}-{overrides.get('academic_year', 113)}-{overrides.get('semester', 'y')}",
        quota_management_mode=QuotaManagementMode.matrix_based,
        is_active=True,
        amount=40000,
    )
    defaults.update(overrides)
    return ScholarshipConfiguration(**defaults)


def _make_application(scholarship_type_id: int, user_id: int, college_code: str, **overrides) -> Application:
    """Build an Application with all NOT NULL columns populated.

    Quota usage in the endpoint is derived from student_data['std_academyno'] and
    quota_allocation_status == 'allocated' (not from a Student model / status).
    """
    defaults = dict(
        app_id=overrides.pop("app_id"),
        user_id=user_id,
        scholarship_type_id=scholarship_type_id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        academic_year=113,
        semester=None,
        status=ApplicationStatus.approved.value,
        quota_allocation_status="allocated",
        student_data={"std_academyno": college_code},
        agree_terms=True,
    )
    defaults.update(overrides)
    return Application(**defaults)


class TestQuotaManagementPermissions:
    """Test permission-based access to quota management"""

    @pytest.mark.asyncio
    async def test_super_admin_can_access_quota_endpoints(
        self,
        client: AsyncClient,
        super_admin_user: User,
        db: AsyncSession,
    ):
        """Super admin should have full access to quota management"""
        _auth_as(super_admin_user)

        phd_scholarship = ScholarshipType(code="phd", name="博士生獎學金", status="active")
        db.add(phd_scholarship)
        await db.commit()

        config = _make_config(
            phd_scholarship.id,
            quotas={"nstc": {"E": 5, "C": 3}, "moe_1w": {"E": 2, "C": 1}},
        )
        db.add(config)
        await db.commit()

        response = await client.get(
            "/api/v1/scholarship-configurations/available-semesters?quota_management_mode=matrix_based",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) > 0

    @pytest.mark.asyncio
    async def test_regular_admin_with_permission_can_access(
        self, client: AsyncClient, admin_db_user: User, db: AsyncSession
    ):
        """Regular admin with scholarship permissions should have access"""
        _auth_as(admin_db_user)

        phd_scholarship = ScholarshipType(code="phd", name="博士生獎學金", status="active")
        db.add(phd_scholarship)
        await db.commit()

        permission = AdminScholarship(admin_id=admin_db_user.id, scholarship_id=phd_scholarship.id)
        db.add(permission)
        await db.commit()

        response = await client.get("/api/v1/scholarship-configurations/available-semesters")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_admin_without_permission_denied(self, client: AsyncClient, admin_db_user: User):
        """Regular admin without permissions sees no accessible scholarships"""
        _auth_as(admin_db_user)

        response = await client.get("/api/v1/scholarship-configurations/available-semesters")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 0  # No accessible scholarships


class TestMatrixQuotaOperations:
    """Test matrix quota CRUD operations"""

    @pytest.mark.asyncio
    async def test_get_matrix_quota_status_success(
        self,
        client: AsyncClient,
        super_admin_user: User,
        db: AsyncSession,
    ):
        """Test successful retrieval of matrix quota status"""
        _auth_as(super_admin_user)

        phd_scholarship = ScholarshipType(
            code="phd",
            name="博士生獎學金",
            status="active",
            sub_type_list=["nstc", "moe_1w", "moe_2w"],
        )
        db.add(phd_scholarship)
        await db.commit()

        config = _make_config(
            phd_scholarship.id,
            quotas={
                "nstc": {"E": 5, "C": 3, "I": 2},
                "moe_1w": {"E": 2, "C": 1, "I": 1},
            },
        )
        db.add(config)
        await db.commit()

        response = await client.get("/api/v1/scholarship-configurations/matrix-quota-status/113")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        quota_data = data["data"]
        assert quota_data["academic_year"] == "113"
        assert quota_data["period_type"] == "academic_year"
        assert "phd_quotas" in quota_data
        assert "nstc" in quota_data["phd_quotas"]
        assert "E" in quota_data["phd_quotas"]["nstc"]
        assert quota_data["phd_quotas"]["nstc"]["E"]["total_quota"] == 5

    @pytest.mark.asyncio
    async def test_update_matrix_quota_success(
        self,
        client: AsyncClient,
        super_admin_user: User,
        db: AsyncSession,
    ):
        """Test successful quota update"""
        _auth_as(super_admin_user)

        phd_scholarship = ScholarshipType(
            code="phd",
            name="博士生獎學金",
            status="active",
            sub_type_list=["nstc", "moe_1w"],
        )
        db.add(phd_scholarship)
        await db.commit()

        config = _make_config(
            phd_scholarship.id,
            quotas={"nstc": {"E": 5, "C": 3}, "moe_1w": {"E": 2, "C": 1}},
            total_quota=11,
        )
        db.add(config)
        await db.commit()

        response = await client.put(
            "/api/v1/scholarship-configurations/matrix-quota",
            json={
                "sub_type": "nstc",
                "college": "E",
                "new_quota": 8,
                "academic_year": 113,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["old_quota"] == 5
        assert data["data"]["new_quota"] == 8

    @pytest.mark.asyncio
    async def test_update_matrix_quota_negative_value_rejected(
        self,
        client: AsyncClient,
        super_admin_user: User,
        db: AsyncSession,
    ):
        """Test that negative quota values are rejected"""
        _auth_as(super_admin_user)

        response = await client.put(
            "/api/v1/scholarship-configurations/matrix-quota",
            json={
                "sub_type": "nstc",
                "college": "E",
                "new_quota": -1,
                "academic_year": 113,
            },
        )

        assert response.status_code == 400
        data = response.json()
        # Endpoint returns the Chinese message "配額不能為負數".
        assert "配額不能為負數" in data["message"]


class TestQuotaUsageCalculation:
    """Test quota usage calculation from applications"""

    @pytest.mark.asyncio
    async def test_quota_usage_calculation_accuracy(
        self,
        client: AsyncClient,
        super_admin_user: User,
        db: AsyncSession,
    ):
        """Test that quota usage is calculated correctly from applications"""
        _auth_as(super_admin_user)

        phd_scholarship = ScholarshipType(
            code="phd",
            name="博士生獎學金",
            status="active",
            sub_type_list=["nstc"],
        )
        db.add(phd_scholarship)
        await db.commit()

        config = _make_config(
            phd_scholarship.id,
            quotas={"nstc": {"E": 5, "C": 3}},
        )
        db.add(config)
        await db.commit()

        # Applicants need real Users (Application.user_id FK). College comes from
        # student_data['std_academyno']; usage counts quota_allocation_status='allocated'.
        applicant_e = User(
            nycu_id="applicant_e",
            name="Applicant E",
            email="applicant_e@university.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        applicant_c = User(
            nycu_id="applicant_c",
            name="Applicant C",
            email="applicant_c@university.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add_all([applicant_e, applicant_c])
        await db.commit()
        await db.refresh(applicant_e)
        await db.refresh(applicant_c)

        # 2 allocated apps for college E, 1 for college C.
        app1 = _make_application(phd_scholarship.id, applicant_e.id, "E", app_id="APP-113-0-00001")
        app2 = _make_application(phd_scholarship.id, applicant_e.id, "E", app_id="APP-113-0-00002")
        app3 = _make_application(phd_scholarship.id, applicant_c.id, "C", app_id="APP-113-0-00003")
        db.add_all([app1, app2, app3])
        await db.commit()

        response = await client.get("/api/v1/scholarship-configurations/matrix-quota-status/113")

        assert response.status_code == 200
        data = response.json()
        quota_data = data["data"]

        assert quota_data["phd_quotas"]["nstc"]["E"]["used"] == 2  # 2 allocated apps for college E
        assert quota_data["phd_quotas"]["nstc"]["C"]["used"] == 1  # 1 allocated app for college C
        assert quota_data["phd_quotas"]["nstc"]["E"]["available"] == 3  # 5 - 2 = 3
        assert quota_data["phd_quotas"]["nstc"]["C"]["available"] == 2  # 3 - 1 = 2


class TestPeriodFiltering:
    """Test academic period filtering functionality"""

    @pytest.mark.asyncio
    async def test_matrix_based_filtering_shows_only_academic_years(
        self,
        client: AsyncClient,
        super_admin_user: User,
        db: AsyncSession,
    ):
        """Test that matrix-based scholarships only show academic years, not semesters"""
        _auth_as(super_admin_user)

        phd_scholarship = ScholarshipType(code="phd", name="博士生獎學金", status="active")
        db.add(phd_scholarship)

        undergrad_scholarship = ScholarshipType(
            code="undergraduate_freshman",
            name="大學部新生獎學金",
            status="active",
        )
        db.add(undergrad_scholarship)
        await db.commit()

        # PhD config - yearly, matrix-based
        phd_config = _make_config(
            phd_scholarship.id,
            semester=None,
            quota_management_mode=QuotaManagementMode.matrix_based,
        )

        # Undergrad config - semester-based, not matrix
        undergrad_config = _make_config(
            undergrad_scholarship.id,
            semester=Semester.first,
            quota_management_mode=QuotaManagementMode.simple,
        )

        db.add_all([phd_config, undergrad_config])
        await db.commit()

        response = await client.get(
            "/api/v1/scholarship-configurations/available-semesters?quota_management_mode=matrix_based",
        )

        assert response.status_code == 200
        data = response.json()
        periods = data["data"]

        # Should only return academic year "113", not "113-1"
        assert "113" in periods
        assert "113-1" not in periods
        assert all("-" not in period for period in periods)  # No semester periods


class TestCollegeMappings:
    """Test centralized college mapping functionality"""

    def test_college_mappings_completeness(self):
        """Test that all college codes have proper mappings"""
        colleges = get_all_colleges()

        expected_codes = [
            "E",
            "C",
            "I",
            "S",
            "B",
            "O",
            "D",
            "1",
            "6",
            "7",
            "M",
            "A",
            "K",
        ]
        actual_codes = [c["code"] for c in colleges]

        for code in expected_codes:
            assert code in actual_codes
            assert is_valid_college_code(code)

    def test_college_mapping_consistency(self):
        """Test that mappings are consistent between backend and frontend expectations"""
        from app.core.college_mappings import COLLEGE_MAPPINGS as BACKEND_MAPPINGS

        assert BACKEND_MAPPINGS["E"] == "電機學院"
        assert BACKEND_MAPPINGS["C"] == "資訊學院"
        assert BACKEND_MAPPINGS["I"] == "工學院"


class TestAPIResponseFormat:
    """Test API response format consistency"""

    @pytest.mark.asyncio
    async def test_api_response_format_consistency(self, client: AsyncClient, super_admin_user: User):
        """Test that all quota API endpoints return consistent response format"""
        _auth_as(super_admin_user)

        endpoints_to_test = [
            "/api/v1/scholarship-configurations/available-semesters",
            "/api/v1/scholarship-configurations/colleges",
            "/api/v1/scholarship-configurations/scholarship-types",
        ]

        for endpoint in endpoints_to_test:
            response = await client.get(endpoint)

            assert response.status_code == 200
            data = response.json()

            assert "success" in data
            assert "message" in data
            assert "data" in data
            assert isinstance(data["success"], bool)
            assert isinstance(data["message"], str)
