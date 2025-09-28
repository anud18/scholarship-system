"""
Tests for quota management functionality
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base_class import Base

from app.core.college_mappings import get_all_colleges, is_valid_college_code
from app.models.application import Application, ApplicationStatus

# Student model removed - student data from external API
from app.models.enums import QuotaManagementMode, Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import AdminScholarship, User


class Student(Base):  # pragma: no cover - lightweight model for tests only
    """Minimal student model used by quota management tests."""

    __tablename__ = "test_students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(20), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    dept_code = Column(String(10), nullable=False)
    year = Column(Integer, nullable=False)


class TestQuotaManagementPermissions:
    """Test permission-based access to quota management"""

    @pytest.mark.asyncio
    async def test_super_admin_can_access_quota_endpoints(
        self,
        async_client: AsyncClient,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        """Super admin should have full access to quota management"""
        # Create PhD scholarship configuration
        phd_scholarship = ScholarshipType(code="phd", name="博士生獎學金", category="doctoral", status="active")
        db_session.add(phd_scholarship)
        await db_session.commit()

        config = ScholarshipConfiguration(
            scholarship_type_id=phd_scholarship.id,
            academic_year=113,
            semester=None,
            quota_management_mode=QuotaManagementMode.matrix_based,
            is_active=True,
            quotas={"nstc": {"E": 5, "C": 3}, "moe_1w": {"E": 2, "C": 1}},
        )
        db_session.add(config)
        await db_session.commit()

        # Test available semesters endpoint
        response = await async_client.get(
            "/api/v1/scholarship-configurations/available-semesters?quota_management_mode=matrix_based",
            headers={"Authorization": f"Bearer {super_admin_user.token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) > 0

    @pytest.mark.asyncio
    async def test_regular_admin_with_permission_can_access(
        self, async_client: AsyncClient, admin_user: User, db_session: AsyncSession
    ):
        """Regular admin with scholarship permissions should have access"""
        # Create PhD scholarship
        phd_scholarship = ScholarshipType(code="phd", name="博士生獎學金", category="doctoral", status="active")
        db_session.add(phd_scholarship)
        await db_session.commit()

        # Grant permission to admin
        permission = AdminScholarship(admin_id=admin_user.id, scholarship_id=phd_scholarship.id)
        db_session.add(permission)
        await db_session.commit()

        response = await async_client.get(
            "/api/v1/scholarship-configurations/available-semesters",
            headers={"Authorization": f"Bearer {admin_user.token}"},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_regular_admin_without_permission_denied(self, async_client: AsyncClient, admin_user: User):
        """Regular admin without permissions should be denied"""
        response = await async_client.get(
            "/api/v1/scholarship-configurations/available-semesters",
            headers={"Authorization": f"Bearer {admin_user.token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) == 0  # No accessible scholarships


class TestMatrixQuotaOperations:
    """Test matrix quota CRUD operations"""

    @pytest.mark.asyncio
    async def test_get_matrix_quota_status_success(
        self,
        async_client: AsyncClient,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        """Test successful retrieval of matrix quota status"""
        # Setup PhD scholarship with matrix configuration
        phd_scholarship = ScholarshipType(
            code="phd",
            name="博士生獎學金",
            category="doctoral",
            status="active",
            sub_type_list=["nstc", "moe_1w", "moe_2w"],
        )
        db_session.add(phd_scholarship)
        await db_session.commit()

        config = ScholarshipConfiguration(
            scholarship_type_id=phd_scholarship.id,
            academic_year=113,
            semester=None,
            quota_management_mode=QuotaManagementMode.matrix_based,
            is_active=True,
            quotas={
                "nstc": {"E": 5, "C": 3, "I": 2},
                "moe_1w": {"E": 2, "C": 1, "I": 1},
            },
        )
        db_session.add(config)
        await db_session.commit()

        response = await async_client.get(
            "/api/v1/scholarship-configurations/matrix-quota-status/113",
            headers={"Authorization": f"Bearer {super_admin_user.token}"},
        )

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
        async_client: AsyncClient,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        """Test successful quota update"""
        # Setup PhD scholarship
        phd_scholarship = ScholarshipType(
            code="phd",
            name="博士生獎學金",
            category="doctoral",
            status="active",
            sub_type_list=["nstc", "moe_1w"],
        )
        db_session.add(phd_scholarship)
        await db_session.commit()

        config = ScholarshipConfiguration(
            scholarship_type_id=phd_scholarship.id,
            academic_year=113,
            semester=None,
            quota_management_mode=QuotaManagementMode.matrix_based,
            is_active=True,
            quotas={"nstc": {"E": 5, "C": 3}, "moe_1w": {"E": 2, "C": 1}},
            total_quota=11,
        )
        db_session.add(config)
        await db_session.commit()

        # Update quota
        response = await async_client.put(
            "/api/v1/scholarship-configurations/matrix-quota",
            json={
                "sub_type": "nstc",
                "college": "E",
                "new_quota": 8,
                "academic_year": 113,
            },
            headers={"Authorization": f"Bearer {super_admin_user.token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["old_quota"] == 5
        assert data["data"]["new_quota"] == 8

    @pytest.mark.asyncio
    async def test_update_matrix_quota_negative_value_rejected(
        self,
        async_client: AsyncClient,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        """Test that negative quota values are rejected"""
        response = await async_client.put(
            "/api/v1/scholarship-configurations/matrix-quota",
            json={
                "sub_type": "nstc",
                "college": "E",
                "new_quota": -1,
                "academic_year": 113,
            },
            headers={"Authorization": f"Bearer {super_admin_user.token}"},
        )

        assert response.status_code == 400
        data = response.json()
        assert "Quota cannot be negative" in data["detail"]


class TestQuotaUsageCalculation:
    """Test quota usage calculation from applications"""

    @pytest.mark.asyncio
    async def test_quota_usage_calculation_accuracy(
        self,
        async_client: AsyncClient,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        """Test that quota usage is calculated correctly from applications"""
        # Setup scholarship and student
        phd_scholarship = ScholarshipType(
            code="phd",
            name="博士生獎學金",
            category="doctoral",
            status="active",
            sub_type_list=["nstc"],
        )
        db_session.add(phd_scholarship)
        await db_session.commit()

        config = ScholarshipConfiguration(
            scholarship_type_id=phd_scholarship.id,
            academic_year=113,
            semester=None,
            quota_management_mode=QuotaManagementMode.matrix_based,
            is_active=True,
            quotas={"nstc": {"E": 5, "C": 3}},
        )
        db_session.add(config)
        await db_session.commit()

        # Create students in different colleges
        student_e = Student(student_id="110001001", name="Test Student E", dept_code="E", year=3)
        student_c = Student(student_id="110001002", name="Test Student C", dept_code="C", year=3)
        db_session.add_all([student_e, student_c])
        await db_session.commit()

        # Create approved applications
        app1 = Application(
            scholarship_type_id=phd_scholarship.id,
            student_id=student_e.id,
            academic_year=113,
            status=ApplicationStatus.APPROVED,
        )
        app2 = Application(
            scholarship_type_id=phd_scholarship.id,
            student_id=student_e.id,
            academic_year=113,
            status=ApplicationStatus.APPROVED,
        )
        app3 = Application(
            scholarship_type_id=phd_scholarship.id,
            student_id=student_c.id,
            academic_year=113,
            status=ApplicationStatus.APPROVED,
        )
        db_session.add_all([app1, app2, app3])
        await db_session.commit()

        # Get quota status
        response = await async_client.get(
            "/api/v1/scholarship-configurations/matrix-quota-status/113",
            headers={"Authorization": f"Bearer {super_admin_user.token}"},
        )

        assert response.status_code == 200
        data = response.json()
        quota_data = data["data"]

        # Check usage calculation
        assert quota_data["phd_quotas"]["nstc"]["E"]["used"] == 2  # 2 approved apps for college E
        assert quota_data["phd_quotas"]["nstc"]["C"]["used"] == 1  # 1 approved app for college C
        assert quota_data["phd_quotas"]["nstc"]["E"]["available"] == 3  # 5 - 2 = 3
        assert quota_data["phd_quotas"]["nstc"]["C"]["available"] == 2  # 3 - 1 = 2


class TestPeriodFiltering:
    """Test academic period filtering functionality"""

    @pytest.mark.asyncio
    async def test_matrix_based_filtering_shows_only_academic_years(
        self,
        async_client: AsyncClient,
        super_admin_user: User,
        db_session: AsyncSession,
    ):
        """Test that matrix-based scholarships only show academic years, not semesters"""

        # Create PhD scholarship (yearly, matrix-based)
        phd_scholarship = ScholarshipType(code="phd", name="博士生獎學金", category="doctoral", status="active")
        db_session.add(phd_scholarship)

        # Create undergraduate scholarship (semester-based, not matrix)
        undergrad_scholarship = ScholarshipType(
            code="undergraduate_freshman",
            name="大學部新生獎學金",
            category="undergraduate",
            status="active",
        )
        db_session.add(undergrad_scholarship)
        await db_session.commit()

        # PhD config - yearly, matrix-based
        phd_config = ScholarshipConfiguration(
            scholarship_type_id=phd_scholarship.id,
            academic_year=113,
            semester=None,  # No semester for yearly scholarships
            quota_management_mode=QuotaManagementMode.matrix_based,
            is_active=True,
        )

        # Undergrad config - semester-based, not matrix
        undergrad_config = ScholarshipConfiguration(
            scholarship_type_id=undergrad_scholarship.id,
            academic_year=113,
            semester=Semester.first,  # Has semester
            quota_management_mode=QuotaManagementMode.simple,
            is_active=True,
        )

        db_session.add_all([phd_config, undergrad_config])
        await db_session.commit()

        # Test matrix_based filtering
        response = await async_client.get(
            "/api/v1/scholarship-configurations/available-semesters?quota_management_mode=matrix_based",
            headers={"Authorization": f"Bearer {super_admin_user.token}"},
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

        # Check that we have all expected colleges
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

        # Test some key mappings
        assert BACKEND_MAPPINGS["E"] == "電機學院"
        assert BACKEND_MAPPINGS["C"] == "資訊學院"
        assert BACKEND_MAPPINGS["I"] == "工學院"


class TestAPIResponseFormat:
    """Test API response format consistency"""

    @pytest.mark.asyncio
    async def test_api_response_format_consistency(self, async_client: AsyncClient, super_admin_user: User):
        """Test that all quota API endpoints return consistent response format"""

        endpoints_to_test = [
            "/api/v1/scholarship-configurations/available-semesters",
            "/api/v1/scholarship-configurations/colleges",
            "/api/v1/scholarship-configurations/scholarship-types",
        ]

        for endpoint in endpoints_to_test:
            response = await async_client.get(endpoint, headers={"Authorization": f"Bearer {super_admin_user.token}"})

            assert response.status_code == 200
            data = response.json()

            # Check standard ApiResponse format
            assert "success" in data
            assert "message" in data
            assert "data" in data
            assert isinstance(data["success"], bool)
            assert isinstance(data["message"], str)


# Fixtures for test setup would be defined here or in conftest.py
# These are referenced but implementation depends on your existing test setup
