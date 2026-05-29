"""
Unit tests for ApplicationService
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole
from app.schemas.application import ApplicationCreate, ApplicationFormData, ApplicationUpdate
from app.services.application_service import ApplicationService


class TestApplicationService:
    """Test cases for ApplicationService"""

    @pytest.fixture
    def service(self, db: AsyncSession):
        """Create ApplicationService instance for testing"""
        return ApplicationService(db)

    @pytest.fixture
    def mock_application_data(self):
        """Mock application data for testing"""
        return ApplicationCreate(
            scholarship_type="undergraduate_freshman",
            configuration_id=1,
            scholarship_subtype_list=[],
            is_renewal=False,
            form_data=ApplicationFormData(fields={}),
            agree_terms=True,
        )

    @pytest.fixture
    def mock_scholarship_type(self):
        """Mock scholarship type for testing"""
        mock = Mock()
        mock.id = 1
        mock.code = "undergraduate_freshman"
        mock.name = "Undergraduate Freshman Scholarship"
        mock.is_active = True
        mock.is_application_period = True
        mock.whitelist_enabled = False
        mock.eligible_student_types = []
        return mock

    @pytest.fixture
    def mock_student(self):
        """Mock student for testing"""
        student = Mock()
        student.id = 1
        student.std_stdcode = "112550001"
        student.get_student_type.return_value = "undergraduate"
        return student

    def test_serialize_for_json(self, service):
        """Test JSON serialization helper method"""
        # Test Decimal
        result = service._serialize_for_json(Decimal("10.5"))
        assert result == 10.5
        assert isinstance(result, float)

        # Test datetime
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = service._serialize_for_json(dt)
        assert result == dt.isoformat()

        # Test list
        data = [Decimal("5.0"), datetime(2024, 1, 1)]
        result = service._serialize_for_json(data)
        assert len(result) == 2
        assert result[0] == 5.0
        assert isinstance(result[1], str)

        # Test dict
        data = {"amount": Decimal("100.0"), "date": datetime(2024, 1, 1)}
        result = service._serialize_for_json(data)
        assert result["amount"] == 100.0
        assert isinstance(result["date"], str)

        # Test other types
        assert service._serialize_for_json("string") == "string"
        assert service._serialize_for_json(42) == 42

    @pytest.mark.asyncio
    async def test_validate_student_eligibility_success(
        self, service, mock_student, mock_scholarship_type, mock_application_data
    ):
        """Test successful student eligibility validation"""
        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_scholarship_type
            mock_execute.return_value = mock_result

            # Should not raise any exception
            await service._validate_student_eligibility(mock_student, "undergraduate_freshman", mock_application_data)

    @pytest.mark.asyncio
    async def test_validate_student_eligibility_scholarship_not_found(
        self, service, mock_student, mock_application_data
    ):
        """Test eligibility validation when scholarship type not found"""
        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_result

            with pytest.raises(NotFoundError, match="Scholarship type"):
                await service._validate_student_eligibility(mock_student, "invalid_scholarship", mock_application_data)

    @pytest.mark.asyncio
    async def test_validate_student_eligibility_inactive_scholarship(
        self, service, mock_student, mock_scholarship_type, mock_application_data
    ):
        """Test eligibility validation when scholarship is inactive"""
        mock_scholarship_type.is_active = False

        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_scholarship_type
            mock_execute.return_value = mock_result

            with pytest.raises(ValidationError, match="Scholarship type is not active"):
                await service._validate_student_eligibility(
                    mock_student, "undergraduate_freshman", mock_application_data
                )

    @pytest.mark.asyncio
    async def test_validate_student_eligibility_application_period_ended(
        self, service, mock_student, mock_scholarship_type, mock_application_data
    ):
        """Test eligibility validation when application period has ended"""
        mock_scholarship_type.is_application_period = False

        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_scholarship_type
            mock_execute.return_value = mock_result

            with pytest.raises(ValidationError, match="Application period has ended"):
                await service._validate_student_eligibility(
                    mock_student, "undergraduate_freshman", mock_application_data
                )

    @pytest.mark.asyncio
    async def test_validate_student_eligibility_student_type_not_eligible(
        self, service, mock_student, mock_scholarship_type, mock_application_data
    ):
        """Test eligibility validation when student type is not eligible"""
        mock_scholarship_type.eligible_student_types = ["graduate"]  # Only graduate students eligible

        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_scholarship_type
            mock_execute.return_value = mock_result

            with pytest.raises(ValidationError, match="Student type undergraduate is not eligible"):
                await service._validate_student_eligibility(
                    mock_student, "undergraduate_freshman", mock_application_data
                )

    @pytest.mark.asyncio
    @pytest.mark.smoke
    async def test_create_application_draft(self, service, mock_application_data):
        """Test creating a draft application"""
        mock_scholarship = Mock(spec=ScholarshipType)
        mock_scholarship.id = 1
        mock_scholarship.sub_type_selection_mode = None
        mock_scholarship.name = "Test Scholarship"

        mock_config = Mock()
        mock_config.id = 1
        mock_config.academic_year = 113
        mock_config.semester = "first"
        mock_config.config_name = "Test Config"
        mock_config.amount = 50000

        mock_user_obj = Mock()
        mock_user_obj.id = 1

        mock_draft_app = Mock(spec=Application)
        mock_draft_app.id = 1
        mock_draft_app.app_id = "APP-113-1-00001"
        mock_draft_app.status = ApplicationStatus.draft.value
        mock_draft_app.status_name = "草稿"
        mock_draft_app.submitted_at = None
        mock_draft_app.files = []
        mock_draft_app.reviews = []
        mock_draft_app.scholarship = mock_scholarship
        mock_draft_app.submitted_form_data = {}
        mock_draft_app.user_id = 1

        with (
            patch.object(service, "_get_scholarship_and_config", new_callable=AsyncMock) as mock_get_sc,
            patch.object(service, "_get_user_and_student_data", new_callable=AsyncMock) as mock_get_user,
            patch("app.services.application_service.EligibilityService") as mock_elig_cls,
            patch.object(service, "_create_application_instance", new_callable=AsyncMock) as mock_create_inst,
            patch.object(service, "_clone_user_profile_documents", new_callable=AsyncMock),
            patch.object(service, "_build_application_response", new_callable=AsyncMock) as mock_build_resp,
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "commit", new_callable=AsyncMock),
            patch.object(service.db, "refresh", new_callable=AsyncMock),
            patch.object(service.db, "execute", new_callable=AsyncMock) as mock_execute,
        ):
            mock_get_sc.return_value = (mock_scholarship, mock_config)
            mock_get_user.return_value = (mock_user_obj, {})

            mock_elig_instance = AsyncMock()
            mock_elig_cls.return_value = mock_elig_instance
            mock_elig_instance.check_student_eligibility.return_value = (True, [])

            mock_create_inst.return_value = mock_draft_app
            mock_build_resp.return_value = mock_draft_app

            mock_exec_result = Mock()
            mock_exec_result.scalar_one.return_value = mock_draft_app
            mock_execute.return_value = mock_exec_result

            result = await service.create_application(
                user_id=1,
                student_code="112550001",
                application_data=mock_application_data,
                is_draft=True,
            )

            mock_add.assert_called_once()
            added_application = mock_add.call_args[0][0]
            assert added_application.status == ApplicationStatus.draft.value
            assert added_application.status_name == "草稿"
            assert added_application.submitted_at is None

            assert result == mock_draft_app

    @pytest.mark.asyncio
    @pytest.mark.smoke
    async def test_create_application_submitted(self, service, mock_application_data):
        """Test creating a submitted application"""
        mock_scholarship = Mock(spec=ScholarshipType)
        mock_scholarship.id = 1
        mock_scholarship.sub_type_selection_mode = None
        mock_scholarship.name = "Test Scholarship"

        mock_config = Mock()
        mock_config.id = 1
        mock_config.academic_year = 113
        mock_config.semester = "first"
        mock_config.config_name = "Test Config"
        mock_config.amount = 50000

        mock_user_obj = Mock()
        mock_user_obj.id = 1

        mock_submitted_app = Mock(spec=Application)
        mock_submitted_app.id = 1
        mock_submitted_app.app_id = "APP-113-1-00001"
        mock_submitted_app.status = ApplicationStatus.submitted.value
        mock_submitted_app.status_name = "已提交"
        mock_submitted_app.submitted_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        mock_submitted_app.files = []
        mock_submitted_app.reviews = []
        mock_submitted_app.scholarship = mock_scholarship
        mock_submitted_app.submitted_form_data = {}
        mock_submitted_app.student_data = {}
        mock_submitted_app.user_id = 1

        with (
            patch.object(service, "_get_scholarship_and_config", new_callable=AsyncMock) as mock_get_sc,
            patch.object(service, "_get_user_and_student_data", new_callable=AsyncMock) as mock_get_user,
            patch("app.services.application_service.EligibilityService") as mock_elig_cls,
            patch.object(service, "_create_application_instance", new_callable=AsyncMock) as mock_create_inst,
            patch.object(service, "_clone_user_profile_documents", new_callable=AsyncMock),
            patch.object(service, "_build_application_response", new_callable=AsyncMock) as mock_build_resp,
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "commit", new_callable=AsyncMock),
            patch.object(service.db, "refresh", new_callable=AsyncMock),
            patch.object(service.db, "execute", new_callable=AsyncMock) as mock_execute,
        ):
            mock_get_sc.return_value = (mock_scholarship, mock_config)
            mock_get_user.return_value = (mock_user_obj, {})

            mock_elig_instance = AsyncMock()
            mock_elig_cls.return_value = mock_elig_instance
            mock_elig_instance.check_student_eligibility.return_value = (True, [])

            mock_create_inst.return_value = mock_submitted_app
            mock_build_resp.return_value = mock_submitted_app

            mock_exec_result = Mock()
            mock_exec_result.scalar_one.return_value = mock_submitted_app
            mock_exec_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_exec_result

            result = await service.create_application(
                user_id=1,
                student_code="112550001",
                application_data=mock_application_data,
                is_draft=False,
            )

            mock_add.assert_called_once()
            added_application = mock_add.call_args[0][0]
            assert added_application.status == ApplicationStatus.submitted.value
            assert added_application.status_name == "已提交"
            assert added_application.submitted_at is not None

            assert result == mock_submitted_app

    @pytest.mark.asyncio
    async def test_get_application_by_id_student_access(self, service):
        """Test getting application by ID with student access control"""
        application_id = 1
        user_id = 1

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock()
        mock_application.id = application_id
        mock_application.user_id = user_id
        mock_application.app_id = "APP-2024-001"
        mock_application.scholarship_type_id = 1
        mock_application.scholarship_subtype_list = []
        mock_application.sub_scholarship_type = None
        mock_application.status = ApplicationStatus.draft.value
        mock_application.status_name = "草稿"
        mock_application.review_stage = None
        mock_application.is_renewal = False
        mock_application.renewal_year = None
        mock_application.previous_application_id = None
        mock_application.challenges_application_id = None
        mock_application.cancelled_due_to_application_id = None
        mock_application.academic_year = 2024
        mock_application.semester = "first"
        mock_application.student_data = {}
        mock_application.submitted_form_data = {}
        mock_application.files = []
        mock_application.reviews = []
        mock_application.agree_terms = True
        mock_application.professor_id = None
        mock_application.reviewer_id = None
        mock_application.final_approver_id = None
        mock_application.submitted_at = None
        mock_application.reviewed_at = None
        mock_application.approved_at = None
        mock_application.created_at = datetime.now(timezone.utc)
        mock_application.updated_at = datetime.now(timezone.utc)
        mock_application.meta_data = None
        mock_application.application_document_url = None
        mock_application.application_document_original_filename = None
        mock_application.amount = None
        mock_application.scholarship_configuration = None
        mock_application.scholarship = None
        mock_application.student = None

        with patch.object(service, "_get_application_model", new_callable=AsyncMock) as mock_get_model:
            mock_get_model.return_value = mock_application

            result = await service.get_application_by_id(application_id, mock_user)

            assert result is not None
            assert result.app_id == "APP-2024-001"
            mock_get_model.assert_called_once_with(application_id, mock_user)

    @pytest.mark.asyncio
    async def test_get_application_by_id_student_unauthorized(self, service):
        """Test getting application by ID when student doesn't own application"""
        application_id = 1
        user_id = 1
        other_user_id = 2

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = other_user_id  # Different user owns this application

        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_application
            mock_execute.return_value = mock_result

            result = await service.get_application_by_id(application_id, mock_user)

            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.smoke
    async def test_get_application_by_id_admin_access(self, service):
        """Test getting application by ID with admin access"""
        application_id = 1
        other_user_id = 2

        mock_user = Mock(spec=User)
        mock_user.id = 1
        mock_user.role = UserRole.admin

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = other_user_id
        mock_application.app_id = "APP-2024-001"
        mock_application.scholarship_type_id = 1
        mock_application.status = ApplicationStatus.draft.value
        mock_application.status_name = "草稿"
        mock_application.review_stage = None
        mock_application.is_renewal = False
        mock_application.academic_year = 2024
        mock_application.semester = "first"
        mock_application.student_data = {}
        mock_application.submitted_form_data = {}
        mock_application.agree_terms = True
        mock_application.professor_id = None
        mock_application.reviewer_id = None
        mock_application.final_approver_id = None
        mock_application.submitted_at = None
        mock_application.reviewed_at = None
        mock_application.approved_at = None
        mock_application.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_application.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_application.meta_data = None
        mock_application.application_document_url = None
        mock_application.application_document_original_filename = None
        mock_application.amount = None
        mock_application.files = []
        mock_application.reviews = []
        mock_application.scholarship_configuration = None
        mock_application.scholarship = None
        mock_application.student = None
        mock_application.scholarship_subtype_list = []
        mock_application.sub_scholarship_type = "general"
        mock_application.renewal_year = None
        mock_application.previous_application_id = None
        mock_application.challenges_application_id = None
        mock_application.cancelled_due_to_application_id = None

        with patch.object(service, "_get_application_model", new_callable=AsyncMock) as mock_get_model:
            mock_get_model.return_value = mock_application

            result = await service.get_application_by_id(application_id, mock_user)

            assert result is not None
            assert result.id == application_id
            assert result.user_id == other_user_id
            mock_get_model.assert_called_once_with(application_id, mock_user)

    @pytest.mark.asyncio
    async def test_update_application_success(self, service):
        """Test successful application update"""
        application_id = 1
        user_id = 1

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = user_id
        mock_application.is_editable = True
        mock_application.submitted_form_data = {}
        mock_application.files = []
        mock_application.scholarship_subtype_list = []
        mock_application.app_id = "APP-2024-001"

        update_data = ApplicationUpdate(
            form_data=ApplicationFormData(fields={}, documents=[]),
            status=ApplicationStatus.draft.value,
            is_renewal=True,
        )

        with (
            patch.object(service, "_get_application_model", new_callable=AsyncMock, return_value=mock_application),
            patch.object(service, "_clone_user_profile_documents", new_callable=AsyncMock),
            patch.object(service.db, "commit") as mock_commit,
            patch.object(service.db, "refresh") as mock_refresh,
        ):
            result = await service.update_application(application_id, update_data, mock_user)

            assert result == mock_application
            assert mock_application.status == ApplicationStatus.draft.value
            assert mock_application.is_renewal
            mock_commit.assert_called_once()
            mock_refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_application_not_editable(self, service):
        """Test updating application that is not editable"""
        application_id = 1
        user_id = 1

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = user_id
        mock_application.is_editable = False  # Not editable

        update_data = ApplicationUpdate(form_data=ApplicationFormData(fields={}))

        with patch.object(service, "_get_application_model", new_callable=AsyncMock, return_value=mock_application):
            with pytest.raises(ValidationError, match="Application cannot be edited"):
                await service.update_application(application_id, update_data, mock_user)

    @pytest.mark.asyncio
    async def test_delete_application_success(self, service):
        """Test successful application deletion"""
        application_id = 1
        user_id = 1

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.app_id = "APP-2024-001"
        mock_application.user_id = user_id
        mock_application.status = ApplicationStatus.draft
        mock_application.submitted_form_data = {}
        mock_application.files = []

        with (
            patch.object(service.db, "execute") as mock_execute,
            patch.object(service.db, "delete") as mock_delete,
            patch.object(service.db, "commit") as mock_commit,
            patch("app.services.application_service.cache_invalidate", new_callable=AsyncMock),
        ):
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_application
            mock_execute.return_value = mock_result

            result = await service.delete_application(application_id, mock_user)

            assert result == mock_application
            mock_delete.assert_called_once_with(mock_application)
            mock_commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_application_not_draft(self, service):
        """Test deleting application that is not in draft status"""
        application_id = 1
        user_id = 1

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = user_id
        mock_application.status = ApplicationStatus.submitted  # Not draft

        with patch.object(service.db, "execute") as mock_execute:
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_application
            mock_execute.return_value = mock_result

            with pytest.raises(ValidationError, match="Only draft applications can be deleted"):
                await service.delete_application(application_id, mock_user)

    @pytest.mark.asyncio
    async def test_delete_application_unauthorized(self, service):
        """Test deleting application without proper authorization"""
        application_id = 1
        user_id = 1
        other_user_id = 2

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = other_user_id  # Different user owns this
        mock_application.status = ApplicationStatus.draft.value

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

            with pytest.raises(AuthorizationError, match="You can only delete your own applications"):
                await service.delete_application(application_id, mock_user)
