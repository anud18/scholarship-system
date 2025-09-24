"""
Pydantic schemas for pre-authorization functionality
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class PreAuthorizeUserRequest(BaseModel):
    """Request schema for pre-authorizing a user"""

    nycu_id: str = Field(..., description="NYCU ID of the user to pre-authorize")
    role: str = Field(..., description="Role to assign (student, professor, college, admin)")
    comment: Optional[str] = Field(None, description="Optional comment for the pre-authorization")


class PreAuthorizeUserResponse(BaseModel):
    """Response schema for pre-authorizing a user"""

    success: bool
    message: str
    data: dict


class AssignScholarshipRequest(BaseModel):
    """Request schema for assigning a scholarship to an admin"""

    admin_nycu_id: str = Field(..., description="NYCU ID of the admin")
    scholarship_id: int = Field(..., description="ID of the scholarship to assign")
    comment: Optional[str] = Field(None, description="Optional comment for the assignment")


class AssignScholarshipResponse(BaseModel):
    """Response schema for assigning a scholarship to an admin"""

    success: bool
    message: str
    data: dict


class PreAuthorizedUser(BaseModel):
    """Schema for a pre-authorized user"""

    nycu_id: str
    name: str
    email: str
    role: str
    created_at: str
    comment: Optional[str] = None


class PreAuthorizedUserList(BaseModel):
    """Response schema for list of pre-authorized users"""

    success: bool
    message: str
    data: List[PreAuthorizedUser]


class AdminScholarship(BaseModel):
    """Schema for admin-scholarship assignment"""

    admin_nycu_id: str
    scholarship_id: int
    assigned_at: str


class AdminScholarshipList(BaseModel):
    """Response schema for list of admin-scholarship assignments"""

    success: bool
    message: str
    data: List[AdminScholarship]


class UserInfo(BaseModel):
    """Schema for user information"""

    nycu_id: str
    name: str
    email: str
    role: str
    user_type: Optional[str] = None
    status: Optional[str] = None
    dept_code: Optional[str] = None
    dept_name: Optional[str] = None
    last_login_at: Optional[str] = None
    comment: Optional[str] = None


class UserInfoResponse(BaseModel):
    """Response schema for user information"""

    success: bool
    message: str
    data: UserInfo
