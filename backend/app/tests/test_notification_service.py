"""
Unit tests for NotificationService
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPriority, NotificationType
from app.services.notification_service import NotificationService


class TestNotificationService:
    """Test cases for NotificationService"""

    @pytest.fixture
    def service(self, db: AsyncSession):
        """Create NotificationService instance for testing"""
        return NotificationService(db)

    @pytest.fixture
    def mock_notification(self):
        """Mock notification object"""
        notification = Mock(spec=Notification)
        notification.id = 1
        notification.user_id = 1
        notification.title = "Test Notification"
        notification.title_en = "Test Notification"
        notification.message = "Test message"
        notification.message_en = "Test message"
        notification.notification_type = NotificationType.info.value
        notification.priority = NotificationPriority.normal.value
        notification.is_read = False
        notification.is_dismissed = False
        notification.created_at = datetime.now()
        notification.read_at = None
        notification.expires_at = None
        notification.action_url = None
        notification.related_resource_type = None
        notification.related_resource_id = None
        notification.meta_data = {}
        return notification

    @pytest.mark.asyncio
    async def test_create_user_notification_success(self, service):
        """Test creating a user notification successfully"""
        user_id = 1
        title = "Test Notification"
        message = "Test message"

        with (
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "commit") as mock_commit,
            patch.object(service.db, "refresh") as mock_refresh,
        ):
            # Mock the created notification
            created_notification = Mock(spec=Notification)
            created_notification.id = 1
            created_notification.user_id = user_id
            created_notification.title = title
            created_notification.message = message

            with patch(
                "app.models.notification.Notification",
                return_value=created_notification,
            ):
                result = await service.createUserNotification(user_id=user_id, title=title, message=message)

                # Verify database operations
                mock_add.assert_called_once_with(created_notification)
                mock_commit.assert_called_once()
                mock_refresh.assert_called_once_with(created_notification)

                # Verify result
                assert result == created_notification

    @pytest.mark.asyncio
    async def test_create_user_notification_with_all_params(self, service):
        """Test creating user notification with all optional parameters"""
        user_id = 1
        title = "Test Notification"
        message = "Test message"
        title_en = "Test Notification EN"
        message_en = "Test message EN"
        notification_type = NotificationType.warning.value
        priority = NotificationPriority.high.value
        related_resource_type = "application"
        related_resource_id = 123
        action_url = "/test-url"
        expires_at = datetime.now() + timedelta(days=7)
        metadata = {"key": "value"}

        with patch.object(service.db, "add"), patch.object(service.db, "commit"), patch.object(service.db, "refresh"):
            created_notification = Mock(spec=Notification)

            with patch("app.models.notification.Notification") as mock_notification_class:
                mock_notification_class.return_value = created_notification

                result = await service.createUserNotification(
                    user_id=user_id,
                    title=title,
                    message=message,
                    title_en=title_en,
                    message_en=message_en,
                    notification_type=notification_type,
                    priority=priority,
                    related_resource_type=related_resource_type,
                    related_resource_id=related_resource_id,
                    action_url=action_url,
                    expires_at=expires_at,
                    metadata=metadata,
                )

                # Verify Notification was created with correct parameters
                mock_notification_class.assert_called_once_with(
                    user_id=user_id,
                    title=title,
                    title_en=title_en,
                    message=message,
                    message_en=message_en,
                    notification_type=notification_type,
                    priority=priority,
                    related_resource_type=related_resource_type,
                    related_resource_id=related_resource_id,
                    action_url=action_url,
                    expires_at=expires_at,
                    meta_data=metadata,
                )

                assert result == created_notification

    @pytest.mark.asyncio
    async def test_create_system_announcement_success(self, service):
        """Test creating a system announcement successfully"""
        title = "System Announcement"
        message = "Important system message"

        with (
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "commit") as mock_commit,
            patch.object(service.db, "refresh") as mock_refresh,
        ):
            created_notification = Mock(spec=Notification)
            created_notification.id = 1
            created_notification.user_id = None  # System announcement
            created_notification.title = title
            created_notification.message = message

            with patch(
                "app.models.notification.Notification",
                return_value=created_notification,
            ):
                result = await service.createSystemAnnouncement(title=title, message=message)

                # Verify database operations
                mock_add.assert_called_once_with(created_notification)
                mock_commit.assert_called_once()
                mock_refresh.assert_called_once_with(created_notification)

                # Verify result
                assert result == created_notification

    @pytest.mark.asyncio
    async def test_notify_application_status_change_approved(self, service):
        """Test notifying application status change to approved"""
        user_id = 1
        application_id = 123
        new_status = "approved"
        application_title = "獎學金申請"

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyApplicationStatusChange(
                user_id=user_id,
                application_id=application_id,
                new_status=new_status,
                application_title=application_title,
            )

            # Verify createUserNotification was called with correct parameters
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]

            assert call_args["user_id"] == user_id
            assert call_args["title"] == f"{application_title}狀態更新"
            assert call_args["title_en"] == f"{application_title} Status Update"
            assert "恭喜" in call_args["message"]  # Approved message should contain congratulations
            assert call_args["notification_type"] == NotificationType.success.value
            assert call_args["priority"] == NotificationPriority.high.value
            assert call_args["related_resource_type"] == "application"
            assert call_args["related_resource_id"] == application_id
            assert call_args["action_url"] == f"/applications/{application_id}"

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_application_status_change_rejected(self, service):
        """Test notifying application status change to rejected"""
        user_id = 1
        application_id = 123
        new_status = "rejected"

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyApplicationStatusChange(
                user_id=user_id, application_id=application_id, new_status=new_status
            )

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert "很抱歉" in call_args["message"]  # Rejected message should contain apology
            assert call_args["notification_type"] == NotificationType.info.value
            assert call_args["priority"] == NotificationPriority.high.value

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_application_status_change_under_review(self, service):
        """Test notifying application status change to under review"""
        user_id = 1
        application_id = 123
        new_status = "under_review"

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyApplicationStatusChange(
                user_id=user_id, application_id=application_id, new_status=new_status
            )

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert "審核中" in call_args["message"]  # Under review message
            assert call_args["notification_type"] == NotificationType.info.value
            assert call_args["priority"] == NotificationPriority.normal.value

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_document_required_with_deadline(self, service):
        """Test notifying required documents with deadline"""
        user_id = 1
        application_id = 123
        required_documents = ["成績單", "推薦信", "證明文件"]
        deadline = datetime.now() + timedelta(days=7)

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyDocumentRequired(
                user_id=user_id,
                application_id=application_id,
                required_documents=required_documents,
                deadline=deadline,
            )

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert call_args["user_id"] == user_id
            assert call_args["title"] == "申請文件補充通知"
            assert call_args["title_en"] == "Document Requirement Notification"
            assert "成績單、推薦信、證明文件" in call_args["message"]
            assert call_args["notification_type"] == NotificationType.warning.value
            assert call_args["priority"] == NotificationPriority.high.value
            assert call_args["expires_at"] == deadline

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_document_required_without_deadline(self, service):
        """Test notifying required documents without deadline"""
        user_id = 1
        application_id = 123
        required_documents = ["成績單"]

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyDocumentRequired(
                user_id=user_id,
                application_id=application_id,
                required_documents=required_documents,
                deadline=None,
            )

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert "成績單" in call_args["message"]
            assert "請於" not in call_args["message"]  # No deadline text
            assert call_args["expires_at"] is None

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_deadline_reminder_multiple_days(self, service):
        """Test deadline reminder with multiple days left"""
        user_id = 1
        title = "獎學金申請"
        title_en = "Scholarship Application"
        deadline = datetime.now() + timedelta(days=5)
        action_url = "/applications/123"

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyDeadlineReminder(
                user_id=user_id,
                title=title,
                title_en=title_en,
                deadline=deadline,
                action_url=action_url,
            )

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert "5 天後到期" in call_args["message"]
            assert call_args["priority"] == NotificationPriority.high.value
            assert call_args["notification_type"] == NotificationType.reminder.value

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_deadline_reminder_tomorrow(self, service):
        """Test deadline reminder with one day left"""
        user_id = 1
        title = "獎學金申請"
        deadline = datetime.now() + timedelta(days=1)

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyDeadlineReminder(user_id=user_id, title=title, deadline=deadline)

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert "明天到期" in call_args["message"]
            assert call_args["priority"] == NotificationPriority.URGENT.value

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_notify_deadline_reminder_expired(self, service):
        """Test deadline reminder when deadline has passed"""
        user_id = 1
        title = "獎學金申請"
        deadline = datetime.now() - timedelta(days=1)  # Yesterday

        with patch.object(service, "createUserNotification") as mock_create:
            mock_notification = Mock(spec=Notification)
            mock_create.return_value = mock_notification

            result = await service.notifyDeadlineReminder(user_id=user_id, title=title, deadline=deadline)

            # Verify createUserNotification was called with correct parameters
            call_args = mock_create.call_args[1]

            assert "已到期" in call_args["message"]
            assert call_args["priority"] == NotificationPriority.URGENT.value

            assert result == mock_notification

    @pytest.mark.asyncio
    async def test_bulk_notify_users_success(self, service):
        """Test bulk notification to multiple users"""
        user_ids = [1, 2, 3]
        title = "系統通知"
        message = "重要系統消息"

        with (
            patch.object(service.db, "add_all") as mock_add_all,
            patch.object(service.db, "commit") as mock_commit,
            patch.object(service.db, "refresh") as mock_refresh,
        ):
            # Mock created notifications
            created_notifications = [Mock(spec=Notification) for _ in user_ids]
            for i, notification in enumerate(created_notifications):
                notification.id = i + 1
                notification.user_id = user_ids[i]

            with patch(
                "app.models.notification.Notification",
                side_effect=created_notifications,
            ):
                result = await service.bulkNotifyUsers(
                    user_ids=user_ids,
                    title=title,
                    message=message,
                    notification_type=NotificationType.info.value,
                    priority=NotificationPriority.high.value,
                )

                # Verify database operations
                mock_add_all.assert_called_once()
                mock_commit.assert_called_once()
                assert mock_refresh.call_count == len(user_ids)

                # Verify result
                assert len(result) == len(user_ids)
                assert result == created_notifications

    @pytest.mark.asyncio
    async def test_get_user_notifications_personal_only(self, service):
        """Test getting user notifications (personal notifications only)"""
        user_id = 1
        mock_notifications = [Mock(spec=Notification) for _ in range(3)]

        # Set up mock notifications
        for i, notification in enumerate(mock_notifications):
            notification.id = i + 1
            notification.user_id = user_id  # Personal notification
            notification.title = f"Notification {i+1}"
            notification.message = f"Message {i+1}"
            notification.is_read = False
            notification.created_at = datetime.now()
            notification.expires_at = None
            notification.meta_data = {}

        with patch.object(service.db, "execute") as mock_execute:
            # Mock notification query result
            mock_execute.return_value.scalars.return_value.all.return_value = mock_notifications

            # Mock read records query (empty)
            mock_execute.return_value.scalars.return_value.all.side_effect = [
                mock_notifications,  # First call for notifications
                [],  # Second call for read records
            ]

            result = await service.getUserNotifications(user_id=user_id)

            # Verify result structure
            assert len(result) == 3
            for i, notification_data in enumerate(result):
                assert notification_data["id"] == i + 1
                assert notification_data["title"] == f"Notification {i+1}"
                assert notification_data["message"] == f"Message {i+1}"
                assert notification_data["is_read"] is False

    @pytest.mark.asyncio
    async def test_get_unread_notification_count(self, service):
        """Test getting unread notification count"""
        user_id = 1

        with patch.object(service.db, "execute") as mock_execute:
            # Mock personal notifications count (3 unread)
            # Mock system notifications count (2 unread)
            mock_execute.return_value.scalar.side_effect = [3, 2]

            result = await service.getUnreadNotificationCount(user_id)

            # Total should be 3 + 2 = 5
            assert result == 5

            # Verify both queries were executed
            assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_mark_notification_as_read_personal(self, service):
        """Test marking personal notification as read"""
        notification_id = 1
        user_id = 1

        # Create mock notification (personal)
        mock_notification = Mock(spec=Notification)
        mock_notification.id = notification_id
        mock_notification.user_id = user_id
        mock_notification.mark_as_read = Mock()

        with patch.object(service.db, "execute") as mock_execute, patch.object(service.db, "commit") as mock_commit:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_notification

            result = await service.markNotificationAsRead(notification_id, user_id)

            # Verify notification was marked as read
            mock_notification.mark_as_read.assert_called_once()
            mock_commit.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_mark_notification_as_read_system_new_record(self, service):
        """Test marking system notification as read (creating new read record)"""
        notification_id = 1
        user_id = 1

        # Create mock system notification
        mock_notification = Mock(spec=Notification)
        mock_notification.id = notification_id
        mock_notification.user_id = None  # System notification

        with (
            patch.object(service.db, "execute") as mock_execute,
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "commit") as mock_commit,
        ):
            # Mock notification query
            mock_execute.return_value.scalar_one_or_none.side_effect = [
                mock_notification,  # Notification found
                None,  # No existing read record
            ]

            result = await service.markNotificationAsRead(notification_id, user_id)

            # Verify read record was created
            mock_add.assert_called_once()
            added_record = mock_add.call_args[0][0]
            assert hasattr(added_record, "notification_id")
            assert hasattr(added_record, "user_id")

            mock_commit.assert_called_once()
            assert result is True

    @pytest.mark.asyncio
    async def test_mark_notification_as_read_not_found(self, service):
        """Test marking notification as read when notification not found"""
        notification_id = 999
        user_id = 1

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = None

            result = await service.markNotificationAsRead(notification_id, user_id)

            assert result is False

    @pytest.mark.asyncio
    async def test_mark_all_notifications_as_read(self, service):
        """Test marking all notifications as read for a user"""
        user_id = 1

        with (
            patch.object(service.db, "execute") as mock_execute,
            patch.object(service.db, "add_all") as mock_add_all,
            patch.object(service.db, "commit") as mock_commit,
        ):
            # Mock personal update result
            mock_personal_result = Mock()
            mock_personal_result.rowcount = 3

            # Mock system notifications query result
            mock_system_result = Mock()
            mock_system_result.fetchall.return_value = [
                (1,),
                (2,),
                (3,),
            ]  # 3 system notifications

            mock_execute.side_effect = [
                mock_personal_result,  # Personal update result
                mock_system_result,  # System notifications query result
            ]

            result = await service.markAllNotificationsAsRead(user_id)

            # Verify read records were created for system notifications
            mock_add_all.assert_called_once()
            added_records = mock_add_all.call_args[0][0]
            assert len(added_records) == 3  # 3 system notifications

            mock_commit.assert_called_once()

            # Total should be 3 personal + 3 system = 6
            assert result == 6

    @pytest.mark.asyncio
    async def test_get_user_notifications_with_filters(self, service):
        """Test getting user notifications with filters"""
        user_id = 1

        with patch.object(service.db, "execute") as mock_execute:
            mock_notifications = []
            mock_execute.return_value.scalars.return_value.all.side_effect = [
                mock_notifications,  # Notifications query
                [],  # Read records query
            ]

            result = await service.getUserNotifications(
                user_id=user_id,
                skip=10,
                limit=20,
                unread_only=True,
                notification_type=NotificationType.warning.value,
            )

            # Verify query was executed with filters
            assert mock_execute.call_count >= 1
            assert isinstance(result, list)
