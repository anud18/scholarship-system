"""
Pydantic schemas for email management
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.email_management import EmailCategory, EmailStatus, ScheduleStatus


class EmailHistoryBase(BaseModel):
    """Base schema for email history"""

    recipient_email: str
    cc_emails: Optional[str] = None
    bcc_emails: Optional[str] = None
    subject: str
    body: str
    template_key: Optional[str] = None
    email_category: Optional[EmailCategory] = None
    application_id: Optional[int] = None
    scholarship_type_id: Optional[int] = None
    sent_by_user_id: Optional[int] = None
    sent_by_system: bool = True
    status: EmailStatus
    error_message: Optional[str] = None
    retry_count: int = 0
    email_size_bytes: Optional[int] = None


class EmailHistoryRead(EmailHistoryBase):
    """Schema for reading email history"""

    id: int
    sent_at: datetime

    # Related entity names for display
    application_app_id: Optional[str] = None
    scholarship_type_name: Optional[str] = None
    sent_by_username: Optional[str] = None
    template_description: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_relations(cls, obj):
        """Create schema from ORM object with related data"""
        data = {
            "id": obj.id,
            "recipient_email": obj.recipient_email,
            "cc_emails": obj.cc_emails,
            "bcc_emails": obj.bcc_emails,
            "subject": obj.subject,
            "body": obj.body,
            "template_key": obj.template_key,
            "email_category": obj.email_category,
            "application_id": obj.application_id,
            "scholarship_type_id": obj.scholarship_type_id,
            "sent_by_user_id": obj.sent_by_user_id,
            "sent_by_system": obj.sent_by_system,
            "status": obj.status,
            "error_message": obj.error_message,
            "sent_at": obj.sent_at,
            "retry_count": obj.retry_count,
            "email_size_bytes": obj.email_size_bytes,
            # Related data
            "application_app_id": obj.application.app_id if obj.application else None,
            "scholarship_type_name": obj.scholarship_type.name if obj.scholarship_type else None,
            "sent_by_username": obj.sent_by.nycu_id if obj.sent_by else None,
            "template_description": obj.template.key if obj.template else None,
        }
        return cls(**data)


class EmailHistoryListResponse(BaseModel):
    """Response schema for paginated email history"""

    items: List[EmailHistoryRead]
    total: int
    skip: int
    limit: int


class ScheduledEmailBase(BaseModel):
    """Base schema for scheduled email"""

    recipient_email: str
    cc_emails: Optional[str] = None
    bcc_emails: Optional[str] = None
    subject: str
    body: str
    template_key: Optional[str] = None
    email_category: Optional[EmailCategory] = None
    scheduled_for: datetime
    application_id: Optional[int] = None
    scholarship_type_id: Optional[int] = None
    requires_approval: bool = False
    priority: int = Field(default=5, ge=1, le=10)


class ScheduledEmailCreate(ScheduledEmailBase):
    """Schema for creating scheduled email"""

    created_by_user_id: int


class ScheduledEmailUpdate(BaseModel):
    """Schema for updating scheduled email"""

    approval_notes: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


class ScheduledEmailRead(ScheduledEmailBase):
    """Schema for reading scheduled email"""

    id: int
    status: ScheduleStatus
    approved_by_user_id: Optional[int] = None
    approved_at: Optional[datetime] = None
    approval_notes: Optional[str] = None
    created_by_user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    retry_count: int = 0
    last_error: Optional[str] = None

    # Related entity names for display
    application_app_id: Optional[str] = None
    scholarship_type_name: Optional[str] = None
    created_by_username: Optional[str] = None
    approved_by_username: Optional[str] = None
    template_description: Optional[str] = None

    # Computed properties
    is_due: bool = False
    is_ready_to_send: bool = False

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_relations(cls, obj):
        """Create schema from ORM object with related data"""
        data = {
            "id": obj.id,
            "recipient_email": obj.recipient_email,
            "cc_emails": obj.cc_emails,
            "bcc_emails": obj.bcc_emails,
            "subject": obj.subject,
            "body": obj.body,
            "template_key": obj.template_key,
            "email_category": obj.email_category,
            "scheduled_for": obj.scheduled_for,
            "status": obj.status,
            "application_id": obj.application_id,
            "scholarship_type_id": obj.scholarship_type_id,
            "requires_approval": obj.requires_approval,
            "approved_by_user_id": obj.approved_by_user_id,
            "approved_at": obj.approved_at,
            "approval_notes": obj.approval_notes,
            "created_by_user_id": obj.created_by_user_id,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "retry_count": obj.retry_count,
            "last_error": obj.last_error,
            "priority": obj.priority,
            # Related data
            "application_app_id": obj.application.app_id if obj.application else None,
            "scholarship_type_name": obj.scholarship_type.name if obj.scholarship_type else None,
            "created_by_username": obj.created_by.nycu_id if obj.created_by else None,
            "approved_by_username": obj.approved_by.nycu_id if obj.approved_by else None,
            "template_description": obj.template.key if obj.template else None,
            # Computed properties
            "is_due": obj.is_due,
            "is_ready_to_send": obj.is_ready_to_send,
        }
        return cls(**data)


class ScheduledEmailListResponse(BaseModel):
    """Response schema for paginated scheduled emails"""

    items: List[ScheduledEmailRead]
    total: int
    skip: int
    limit: int


class EmailProcessingStats(BaseModel):
    """Schema for email processing statistics"""

    processed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0


class EmailFilterOptions(BaseModel):
    """Schema for email filter options"""

    categories: List[str]
    email_statuses: List[str]
    schedule_statuses: List[str]
    scholarship_types: List[Dict[str, Any]]  # {id, name}


class EmailSummaryStats(BaseModel):
    """Schema for email summary statistics"""

    total_sent_today: int = 0
    total_sent_this_week: int = 0
    total_sent_this_month: int = 0
    total_failed_today: int = 0
    scheduled_pending: int = 0
    scheduled_due: int = 0
    scheduled_awaiting_approval: int = 0
    by_category: Dict[str, int] = {}
    by_scholarship_type: Dict[str, int] = {}


class SendTestEmailRequest(BaseModel):
    """Schema for sending test email"""

    template_key: str = Field(..., description="郵件模板鍵名")
    recipient_email: str = Field(..., description="測試收件人信箱")
    test_data: Dict[str, Any] = Field(default_factory=dict, description="測試數據（用於模板變數替換）")
    subject_override: Optional[str] = Field(None, description="覆蓋主旨（可選）")
    body_override: Optional[str] = Field(None, description="覆蓋內容（可選）")


class SendTestEmailResponse(BaseModel):
    """Schema for test email response"""

    success: bool
    message: str
    email_id: Optional[int] = None
    rendered_subject: Optional[str] = None
    rendered_body: Optional[str] = None
    error: Optional[str] = None


class SimpleTestEmailRequest(BaseModel):
    """Schema for sending simple test email without template"""

    recipient_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body (plain text or HTML)")


class SimpleTestEmailResponse(BaseModel):
    """Schema for simple test email response"""

    success: bool
    message: str
    email_id: Optional[int] = None
    error: Optional[str] = None
