"""
Batch Import schemas for API requests and responses
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BatchImportUploadResponse(BaseModel):
    """Response after uploading batch import file"""

    batch_id: int = Field(..., description="批次匯入ID")
    file_name: str = Field(..., description="檔案名稱")
    total_records: int = Field(..., description="總筆數")
    preview_data: List[Dict[str, Any]] = Field(..., description="預覽資料（前10筆）")
    validation_summary: Dict[str, Any] = Field(..., description="驗證摘要")


class BatchImportValidationError(BaseModel):
    """Single validation error"""

    row_number: int = Field(..., description="行號")
    student_id: Optional[str] = Field(None, description="學號")
    field: str = Field(..., description="欄位名稱")
    error_type: str = Field(..., description="錯誤類型")
    message: str = Field(..., description="錯誤訊息")


class BatchImportConfirmRequest(BaseModel):
    """Request to confirm batch import"""

    batch_id: int = Field(..., description="批次匯入ID")
    confirm: bool = Field(..., description="確認匯入")


class BatchImportConfirmResponse(BaseModel):
    """Response after confirming batch import"""

    batch_id: int
    success_count: int = Field(..., description="成功筆數")
    failed_count: int = Field(..., description="失敗筆數")
    errors: List[BatchImportValidationError] = Field(default=[], description="錯誤清單")
    created_application_ids: List[int] = Field(default=[], description="成功建立的申請ID列表")


class BatchImportHistoryItem(BaseModel):
    """Single batch import history item"""

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
    importer_name: Optional[str] = None  # From relationship


class BatchImportHistoryResponse(BaseModel):
    """Batch import history response"""

    total: int = Field(..., description="總筆數")
    items: List[BatchImportHistoryItem] = Field(..., description="匯入歷史列表")


class BatchImportDetailResponse(BaseModel):
    """Detailed batch import information"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    college_code: str
    scholarship_type_id: Optional[int] = None
    academic_year: int
    semester: Optional[str] = None
    file_name: str
    file_path: Optional[str] = None
    total_records: int
    success_count: int
    failed_count: int
    error_summary: Optional[Dict[str, Any]] = None
    import_status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    importer_name: Optional[str] = None
    created_applications: Optional[List[int]] = Field(default=[], description="建立的申請ID列表")


class ApplicationDataRow(BaseModel):
    """Single row of application data from Excel/CSV"""

    # 必要欄位
    student_id: str = Field(..., description="學號", min_length=1, max_length=20)
    student_name: str = Field(..., description="姓名", min_length=1, max_length=100)

    # 系所欄位（供權限驗證使用）
    dept_code: Optional[str] = Field(None, description="系所代碼", max_length=20)

    # 子類型
    sub_types: List[str] = Field(default=[], description="子類型列表")

    # 郵局帳戶資訊
    postal_account: Optional[str] = Field(None, description="郵局帳號", max_length=20)

    # 其他動態欄位
    custom_fields: Optional[Dict[str, Any]] = Field(default={}, description="其他自定義欄位")

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, v: str) -> str:
        """Validate student ID format - alphanumeric only"""
        v = v.strip()
        if not re.match(r"^[A-Za-z0-9]+$", v):
            raise ValueError("學號僅能包含英文字母和數字")
        return v

    @field_validator("dept_code")
    @classmethod
    def validate_dept_code(cls, v: Optional[str]) -> Optional[str]:
        """Normalize and validate department code when provided"""
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not re.match(r"^[A-Za-z0-9_-]+$", v):
            raise ValueError("系所代碼僅能包含英數字、底線或連字號")
        return v

    @field_validator("student_name")
    @classmethod
    def validate_name_fields(cls, v: str) -> str:
        """Validate name fields - no HTML/script tags for XSS prevention"""
        v = v.strip()
        # Check for common XSS patterns
        if re.search(r"<[^>]*script|<[^>]*iframe|javascript:", v, re.IGNORECASE):
            raise ValueError("名稱欄位包含不允許的字元")
        return v

    @field_validator("postal_account")
    @classmethod
    def validate_postal_account(cls, v: Optional[str]) -> Optional[str]:
        """Validate postal account - numbers and hyphens only"""
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[0-9\-]+$", v):
            raise ValueError("郵局帳號僅能包含數字和連字號")
        return v


class BatchImportDataRequest(BaseModel):
    """Request to create batch import with data"""

    scholarship_type: str = Field(..., description="獎學金類型代碼")
    academic_year: int = Field(..., description="學年度", ge=100, le=200)
    semester: Optional[str] = Field(None, description="學期")
    data_rows: List[ApplicationDataRow] = Field(..., description="申請資料列表", min_length=1)


class BatchImportUpdateRecordRequest(BaseModel):
    """Request to update a single record in batch import"""

    record_index: int = Field(..., description="記錄索引（從0開始）", ge=0)
    updates: Dict[str, Any] = Field(..., description="要更新的欄位")


class BatchImportRevalidateResponse(BaseModel):
    """Response after revalidation"""

    batch_id: int
    total_records: int
    valid_count: int
    invalid_count: int
    errors: List[Dict[str, Any]] = Field(default=[], description="驗證錯誤列表")
    warnings: List[Dict[str, Any]] = Field(default=[], description="驗證警告列表")


class BatchDocumentUploadResult(BaseModel):
    """Result of document matching"""

    student_id: str
    file_name: str
    document_type: str
    status: str  # "success" or "error"
    message: Optional[str] = None
    application_id: Optional[int] = None


class BatchDocumentUploadResponse(BaseModel):
    """Response after bulk document upload"""

    batch_id: int
    total_files: int
    matched_count: int
    unmatched_count: int
    error_count: int
    results: List[BatchDocumentUploadResult] = Field(default=[], description="上傳結果詳情")
