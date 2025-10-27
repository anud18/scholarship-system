"""
Payment roster Pydantic schemas
造冊相關資料結構定義
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment_roster import RosterCycle, RosterStatus, RosterTriggerType, StudentVerificationStatus


# Base schemas
class PaymentRosterBase(BaseModel):
    """造冊基礎資料結構"""

    roster_code: str = Field(..., description="造冊代碼")
    scholarship_configuration_id: int = Field(..., description="獎學金配置ID")
    period_label: str = Field(..., description="期間標記")
    academic_year: int = Field(..., description="學年度")
    roster_cycle: RosterCycle = Field(..., description="造冊週期")
    student_verification_enabled: bool = Field(True, description="是否啟用學籍驗證")
    notes: Optional[str] = Field(None, description="備註")


class PaymentRosterItemBase(BaseModel):
    """造冊明細基礎資料結構"""

    student_id_number: str = Field(..., description="學生身分證字號")
    student_name: str = Field(..., description="學生姓名")
    student_email: Optional[str] = Field(None, description="學生信箱")
    bank_account: Optional[str] = Field(None, description="郵局帳號")
    scholarship_name: str = Field(..., description="獎學金名稱")
    scholarship_amount: Decimal = Field(..., description="獎學金金額")
    scholarship_subtype: Optional[str] = Field(None, description="獎學金子類型")
    is_included: bool = Field(True, description="是否納入造冊")
    exclusion_reason: Optional[str] = Field(None, description="排除原因")


# Create schemas
class RosterGenerationRequest(BaseModel):
    """造冊產生請求"""

    scholarship_configuration_id: int = Field(..., description="獎學金配置ID")
    period_label: str = Field(..., description="期間標記 (YYYY-MM, YYYY-H1/H2, YYYY)")
    roster_cycle: RosterCycle = Field(..., description="造冊週期")
    academic_year: int = Field(..., description="學年度")
    trigger_type: Optional[RosterTriggerType] = Field(RosterTriggerType.MANUAL, description="觸發方式")
    student_verification_enabled: bool = Field(True, description="是否啟用學籍驗證")
    force_regenerate: bool = Field(False, description="是否強制重新產生")
    auto_export: bool = Field(False, description="是否自動匯出Excel")
    include_excluded_in_export: bool = Field(False, description="匯出時是否包含排除項目")


class PaymentRosterCreate(PaymentRosterBase):
    """建立造冊請求"""

    trigger_type: RosterTriggerType = Field(..., description="觸發方式")


class RosterExportRequest(BaseModel):
    """造冊匯出請求"""

    include_excluded: bool = Field(False, description="是否包含排除項目")
    async_export: bool = Field(False, description="是否背景匯出")


# Response schemas
class PaymentRosterItemResponse(PaymentRosterItemBase):
    """造冊明細回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    roster_id: int
    application_id: int
    permanent_address: Optional[str] = None
    mailing_address: Optional[str] = None
    verification_status: StudentVerificationStatus
    verification_message: Optional[str] = None
    verification_at: Optional[datetime] = None
    nationality_code: Optional[str] = None
    residence_days_over_183: Optional[str] = None
    excel_remarks: Optional[str] = None
    # Bank account verification status (separate for account number and holder name)
    bank_account_number_status: Optional[str] = None
    bank_account_holder_status: Optional[str] = None
    bank_verification_details: Optional[Dict[str, Any]] = None
    bank_manual_review_notes: Optional[str] = None
    # Rule validation results
    rule_validation_result: Optional[Dict[str, Any]] = None
    failed_rules: Optional[List[str]] = None
    warning_rules: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime


