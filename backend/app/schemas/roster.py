"""
造冊相關的Pydantic模型
Payment roster related Pydantic models
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.payment_roster import RosterCycle, RosterStatus, RosterTriggerType, StudentVerificationStatus
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel


class RosterCreateRequest(BaseModel):
    """造冊建立請求"""

    scholarship_configuration_id: int = Field(..., description="獎學金配置ID")
    period_label: str = Field(..., description="期間標籤 (YYYY-MM, YYYY-H1/H2, YYYY)")
    roster_cycle: RosterCycle = Field(..., description="造冊週期")
    academic_year: int = Field(..., description="學年度")
    student_verification_enabled: bool = Field(True, description="是否啟用學籍驗證")
    ranking_id: Optional[int] = Field(None, description="指定排名ID（若有多個排名時使用）")


class RosterExportRequest(BaseModel):
    """造冊匯出請求"""

    template_name: str = Field("STD_UP_MIXLISTA", description="Excel範本名稱")
    include_header: bool = Field(True, description="是否包含標題行")
    include_statistics: bool = Field(True, description="是否包含統計資訊")
    max_preview_rows: Optional[int] = Field(10, description="預覽模式最大行數")
    async_mode: bool = Field(False, description="是否使用非同步匯出")
    include_excluded: bool = Field(False, description="是否包含排除項目")


class RosterItemResponse(BaseModel):
    """造冊項目回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    roster_id: int
    application_id: int
    student_id_number: str
    student_name: str
    scholarship_amount: Decimal
    verification_status: StudentVerificationStatus
    verification_snapshot: Optional[Dict[str, Any]] = None  # 對應 model 欄位名稱
    is_included: bool  # 對應 model 欄位名稱
    exclusion_reason: Optional[str] = None  # 對應 model 欄位名稱
    created_at: datetime
    updated_at: Optional[datetime] = None


class RosterAuditLogResponse(BaseModel):
    """造冊稽核記錄回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    roster_id: int
    action: RosterAuditAction
    level: RosterAuditLevel
    title: str
    description: Optional[str] = None
    audit_metadata: Optional[Dict[str, Any]] = None
    created_by_user_id: Optional[int] = None
    created_at: datetime


class RosterResponse(BaseModel):
    """造冊回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    roster_code: str
    scholarship_configuration_id: int
    ranking_id: Optional[int] = None  # 關聯的排名ID（可選）
    period_label: str
    roster_cycle: RosterCycle
    academic_year: int
    status: RosterStatus
    trigger_type: RosterTriggerType
    qualified_count: int
    disqualified_count: int
    total_amount: Decimal
    created_by_user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    locked_at: Optional[datetime] = None
    locked_by_user_id: Optional[int] = None

    # 前端需要的額外欄位
    scholarship_config_name: Optional[str] = None
    ranking_name: Optional[str] = None  # 關聯排名的名稱
    student_count: Optional[int] = None
    roster_name: Optional[str] = None  # 對應 roster_code
    roster_period: Optional[str] = None  # 對應 roster_cycle.value

    # 關聯資料（選用）
    items: Optional[List[RosterItemResponse]] = None
    audit_logs: Optional[List[RosterAuditLogResponse]] = None


class RosterListResponse(BaseModel):
    """造冊清單回應"""

    items: List[RosterResponse]
    total: int
    skip: int
    limit: int


class RosterStatisticsResponse(BaseModel):
    """造冊統計回應"""

    roster_id: int
    total_items: int
    qualified_count: int
    disqualified_count: int
    total_amount: Decimal
    verification_status_counts: Dict[str, int]
    created_at: datetime
    status: RosterStatus


class RosterScheduleRequest(BaseModel):
    """造冊排程請求"""

    scholarship_configuration_id: int = Field(..., description="獎學金配置ID")
    roster_cycle: RosterCycle = Field(..., description="造冊週期")
    schedule_cron: str = Field(..., description="Cron表達式")
    is_active: bool = Field(True, description="是否啟用排程")
    notification_emails: Optional[List[str]] = Field(None, description="通知信箱清單")


class RosterScheduleResponse(BaseModel):
    """造冊排程回應"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    scholarship_configuration_id: int
    roster_cycle: RosterCycle
    schedule_cron: str
    is_active: bool
    notification_emails: Optional[List[str]] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    created_by_user_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class StudentVerificationResponse(BaseModel):
    """學籍驗證回應"""

    student_id_number: str
    student_name: str
    status: StudentVerificationStatus
    message: str
    student_info: Dict[str, Any]
    verified_at: datetime
    api_response: Dict[str, Any]


class BatchVerificationRequest(BaseModel):
    """批次驗證請求"""

    students: List[Dict[str, str]] = Field(..., description="學生清單")
    # students format: [{"id": "A123456789", "name": "張三"}, ...]


class BatchVerificationResponse(BaseModel):
    """批次驗證回應"""

    results: Dict[str, StudentVerificationResponse]
    total_count: int
    success_count: int
    error_count: int


# 用於前端的簡化回應模型
class RosterSummaryResponse(BaseModel):
    """造冊摘要回應（用於列表顯示）"""

    id: int
    roster_code: str
    period_label: str
    status: RosterStatus
    qualified_count: int
    disqualified_count: int
    total_amount: Decimal
    created_at: datetime
    locked_at: Optional[datetime] = None


class RosterItemSummaryResponse(BaseModel):
    """造冊項目摘要回應"""

    id: int
    student_name: str
    student_id_number: str
    scholarship_amount: Decimal
    verification_status: StudentVerificationStatus
    is_qualified: bool


# 統計和報表相關模型
class RosterAnalyticsRequest(BaseModel):
    """造冊分析請求"""

    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    scholarship_configuration_ids: Optional[List[int]] = None
    status_filter: Optional[List[RosterStatus]] = None


class RosterAnalyticsResponse(BaseModel):
    """造冊分析回應"""

    total_rosters: int
    total_amount: Decimal
    average_amount_per_roster: Decimal
    status_distribution: Dict[str, int]
    monthly_statistics: List[Dict[str, Any]]
    scholarship_type_distribution: Dict[str, Any]
    verification_status_summary: Dict[str, int]
