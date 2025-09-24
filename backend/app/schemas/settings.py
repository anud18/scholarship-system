"""
Settings schemas for API requests and responses
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class SystemSettingBase(BaseModel):
    """Base system setting schema"""

    key: str = Field(..., description="Setting key")
    value: str = Field(..., description="Setting value")
    description: Optional[str] = Field(None, description="Setting description")
    is_public: bool = Field(False, description="Whether this setting is publicly accessible")
    category: str = Field(..., description="Setting category (e.g., 'general', 'email', 'scholarship')")


class SystemSettingCreate(SystemSettingBase):
    """System setting creation schema"""

    pass


class SystemSettingUpdate(BaseModel):
    """System setting update schema"""

    value: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    category: Optional[str] = None


class SystemSettingResponse(SystemSettingBase):
    """System setting response schema"""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailTemplateBase(BaseModel):
    """Base email template schema"""

    key: str = Field(..., description="Template key")
    subject_template: str = Field(..., description="Email subject template")
    body_template: str = Field(..., description="Email body template")
    cc: Optional[List[EmailStr]] = Field(None, description="CC recipients")
    bcc: Optional[List[EmailStr]] = Field(None, description="BCC recipients")
    description: Optional[str] = Field(None, description="Template description")
    variables: Optional[List[str]] = Field(None, description="List of template variables")
    category: str = Field(..., description="Template category (e.g., 'application', 'notification')")


class EmailTemplateCreate(EmailTemplateBase):
    """Email template creation schema"""

    pass


class EmailTemplateUpdate(BaseModel):
    """Email template update schema"""

    subject_template: Optional[str] = None
    body_template: Optional[str] = None
    cc: Optional[List[EmailStr]] = None
    bcc: Optional[List[EmailStr]] = None
    description: Optional[str] = None
    variables: Optional[List[str]] = None
    category: Optional[str] = None


class EmailTemplateResponse(EmailTemplateBase):
    """Email template response schema"""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmailConfig(BaseModel):
    """Email configuration schema"""

    smtp_host: str = Field(..., description="SMTP host")
    smtp_port: int = Field(..., description="SMTP port")
    smtp_user: str = Field(..., description="SMTP username")
    smtp_password: str = Field(..., description="SMTP password")
    use_tls: bool = Field(True, description="Use TLS for SMTP")
    default_from_email: EmailStr = Field(..., description="Default sender email")
    default_from_name: str = Field(..., description="Default sender name")
    reply_to_email: Optional[EmailStr] = Field(None, description="Reply-to email address")
    reply_to_name: Optional[str] = Field(None, description="Reply-to name")


class EmailSendRequest(BaseModel):
    """Email send request schema"""

    template_key: str = Field(..., description="Email template key")
    to_emails: List[EmailStr] = Field(..., description="Recipient email addresses")
    cc: Optional[List[EmailStr]] = Field(None, description="CC recipients")
    bcc: Optional[List[EmailStr]] = Field(None, description="BCC recipients")
    variables: Optional[Dict[str, Any]] = Field(None, description="Template variables")
    attachments: Optional[List[Dict[str, Any]]] = Field(None, description="Email attachments")