class PaymentRosterResponse(PaymentRosterBase):
    """造冊回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: RosterStatus
    trigger_type: RosterTriggerType
    created_by: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    locked_by: Optional[int] = None
    total_applications: Optional[int] = None
    qualified_count: Optional[int] = None
    disqualified_count: Optional[int] = None
    total_amount: Optional[Decimal] = None
    excel_filename: Optional[str] = None
    excel_file_size: Optional[int] = None
    verification_api_failures: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    # Computed properties
    @property
    def is_locked(self) -> bool:
        return self.status == RosterStatus.LOCKED

    @property
    def can_be_modified(self) -> bool:
        return self.status in [RosterStatus.DRAFT, RosterStatus.FAILED]

    @property
    def is_completed(self) -> bool:
        return self.status in [RosterStatus.COMPLETED, RosterStatus.LOCKED]


class PaymentRosterListResponse(BaseModel):
    """造冊清單回應"""

    items: List[PaymentRosterResponse]
    total: int
    skip: int
    limit: int


# Summary schemas
class RosterSummary(BaseModel):
    """造冊摘要"""

    roster_code: str
    period_label: str
    status: RosterStatus
    total_applications: int
    qualified_count: int
    disqualified_count: int
    total_amount: Decimal
    created_at: datetime
    completed_at: Optional[datetime]


class RosterStatistics(BaseModel):
    """造冊統計資訊"""

    total_rosters: int = Field(..., description="總造冊數")
    completed_rosters: int = Field(..., description="已完成造冊數")
    locked_rosters: int = Field(..., description="已鎖定造冊數")
    processing_rosters: int = Field(..., description="處理中造冊數")
    total_students: int = Field(..., description="總學生數")
    total_amount: Decimal = Field(..., description="總金額")

    by_cycle: Dict[str, int] = Field(default_factory=dict, description="依週期統計")
    by_status: Dict[str, int] = Field(default_factory=dict, description="依狀態統計")
    by_academic_year: Dict[str, int] = Field(default_factory=dict, description="依學年度統計")


# Audit log schemas
class RosterAuditLogResponse(BaseModel):
    """造冊稽核日誌回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    roster_id: int
    action: str
    level: str
    title: str
    description: Optional[str] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    client_ip: Optional[str] = None
    api_endpoint: Optional[str] = None
    request_method: Optional[str] = None
    response_status: Optional[int] = None
    processing_time_ms: Optional[int] = None
    affected_items_count: Optional[int] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    created_at: datetime


class RosterAuditLogListResponse(BaseModel):
    """造冊稽核日誌清單回應"""

    items: List[RosterAuditLogResponse]
    total: int
    skip: int
    limit: int


# Verification schemas
class StudentVerificationResult(BaseModel):
    """學生驗證結果"""

    student_id: str
    student_name: str
    status: StudentVerificationStatus
    message: str
    student_info: Dict[str, Any] = Field(default_factory=dict)
    verified_at: datetime
    api_response: Dict[str, Any] = Field(default_factory=dict)


class BatchVerificationRequest(BaseModel):
    """批次驗證請求"""

    students: List[Dict[str, str]] = Field(..., description="學生清單 [{'id': '身分證字號', 'name': '姓名'}, ...]")


class BatchVerificationResponse(BaseModel):
    """批次驗證回應"""

    results: Dict[str, StudentVerificationResult]
    total_students: int
    verified_count: int
    error_count: int
    processing_time_ms: int


# Excel export schemas
class ExcelExportResult(BaseModel):
    """Excel匯出結果"""

    file_path: str
    file_name: str
    file_size: int
    file_hash: str
    total_rows: int
    qualified_count: int
    disqualified_count: int
    export_time: datetime = Field(default_factory=datetime.now)


class ExcelFileInfo(BaseModel):
    """Excel檔案資訊"""

    file_name: str
    file_size: int
    file_hash: str
    created_at: datetime
    download_url: Optional[str] = None


# Schedule schemas (for future roster scheduling feature)
class RosterScheduleBase(BaseModel):
    """造冊排程基礎資料結構"""

    scholarship_configuration_id: int
    schedule_name: str
    cron_expression: str
    is_enabled: bool = True
    timezone: str = "Asia/Taipei"
    retry_count: int = 3
    retry_delay_minutes: int = 30
    student_verification_enabled: bool = True
    auto_lock_after_completion: bool = False
    max_execution_time_minutes: int = 60


class RosterScheduleCreate(RosterScheduleBase):
    """建立造冊排程請求"""

    notify_on_success: bool = True
    notify_on_failure: bool = True
    notification_emails: Optional[List[str]] = None


class RosterScheduleResponse(RosterScheduleBase):
    """造冊排程回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_roster_id: Optional[int] = None
    next_run_at: Optional[datetime] = None

    @property
    def is_active(self) -> bool:
        return self.is_enabled and bool(self.cron_expression)
