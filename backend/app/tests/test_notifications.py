"""
Tests for notification system
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.main import app
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User, UserRole, UserType
from app.services.notification_service import NotificationService


class TestNotificationService:
    """Test notification service functionality"""

    @pytest.mark.asyncio
    async def test_create_user_notification(self, db: AsyncSession):
        """Test creating a user notification"""
        # Create test user
        user = User(
            email="test@example.com",
            nycu_id="testuser",
            name="Test User",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Create notification service
        notification_service = NotificationService(db)

        # Create notification
        notification = await notification_service.createUserNotification(
            user_id=user.id,
            title="測試通知",
            title_en="Test Notification",
            message="這是一個測試通知",
            message_en="This is a test notification",
            notification_type=NotificationType.info,
            priority=NotificationPriority.normal,
        )

        # Assertions
        assert notification.id is not None
        assert notification.user_id == user.id
        assert notification.title == "測試通知"
        assert notification.title_en == "Test Notification"
        assert notification.message == "這是一個測試通知"
        assert notification.message_en == "This is a test notification"
        assert notification.notification_type == NotificationType.info
        assert notification.priority == NotificationPriority.normal
        assert notification.is_read is False
        assert notification.is_dismissed is False

    @pytest.mark.asyncio
    async def test_create_system_announcement(self, db: AsyncSession):
        """Test creating a system announcement"""
        notification_service = NotificationService(db)

        notification = await notification_service.createSystemAnnouncement(
            title="系統公告",
            title_en="System Announcement",
            message="這是一個系統公告",
            message_en="This is a system announcement",
            notification_type=NotificationType.warning,
            priority=NotificationPriority.high,
        )

        # Assertions
        assert notification.id is not None
        assert notification.user_id is None  # System announcement
        assert notification.title == "系統公告"
        assert notification.related_resource_type == "system"
        assert notification.notification_type == NotificationType.warning
        assert notification.priority == NotificationPriority.high

    @pytest.mark.asyncio
    async def test_notify_application_status_change(self, db: AsyncSession):
        """Test application status change notification"""
        # Create test user
        user = User(
            email="student@example.com",
            nycu_id="student",
            name="Student User",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        notification_service = NotificationService(db)

        # Test approved status.
        # Patch the delivery side-effect: it calls notification.to_dict() -> age_in_hours,
        # which subtracts an aware now() from created_at. Under SQLite, DateTime(timezone=True)
        # round-trips as a naive datetime (Postgres keeps it aware), so the subtraction raises.
        # The notification is still created/refreshed for real, so all assertions stay live.
        with patch.object(NotificationService, "_deliver_notification", new=AsyncMock()):
            notification = await notification_service.notifyApplicationStatusChange(
                user_id=user.id,
                application_id=1,
                new_status="approved",
                application_title="學術優秀獎學金",
            )

        assert notification.user_id == user.id
        assert notification.notification_type == NotificationType.success
        assert notification.priority == NotificationPriority.high
        assert "恭喜" in notification.message
        # English copy is stored in the JSON data payload by create_notification,
        # not in the message_en column.
        assert "Congratulations" in notification.data["message_en"]


class TestNotificationAPI:
    """Test notification API endpoints"""

    @pytest.fixture
    async def test_user_with_notifications(self, db: AsyncSession):
        """Create test user with some notifications"""
        user = User(
            email="user@example.com",
            nycu_id="user",
            name="Test User",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Create some test notifications
        notifications = [
            Notification(
                user_id=user.id,
                title="個人通知 1",
                message="這是第一個個人通知",
                notification_type=NotificationType.info,
                priority=NotificationPriority.normal,
                is_read=False,
            ),
            Notification(
                user_id=user.id,
                title="個人通知 2",
                message="這是第二個個人通知",
                notification_type=NotificationType.warning,
                priority=NotificationPriority.high,
                is_read=True,
            ),
            Notification(
                user_id=None,  # System announcement
                title="系統公告",
                message="這是系統公告",
                notification_type=NotificationType.info,
                priority=NotificationPriority.normal,
                related_resource_type="system",
                is_read=False,
            ),
        ]

        db.add_all(notifications)
        await db.commit()

        return user

    @pytest.fixture
    def auth_override(self, test_user_with_notifications: User):
        """Override get_current_user to authenticate as the notifications owner."""
        app.dependency_overrides[get_current_user] = lambda: test_user_with_notifications
        yield
        # The client fixture also clears overrides, but be explicit here.
        app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_get_user_notifications(self, client: AsyncClient, test_user_with_notifications: User, auth_override):
        """Test getting user notifications"""
        response = await client.get("/api/v1/notifications")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 2  # User notifications + system announcements

    @pytest.mark.asyncio
    async def test_get_unread_count(self, client: AsyncClient, test_user_with_notifications: User, auth_override):
        """Test getting unread notification count"""
        response = await client.get("/api/v1/notifications/unread-count")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert isinstance(data["data"], int)
        assert data["data"] >= 1  # At least one unread notification

    @pytest.mark.asyncio
    async def test_mark_notification_as_read(
        self,
        client: AsyncClient,
        test_user_with_notifications: User,
        auth_override,
        db: AsyncSession,
    ):
        """Test marking a notification as read"""
        # Get an unread personal notification
        result = await db.execute(
            select(Notification)
            .where(
                Notification.user_id == test_user_with_notifications.id,
                Notification.is_read.is_(False),
            )
            .limit(1)
        )
        notification = result.scalar_one_or_none()
        assert notification is not None

        response = await client.patch(f"/api/v1/notifications/{notification.id}/read")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True

        # Confirm the underlying row was flipped to read.
        await db.refresh(notification)
        assert notification.is_read is True

    @pytest.mark.asyncio
    async def test_dismiss_notification(
        self,
        client: AsyncClient,
        test_user_with_notifications: User,
        auth_override,
        db: AsyncSession,
    ):
        """Test dismissing a notification"""
        # Get a notification
        result = await db.execute(
            select(Notification).where(Notification.user_id == test_user_with_notifications.id).limit(1)
        )
        notification = result.scalar_one_or_none()
        assert notification is not None

        response = await client.patch(f"/api/v1/notifications/{notification.id}/dismiss")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True


class TestNotificationIntegration:
    """Integration tests for notification system"""

    @pytest.mark.asyncio
    async def test_notification_workflow(self, db: AsyncSession):
        """Test complete notification workflow"""
        # Create users
        student = User(
            email="student@example.com",
            nycu_id="student",
            name="Student User",
            user_type=UserType.student,
            role=UserRole.student,
        )
        admin = User(
            email="admin@example.com",
            nycu_id="admin",
            name="Admin User",
            user_type=UserType.employee,
            role=UserRole.admin,
        )

        db.add_all([student, admin])
        await db.commit()
        await db.refresh(student)
        await db.refresh(admin)

        notification_service = NotificationService(db)

        # 1. Admin creates system announcement
        system_announcement = await notification_service.createSystemAnnouncement(
            title="重要公告",
            message="這是一個重要的系統公告",
            notification_type=NotificationType.warning,
            priority=NotificationPriority.high,
        )

        # 2. System sends application status notification to student.
        # Patch the delivery side-effect (see note in test_notify_application_status_change):
        # to_dict()->age_in_hours fails under SQLite's naive datetime round-trip.
        with patch.object(NotificationService, "_deliver_notification", new=AsyncMock()):
            status_notification = await notification_service.notifyApplicationStatusChange(
                user_id=student.id, application_id=1, new_status="approved"
            )

        # 3. System sends document requirement notification
        doc_notification = await notification_service.notifyDocumentRequired(
            user_id=student.id,
            application_id=1,
            required_documents=["成績單", "在學證明"],
            deadline=datetime.now() + timedelta(days=7),
        )

        # Verify notifications were created
        from sqlalchemy import func

        # Count system announcements (visible to all users)
        system_count = await db.execute(select(func.count(Notification.id)).where(Notification.user_id.is_(None)))
        assert system_count.scalar() == 1

        # Count student's personal notifications
        student_count = await db.execute(select(func.count(Notification.id)).where(Notification.user_id == student.id))
        assert student_count.scalar() == 2

        # Verify notification types and priorities
        assert system_announcement.notification_type == NotificationType.warning
        assert status_notification.notification_type == NotificationType.success
        assert doc_notification.notification_type == NotificationType.warning
        assert doc_notification.priority == NotificationPriority.high
