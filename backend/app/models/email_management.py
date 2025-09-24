"""
Email management models for tracking sent emails and scheduled emails
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class EmailStatus(enum.Enum):
    """Email status enum"""

    SENT = "SENT"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    PENDING = "PENDING"


class ScheduleStatus(enum.Enum):
    """Schedule status enum"""

    PENDING = "PENDING"
    SENT = "SENT"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"


class EmailCategory(enum.Enum):
    """Email category enum for different notification types"""

    APPLICATION_WHITELIST = "APPLICATION_WHITELIST"  # 申請通知－白名單
    APPLICATION_STUDENT = "APPLICATION_STUDENT"  # 申請通知－申請者
    RECOMMENDATION_PROFESSOR = "RECOMMENDATION_PROFESSOR"  # 推薦通知－指導教授
    REVIEW_COLLEGE = "REVIEW_COLLEGE"  # 審核通知－學院
    SUPPLEMENT_STUDENT = "SUPPLEMENT_STUDENT"  # 補件通知－申請者
    RESULT_PROFESSOR = "RESULT_PROFESSOR"  # 結果通知－指導教授
    RESULT_COLLEGE = "RESULT_COLLEGE"  # 結果通知－學院
    RESULT_STUDENT = "RESULT_STUDENT"  # 結果通知－申請者
    ROSTER_STUDENT = "ROSTER_STUDENT"  # 造冊通知－申請者
    SYSTEM = "SYSTEM"  # 系統通知
    OTHER = "OTHER"  # 其他


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
    email_category = Column(Enum(EmailCategory), nullable=True, index=True)

    # Related entities (for permission filtering)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=True, index=True)

    # Sender information
    sent_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    sent_by_system = Column(Boolean, default=True, nullable=False)  # True for system auto, False for manual

    # Status tracking
    status = Column(Enum(EmailStatus), default=EmailStatus.SENT, nullable=False, index=True)
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
    email_category = Column(Enum(EmailCategory), nullable=True)

    # Scheduling information
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum(ScheduleStatus), default=ScheduleStatus.PENDING, nullable=False, index=True)

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
        if self.status != ScheduleStatus.PENDING:
            return False
        if self.requires_approval and not self.approved_by_user_id:
            return False
        return True

    def mark_as_sent(self):
        """Mark the scheduled email as sent"""
        self.status = ScheduleStatus.SENT

    def mark_as_failed(self, error_message: str):
        """Mark the scheduled email as failed with error message"""
        self.status = ScheduleStatus.FAILED
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
        self.status = ScheduleStatus.CANCELLED
