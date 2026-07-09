"""Renewal-import schemas for API requests and responses."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RenewalDataRow(BaseModel):
    """Single renewal-passed row imported from Excel/CSV."""

    student_id: str = Field(..., description="學號", min_length=1, max_length=20)
    student_name: str = Field(..., description="姓名", min_length=1, max_length=100)
    sub_type: str = Field(..., description="獎學金子類型代碼 (e.g. nstc, moe_1w)", min_length=1, max_length=50)
    postal_account: Optional[str] = Field(None, description="郵局帳號", max_length=20)
    advisor_nycu_id: Optional[str] = Field(None, description="指導教授本校人事編號", max_length=50)
    advisor_name: Optional[str] = Field(None, description="指導教授姓名", max_length=100)

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[A-Za-z0-9]+$", v):
            raise ValueError("學號僅能包含英文字母和數字")
        return v

    @field_validator("student_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if re.search(r"<[^>]*script|<[^>]*iframe|javascript:", v, re.IGNORECASE):
            raise ValueError("名稱欄位包含不允許的字元")
        return v

    @field_validator("postal_account")
    @classmethod
    def validate_postal_account(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[0-9\-]+$", v):
            raise ValueError("郵局帳號僅能包含數字和連字號")
        return v


class RenewalImportUploadResponse(BaseModel):
    batch_id: int
    file_name: str
    total_records: int = Field(..., description="通過並將匯入的筆數")
    skipped_records: int = Field(..., description="未通過/未申請而跳過的筆數")
    preview_data: List[Dict[str, Any]]
    validation_summary: Dict[str, Any]


class RenewalImportConfirmRequest(BaseModel):
    batch_id: int
    confirm: bool = True


class RenewalImportConfirmResponse(BaseModel):
    batch_id: int
    success_count: int
    failed_count: int
    errors: List[Dict[str, Any]] = Field(default=[])
    created_application_ids: List[int] = Field(default=[])


class RenewalImportHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    college_code: str
    scholarship_type_id: Optional[int] = None
    academic_year: int
    semester: Optional[str] = None
    file_name: str
    total_records: int
    success_count: int
    failed_count: int
    import_status: str
    created_at: datetime
    importer_name: Optional[str] = None


class RenewalImportHistoryResponse(BaseModel):
    total: int
    items: List[RenewalImportHistoryItem]


class RenewalImportDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    college_code: str
    scholarship_type_id: Optional[int] = None
    academic_year: int
    semester: Optional[str] = None
    file_name: str
    total_records: int
    success_count: int
    failed_count: int
    error_summary: Optional[Dict[str, Any]] = None
    import_status: str
    created_at: datetime
    created_applications: Optional[List[int]] = Field(default=[])
