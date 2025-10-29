"""
Notification schemas for API requests and responses
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, validator

from app.models.notification import NotificationPriority, NotificationType


class NotificationResponse(BaseModel):
    """Notification response schema"""

    id: int
    title: str
    title_en: Optional[str] = None
    message: str
    message_en: Optional[str] = None
    notification_type: str
    priority: str
    related_resource_type: Optional[str] = None
    related_resource_id: Optional[int] = None
    action_url: Optional[str] = None
    is_read: bool
    is_dismissed: bool
    scheduled_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = Field(None, alias="meta_data")

    class Config:
        from_attributes = True
        populate_by_name = True


class NotificationCreate(BaseModel):
    """Schema for creating system announcements"""

    title: str = Field(..., min_length=1, max_length=200, description="公告標題")
    title_en: Optional[str] = Field(None, max_length=200, description="英文標題")
    message: str = Field(..., min_length=1, description="公告內容")
    message_en: Optional[str] = Field(None, description="英文內容")
    notification_type: str = Field(default=NotificationType.info.value, description="公告類型")
    priority: str = Field(default=NotificationPriority.normal.value, description="優先級")
    action_url: Optional[str] = Field(None, max_length=500, description="行動連結")
    expires_at: Optional[datetime] = Field(None, description="過期時間")
    metadata: Optional[Dict[str, Any]] = Field(None, description="額外資料")

    @validator("notification_type")
    def validate_notification_type(cls, v):
        valid_types = [t.value for t in NotificationType]
        if v not in valid_types:
            raise ValueError(f"Invalid notification type. Must be one of: {valid_types}")
        return v

    @validator("priority")
    def validate_priority(cls, v):
        valid_priorities = [p.value for p in NotificationPriority]
        if v not in valid_priorities:
            raise ValueError(f"Invalid priority. Must be one of: {valid_priorities}")
        return v


class NotificationUpdate(BaseModel):
    """Schema for updating system announcements"""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    title_en: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, min_length=1)
    message_en: Optional[str] = Field(None)
    notification_type: Optional[str] = Field(None)
    priority: Optional[str] = Field(None)
    action_url: Optional[str] = Field(None, max_length=500)
    expires_at: Optional[datetime] = Field(None)
    metadata: Optional[Dict[str, Any]] = Field(None)
    is_dismissed: Optional[bool] = Field(None, description="是否已關閉")

    @validator("notification_type")
    def validate_notification_type(cls, v):
        if v is not None:
            valid_types = [t.value for t in NotificationType]
            if v not in valid_types:
                raise ValueError(f"Invalid notification type. Must be one of: {valid_types}")
        return v

    @validator("priority")
    def validate_priority(cls, v):
        if v is not None:
            valid_priorities = [p.value for p in NotificationPriority]
            if v not in valid_priorities:
                raise ValueError(f"Invalid priority. Must be one of: {valid_priorities}")
        return v
