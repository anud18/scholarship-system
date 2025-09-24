"""
Integration tests for ApplicationService
Target: Increase coverage from 12% to 70%
Focus: Real execution, test actual methods
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole
from app.services.application_service import (
    ApplicationService,
    get_student_data_from_user,
)


class TestApplicationServiceHelpers:
    """Test helper methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_serialize_for_json_decimal(self, service):
        """Test Decimal serialization"""
        result = service._serialize_for_json(Decimal("3.14"))
        assert result == 3.14
        assert isinstance(result, float)

    def test_serialize_for_json_datetime(self, service):
        """Test datetime serialization"""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = service._serialize_for_json(dt)
        assert "2024-01-01" in result
        assert isinstance(result, str)

    def test_serialize_for_json_list(self, service):
        """Test list serialization"""
        data = [Decimal("3.14"), Decimal("2.71")]
        result = service._serialize_for_json(data)
        assert result == [3.14, 2.71]

    def test_serialize_for_json_dict(self, service):
        """Test dict serialization"""
        data = {
            "gpa": Decimal("3.5"),
            "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }
        result = service._serialize_for_json(data)
        assert result["gpa"] == 3.5
        assert isinstance(result["timestamp"], str)

    def test_serialize_for_json_primitive(self, service):
        """Test primitive value passthrough"""
        assert service._serialize_for_json("test") == "test"
        assert service._serialize_for_json(123) == 123
        assert service._serialize_for_json(None) is None

    def test_get_student_id_from_user(self, service):
        """Test getting student ID from user"""
        user = Mock(spec=User)
        user.nycu_id = "112550001"

        result = service._get_student_id_from_user(user)
        assert result == "112550001"

    def test_get_student_id_from_user_none(self, service):
        """Test getting student ID with None user"""
        result = service._get_student_id_from_user(None)
        assert result is None

    def test_get_student_id_from_user_no_nycu_id(self, service):
        """Test getting student ID with no nycu_id"""
        user = Mock(spec=User)
        user.nycu_id = None

        result = service._get_student_id_from_user(user)
        assert result is None

    def test_convert_semester_to_string_first(self, service):
        """Test semester conversion for first semester"""
        result = service._convert_semester_to_string(Semester.FIRST)
        assert result == "first"

    def test_convert_semester_to_string_second(self, service):
        """Test semester conversion for second semester"""
        result = service._convert_semester_to_string(Semester.SECOND)
        assert result == "second"

    def test_convert_semester_to_string_none(self, service):
        """Test semester conversion for None"""
        result = service._convert_semester_to_string(None)
        assert result is None

    def test_generate_app_id(self, service):
        """Test app ID generation"""
        app_id = service._generate_app_id()
        assert isinstance(app_id, str)
        assert len(app_id) > 0
        assert app_id.startswith("APP")


@pytest.mark.asyncio
class TestGetStudentDataFromUser:
    """Test standalone get_student_data_from_user function"""

    async def test_get_student_data_student_role(self):
        """Test getting student data for student role"""
        user = Mock(spec=User)
        user.role = UserRole.STUDENT
        user.nycu_id = "112550001"

        with patch("app.services.application_service.StudentService") as mock_service:
            mock_instance = AsyncMock()
            mock_service.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = {
                "student_id": "112550001"
            }

            result = await get_student_data_from_user(user)
            assert result == {"student_id": "112550001"}

    async def test_get_student_data_non_student(self):
        """Test getting student data for non-student role"""
        user = Mock(spec=User)
        user.role = UserRole.ADMIN
        user.nycu_id = "admin001"

        result = await get_student_data_from_user(user)
        assert result is None

    async def test_get_student_data_no_nycu_id(self):
        """Test getting student data with no nycu_id"""
        user = Mock(spec=User)
        user.role = UserRole.STUDENT
        user.nycu_id = None

        result = await get_student_data_from_user(user)
        assert result is None


@pytest.mark.asyncio
class TestApplicationServiceIntegration:
    """Test application integration methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_integrate_application_file_data_basic(self, service):
        """Test file data integration"""
        application = Mock(spec=Application)
        application.submitted_form_data = {"name": "Test"}
        application.documents = {}
        application.app_id = "APP001"

        user = Mock(spec=User)

        result = service._integrate_application_file_data(application, user)
        assert result["name"] == "Test"

    def test_integrate_application_file_data_with_documents(self, service):
        """Test file data integration with documents"""
        application = Mock(spec=Application)
        application.submitted_form_data = {"name": "Test"}
        application.documents = {"transcript": "path/to/file.pdf"}
        application.app_id = "APP001"

        user = Mock(spec=User)

        result = service._integrate_application_file_data(application, user)
        assert "documents" in result


@pytest.mark.asyncio
class TestApplicationServiceDashboard:
    """Test dashboard methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    async def test_get_student_dashboard_stats(self, service):
        """Test getting student dashboard stats"""
        user = Mock(spec=User)
        user.id = 1
        user.nycu_id = "112550001"

        # Mock database queries
        mock_result = Mock()
        mock_result.scalar.return_value = 0
        mock_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=mock_result)

        stats = await service.get_student_dashboard_stats(user)

        assert "total_applications" in stats
        assert "draft_count" in stats
        assert "submitted_count" in stats
        assert "approved_count" in stats


@pytest.mark.asyncio
class TestApplicationServiceListResponse:
    """Test list response creation"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_create_application_list_response(self, service):
        """Test creating application list response"""
        application = Mock(spec=Application)
        application.id = 1
        application.app_id = "APP001"
        application.user_id = 1
        application.scholarship_type_id = 1
        application.scholarship_subtype_list = ["type_a"]
        application.status = ApplicationStatus.DRAFT.value
        application.status_name = "草稿"
        application.is_renewal = False
        application.academic_year = 113
        application.semester = Semester.FIRST
        application.created_at = datetime.now(timezone.utc)
        application.submitted_at = None
        application.approved_at = None

        user = Mock(spec=User)
        user.nycu_id = "112550001"

        integrated_data = {"name": "Test"}

        response = service._create_application_list_response(
            application, user, integrated_data
        )

        assert response.app_id == "APP001"
        assert response.status == ApplicationStatus.DRAFT.value


@pytest.mark.asyncio
class TestApplicationServiceZhTranslation:
    """Test Chinese translation methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_add_scholarship_type_zh(self, service):
        """Test adding Chinese scholarship type"""
        from app.schemas.application import ApplicationListResponse

        app_data = Mock(spec=ApplicationListResponse)
        app_data.scholarship_type_id = 1
        app_data.scholarship_type_zh = None
        app_data.scholarship_subtype_list = []

        result = service._add_scholarship_type_zh(app_data)
        assert result is not None
