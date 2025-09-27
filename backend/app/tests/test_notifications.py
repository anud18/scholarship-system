"""
Tests for notification system
"""

from datetime import datetime, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User, UserRole
from app.services.notification_service import NotificationService


class TestNotificationService:
    """Test notification service functionality"""

    @pytest.mark.asyncio
    async def test_create_user_notification(self, db_session: AsyncSession):
        """Test creating a user notification"""
        # Create test user
        user = User(
            email="test@example.com",
            username="testuser",
            hashed_password="hashed_password",
            full_name="Test User",
            role=UserRole.STUDENT,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create notification service
        notification_service = NotificationService(db_session)

        # Create notification
        notification = await notification_service.createUserNotification(
            user_id=user.id,
            title="測試通知",
            title_en="Test Notification",
            message="這是一個測試通知",
            message_en="This is a test notification",
            notification_type=NotificationType.INFO.value,
            priority=NotificationPriority.NORMAL.value,
        )

        # Assertions
        assert notification.id is not None
        assert notification.user_id == user.id
        assert notification.title == "測試通知"
        assert notification.title_en == "Test Notification"
        assert notification.message == "這是一個測試通知"
        assert notification.message_en == "This is a test notification"
        assert notification.notification_type == NotificationType.INFO.value
        assert notification.priority == NotificationPriority.NORMAL.value
        assert notification.is_read is False
        assert notification.is_dismissed is False

    @pytest.mark.asyncio
    async def test_create_system_announcement(self, db_session: AsyncSession):
        """Test creating a system announcement"""
        notification_service = NotificationService(db_session)

        notification = await notification_service.createSystemAnnouncement(
            title="系統公告",
            title_en="System Announcement",
            message="這是一個系統公告",
            message_en="This is a system announcement",
            notification_type=NotificationType.WARNING.value,
            priority=NotificationPriority.HIGH.value,
        )

        # Assertions
        assert notification.id is not None
        assert notification.user_id is None  # System announcement
        assert notification.title == "系統公告"
        assert notification.related_resource_type == "system"
        assert notification.notification_type == NotificationType.WARNING.value
        assert notification.priority == NotificationPriority.HIGH.value

    @pytest.mark.asyncio
    async def test_notify_application_status_change(self, db_session: AsyncSession):
        """Test application status change notification"""
        # Create test user
        user = User(
            email="student@example.com",
            username="student",
            hashed_password="hashed_password",
            full_name="Student User",
            role=UserRole.STUDENT,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        notification_service = NotificationService(db_session)

        # Test approved status
        notification = await notification_service.notifyApplicationStatusChange(
            user_id=user.id,
            application_id=1,
            new_status="approved",
            application_title="學術優秀獎學金",
        )

        assert notification.user_id == user.id
        assert notification.related_resource_type == "application"
        assert notification.related_resource_id == 1
        assert notification.notification_type == NotificationType.SUCCESS.value
        assert notification.priority == NotificationPriority.HIGH.value
        assert "恭喜" in notification.message
        assert "Congratulations" in notification.message_en


class TestNotificationAPI:
    """Test notification API endpoints"""

    @pytest.fixture
    async def test_user_with_notifications(self, db_session: AsyncSession):
        """Create test user with some notifications"""
        user = User(
            email="user@example.com",
            username="user",
            hashed_password="hashed_password",
            full_name="Test User",
            role=UserRole.STUDENT,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # Create some test notifications
        notifications = [
            Notification(
                user_id=user.id,
                title="個人通知 1",
                message="這是第一個個人通知",
                notification_type=NotificationType.INFO.value,
                priority=NotificationPriority.NORMAL.value,
                is_read=False,
            ),
            Notification(
                user_id=user.id,
                title="個人通知 2",
                message="這是第二個個人通知",
                notification_type=NotificationType.WARNING.value,
                priority=NotificationPriority.HIGH.value,
                is_read=True,
            ),
            Notification(
                user_id=None,  # System announcement
                title="系統公告",
                message="這是系統公告",
                notification_type=NotificationType.INFO.value,
                priority=NotificationPriority.NORMAL.value,
                related_resource_type="system",
                is_read=False,
            ),
        ]

        db_session.add_all(notifications)
        await db_session.commit()

        return user

    @pytest.mark.asyncio
    async def test_get_user_notifications(self, client: AsyncClient, test_user_with_notifications: User):
        """Test getting user notifications"""
        # Mock authentication
        # In a real test, you would need to set up proper authentication

        response = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer mock_token_for_{test_user_with_notifications.id}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]) >= 2  # User notifications + system announcements

    @pytest.mark.asyncio
    async def test_get_unread_count(self, client: AsyncClient, test_user_with_notifications: User):
        """Test getting unread notification count"""
        response = await client.get(
            "/api/v1/notifications/unread-count",
            headers={"Authorization": f"Bearer mock_token_for_{test_user_with_notifications.id}"},
        )

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
        db_session: AsyncSession,
    ):
        """Test marking a notification as read"""
        # Get an unread notification
        from sqlalchemy import select

        result = await db_session.execute(
            select(Notification)
            .where(
                Notification.user_id == test_user_with_notifications.id,
                not Notification.is_read,
            )
            .limit(1)
        )
        notification = result.scalar_one_or_none()

        if notification:
            response = await client.patch(
                f"/api/v1/notifications/{notification.id}/read",
                headers={"Authorization": f"Bearer mock_token_for_{test_user_with_notifications.id}"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True
            assert data["data"]["is_read"] is True

    @pytest.mark.asyncio
    async def test_dismiss_notification(
        self,
        client: AsyncClient,
        test_user_with_notifications: User,
        db_session: AsyncSession,
    ):
        """Test dismissing a notification"""
        # Get a notification
        from sqlalchemy import select

        result = await db_session.execute(
            select(Notification).where(Notification.user_id == test_user_with_notifications.id).limit(1)
        )
        notification = result.scalar_one_or_none()

        if notification:
            response = await client.patch(
                f"/api/v1/notifications/{notification.id}/dismiss",
                headers={"Authorization": f"Bearer mock_token_for_{test_user_with_notifications.id}"},
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["success"] is True


class TestNotificationIntegration:
    """Integration tests for notification system"""

    @pytest.mark.asyncio
    async def test_notification_workflow(self, db_session: AsyncSession):
        """Test complete notification workflow"""
        # Create users
        student = User(
            email="student@example.com",
            username="student",
            hashed_password="hashed_password",
            full_name="Student User",
            role=UserRole.STUDENT,
        )
        admin = User(
            email="admin@example.com",
            username="admin",
            hashed_password="hashed_password",
            full_name="Admin User",
            role=UserRole.ADMIN,
        )

        db_session.add_all([student, admin])
        await db_session.commit()
        await db_session.refresh(student)
        await db_session.refresh(admin)

        notification_service = NotificationService(db_session)

        # 1. Admin creates system announcement
        system_announcement = await notification_service.createSystemAnnouncement(
            title="重要公告",
            message="這是一個重要的系統公告",
            notification_type=NotificationType.WARNING.value,
            priority=NotificationPriority.HIGH.value,
        )

        # 2. System sends application status notification to student
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
        from sqlalchemy import func, select

        # Count system announcements (visible to all users)
        system_count = await db_session.execute(
            select(func.count(Notification.id)).where(Notification.user_id.is_(None))
        )
        assert system_count.scalar() == 1

        # Count student's personal notifications
        student_count = await db_session.execute(
            select(func.count(Notification.id)).where(Notification.user_id == student.id)
        )
        assert student_count.scalar() == 2

        # Verify notification types and priorities
        assert system_announcement.notification_type == NotificationType.WARNING.value
        assert status_notification.notification_type == NotificationType.SUCCESS.value
        assert doc_notification.notification_type == NotificationType.WARNING.value
        assert doc_notification.priority == NotificationPriority.HIGH.value
