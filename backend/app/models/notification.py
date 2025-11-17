"""
Enhanced notification system for Facebook-style notifications
"""

import enum
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class NotificationChannel(enum.Enum):
    """Notification delivery channels"""

    in_app = "in_app"
    email = "email"
    sms = "sms"
    push = "push"


class NotificationType(enum.Enum):
    """Enhanced notification types for scholarship platform"""

    # Legacy types (maintain backward compatibility)
    info = "info"
    warning = "warning"
    error = "error"
    success = "success"
    reminder = "reminder"

    # Application lifecycle
    application_submitted = "application_submitted"
    application_approved = "application_approved"
    application_rejected = "application_rejected"
    application_requires_review = "application_requires_review"
    application_under_review = "application_under_review"

    # Document management
    document_required = "document_required"
    document_approved = "document_approved"
    document_rejected = "document_rejected"

    # Deadlines and reminders
    deadline_approaching = "deadline_approaching"
    deadline_extended = "deadline_extended"
    review_deadline = "review_deadline"
    application_deadline = "application_deadline"

    # New opportunities
    new_scholarship_available = "new_scholarship_available"
    matching_scholarship = "matching_scholarship"
    scholarship_opening_soon = "scholarship_opening_soon"

    # Review process
    professor_review_requested = "professor_review_requested"
    professor_review_completed = "professor_review_completed"
    professor_assignment = "professor_assignment"
    admin_review_requested = "admin_review_requested"

    # System and admin
    system_maintenance = "system_maintenance"
    admin_message = "admin_message"
    account_update = "account_update"
    security_alert = "security_alert"


class NotificationPriority(enum.Enum):
    """Enhanced notification priority levels"""

    low = "low"  # General announcements
    normal = "normal"  # Status updates, deadlines
    high = "high"  # Application approvals/rejections
    urgent = "urgent"  # System alerts, critical issues (formerly CRITICAL)


class NotificationFrequency(enum.Enum):
    """Notification delivery frequency"""

    immediate = "immediate"
    daily = "daily"
    weekly = "weekly"
    disabled = "disabled"


