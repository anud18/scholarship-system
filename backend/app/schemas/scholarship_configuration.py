"""
Scholarship Configuration schemas for API requests and responses
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester


class ScholarshipConfigurationBase(BaseModel):
    """Base schema for scholarship configuration"""

    academic_year: int = Field(..., gt=0, description="民國年，如 113 表示 113 學年度")
    semester: Optional[Semester] = Field(None, description="學期（學期制獎學金需要，學年制可為 None）")
    config_name: str = Field(..., min_length=1, max_length=200)
    config_code: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = None
    description_en: Optional[str] = None

    # 配額限制配置
    has_quota_limit: bool = False
    has_college_quota: bool = False
    quota_management_mode: QuotaManagementMode = QuotaManagementMode.none

    # 配額詳細設定
    total_quota: Optional[int] = Field(None, ge=0)
    quotas: Optional[Dict[str, Dict[str, int]]] = None

    # 金額設定 (從 ScholarshipType 移至此處)
    amount: int = Field(..., gt=0, description="獎學金金額（整數）")
    currency: str = Field(default="TWD", max_length=10)

    whitelist_student_ids: Dict[str, List[int]] = Field(default={}, description="白名單學生ID列表，依子獎學金區分")

    # 申請時間 (從 ScholarshipType 移至此處)
    # 續領申請期間（優先處理）
    renewal_application_start_date: Optional[datetime] = None
    renewal_application_end_date: Optional[datetime] = None

    # 一般申請期間（續領處理完畢後）
    application_start_date: Optional[datetime] = None
    application_end_date: Optional[datetime] = None

    # 續領審查期間 (從 ScholarshipType 移至此處)
    renewal_professor_review_start: Optional[datetime] = None
    renewal_professor_review_end: Optional[datetime] = None
    renewal_college_review_start: Optional[datetime] = None
    renewal_college_review_end: Optional[datetime] = None

    # 一般申請審查期間 (從 ScholarshipType 移至此處)
    requires_professor_recommendation: bool = False
    professor_review_start: Optional[datetime] = None
    professor_review_end: Optional[datetime] = None

    requires_college_review: bool = False
    college_review_start: Optional[datetime] = None
    college_review_end: Optional[datetime] = None

    review_deadline: Optional[datetime] = None

    # 狀態與有效性
    is_active: bool = True
    effective_start_date: Optional[datetime] = None
    effective_end_date: Optional[datetime] = None

    # 版本控制
    version: str = "1.0"

    @field_validator("total_quota")
    @classmethod
    def validate_total_quota(cls, v, values):
        """Validate total quota when quota limit is enabled"""
        if values.data.get("has_quota_limit") and v is None:
            raise ValueError("總配額不能為空當啟用配額限制時")
        return v

    @field_validator("quotas")
    @classmethod
    def validate_quotas(cls, v, values):
        """Validate quota configuration"""
        if values.data.get("has_college_quota"):
            if not v:
                raise ValueError("配額配置不能為空當啟用學院配額時")

            # Check if college quota sum exceeds total quota
            total_quota = values.data.get("total_quota")
            if total_quota and v:
                # For matrix structure: {sub_type: {college: quota}}
                college_total = sum(
                    sum(college_quotas.values()) for college_quotas in v.values() if isinstance(college_quotas, dict)
                )
                if college_total > total_quota:
                    raise ValueError(f"配額總和 ({college_total}) 超過總配額 ({total_quota})")
        return v

    @field_validator("renewal_professor_review_end")
    @classmethod
    def validate_renewal_professor_review(cls, v, values):
        """Validate renewal professor review dates"""
        if not values.data.get("requires_professor_recommendation"):
            if v or values.data.get("renewal_professor_review_start"):
                raise ValueError("續領教授審查時間不應設定當不需要教授推薦時")
        return v

    @field_validator("renewal_college_review_end")
    @classmethod
    def validate_renewal_college_review(cls, v, values):
        """Validate renewal college review dates"""
        if not values.data.get("requires_college_review"):
            if v or values.data.get("renewal_college_review_start"):
                raise ValueError("續領學院審查時間不應設定當不需要學院審查時")
        return v

    @field_validator("effective_end_date")
    @classmethod
    def validate_effective_dates(cls, v, values):
        """Validate effective date range"""
        start_date = values.data.get("effective_start_date")
        if start_date and v and v <= start_date:
            raise ValueError("結束日期必須晚於開始日期")
        return v


class ScholarshipConfigurationCreate(ScholarshipConfigurationBase):
    """Schema for creating scholarship configuration"""

    scholarship_type_id: int = Field(..., gt=0)


class ScholarshipConfigurationUpdate(BaseModel):
    """Schema for updating scholarship configuration"""

    academic_year: Optional[int] = Field(None, gt=0, description="民國年，如 113 表示 113 學年度")
    semester: Optional[Semester] = Field(None, description="學期（學期制獎學金需要，學年制可為 None）")
    config_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    description_en: Optional[str] = None

    # 配額限制配置
    has_quota_limit: Optional[bool] = None
    has_college_quota: Optional[bool] = None
    quota_management_mode: Optional[QuotaManagementMode] = None

    # 配額詳細設定
    total_quota: Optional[int] = Field(None, ge=0)
    quotas: Optional[Dict[str, Dict[str, int]]] = None

    # 金額設定 (從 ScholarshipType 移至此處)
    amount: Optional[int] = Field(None, gt=0, description="獎學金金額（整數）")
    currency: Optional[str] = Field(None, max_length=10)

    whitelist_student_ids: Optional[Dict[str, List[int]]] = Field(None, description="白名單學生ID列表，依子獎學金區分")

    # 申請時間 (從 ScholarshipType 移至此處)
    # 續領申請期間（優先處理）
    renewal_application_start_date: Optional[datetime] = None
    renewal_application_end_date: Optional[datetime] = None

    # 一般申請期間（續領處理完畢後）
    application_start_date: Optional[datetime] = None
    application_end_date: Optional[datetime] = None

    # 續領審查期間 (從 ScholarshipType 移至此處)
    renewal_professor_review_start: Optional[datetime] = None
    renewal_professor_review_end: Optional[datetime] = None
    renewal_college_review_start: Optional[datetime] = None
    renewal_college_review_end: Optional[datetime] = None

    # 一般申請審查期間 (從 ScholarshipType 移至此處)
    requires_professor_recommendation: Optional[bool] = None
    professor_review_start: Optional[datetime] = None
    professor_review_end: Optional[datetime] = None

    requires_college_review: Optional[bool] = None
    college_review_start: Optional[datetime] = None
    college_review_end: Optional[datetime] = None

    review_deadline: Optional[datetime] = None

    # 狀態與有效性
    is_active: Optional[bool] = None
    effective_start_date: Optional[datetime] = None
    effective_end_date: Optional[datetime] = None

    # 版本控制
    version: Optional[str] = None


class ScholarshipConfigurationResponse(ScholarshipConfigurationBase):
    """Schema for scholarship configuration response"""

    id: int
    scholarship_type_id: int
    previous_config_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

    # Computed fields
    is_effective: bool = False
    validation_errors: List[str] = []

    @property
    def cycle(self) -> str:
        """Get cycle string representation for compatibility"""
        if self.semester:
            return f"{self.academic_year}-{self.semester.value}"
        return str(self.academic_year)

    model_config = ConfigDict(from_attributes=True)


class ScholarshipConfigurationQuotaStatus(BaseModel):
    """Schema for quota status information"""

    config_id: int
    config_code: str
    config_name: str

    # Quota information
    total_quota: Optional[int] = None
    used_quota: int = 0
    available_quota: Optional[int] = None
    usage_percentage: Optional[float] = None

    # College-specific quota
    college_quotas: Optional[
        Dict[str, Dict[str, int]]
    ] = None  # {"engineering": {"total": 10, "used": 3, "available": 7}}

    # Status
    is_quota_exceeded: bool = False
    is_quota_warning: bool = False  # > 80% used

    model_config = ConfigDict(from_attributes=True)


class ScholarshipConfigurationSummary(BaseModel):
    """Schema for configuration summary"""

    id: int
    config_code: str
    config_name: str
    scholarship_type_id: int
    academic_year: int
    semester: Optional[Semester] = None
    application_period: ApplicationCycle
    quota_management_mode: QuotaManagementMode
    has_quota_limit: bool
    has_college_quota: bool
    is_active: bool
    is_effective: bool
    created_at: datetime
    updated_at: datetime

    @property
    def cycle(self) -> str:
        """Get cycle string representation for compatibility"""
        if self.semester:
            return f"{self.academic_year}-{self.semester.value}"
        return str(self.academic_year)

    model_config = ConfigDict(from_attributes=True)


class ScholarshipConfigurationBulkCreate(BaseModel):
    """Schema for bulk creating scholarship configurations"""

    configurations: List[ScholarshipConfigurationCreate]

    @field_validator("configurations")
    @classmethod
    def validate_configurations(cls, v):
        """Validate configurations list"""
        if not v:
            raise ValueError("至少需要一個配置")

        # Check for duplicate config codes
        codes = [config.config_code for config in v]
        duplicates = [code for code in codes if codes.count(code) > 1]
        if duplicates:
            raise ValueError(f"配置代碼重複: {list(set(duplicates))}")

        return v


class ScholarshipConfigurationExport(BaseModel):
    """Schema for exporting configurations"""

    format: str = Field("json", pattern="^(json|csv|excel)$")
    include_inactive: bool = False
    include_expired: bool = False
    scholarship_type_ids: Optional[List[int]] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "format": "json",
                "include_inactive": False,
                "include_expired": False,
                "scholarship_type_ids": [1, 2, 3],
            }
        },
    )


class ScholarshipConfigurationImport(BaseModel):
    """Schema for importing configurations"""

    configurations: List[Dict[str, Any]]
    overwrite_existing: bool = False
    validate_only: bool = False

    @field_validator("configurations")
    @classmethod
    def validate_import_data(cls, v):
        """Validate import data structure"""
        if not v:
            raise ValueError("匯入資料不能為空")

        required_fields = ["config_code", "config_name", "scholarship_type_id"]
        for i, config in enumerate(v):
            missing_fields = [field for field in required_fields if field not in config]
            if missing_fields:
                raise ValueError(f"配置 {i+1} 缺少必要欄位: {missing_fields}")

        return v


class ScholarshipConfigurationValidation(BaseModel):
    """Schema for configuration validation results"""

    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    suggestions: List[str] = []

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "is_valid": False,
                "errors": ["總配額不能為空當啟用配額限制時"],
                "warnings": ["配額使用率已達 90%"],
                "suggestions": ["建議增加配額或調整分配策略"],
            }
        },
    )


# Whitelist Management Schemas


class WhitelistStudentInfo(BaseModel):
    """申請白名單學生資訊"""

    student_id: Optional[int] = Field(None, description="學生ID（如已註冊）")
    nycu_id: str = Field(..., description="學號")
    name: Optional[str] = Field(None, description="姓名（如已註冊）")
    sub_type: str = Field(..., description="子獎學金類型")
    note: Optional[str] = Field(None, description="備註")
    is_registered: bool = Field(default=False, description="是否已註冊")

    model_config = ConfigDict(from_attributes=True)


class WhitelistBatchAddRequest(BaseModel):
    """批量新增白名單請求"""

    students: List[Dict[str, Any]] = Field(..., description="學生列表 [{'nycu_id': '0856001', 'sub_type': 'nstc'}, ...]")

    @field_validator("students")
    @classmethod
    def validate_students(cls, v):
        if not v:
            raise ValueError("學生列表不能為空")
        for student in v:
            if "nycu_id" not in student or "sub_type" not in student:
                raise ValueError("每個學生必須包含 nycu_id 和 sub_type")
        return v


class WhitelistBatchRemoveRequest(BaseModel):
    """批量移除白名單請求"""

    nycu_ids: List[str] = Field(..., description="學號列表 ['0856001', '0856002', ...]")
    sub_type: Optional[str] = Field(None, description="子獎學金類型，若為 None 則從所有子類型中移除")

    @field_validator("nycu_ids")
    @classmethod
    def validate_nycu_ids(cls, v):
        if not v:
            raise ValueError("學號列表不能為空")
        return v


class WhitelistResponse(BaseModel):
    """白名單響應"""

    sub_type: str = Field(..., description="子獎學金類型")
    students: List[WhitelistStudentInfo] = Field(..., description="白名單學生列表")
    total: int = Field(..., description="總人數")


class WhitelistImportResult(BaseModel):
    """白名單匯入結果"""

    success_count: int = Field(..., description="成功匯入數量")
    error_count: int = Field(..., description="錯誤數量")
    errors: List[Dict[str, str]] = Field(
        default=[], description="錯誤詳情 [{'row': '2', 'nycu_id': '0856001', 'error': '學號不存在'}]"
    )
    warnings: List[str] = Field(default=[], description="警告訊息")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success_count": 45,
                "error_count": 3,
                "errors": [
                    {"row": "2", "nycu_id": "0856999", "error": "學號不存在"},
                    {"row": "5", "nycu_id": "0856888", "error": "子獎學金類型無效: invalid_type"},
                ],
                "warnings": ["第 10 行學號重複，已跳過"],
            }
        },
    )
