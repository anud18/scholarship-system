"""
Roster Schedule Schemas
造冊排程相關的 Pydantic 模型
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, validator

from app.models.payment_roster import RosterCycle
from app.models.roster_schedule import RosterScheduleStatus


class RosterScheduleBase(BaseModel):
    """造冊排程基本模型"""

    schedule_name: Optional[str] = Field(None, min_length=1, max_length=100, description="排程名稱（留空則自動生成）")
    description: Optional[str] = Field(None, description="排程說明")
    scholarship_configuration_id: int = Field(..., description="獎學金配置ID")
    roster_cycle: RosterCycle = Field(..., description="造冊週期")
    cron_expression: Optional[str] = Field(None, description="Cron表達式")
    auto_lock: bool = Field(False, description="自動鎖定產生的造冊")
    student_verification_enabled: bool = Field(True, description="是否啟用學籍驗證")
    notification_enabled: bool = Field(True, description="是否發送通知")
    notification_emails: Optional[List[str]] = Field(None, description="通知信箱清單")
    notification_settings: Optional[Dict[str, Any]] = Field(None, description="通知設定")

    @validator("cron_expression")
    def validate_cron_expression(cls, v):
        """驗證Cron表達式格式"""
        if v is not None:
            from croniter import croniter

            if not croniter.is_valid(v):
                raise ValueError("Invalid cron expression format")
        return v

    @validator("notification_emails")
    def validate_notification_emails(cls, v):
        """驗證通知信箱格式"""
        if v is not None:
            import re

            email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
            for email in v:
                if not email_pattern.match(email):
                    raise ValueError(f"Invalid email format: {email}")
        return v


class RosterScheduleCreate(RosterScheduleBase):
    """建立造冊排程模型"""

    pass


class RosterScheduleUpdate(BaseModel):
    """更新造冊排程模型"""

    schedule_name: Optional[str] = Field(None, min_length=1, max_length=100, description="排程名稱")
    description: Optional[str] = Field(None, description="排程說明")
    roster_cycle: Optional[RosterCycle] = Field(None, description="造冊週期")
    cron_expression: Optional[str] = Field(None, description="Cron表達式")
    auto_lock: Optional[bool] = Field(None, description="自動鎖定產生的造冊")
    student_verification_enabled: Optional[bool] = Field(None, description="是否啟用學籍驗證")
    notification_enabled: Optional[bool] = Field(None, description="是否發送通知")
    notification_emails: Optional[List[str]] = Field(None, description="通知信箱清單")
    notification_settings: Optional[Dict[str, Any]] = Field(None, description="通知設定")

    @validator("cron_expression")
    def validate_cron_expression(cls, v):
        """驗證Cron表達式格式"""
        if v is not None:
            from croniter import croniter

            if not croniter.is_valid(v):
                raise ValueError("Invalid cron expression format")
        return v

    @validator("notification_emails")
    def validate_notification_emails(cls, v):
        """驗證通知信箱格式"""
        if v is not None:
            import re

            email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
            for email in v:
                if not email_pattern.match(email):
                    raise ValueError(f"Invalid email format: {email}")
        return v


class RosterScheduleStatusUpdate(BaseModel):
    """更新排程狀態模型"""

    status: RosterScheduleStatus = Field(..., description="排程狀態")


class RosterScheduleResponse(BaseModel):
    """造冊排程回應模型"""

    id: int
    schedule_name: str
    description: Optional[str]
    scholarship_configuration_id: int
    roster_cycle: RosterCycle
    cron_expression: Optional[str]
    auto_lock: bool
    student_verification_enabled: bool
    notification_enabled: bool
    status: RosterScheduleStatus
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    last_run_result: Optional[str]
    last_error_message: Optional[str]
    total_runs: Optional[int]
    successful_runs: Optional[int]
    failed_runs: Optional[int]
    notification_emails: Optional[List[str]]
    notification_settings: Optional[Dict[str, Any]]
    created_by_user_id: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    scheduler_info: Optional[Dict[str, Any]] = Field(None, description="排程器狀態資訊")

    class Config:
        from_attributes = True


class RosterScheduleListResponse(BaseModel):
    """造冊排程列表回應模型"""

    schedules: List[Dict[str, Any]] = Field(..., description="排程列表")
    total: int = Field(..., description="總數量")
    skip: int = Field(..., description="跳過數量")
    limit: int = Field(..., description="限制數量")


class SchedulerStatusResponse(BaseModel):
    """排程器狀態回應模型"""

    success: bool
    scheduler_running: bool
    total_jobs: int
    jobs: List[Dict[str, Any]]


class ScheduleExecutionResponse(BaseModel):
    """排程執行回應模型"""

    success: bool
    message: str
    schedule_id: int


class ScheduleDeleteResponse(BaseModel):
    """排程刪除回應模型"""

    success: bool
    message: str


# 排程執行統計模型
class ScheduleExecutionStats(BaseModel):
    """排程執行統計"""

    total_runs: int = Field(0, description="總執行次數")
    successful_runs: int = Field(0, description="成功執行次數")
    failed_runs: int = Field(0, description="失敗執行次數")
    success_rate: float = Field(0.0, description="成功率")
    last_run_at: Optional[datetime] = Field(None, description="上次執行時間")
    last_run_result: Optional[str] = Field(None, description="上次執行結果")
    next_run_at: Optional[datetime] = Field(None, description="下次執行時間")


class ScheduleCronValidation(BaseModel):
    """Cron表達式驗證模型"""

    cron_expression: str = Field(..., description="Cron表達式")


class ScheduleCronValidationResponse(BaseModel):
    """Cron表達式驗證回應"""

    valid: bool = Field(..., description="是否有效")
    error_message: Optional[str] = Field(None, description="錯誤訊息")
    next_run_times: Optional[List[datetime]] = Field(None, description="接下來的執行時間")


# 排程執行歷史模型
class ScheduleExecutionHistory(BaseModel):
    """排程執行歷史"""

    id: int
    schedule_id: int
    started_at: datetime
    completed_at: Optional[datetime]
    status: str  # 'running', 'completed', 'failed'
    result: Optional[str]
    error_message: Optional[str]
    roster_id: Optional[int]  # 產生的造冊ID
    execution_time_seconds: Optional[float]

    class Config:
        from_attributes = True


class ScheduleExecutionHistoryResponse(BaseModel):
    """排程執行歷史回應"""

    executions: List[ScheduleExecutionHistory]
    total: int
    skip: int
    limit: int