class Notification(Base):
    """Enhanced notification model with Facebook-style features"""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 系統公告的 user_id 為 null

    # Enhanced notification content
    title = Column(String(255), nullable=False)
    title_en = Column(String(255))
    message = Column(Text, nullable=False)
    message_en = Column(Text)

    # Enhanced type system with backward compatibility
    notification_type = Column(
        Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj]),
        default=NotificationType.info,
        nullable=False,
        index=True,
    )

    # Enhanced priority system
    priority = Column(
        Enum(NotificationPriority, values_callable=lambda obj: [e.value for e in obj]),
        default=NotificationPriority.normal,
        nullable=False,
        index=True,
    )

    # Delivery channel
    channel = Column(
        Enum(NotificationChannel, values_callable=lambda obj: [e.value for e in obj]),
        default=NotificationChannel.in_app,
        nullable=False,
    )

    # Enhanced metadata and context
    data = Column(JSON, default={})  # Facebook-style flexible data storage
    href = Column(String(500))  # Direct click-through link

    # Legacy fields (maintain backward compatibility)
    related_resource_type = Column(String(50))  # application, review, system, etc.
    related_resource_id = Column(Integer)
    action_url = Column(String(500))  # Deprecated in favor of href
    meta_data = Column(JSON)  # Deprecated in favor of data

    # Enhanced state management
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    is_dismissed = Column(Boolean, default=False, nullable=False)  # Legacy
    is_archived = Column(Boolean, default=False, nullable=False)
    is_hidden = Column(Boolean, default=False, nullable=False)

    # Enhanced delivery tracking
    send_email = Column(Boolean, default=False)  # Legacy
    email_sent = Column(Boolean, default=False)  # Legacy
    email_sent_at = Column(DateTime(timezone=True))  # Legacy

    # Facebook-style grouping and batching
    group_key = Column(String(100), nullable=True, index=True)  # For grouping similar notifications
    batch_id = Column(String(50), nullable=True)  # For batched notifications

    # Enhanced timing
    scheduled_at = Column(DateTime(timezone=True), nullable=True)  # Legacy: renamed to scheduled_for
    scheduled_for = Column(DateTime(timezone=True), nullable=True, index=True)  # For delayed notifications
    expires_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Enhanced timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="notifications")
    read_records = relationship("NotificationRead", back_populates="notification", cascade="all, delete-orphan")

    # Enhanced indexes for Facebook-style performance
    __table_args__ = (
        Index("idx_notifications_user_unread", "user_id", "is_read", "created_at"),
        Index("idx_notifications_type_created", "notification_type", "created_at"),
        Index("idx_notifications_group_key", "group_key", "created_at"),
        Index("idx_notifications_priority_scheduled", "priority", "scheduled_for"),
    )

    def __repr__(self):
        return f"<Notification(id={self.id}, user_id={self.user_id}, notification_type={self.notification_type}, is_read={self.is_read})>"

    @property
    def is_expired(self) -> bool:
        """Check if notification is expired"""
        if self.expires_at:
            return bool(datetime.now(timezone.utc) > self.expires_at)
        return False

    @property
    def is_urgent(self) -> bool:
        """Check if notification is urgent"""
        return bool(self.priority in [NotificationPriority.urgent, NotificationPriority.high])

    @property
    def is_critical(self) -> bool:
        """Check if notification is critical priority"""
        return bool(self.priority == NotificationPriority.urgent)

    @property
    def is_system_announcement(self) -> bool:
        """Check if this is a system announcement"""
        return self.user_id is None

    @property
    def age_in_hours(self) -> float:
        """Get notification age in hours (Facebook-style)"""
        return (datetime.now(timezone.utc) - self.created_at).total_seconds() / 3600

    @property
    def effective_href(self) -> Optional[str]:
        """Get effective href, preferring new href over legacy action_url"""
        return self.href or self.action_url

    @property
    def effective_data(self) -> Dict[str, Any]:
        """Get effective data, merging legacy meta_data with new data"""
        result = {}
        if self.meta_data:
            result.update(self.meta_data)
        if self.data:
            result.update(self.data)
        return result

    def mark_as_read(self) -> None:
        """Enhanced mark as read with timezone support"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.now(timezone.utc)

    def mark_as_unread(self) -> None:
        """Mark notification as unread (Facebook-style)"""
        if self.is_read:
            self.is_read = False
            self.read_at = None

    def archive(self) -> None:
        """Archive notification (Facebook-style)"""
        self.is_archived = True

    def hide(self) -> None:
        """Hide notification from user"""
        self.is_hidden = True

    def dismiss(self) -> None:
        """Dismiss notification (legacy support)"""
        self.is_dismissed = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary for API responses (Facebook-style)"""
        return {
            "id": self.id,
            "type": (
                self.notification_type.value
                if isinstance(self.notification_type, NotificationType)
                else self.notification_type
            ),
            "title": self.title,
            "title_en": self.title_en,
            "message": self.message,
            "message_en": self.message_en,
            "data": self.effective_data,
            "href": self.effective_href,
            "is_read": self.is_read,
            "is_archived": self.is_archived,
            "is_hidden": self.is_hidden,
            "priority": self.priority.value if isinstance(self.priority, NotificationPriority) else self.priority,
            "channel": self.channel.value if isinstance(self.channel, NotificationChannel) else self.channel,
            "created_at": self.created_at.isoformat(),
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "group_key": self.group_key,
            "age_in_hours": self.age_in_hours,
            "is_expired": self.is_expired,
            "is_urgent": self.is_urgent,
            "is_system_announcement": self.is_system_announcement,
        }


class NotificationRead(Base):
    """Track per-user read status for notifications"""

    __tablename__ = "notification_reads"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # 讀取狀態
    is_read = Column(Boolean, default=True)  # 創建記錄就表示已讀
    read_at = Column(DateTime(timezone=True), server_default=func.now())

    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 關聯
    notification = relationship("Notification", back_populates="read_records")
    user = relationship("User")

    # 確保每個用戶對每個通知只有一個讀取記錄
    __table_args__ = (UniqueConstraint("notification_id", "user_id", name="_notification_user_read_uc"),)

    def __repr__(self):
        return f"<NotificationRead(notification_id={self.notification_id}, user_id={self.user_id}, read_at={self.read_at})>"


