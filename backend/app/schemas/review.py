"""
Review Schemas

Pydantic schemas for review system
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ReviewItemCreate(BaseModel):
    """子項目審查創建 schema"""

    sub_type_code: str = Field(..., description="子項目代碼（例如 'nstc', 'moe_1w', 'default'）")
    recommendation: str = Field(..., description="審查建議：'approve' 或 'reject'")
    comments: Optional[str] = Field(None, description="評論（拒絕時建議必填，同意時可空）")

    @field_validator("recommendation")
    @classmethod
    def validate_recommendation(cls, v: str) -> str:
        """驗證 recommendation 只能是 approve 或 reject"""
        if v not in ["approve", "reject"]:
            raise ValueError("recommendation 必須是 'approve' 或 'reject'")
        return v


class ReviewSubmitRequest(BaseModel):
    """審查提交請求 schema（用於 professor endpoints，application_id 來自路徑參數）"""

    items: List[ReviewItemCreate] = Field(..., min_length=1, description="子項目審查列表")

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[ReviewItemCreate]) -> List[ReviewItemCreate]:
        """驗證至少有一個子項目"""
        if not v:
            raise ValueError("至少需要一個子項目審查")
        return v


class ReviewCreate(BaseModel):
    """審查創建 schema（完整版本，用於內部服務調用）"""

    application_id: int = Field(..., description="申請 ID")
    items: List[ReviewItemCreate] = Field(..., min_length=1, description="子項目審查列表")

    @field_validator("items")
    @classmethod
    def validate_items(cls, v: List[ReviewItemCreate]) -> List[ReviewItemCreate]:
        """驗證至少有一個子項目"""
        if not v:
            raise ValueError("至少需要一個子項目審查")
        return v


class ReviewItemResponse(BaseModel):
    """子項目審查回應 schema"""

    id: int
    review_id: int
    sub_type_code: str
    recommendation: str
    comments: Optional[str] = None

    model_config = {"from_attributes": True}


class ReviewResponse(BaseModel):
    """審查回應 schema"""

    id: int
    application_id: int
    reviewer_id: int
    recommendation: str  # 'approve' | 'partial_approve' | 'reject'（自動計算）
    comments: Optional[str] = None  # 自動從 items 組合而成
    reviewed_at: datetime
    created_at: datetime
    items: List[ReviewItemResponse] = []

    # 審查者資訊
    reviewer_name: Optional[str] = None
    reviewer_role: Optional[str] = None

    model_config = {"from_attributes": True}


class SubTypeCumulativeStatusResponse(BaseModel):
    """子項目累積狀態回應 schema"""

    sub_type_code: str
    status: str  # 'approved' | 'rejected' | 'pending'
    rejected_by: Optional[Dict[str, Any]] = (
        None  # {'role': 'professor', 'name': '王小明', 'reviewed_at': '2025-01-15 14:30:00'}
    )
    comments: Optional[str] = None

    model_config = {"from_attributes": True}


class ApplicationReviewStatusResponse(BaseModel):
    """申請審查狀態回應 schema"""

    application_id: int
    overall_status: str  # 'approved' | 'rejected' | 'pending' | 'partial_approve'
    decision_reason: Optional[str] = None
    subtype_statuses: Dict[str, SubTypeCumulativeStatusResponse]  # key: sub_type_code
    reviews: List[ReviewResponse] = []

    model_config = {"from_attributes": True}


class ReviewableSubTypesResponse(BaseModel):
    """可審查子項目回應 schema"""

    application_id: int
    current_user_role: str
    reviewable_subtypes: List[str]  # 可審查的子項目代碼列表
    all_subtypes: List[str]  # 所有子項目代碼列表
    subtype_statuses: Dict[str, SubTypeCumulativeStatusResponse]  # 所有子項目的累積狀態

    model_config = {"from_attributes": True}
