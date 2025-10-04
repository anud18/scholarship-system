"""
Email management models for tracking sent emails and scheduled emails
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class EmailStatus(enum.Enum):
    """Email status enum"""

    sent = "sent"
    failed = "failed"
    bounced = "bounced"
    pending = "pending"


class ScheduleStatus(enum.Enum):
    """Schedule status enum"""

    pending = "pending"
    sent = "sent"
    cancelled = "cancelled"
    failed = "failed"


class EmailCategory(enum.Enum):
    """Email category enum for different notification types"""

    application_whitelist = "application_whitelist"  # 申請通知－白名單
    application_student = "application_student"  # 申請通知－申請者
    recommendation_professor = "recommendation_professor"  # 推薦通知－指導教授
    review_college = "review_college"  # 審核通知－學院
    supplement_student = "supplement_student"  # 補件通知－申請者
    result_professor = "result_professor"  # 結果通知－指導教授
    result_college = "result_college"  # 結果通知－學院
    result_student = "result_student"  # 結果通知－申請者
    roster_student = "roster_student"  # 造冊通知－申請者
    system = "system"  # 系統通知
    other = "other"  # 其他


class EmailHistory(Base):
    """Email history model for tracking all sent emails"""

    __tablename__ = "email_history"

    id = Column(Integer, primary_key=True, index=True)

    # Basic email information
    recipient_email = Column(String(255), nullable=False, index=True)
    cc_emails = Column(Text)  # JSON array of CC emails
    bcc_emails = Column(Text)  # JSON array of BCC emails
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)

    # Template and categorization
    template_key = Column(String(100), ForeignKey("email_templates.key"), nullable=True)
    email_category = Column(String(100), nullable=True, index=True)

    # Related entities (for permission filtering)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=True, index=True)

    # Sender information
    sent_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sent_by_system = Column(Boolean, default=True, nullable=False)  # True for system auto, False for manual

    # Status tracking
    status = Column(
        String(20),
        default=EmailStatus.sent.value,
        nullable=False,
        index=True,
    )
    error_message = Column(Text)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Additional metadata
    retry_count = Column(Integer, default=0)
    email_size_bytes = Column(Integer)  # For monitoring

    # Relationships
    template = relationship("EmailTemplate", backref="email_history")
    application = relationship("Application", backref="email_history")
    scholarship_type = relationship("ScholarshipType", backref="email_history")
    sent_by = relationship("User", foreign_keys=[sent_by_user_id], backref="sent_emails")

    # Indexes for performance
    __table_args__ = (
        Index("idx_email_history_recipient_date", "recipient_email", "sent_at"),
        Index("idx_email_history_category_date", "email_category", "sent_at"),
        Index("idx_email_history_scholarship_date", "scholarship_type_id", "sent_at"),
        Index("idx_email_history_status_date", "status", "sent_at"),
    )

    def __repr__(self):
        return f"<EmailHistory(id={self.id}, recipient={self.recipient_email}, status={self.status})>"


class ScheduledEmail(Base):
    """Scheduled email model for emails to be sent later"""

    __tablename__ = "scheduled_emails"

    id = Column(Integer, primary_key=True, index=True)

    # Email content
    recipient_email = Column(String(255), nullable=False, index=True)
    cc_emails = Column(Text)  # JSON array of CC emails
    bcc_emails = Column(Text)  # JSON array of BCC emails
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)

    # Template and categorization
    template_key = Column(String(100), ForeignKey("email_templates.key"), nullable=True)
    email_category = Column(Enum(EmailCategory, values_callable=lambda obj: [e.value for e in obj]), nullable=True)

    # Scheduling information
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(
        Enum(ScheduleStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ScheduleStatus.pending,
        nullable=False,
        index=True,
    )

    # Related entities (for permission filtering)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=True, index=True)

    # Approval workflow
    requires_approval = Column(Boolean, default=False, nullable=False)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_notes = Column(Text)

    # Creation tracking
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Error handling
    retry_count = Column(Integer, default=0)
    last_error = Column(Text)

    # Priority for scheduling
    priority = Column(Integer, default=5)  # 1-10, 1 being highest priority

    # Relationships
    template = relationship("EmailTemplate", backref="scheduled_emails")
    application = relationship("Application", backref="scheduled_emails")
    scholarship_type = relationship("ScholarshipType", backref="scheduled_emails")
    created_by = relationship("User", foreign_keys=[created_by_user_id], backref="created_scheduled_emails")
    approved_by = relationship("User", foreign_keys=[approved_by_user_id], backref="approved_scheduled_emails")

    # Indexes for performance
    __table_args__ = (
        Index("idx_scheduled_email_due", "scheduled_for", "status"),
        Index("idx_scheduled_email_approval", "requires_approval", "approved_by_user_id"),
        Index("idx_scheduled_email_scholarship", "scholarship_type_id", "status"),
        Index("idx_scheduled_email_priority", "priority", "scheduled_for"),
    )

    def __repr__(self):
        return f"<ScheduledEmail(id={self.id}, recipient={self.recipient_email}, status={self.status}, scheduled_for={self.scheduled_for})>"

    @property
    def is_due(self) -> bool:
        """Check if email is due to be sent"""
        return self.scheduled_for <= datetime.now(timezone.utc)

    @property
    def is_ready_to_send(self) -> bool:
        """Check if email is ready to be sent (due and approved if needed)"""
        if not self.is_due:
            return False
        if self.status != ScheduleStatus.pending:
            return False
        if self.requires_approval and not self.approved_by_user_id:
            return False
        return True

    def mark_as_sent(self):
        """Mark the scheduled email as sent"""
        self.status = ScheduleStatus.sent

    def mark_as_failed(self, error_message: str):
        """Mark the scheduled email as failed with error message"""
        self.status = ScheduleStatus.failed
        self.last_error = error_message
        self.retry_count += 1

    def approve(self, approved_by_user_id: int, notes: str = None):
        """Approve the scheduled email"""
        self.approved_by_user_id = approved_by_user_id
        self.approved_at = datetime.now(timezone.utc)
        if notes:
            self.approval_notes = notes

    def cancel(self):
        """Cancel the scheduled email"""
        self.status = ScheduleStatus.cancelled


class EmailTestModeAudit(Base):
    """Email test mode audit log for tracking test mode state changes and email interceptions"""

    __tablename__ = "email_test_mode_audit"

    id = Column(Integer, primary_key=True, index=True)

    # Event information
    event_type = Column(String(50), nullable=False, index=True)
    # Event types: 'enabled', 'disabled', 'expired', 'email_intercepted', 'config_updated'
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # User who triggered the event
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # Configuration snapshots (for state change events)
    config_before = Column(JSONB, nullable=True)
    config_after = Column(JSONB, nullable=True)

    # Email interception details (for email_intercepted events)
    original_recipient = Column(String(255), nullable=True)
    actual_recipient = Column(String(255), nullable=True)
    email_subject = Column(Text, nullable=True)
    session_id = Column(String(100), nullable=True, index=True)

    # Request metadata
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", backref="email_test_mode_audits")

    def __repr__(self):
        return f"<EmailTestModeAudit(id={self.id}, event_type={self.event_type}, timestamp={self.timestamp})>"

    @classmethod
    def log_enabled(cls, user_id: int, config_after: dict, ip_address: str = None, user_agent: str = None):
        """Create audit log for test mode enabled event"""
        return cls(
            event_type="enabled",
            user_id=user_id,
            config_after=config_after,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @classmethod
    def log_disabled(cls, user_id: int, config_before: dict, ip_address: str = None, user_agent: str = None):
        """Create audit log for test mode disabled event"""
        return cls(
            event_type="disabled",
            user_id=user_id,
            config_before=config_before,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    @classmethod
    def log_email_intercepted(
        cls,
        original_recipient: str,
        actual_recipient: str,
        email_subject: str,
        session_id: str,
        user_id: int = None,
    ):
        """Create audit log for email interception event"""
        return cls(
            event_type="email_intercepted",
            user_id=user_id,
            original_recipient=original_recipient,
            actual_recipient=actual_recipient,
            email_subject=email_subject,
            session_id=session_id,
        )

    @classmethod
    def log_expired(cls, config_before: dict):
        """Create audit log for test mode auto-expiration event"""
        return cls(event_type="expired", config_before=config_before)
