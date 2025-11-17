"""
User Profile schemas for API requests and responses
"""

import re
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BankInfoBase(BaseModel):
    """Base post office account information schema"""

    account_number: Optional[str] = Field(None, max_length=50, description="郵局帳號")


class AdvisorInfoBase(BaseModel):
    """Base advisor information schema"""

    advisor_name: Optional[str] = Field(None, max_length=100, description="指導教授姓名")
    advisor_email: Optional[str] = Field(None, description="指導教授Email")
    advisor_nycu_id: Optional[str] = Field(None, max_length=20, description="指導教授NYCU ID")

    @field_validator("advisor_email", mode="before")
    @classmethod
    def validate_email(cls, v):
        # Convert empty string to None
        if v == "" or v is None:
            return None

        # If it's not empty, validate email format
        if v:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")

        return v


class UserProfileCreate(BaseModel):
    """User profile creation schema"""

    # Post office account information
    account_number: Optional[str] = None

    # Advisor information
    advisor_name: Optional[str] = None
    advisor_email: Optional[str] = None
    advisor_nycu_id: Optional[str] = None

    @field_validator("advisor_email", mode="before")
    @classmethod
    def validate_email(cls, v):
        # Convert empty string to None
        if v == "" or v is None:
            return None

        # If it's not empty, validate email format
        if v:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")

        return v

    # Personal information
    preferred_language: str = "zh-TW"

    # Privacy settings
    privacy_settings: Optional[Dict[str, Any]] = None
    custom_fields: Optional[Dict[str, Any]] = None


class UserProfileUpdate(BaseModel):
    """User profile update schema"""

    # Post office account information
    account_number: Optional[str] = Field(None, max_length=50)

    # Advisor information
    advisor_name: Optional[str] = Field(None, max_length=100)
    advisor_email: Optional[str] = None
    advisor_nycu_id: Optional[str] = Field(None, max_length=20)

    @field_validator("advisor_email", mode="before")
    @classmethod
    def validate_email(cls, v):
        # Convert empty string to None
        if v == "" or v is None:
            return None

        # If it's not empty, validate email format
        if v:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, v):
                raise ValueError("Invalid email format")

        return v

    # Personal information
    preferred_language: Optional[str] = Field(None, max_length=10)

    # Privacy settings
    privacy_settings: Optional[Dict[str, Any]] = None
    custom_fields: Optional[Dict[str, Any]] = None


class UserProfileResponse(BaseModel):
    """User profile response schema"""

    id: int
    user_id: int

    # Post office account information
    account_number: Optional[str] = None
    bank_document_photo_url: Optional[str] = None  # Post office account document photo

    # Advisor information
    advisor_name: Optional[str] = None
    advisor_email: Optional[str] = None
    advisor_nycu_id: Optional[str] = None

    # Personal information
    preferred_language: str

    # Metadata
    privacy_settings: Optional[Dict[str, Any]] = None
    custom_fields: Optional[Dict[str, Any]] = None
    has_complete_bank_info: bool
    has_advisor_info: bool
    profile_completion_percentage: int

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CompleteUserProfileResponse(BaseModel):
    """Complete user profile including read-only data from User model"""

    # Read-only user data (from API)
    user_info: Dict[str, Any]

    # Editable profile data
    profile: Optional[UserProfileResponse] = None

    # Student-specific data (if user is a student)
    student_info: Optional[Dict[str, Any]] = None


class BankDocumentPhotoUpload(BaseModel):
    """Bank document photo upload schema"""

    photo_data: str = Field(..., description="Base64 encoded image data")
    filename: str = Field(..., description="Original filename")
    content_type: str = Field(..., description="MIME type of the image")


class ProfileHistoryResponse(BaseModel):
    """Profile change history response schema"""

    id: int
    user_id: int
    field_name: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    change_reason: Optional[str] = None
    changed_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BankInfoUpdate(BankInfoBase):
    """Schema for updating just bank information"""

    change_reason: Optional[str] = Field(None, description="更新銀行資訊的原因")


class AdvisorInfoUpdate(AdvisorInfoBase):
    """Schema for updating just advisor information"""

    change_reason: Optional[str] = Field(None, description="更新指導教授資訊的原因")
