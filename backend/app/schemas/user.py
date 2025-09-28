"""
User schemas for API requests and responses
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models.user import EmployeeStatus, UserRole, UserType


class UserBase(BaseModel):
    """Base user schema"""

    nycu_id: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    user_type: UserType
    status: EmployeeStatus
    dept_code: Optional[str] = Field(None, max_length=20)
    dept_name: Optional[str] = Field(None, max_length=100)
    role: UserRole = UserRole.student


class UserCreate(UserBase):
    """User creation schema"""

    comment: Optional[str] = Field(None, max_length=255)


class UserUpdate(BaseModel):
    """User update schema"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    user_type: Optional[UserType] = None
    status: Optional[EmployeeStatus] = None
    dept_code: Optional[str] = Field(None, max_length=20)
    dept_name: Optional[str] = Field(None, max_length=100)
    role: Optional[UserRole] = None
    comment: Optional[str] = Field(None, max_length=255)


class UserLogin(BaseModel):
    """User login schema"""

    username: str  # nycu_id or email


class UserResponse(UserBase):
    """User response schema"""

    id: int
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """User list response schema for admin management"""

    id: int
    nycu_id: str
    name: str
    email: str
    user_type: str
    status: str
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None
    role: str
    comment: Optional[str] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserStatsResponse(BaseModel):
    """User statistics response schema"""

    total_users: int
    role_distribution: dict[str, int]
    user_type_distribution: dict[str, int]
    status_distribution: dict[str, int]
    recent_registrations: int


class PortalSSORequest(BaseModel):
    """Portal SSO verification request schema"""

    token: Optional[str] = None
    nycu_id: Optional[str] = None
    username: Optional[str] = None


class DeveloperProfileRequest(BaseModel):
    """Developer profile creation request schema"""

    full_name: Optional[str] = None
    chinese_name: Optional[str] = None
    english_name: Optional[str] = None
    role: UserRole
    email_domain: Optional[str] = "dev.local"
    custom_attributes: Optional[dict] = None


class TokenResponse(BaseModel):
    """Token response schema"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
