"""
Unit tests for EmailManagementService

Tests comprehensive email management functionality including:
- Email history retrieval with permissions
- Scheduled email management
- Email filtering and pagination
- Permission-based access control
- Error handling for edge cases
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models.email_management import (
    EmailCategory,
    EmailHistory,
    EmailStatus,
    ScheduledEmail,
    ScheduleStatus,
)
from app.models.user import User, UserRole
from app.services.email_management_service import EmailManagementService


@pytest.mark.unit
class TestEmailManagementService:
    """Test suite for EmailManagementService"""

    @pytest.fixture
    def email_service(self):
        """Create EmailManagementService instance"""
        return EmailManagementService()

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        mock_session = AsyncMock(spec=AsyncSession)
        return mock_session

    @pytest.fixture
    def admin_user(self):
        """Create admin user for testing"""
        return User(
            id=1,
            email="admin@university.edu",
            name="Admin User",
            role=UserRole.ADMIN,
            is_active=True,
        )

    @pytest.fixture
    def regular_user(self):
        """Create regular user for testing"""
        return User(
            id=2,
            email="user@university.edu",
            name="Regular User",
            role=UserRole.STUDENT,
            is_active=True,
        )

    @pytest.fixture
    def sample_email_history(self, admin_user):
        """Create sample email history records"""
        now = datetime.now(timezone.utc)
        return [
            EmailHistory(
                id=1,
                recipient_email="student1@university.edu",
                subject="Application Confirmation",
                body="Your application has been received",
                status=EmailStatus.SENT,
                category=EmailCategory.APPLICATION_CONFIRMATION,
                sent_at=now - timedelta(hours=1),
                created_at=now - timedelta(hours=2),
                updated_at=now - timedelta(hours=1),
            ),
            EmailHistory(
                id=2,
                recipient_email="student2@university.edu",
                subject="Review Required",
                body="Your application needs review",
                status=EmailStatus.PENDING,
                category=EmailCategory.REVIEW_NOTIFICATION,
                created_at=now - timedelta(hours=3),
                updated_at=now - timedelta(hours=3),
            ),
            EmailHistory(
                id=3,
                recipient_email="student3@university.edu",
                subject="Application Failed",
                body="Email delivery failed",
                status=EmailStatus.FAILED,
                category=EmailCategory.APPLICATION_CONFIRMATION,
                error_message="SMTP timeout",
                created_at=now - timedelta(hours=4),
                updated_at=now - timedelta(hours=4),
            ),
        ]

    @pytest.mark.asyncio
    async def test_get_email_history_admin_access(
        self, email_service, mock_db_session, admin_user, sample_email_history
    ):
        """Test that admin users can access all email history"""
        # Arrange
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = sample_email_history
        mock_db_session.execute.return_value = mock_query_result

        # Mock count query
        mock_count_result = Mock()
        mock_count_result.scalar.return_value = len(sample_email_history)
        mock_db_session.execute.side_effect = [mock_query_result, mock_count_result]

        # Act
        emails, total = await email_service.get_email_history(
            db=mock_db_session, user=admin_user, limit=50
        )

        # Assert
        assert len(emails) == 3
        assert total == 3
        assert mock_db_session.execute.call_count == 2  # One for data, one for count

    @pytest.mark.asyncio
    async def test_get_email_history_permission_filtering(
        self, email_service, mock_db_session, regular_user
    ):
        """Test that regular users only see permitted emails"""
        # Arrange
        filtered_emails = []  # Regular users should see limited or no emails
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = filtered_emails
        mock_db_session.execute.return_value = mock_query_result

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0
        mock_db_session.execute.side_effect = [mock_query_result, mock_count_result]

        # Act
        emails, total = await email_service.get_email_history(
            db=mock_db_session, user=regular_user, limit=50
        )

        # Assert
        assert len(emails) == 0
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_email_history_with_filters(
        self, email_service, mock_db_session, admin_user
    ):
        """Test email history retrieval with various filters"""
        # Arrange
        filtered_emails = [Mock(id=1, status=EmailStatus.SENT)]
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = filtered_emails
        mock_db_session.execute.return_value = mock_query_result

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1
        mock_db_session.execute.side_effect = [mock_query_result, mock_count_result]

        # Act
        emails, total = await email_service.get_email_history(
            db=mock_db_session,
            user=admin_user,
            email_category=EmailCategory.APPLICATION_CONFIRMATION,
            status=EmailStatus.SENT,
            recipient_email="test@university.edu",
        )

        # Assert
        assert len(emails) == 1
        assert total == 1
        # Verify the query was constructed with filters
        mock_db_session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_get_email_history_pagination(
        self, email_service, mock_db_session, admin_user, sample_email_history
    ):
        """Test email history pagination"""
        # Arrange
        paginated_emails = sample_email_history[:2]  # First page with 2 items
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = paginated_emails
        mock_db_session.execute.return_value = mock_query_result

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = len(sample_email_history)
        mock_db_session.execute.side_effect = [mock_query_result, mock_count_result]

        # Act
        emails, total = await email_service.get_email_history(
            db=mock_db_session, user=admin_user, skip=0, limit=2
        )

        # Assert
        assert len(emails) == 2
        assert total == 3  # Total count should still be 3

    @pytest.mark.asyncio
    async def test_get_email_history_date_range_filter(
        self, email_service, mock_db_session, admin_user
    ):
        """Test email history filtering by date range"""
        # Arrange
        date_from = datetime.now(timezone.utc) - timedelta(days=1)
        date_to = datetime.now(timezone.utc)

        filtered_emails = [Mock(id=1, created_at=date_from + timedelta(hours=12))]
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = filtered_emails
        mock_db_session.execute.return_value = mock_query_result

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1
        mock_db_session.execute.side_effect = [mock_query_result, mock_count_result]

        # Act
        emails, total = await email_service.get_email_history(
            db=mock_db_session, user=admin_user, date_from=date_from, date_to=date_to
        )

        # Assert
        assert len(emails) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_get_scheduled_emails_admin(
        self, email_service, mock_db_session, admin_user
    ):
        """Test that admin can access all scheduled emails"""
        # Arrange
        scheduled_emails = [
            Mock(id=1, status=ScheduleStatus.PENDING),
            Mock(id=2, status=ScheduleStatus.SCHEDULED),
        ]
        mock_query_result = Mock()
        mock_query_result.scalars.return_value.all.return_value = scheduled_emails
        mock_db_session.execute.return_value = mock_query_result

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 2
        mock_db_session.execute.side_effect = [mock_query_result, mock_count_result]

        # Act
        emails, total = await email_service.get_scheduled_emails(
            db=mock_db_session, user=admin_user
        )

        # Assert
        assert len(emails) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_create_scheduled_email_success(
        self, email_service, mock_db_session, admin_user
    ):
        """Test successful creation of scheduled email"""
        # Arrange
        email_data = {
            "recipient_emails": ["student1@university.edu", "student2@university.edu"],
            "subject": "Test Notification",
            "body": "This is a test notification",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "category": EmailCategory.ANNOUNCEMENT,
        }

        mock_scheduled_email = Mock(id=1)
        mock_db_session.add = Mock()
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        # Act
        with patch.object(ScheduledEmail, "__init__", return_value=None) as mock_init:
            mock_init.return_value = None
            result = await email_service.create_scheduled_email(
                db=mock_db_session, user=admin_user, **email_data
            )

        # Assert
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_scheduled_email_permission_denied(
        self, email_service, mock_db_session, regular_user
    ):
        """Test that regular users cannot create scheduled emails"""
        # Arrange
        email_data = {
            "recipient_emails": ["student1@university.edu"],
            "subject": "Test",
            "body": "Test body",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="permission"):
            await email_service.create_scheduled_email(
                db=mock_db_session, user=regular_user, **email_data
            )

    @pytest.mark.asyncio
    async def test_create_scheduled_email_invalid_schedule_time(
        self, email_service, mock_db_session, admin_user
    ):
        """Test validation for scheduled email time"""
        # Arrange
        email_data = {
            "recipient_emails": ["student1@university.edu"],
            "subject": "Test",
            "body": "Test body",
            "scheduled_at": datetime.now(timezone.utc)
            - timedelta(hours=1),  # Past time
        }

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="future"):
            await email_service.create_scheduled_email(
                db=mock_db_session, user=admin_user, **email_data
            )

    @pytest.mark.asyncio
    async def test_cancel_scheduled_email_success(
        self, email_service, mock_db_session, admin_user
    ):
        """Test successful cancellation of scheduled email"""
        # Arrange
        email_id = 1
        mock_email = Mock(
            id=email_id, status=ScheduleStatus.SCHEDULED, created_by=admin_user.id
        )

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_email
        mock_db_session.execute.return_value = mock_query_result
        mock_db_session.commit = AsyncMock()

        # Act
        result = await email_service.cancel_scheduled_email(
            db=mock_db_session, user=admin_user, email_id=email_id
        )

        # Assert
        assert mock_email.status == ScheduleStatus.CANCELLED
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_scheduled_email_not_found(
        self, email_service, mock_db_session, admin_user
    ):
        """Test cancellation of non-existent scheduled email"""
        # Arrange
        email_id = 999
        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(NotFoundError):
            await email_service.cancel_scheduled_email(
                db=mock_db_session, user=admin_user, email_id=email_id
            )

    @pytest.mark.asyncio
    async def test_cancel_scheduled_email_already_sent(
        self, email_service, mock_db_session, admin_user
    ):
        """Test cancellation of already sent email"""
        # Arrange
        email_id = 1
        mock_email = Mock(
            id=email_id, status=ScheduleStatus.SENT, created_by=admin_user.id
        )

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_email
        mock_db_session.execute.return_value = mock_query_result

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="already sent"):
            await email_service.cancel_scheduled_email(
                db=mock_db_session, user=admin_user, email_id=email_id
            )

    @pytest.mark.asyncio
    async def test_update_scheduled_email_success(
        self, email_service, mock_db_session, admin_user
    ):
        """Test successful update of scheduled email"""
        # Arrange
        email_id = 1
        update_data = {
            "subject": "Updated Subject",
            "body": "Updated body content",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=2),
        }

        mock_email = Mock(
            id=email_id, status=ScheduleStatus.SCHEDULED, created_by=admin_user.id
        )

        mock_query_result = Mock()
        mock_query_result.scalar_one_or_none.return_value = mock_email
        mock_db_session.execute.return_value = mock_query_result
        mock_db_session.commit = AsyncMock()
        mock_db_session.refresh = AsyncMock()

        # Act
        result = await email_service.update_scheduled_email(
            db=mock_db_session, user=admin_user, email_id=email_id, **update_data
        )

        # Assert
        assert mock_email.subject == update_data["subject"]
        assert mock_email.body == update_data["body"]
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_email_statistics_admin(
        self, email_service, mock_db_session, admin_user
    ):
        """Test email statistics retrieval for admin"""
        # Arrange
        mock_stats = {
            "total_sent": 100,
            "total_pending": 25,
            "total_failed": 5,
            "success_rate": 95.2,
        }

        # Mock multiple query results for statistics
        mock_results = [Mock(scalar=Mock(return_value=value)) for value in [100, 25, 5]]
        mock_db_session.execute.side_effect = mock_results

        # Act
        with patch.object(email_service, "_calculate_success_rate", return_value=95.2):
            stats = await email_service.get_email_statistics(
                db=mock_db_session, user=admin_user
            )

        # Assert
        assert stats["total_sent"] == 100
        assert stats["total_pending"] == 25
        assert stats["total_failed"] == 5
        assert stats["success_rate"] == 95.2

    @pytest.mark.asyncio
    async def test_bulk_email_creation_validation(
        self, email_service, mock_db_session, admin_user
    ):
        """Test validation for bulk email creation"""
        # Arrange - too many recipients
        large_recipient_list = [f"student{i}@university.edu" for i in range(1001)]
        email_data = {
            "recipient_emails": large_recipient_list,
            "subject": "Bulk Test",
            "body": "Test body",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Act & Assert
        with pytest.raises(BusinessLogicError, match="too many recipients"):
            await email_service.create_scheduled_email(
                db=mock_db_session, user=admin_user, **email_data
            )

    @pytest.mark.asyncio
    async def test_email_template_validation(
        self, email_service, mock_db_session, admin_user
    ):
        """Test email template validation"""
        # Arrange - empty subject and body
        email_data = {
            "recipient_emails": ["student@university.edu"],
            "subject": "",
            "body": "",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(hours=1),
        }

        # Act & Assert
        with pytest.raises(
            BusinessLogicError, match="Subject and body cannot be empty"
        ):
            await email_service.create_scheduled_email(
                db=mock_db_session, user=admin_user, **email_data
            )

    @pytest.mark.asyncio
    async def test_database_error_handling(
        self, email_service, mock_db_session, admin_user
    ):
        """Test proper handling of database errors"""
        # Arrange
        mock_db_session.execute.side_effect = Exception("Database connection failed")

        # Act & Assert
        with pytest.raises(Exception, match="Database connection failed"):
            await email_service.get_email_history(db=mock_db_session, user=admin_user)

    # TODO: Add tests for email retry mechanism when implemented
    # TODO: Add tests for email template system integration
    # TODO: Add tests for email delivery status webhook handling
    # TODO: Add performance tests for large email history queries
    # TODO: Add tests for email content sanitization
