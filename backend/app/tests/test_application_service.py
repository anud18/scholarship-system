"""
Unit tests for ApplicationService
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
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
            scholarship_subtype_list=["academic_excellence"],
            is_renewal=False,
            form_data=ApplicationFormData(
                personal_statement="Test personal statement",
                academic_achievements="Test achievements",
                documents=[],
            ),
            agree_terms=True,
        )

    @pytest.fixture
    def mock_scholarship_type(self):
        """Mock scholarship type for testing"""
        return ScholarshipType(
            id=1,
            code="undergraduate_freshman",
            name="Undergraduate Freshman Scholarship",
            category="undergraduate",
            status="active",  # is_active is a computed property from status
            whitelist_enabled=False,
        )

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

    def test_generate_app_id(self, service):
        """Test application ID generation"""
        app_id = service._generate_app_id()

        # Should start with APP-{year}-
        current_year = datetime.now().year
        assert app_id.startswith(f"APP-{current_year}-")

        # Should have 6-digit suffix
        suffix = app_id.split("-")[-1]
        assert len(suffix) == 6
        assert suffix.isdigit()

    @pytest.mark.asyncio
    async def test_validate_student_eligibility_success(
        self, service, mock_student, mock_scholarship_type, mock_application_data
    ):
        """Test successful student eligibility validation"""
        # Mock database queries
        with patch.object(service.db, "execute") as mock_execute:
            # Mock scholarship type query result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = mock_scholarship_type
            mock_execute.return_value = mock_result

            # Mock existing application check
            mock_execute.return_value.scalar_one_or_none.side_effect = [
                mock_scholarship_type,  # First call for scholarship lookup
                mock_scholarship_type,  # Second call for scholarship lookup in conflict check
                None,  # No existing application
            ]

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
    async def test_validate_student_eligibility_existing_application(
        self, service, mock_student, mock_scholarship_type, mock_application_data
    ):
        """Test eligibility validation when student has existing active application"""
        existing_application = Mock(spec=Application)

        with patch.object(service.db, "execute") as mock_execute:
            # Mock scholarship lookup calls
            mock_execute.return_value.scalar_one_or_none.side_effect = [
                mock_scholarship_type,  # First scholarship lookup
                mock_scholarship_type,  # Second scholarship lookup
                existing_application,  # Existing application found
            ]

            with pytest.raises(ConflictError, match="You already have an active application"):
                await service._validate_student_eligibility(
                    mock_student, "undergraduate_freshman", mock_application_data
                )

    @pytest.mark.asyncio
    async def test_create_application_draft(self, service, mock_application_data):
        """Test creating a draft application"""
        user_id = 1
        student_id = 1

        # Mock database objects
        mock_user = Mock(spec=User)
        mock_user.id = user_id

        mock_student = Mock()
        mock_student.id = student_id

        mock_scholarship = Mock(spec=ScholarshipType)
        mock_scholarship.id = 1
        mock_scholarship.sub_type_selection_mode = "single"

        # Mock student service
        mock_student_snapshot = {"name": "Test Student", "student_id": "112550001"}

        with patch.object(service.db, "execute") as mock_execute, patch.object(
            service.db, "add"
        ) as mock_add, patch.object(service.db, "commit") as mock_commit, patch.object(
            service.db, "refresh"
        ), patch.object(
            service.student_service,
            "get_student_snapshot",
            return_value=mock_student_snapshot,
        ):
            # Mock database query results
            mock_execute.return_value.scalar_one.side_effect = [
                mock_user,  # User query
                mock_student,  # Student query
                mock_scholarship,  # Scholarship query
            ]

            # Mock final application with relationships
            mock_final_app = Mock(spec=Application)
            mock_final_app.id = 1
            mock_final_app.app_id = "APP-2024-123456"
            mock_final_app.status = ApplicationStatus.DRAFT.value
            mock_execute.return_value.scalar_one.return_value = mock_final_app

            result = await service.create_application(
                user_id=user_id,
                student_id=student_id,
                application_data=mock_application_data,
                is_draft=True,
            )

            # Verify application was created as draft
            mock_add.assert_called_once()
            added_application = mock_add.call_args[0][0]
            assert added_application.status == ApplicationStatus.DRAFT.value
            assert added_application.status_name == "草稿"
            assert added_application.submitted_at is None

            mock_commit.assert_called()
            assert result == mock_final_app

    @pytest.mark.asyncio
    async def test_create_application_submitted(self, service, mock_application_data):
        """Test creating a submitted application"""
        user_id = 1
        student_id = 1

        # Mock database objects
        mock_user = Mock(spec=User)
        mock_user.id = user_id

        mock_student = Mock()
        mock_student.id = student_id

        mock_scholarship = Mock(spec=ScholarshipType)
        mock_scholarship.id = 1
        mock_scholarship.sub_type_selection_mode = "single"

        # Mock student service
        mock_student_snapshot = {"name": "Test Student", "student_id": "112550001"}

        with patch.object(service.db, "execute") as mock_execute, patch.object(
            service.db, "add"
        ) as mock_add, patch.object(service.db, "commit") as mock_commit, patch.object(
            service.db, "refresh"
        ), patch.object(
            service.student_service,
            "get_student_snapshot",
            return_value=mock_student_snapshot,
        ):
            # Mock database query results
            mock_execute.return_value.scalar_one.side_effect = [
                mock_user,  # User query
                mock_student,  # Student query
                mock_scholarship,  # Scholarship query
            ]

            # Mock final application with relationships
            mock_final_app = Mock(spec=Application)
            mock_final_app.id = 1
            mock_final_app.app_id = "APP-2024-123456"
            mock_final_app.status = ApplicationStatus.SUBMITTED.value
            mock_execute.return_value.scalar_one.return_value = mock_final_app

            result = await service.create_application(
                user_id=user_id,
                student_id=student_id,
                application_data=mock_application_data,
                is_draft=False,
            )

            # Verify application was created as submitted
            mock_add.assert_called_once()
            added_application = mock_add.call_args[0][0]
            assert added_application.status == ApplicationStatus.SUBMITTED.value
            assert added_application.status_name == "已提交"
            assert added_application.submitted_at is not None

            mock_commit.assert_called()
            assert result == mock_final_app

    @pytest.mark.asyncio
    async def test_get_application_by_id_student_access(self, service):
        """Test getting application by ID with student access control"""
        application_id = 1
        user_id = 1

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.student

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = user_id
        mock_application.submitted_form_data = {}
        mock_application.files = []

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

            result = await service.get_application_by_id(application_id, mock_user)

            assert result == mock_application

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
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

            result = await service.get_application_by_id(application_id, mock_user)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_application_by_id_admin_access(self, service):
        """Test getting application by ID with admin access"""
        application_id = 1
        user_id = 1
        other_user_id = 2

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.role = UserRole.admin

        mock_application = Mock(spec=Application)
        mock_application.id = application_id
        mock_application.user_id = other_user_id
        mock_application.submitted_form_data = {}
        mock_application.files = []

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

            result = await service.get_application_by_id(application_id, mock_user)

            assert result == mock_application

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

        update_data = ApplicationUpdate(
            form_data=ApplicationFormData(
                personal_statement="Updated statement",
                academic_achievements="Updated achievements",
                documents=[],
            ),
            status=ApplicationStatus.DRAFT.value,
            is_renewal=True,
        )

        with patch.object(service, "get_application_by_id", return_value=mock_application), patch.object(
            service.db, "commit"
        ) as mock_commit, patch.object(service.db, "refresh") as mock_refresh:
            result = await service.update_application(application_id, update_data, mock_user)

            assert result == mock_application
            assert mock_application.status == ApplicationStatus.DRAFT.value
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

        update_data = ApplicationUpdate(
            form_data=ApplicationFormData(
                personal_statement="Updated statement",
                academic_achievements="Updated achievements",
                documents=[],
            )
        )

        with patch.object(service, "get_application_by_id", return_value=mock_application):
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
        mock_application.user_id = user_id
        mock_application.status = ApplicationStatus.DRAFT.value
        mock_application.submitted_form_data = {}

        with patch.object(service.db, "execute") as mock_execute, patch.object(
            service.db, "delete"
        ) as mock_delete, patch.object(service.db, "commit") as mock_commit:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

            result = await service.delete_application(application_id, mock_user)

            assert result is True
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
        mock_application.status = ApplicationStatus.SUBMITTED.value  # Not draft

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

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
        mock_application.status = ApplicationStatus.DRAFT.value

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_application

            with pytest.raises(AuthorizationError, match="You can only delete your own applications"):
                await service.delete_application(application_id, mock_user)
