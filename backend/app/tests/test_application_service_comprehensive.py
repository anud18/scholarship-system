"""
Comprehensive unit tests for ApplicationService

Tests all major application management functionality:
- Application CRUD operations
- Status transitions and validation
- Permission-based access control
- Data validation and sanitization
- Error handling for edge cases
- Integration with external services
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, BusinessLogicError, ConflictError, NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus, Semester
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole
from app.schemas.application import ApplicationCreate, ApplicationUpdate
from app.services.application_service import ApplicationService, get_student_data_from_user


@pytest.mark.unit
class TestApplicationService:
    """Comprehensive test suite for ApplicationService"""

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        mock_session = AsyncMock(spec=AsyncSession)
        return mock_session

    @pytest.fixture
    def application_service(self, mock_db_session):
        """Create ApplicationService instance with mocked dependencies"""
        with patch("app.services.application_service.EmailService"):
            service = ApplicationService(mock_db_session)
            service.emailService = AsyncMock()
            return service

    @pytest.fixture
    def student_user(self):
        """Create student user for testing"""
        return User(
            id=1,
            email="student@university.edu",
            name="Test Student",
            nycu_id="11011001",
            role=UserRole.STUDENT,
            is_active=True,
        )

    @pytest.fixture
    def admin_user(self):
        """Create admin user for testing"""
        return User(
            id=2,
            email="admin@university.edu",
            name="Admin User",
            role=UserRole.ADMIN,
            is_active=True,
        )

    @pytest.fixture
    def professor_user(self):
        """Create professor user for testing"""
        return User(
            id=3,
            email="professor@university.edu",
            name="Professor User",
            role=UserRole.PROFESSOR,
            is_active=True,
        )

    @pytest.fixture
    def scholarship_type(self):
        """Create scholarship type for testing"""
        return ScholarshipType(
            id=1,
            code="undergraduate_freshman",
            name="Undergraduate Freshman Scholarship",
            category="undergraduate_freshman",
            amount=Decimal("50000"),
            is_active=True,
            is_application_period=True,
            academic_year=113,
            semester=Semester.FIRST,
        )

    @pytest.fixture
    def application_create_data(self, scholarship_type):
        """Create valid application data"""
        return ApplicationCreate(
            scholarship_type_id=scholarship_type.id,
            main_scholarship_type="undergraduate_freshman",
            sub_scholarship_type="general",
            amount=Decimal("50000"),
            academic_year=113,
            semester=Semester.FIRST,
            student_data={
                "name": "Test Student",
                "student_id": "11011001",
                "department": "Computer Science",
                "gpa": 3.85,
            },
            submitted_form_data={
                "personal_statement": "I am passionate about computer science...",
                "career_goals": "To become a software engineer",
                "extracurricular_activities": "Programming club, volunteer work",
            },
            agree_terms=True,
        )

    @pytest.fixture
    def mock_application(self, student_user, scholarship_type):
        """Create mock application instance"""
        return Application(
            id=1,
            app_id="APP-2024-000001",
            user_id=student_user.id,
            scholarship_type_id=scholarship_type.id,
            status=ApplicationStatus.DRAFT.value,
            main_scholarship_type="undergraduate_freshman",
            sub_scholarship_type="general",
            amount=Decimal("50000"),
            academic_year=113,
            semester=Semester.FIRST,
            student_data={
                "name": "Test Student",
                "student_id": "11011001",
                "department": "Computer Science",
            },
            submitted_form_data={"personal_statement": "Test statement"},
            agree_terms=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_create_application_success(
        self,
        application_service,
        student_user,
        application_create_data,
        scholarship_type,
    ):
        """Test successful application creation"""
        # Arrange
        mock_scholarship_query = Mock()
        mock_scholarship_query.scalar_one_or_none.return_value = scholarship_type
        application_service.db.execute.return_value = mock_scholarship_query

        application_service.db.add = Mock()
        application_service.db.commit = AsyncMock()
        application_service.db.refresh = AsyncMock()

        # Mock app_id generation
        with patch(
            "app.services.application_service.ApplicationService._generate_app_id",
            return_value="APP-2024-000001",
        ):
            # Act
            result = await application_service.create_application(
                user=student_user, application_data=application_create_data
            )

            # Assert
            application_service.db.add.assert_called_once()
            application_service.db.commit.assert_called_once()
            assert result is not None

    @pytest.mark.asyncio
    async def test_create_application_invalid_scholarship(
        self, application_service, student_user, application_create_data
    ):
        """Test application creation with invalid scholarship type"""
        # Arrange
        mock_scholarship_query = Mock()
        mock_scholarship_query.scalar_one_or_none.return_value = None
        application_service.db.execute.return_value = mock_scholarship_query

        # Act & Assert
        with pytest.raises(NotFoundError, match="Scholarship type not found"):
            await application_service.create_application(user=student_user, application_data=application_create_data)

    @pytest.mark.asyncio
    async def test_create_application_inactive_scholarship(
        self,
        application_service,
        student_user,
        application_create_data,
        scholarship_type,
    ):
        """Test application creation with inactive scholarship"""
        # Arrange
        scholarship_type.is_active = False
        scholarship_type.is_application_period = False

        mock_scholarship_query = Mock()
        mock_scholarship_query.scalar_one_or_none.return_value = scholarship_type
        application_service.db.execute.return_value = mock_scholarship_query

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="not available for applications"):
            await application_service.create_application(user=student_user, application_data=application_create_data)

    @pytest.mark.asyncio
    async def test_create_application_duplicate_prevention(
        self,
        application_service,
        student_user,
        application_create_data,
        scholarship_type,
    ):
        """Test prevention of duplicate applications"""
        # Arrange
        mock_scholarship_query = Mock()
        mock_scholarship_query.scalar_one_or_none.return_value = scholarship_type

        # Mock existing application check
        mock_existing_query = Mock()
        mock_existing_query.scalar_one_or_none.return_value = Mock(id=1)  # Existing application

        application_service.db.execute.side_effect = [
            mock_scholarship_query,
            mock_existing_query,
        ]

        # Act & Assert
        with pytest.raises(ConflictError, match="already applied"):
            await application_service.create_application(user=student_user, application_data=application_create_data)

    @pytest.mark.asyncio
    async def test_get_application_by_id_success(self, application_service, mock_application):
        """Test successful application retrieval by ID"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result

        # Act
        result = await application_service.get_application_by_id(application_id=1)

        # Assert
        assert result == mock_application
        application_service.db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_application_by_id_not_found(self, application_service):
        """Test application retrieval with invalid ID"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = None
        application_service.db.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(NotFoundError):
            await application_service.get_application_by_id(application_id=999)

    @pytest.mark.asyncio
    async def test_get_user_applications(self, application_service, student_user, mock_application):
        """Test retrieving user's applications"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = [mock_application]
        application_service.db.execute.return_value = mock_query_result

        # Act
        result = await application_service.get_user_applications(user=student_user)

        # Assert
        assert len(result) == 1
        assert result[0] == mock_application

    @pytest.mark.asyncio
    async def test_update_application_success(self, application_service, student_user, mock_application):
        """Test successful application update"""
        # Arrange
        update_data = ApplicationUpdate(
            submitted_form_data={
                "personal_statement": "Updated statement",
                "career_goals": "Updated goals",
            }
        )

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result
        application_service.db.commit = AsyncMock()
        application_service.db.refresh = AsyncMock()

        # Act
        result = await application_service.update_application(
            user=student_user, application_id=1, update_data=update_data
        )

        # Assert
        assert mock_application.submitted_form_data["personal_statement"] == "Updated statement"
        application_service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_application_permission_denied(self, application_service, professor_user, mock_application):
        """Test application update with insufficient permissions"""
        # Arrange
        update_data = ApplicationUpdate(submitted_form_data={"personal_statement": "Unauthorized update"})

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(AuthorizationError):
            await application_service.update_application(user=professor_user, application_id=1, update_data=update_data)

    @pytest.mark.asyncio
    async def test_update_application_invalid_status(self, application_service, student_user, mock_application):
        """Test application update when application is not in draft status"""
        # Arrange
        mock_application.status = ApplicationStatus.SUBMITTED.value
        update_data = ApplicationUpdate(
            submitted_form_data={"personal_statement": "Cannot update submitted application"}
        )

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="cannot be modified"):
            await application_service.update_application(user=student_user, application_id=1, update_data=update_data)

    @pytest.mark.asyncio
    async def test_submit_application_success(self, application_service, student_user, mock_application):
        """Test successful application submission"""
        # Arrange
        mock_application.status = ApplicationStatus.DRAFT.value
        mock_application.submitted_form_data = {
            "personal_statement": "Complete statement with 100+ characters for validation purposes.",
            "career_goals": "Detailed career goals",
        }

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result
        application_service.db.commit = AsyncMock()

        with patch.object(application_service, "_validate_application_completeness", return_value=True):
            # Act
            result = await application_service.submit_application(user=student_user, application_id=1)

            # Assert
            assert mock_application.status == ApplicationStatus.SUBMITTED.value
            assert mock_application.submitted_at is not None
            application_service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_application_incomplete_data(self, application_service, student_user, mock_application):
        """Test application submission with incomplete data"""
        # Arrange
        mock_application.status = ApplicationStatus.DRAFT.value
        mock_application.submitted_form_data = {"personal_statement": "Too short"}  # Incomplete data

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result

        with patch.object(
            application_service,
            "_validate_application_completeness",
            return_value=False,
        ):
            # Act & Assert
            with pytest.raises(ValidationError, match="incomplete"):
                await application_service.submit_application(user=student_user, application_id=1)

    @pytest.mark.asyncio
    async def test_withdraw_application_success(self, application_service, student_user, mock_application):
        """Test successful application withdrawal"""
        # Arrange
        mock_application.status = ApplicationStatus.SUBMITTED.value

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result
        application_service.db.commit = AsyncMock()

        # Act
        result = await application_service.withdraw_application(
            user=student_user, application_id=1, reason="Changed my mind"
        )

        # Assert
        assert mock_application.status == ApplicationStatus.WITHDRAWN.value
        application_service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_withdraw_application_invalid_status(self, application_service, student_user, mock_application):
        """Test withdrawal of application in invalid status"""
        # Arrange
        mock_application.status = ApplicationStatus.APPROVED.value

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="cannot be withdrawn"):
            await application_service.withdraw_application(user=student_user, application_id=1, reason="Too late")

    @pytest.mark.asyncio
    async def test_delete_application_admin_permission(self, application_service, admin_user, mock_application):
        """Test application deletion by admin"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result
        application_service.db.delete = Mock()
        application_service.db.commit = AsyncMock()

        # Act
        await application_service.delete_application(user=admin_user, application_id=1)

        # Assert
        application_service.db.delete.assert_called_once_with(mock_application)
        application_service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_application_permission_denied(self, application_service, student_user, mock_application):
        """Test application deletion without admin permission"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(AuthorizationError):
            await application_service.delete_application(user=student_user, application_id=1)

    @pytest.mark.asyncio
    async def test_update_application_status_admin(self, application_service, admin_user, mock_application):
        """Test application status update by admin"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result
        application_service.db.commit = AsyncMock()

        # Act
        result = await application_service.update_application_status(
            user=admin_user,
            application_id=1,
            new_status=ApplicationStatus.UNDER_REVIEW,
            comments="Review started",
        )

        # Assert
        assert mock_application.status == ApplicationStatus.UNDER_REVIEW.value
        application_service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_applications_with_filters(self, application_service, admin_user):
        """Test application search with various filters"""
        # Arrange
        mock_applications = [Mock(id=1), Mock(id=2)]
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = mock_applications

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 2

        application_service.db.execute.side_effect = [
            mock_query_result,
            mock_count_result,
        ]

        # Act
        results, total = await application_service.search_applications(
            user=admin_user,
            status=ApplicationStatus.SUBMITTED,
            scholarship_type_id=1,
            academic_year=113,
            search_term="computer science",
            page=1,
            size=10,
        )

        # Assert
        assert len(results) == 2
        assert total == 2
        assert application_service.db.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_validate_application_completeness(self, application_service):
        """Test application completeness validation"""
        # Arrange
        complete_application = Mock(
            submitted_form_data={
                "personal_statement": "A comprehensive personal statement with more than 100 characters describing my background, goals, and motivation.",
                "career_goals": "Detailed career objectives",
                "extracurricular_activities": "List of activities",
            },
            agree_terms=True,
        )

        incomplete_application = Mock(submitted_form_data={"personal_statement": "Too short"}, agree_terms=False)

        # Act & Assert
        assert application_service._validate_application_completeness(complete_application) == True
        assert application_service._validate_application_completeness(incomplete_application) == False

    @pytest.mark.asyncio
    async def test_generate_app_id_uniqueness(self, application_service):
        """Test application ID generation ensures uniqueness"""
        # Arrange
        mock_existing_query = Mock()
        mock_existing_query.scalar_one_or_none.side_effect = [
            Mock(id=1),
            None,
        ]  # First ID exists, second is unique
        application_service.db.execute.side_effect = [
            mock_existing_query,
            mock_existing_query,
        ]

        # Act
        with patch("uuid.uuid4", side_effect=[Mock(hex="123456"), Mock(hex="789012")]):
            app_id = await application_service._generate_app_id()

        # Assert
        assert app_id.startswith("APP-")
        assert len(app_id) == 17  # APP- + year + 6 digit hex

    @pytest.mark.asyncio
    async def test_email_notification_on_submission(self, application_service, student_user, mock_application):
        """Test email notification is sent on application submission"""
        # Arrange
        mock_application.status = ApplicationStatus.DRAFT.value
        mock_application.submitted_form_data = {
            "personal_statement": "Complete statement with sufficient length for validation."
        }

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_application
        application_service.db.execute.return_value = mock_query_result
        application_service.db.commit = AsyncMock()

        with patch.object(application_service, "_validate_application_completeness", return_value=True):
            # Act
            await application_service.submit_application(user=student_user, application_id=1)

            # Assert
            application_service.emailService.send_application_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_database_transaction_rollback_on_error(
        self,
        application_service,
        student_user,
        application_create_data,
        scholarship_type,
    ):
        """Test database transaction rollback on error"""
        # Arrange
        mock_scholarship_query = Mock()
        mock_scholarship_query.scalar_one_or_none.return_value = scholarship_type
        application_service.db.execute.return_value = mock_scholarship_query

        application_service.db.add = Mock()
        application_service.db.commit = AsyncMock(side_effect=Exception("Database error"))
        application_service.db.rollback = AsyncMock()

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await application_service.create_application(user=student_user, application_data=application_create_data)

        application_service.db.rollback.assert_called_once()


@pytest.mark.unit
class TestGetStudentDataFromUser:
    """Test suite for get_student_data_from_user utility function"""

    @pytest.mark.asyncio
    async def test_get_student_data_success(self):
        """Test successful student data retrieval"""
        # Arrange
        user = User(id=1, role=UserRole.STUDENT, nycu_id="11011001")

        mock_student_data = {
            "name": "Test Student",
            "student_id": "11011001",
            "department": "Computer Science",
        }

        with patch("app.services.application_service.StudentService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.get_student_basic_info = AsyncMock(return_value=mock_student_data)

            # Act
            result = await get_student_data_from_user(user)

            # Assert
            assert result == mock_student_data
            mock_service.get_student_basic_info.assert_called_once_with("11011001")

    @pytest.mark.asyncio
    async def test_get_student_data_non_student_user(self):
        """Test student data retrieval for non-student user"""
        # Arrange
        user = User(id=1, role=UserRole.PROFESSOR, nycu_id="11011001")

        # Act
        result = await get_student_data_from_user(user)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_student_data_no_nycu_id(self):
        """Test student data retrieval without NYCU ID"""
        # Arrange
        user = User(id=1, role=UserRole.STUDENT, nycu_id=None)

        # Act
        result = await get_student_data_from_user(user)

        # Assert
        assert result is None

    # TODO: Add tests for external API failure handling
    # TODO: Add tests for student data caching mechanism
    # TODO: Add tests for student data validation and sanitization
    # TODO: Add performance tests for bulk application operations
    # TODO: Add tests for application archiving functionality
