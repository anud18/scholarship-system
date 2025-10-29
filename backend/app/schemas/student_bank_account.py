"""
Student Bank Account Schemas
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StudentBankAccountBase(BaseModel):
    """Base schema for student bank account"""

    account_number: str = Field(..., description="郵局帳號")
    account_holder: str = Field(..., description="戶名")
    verification_status: str = Field(..., description="驗證狀態: verified, failed, pending, revoked")
    is_active: bool = Field(..., description="是否為當前使用的帳號")
    verification_notes: Optional[str] = Field(None, description="驗證備註")


class StudentBankAccountResponse(StudentBankAccountBase):
    """Response schema for student bank account"""

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="帳號記錄 ID")
    user_id: int = Field(..., description="用戶 ID")
    verified_at: datetime = Field(..., description="驗證時間")
    verified_by_user_id: Optional[int] = Field(None, description="驗證者用戶 ID")
    verification_source_application_id: Optional[int] = Field(None, description="驗證來源申請 ID")
    created_at: datetime = Field(..., description="創建時間")
    updated_at: Optional[datetime] = Field(None, description="更新時間")


class VerifiedAccountCheckResponse(BaseModel):
    """Response schema for checking if user has verified account"""

    has_verified_account: bool = Field(..., description="是否有已驗證的帳號")
    account: Optional[StudentBankAccountResponse] = Field(None, description="已驗證的帳號資訊（如果有）")
    message: str = Field(..., description="提示訊息")