class NotificationPreference(Base):
    """
    User notification preferences - Facebook-style granular control
    """

    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    notification_type = Column(
        Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj]), nullable=False
    )

    # Channel preferences
    in_app_enabled = Column(Boolean, default=True, nullable=False)
    email_enabled = Column(Boolean, default=True, nullable=False)
    sms_enabled = Column(Boolean, default=False, nullable=False)
    push_enabled = Column(Boolean, default=False, nullable=False)

    # Frequency control
    frequency = Column(
        Enum(NotificationFrequency, values_callable=lambda obj: [e.value for e in obj]),
        default=NotificationFrequency.immediate,
        nullable=False,
    )

    # Time preferences
    quiet_hours_start = Column(String(5), nullable=True)  # Format: "22:00"
    quiet_hours_end = Column(String(5), nullable=True)  # Format: "07:00"
    timezone = Column(String(50), default="UTC", nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User")

    # Unique constraint
    __table_args__ = (UniqueConstraint("user_id", "notification_type", name="_user_notification_type_uc"),)

    def __repr__(self):
        return f"<NotificationPreference(user_id={self.user_id}, type={self.notification_type}, frequency={self.frequency})>"

    def is_enabled_for_channel(self, channel: NotificationChannel) -> bool:
        """Check if notifications are enabled for a specific channel"""
        channel_map = {
            NotificationChannel.in_app: self.in_app_enabled,
            NotificationChannel.email: self.email_enabled,
            NotificationChannel.sms: self.sms_enabled,
            NotificationChannel.push: self.push_enabled,
        }
        return channel_map.get(channel, False)

    def is_in_quiet_hours(self, current_time: datetime = None) -> bool:
        """Check if current time is within user's quiet hours"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False

        if current_time is None:
            current_time = datetime.now(timezone.utc)

        # Convert to user's timezone and check
        # This is a simplified version - in production you'd use proper timezone handling
        current_hour_minute = current_time.strftime("%H:%M")

        if self.quiet_hours_start <= self.quiet_hours_end:
            # Same day quiet hours (e.g., 09:00 to 17:00)
            return self.quiet_hours_start <= current_hour_minute <= self.quiet_hours_end
        else:
            # Overnight quiet hours (e.g., 22:00 to 07:00 next day)
            return current_hour_minute >= self.quiet_hours_start or current_hour_minute <= self.quiet_hours_end


class NotificationTemplate(Base):
    """
    Notification templates for consistent messaging
    """

    __tablename__ = "notification_templates"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(
        Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj]), unique=True, nullable=False
    )

    # Template content
    title_template = Column(String(255), nullable=False)
    title_template_en = Column(String(255), nullable=True)
    message_template = Column(Text, nullable=False)
    message_template_en = Column(Text, nullable=True)
    href_template = Column(String(500), nullable=True)  # URL template with placeholders

    # Default settings
    default_channels = Column(JSON, default=["in_app"])  # Default delivery channels
    default_priority = Column(
        Enum(NotificationPriority, values_callable=lambda obj: [e.value for e in obj]),
        default=NotificationPriority.normal,
    )

    # Template variables documentation
    variables = Column(JSON, default={})  # Available template variables and their descriptions

    # Settings
    is_active = Column(Boolean, default=True, nullable=False)
    requires_user_action = Column(Boolean, default=False, nullable=False)  # Whether notification requires user action

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<NotificationTemplate(type={self.type}, is_active={self.is_active})>"

    def render(self, variables: Dict[str, Any], language: str = "zh") -> Dict[str, str]:
        """Render template with provided variables"""
        if language == "en" and self.title_template_en and self.message_template_en:
            title = self.title_template_en
            message = self.message_template_en
        else:
            title = self.title_template
            message = self.message_template

        href = self.href_template

        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            title = title.replace(placeholder, str(value))
            message = message.replace(placeholder, str(value))
            if href:
                href = href.replace(placeholder, str(value))

        return {"title": title, "message": message, "href": href}


class NotificationQueue(Base):
    """
    Queue for batched and scheduled notifications - Facebook-style batching
    """

    __tablename__ = "notification_queue"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Queue metadata
    batch_id = Column(String(50), nullable=False, index=True)
    notification_type = Column(
        Enum(NotificationType, values_callable=lambda obj: [e.value for e in obj]), nullable=False
    )
    priority = Column(
        Enum(NotificationPriority, values_callable=lambda obj: [e.value for e in obj]),
        default=NotificationPriority.normal,
    )

    # Content
    notifications_data = Column(JSON, nullable=False)  # Array of notification data
    aggregated_content = Column(JSON, nullable=True)  # Pre-computed aggregated content

    # Scheduling
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=3)

    # Status
    status = Column(String(20), default="pending")  # pending, processing, sent, failed
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<NotificationQueue(id={self.id}, batch_id={self.batch_id}, status={self.status})>"
