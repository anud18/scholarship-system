"""
Common schemas for API responses and pagination
"""

from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.models.system_setting import SendingType

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Standard message response"""

    success: bool = True
    message: str
    trace_id: Optional[str] = None


class ApiResponse(BaseModel, Generic[T]):
    """Standard API response format"""

    success: bool = True
    message: str
    data: Optional[T] = None
    errors: Optional[List[str]] = None
    trace_id: Optional[str] = None


class PaginationParams(BaseModel):
    """Pagination parameters"""

    page: int = Field(1, ge=1, description="Page number")
    size: int = Field(20, ge=1, le=100, description="Items per page")
    sort_by: Optional[str] = Field(None, description="Sort field")
    sort_order: Optional[str] = Field(
        "asc", pattern="^(asc|desc)$", description="Sort order"
    )


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper"""

    items: List[T]
    total: int
    page: int
    size: int
    pages: int

    @property
    def has_next(self) -> bool:
        """Check if there are more pages"""
        return self.page < self.pages

    @property
    def has_prev(self) -> bool:
        """Check if there are previous pages"""
        return self.page > 1


class ValidationErrorDetail(BaseModel):
    """Validation error detail"""

    field: str
    message: str
    value: Any = None


class ErrorResponse(BaseModel):
    """Error response"""

    success: bool = False
    message: str
    errors: Optional[List[ValidationErrorDetail]] = None
    trace_id: Optional[str] = None


class SystemSettingSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: str


class RecipientOptionSchema(BaseModel):
    """Schema for recipient option"""

    value: str
    label: str
    description: str


class EmailTemplateSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    key: str
    subject_template: str
    body_template: str
    cc: str | None = None
    bcc: str | None = None
    sending_type: SendingType
    recipient_options: Optional[List[Dict[str, str]]] = None
    requires_approval: bool = False
    max_recipients: Optional[int] = None
    updated_at: datetime | None = None


class EmailTemplateUpdateSchema(BaseModel):
    """Schema for updating email templates"""

    key: str
    subject_template: str
    body_template: str
    cc: Optional[str] = None
    bcc: Optional[str] = None
    sending_type: str = "single"
    recipient_options: Optional[List[Dict[str, str]]] = None
    requires_approval: bool = False
    max_recipients: Optional[int] = None
