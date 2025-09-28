"""
Roster audit log models for tracking all roster operations
造冊稽核日誌模型，追蹤所有造冊操作
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.payment_roster import PaymentRoster
    from app.models.user import User


class RosterAuditAction(enum.Enum):
    """稽核動作類型"""

    CREATE = "create"  # 建立造冊
    UPDATE = "update"  # 更新造冊
    DELETE = "delete"  # 刪除造冊
    LOCK = "lock"  # 鎖定造冊
    UNLOCK = "unlock"  # 解鎖造冊
    EXPORT = "export"  # 匯出Excel
    DOWNLOAD = "download"  # 下載檔案
    STUDENT_VERIFY = "student_verify"  # 學籍驗證
    SCHEDULE_RUN = "schedule_run"  # 排程執行
    MANUAL_RUN = "manual_run"  # 手動執行
    DRY_RUN = "dry_run"  # 預覽執行
    STATUS_CHANGE = "status_change"  # 狀態變更
    ITEM_ADD = "item_add"  # 新增明細
    ITEM_REMOVE = "item_remove"  # 移除明細
    ITEM_UPDATE = "item_update"  # 更新明細


class RosterAuditLevel(enum.Enum):
    """稽核等級"""

    INFO = "info"  # 一般資訊
    WARNING = "warning"  # 警告
    ERROR = "error"  # 錯誤
    CRITICAL = "critical"  # 嚴重錯誤


class RosterAuditLog(Base):
    """造冊稽核日誌"""

    __tablename__ = "roster_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    roster_id = Column(Integer, ForeignKey("payment_rosters.id"), nullable=False, index=True)

    # 稽核基本資訊
    action = Column(Enum(RosterAuditAction, values_callable=lambda obj: [e.value for e in obj]), nullable=False)
    level = Column(
        Enum(RosterAuditLevel, values_callable=lambda obj: [e.value for e in obj]),
        default=RosterAuditLevel.INFO,
        nullable=False,
    )

    # 操作者資訊
    user_id = Column(Integer, ForeignKey("users.id"))  # 可能是系統自動操作，所以nullable=True
    user_name = Column(String(100))  # 操作者姓名快照
    user_role = Column(String(50))  # 操作者角色快照
    client_ip = Column(String(45))  # IPv4/IPv6 地址
    user_agent = Column(String(500))  # 瀏覽器資訊

    # 操作內容
    title = Column(String(200), nullable=False)  # 操作標題
    description = Column(Text)  # 詳細描述
    old_values = Column(JSON)  # 變更前的值
    new_values = Column(JSON)  # 變更後的值

    # 系統資訊
    api_endpoint = Column(String(200))  # API端點
    request_method = Column(String(10))  # HTTP方法
    request_payload = Column(JSON)  # 請求參數
    response_status = Column(Integer)  # 回應狀態碼
    processing_time_ms = Column(Integer)  # 處理時間(毫秒)

    # 業務資訊
    affected_items_count = Column(Integer, default=0)  # 影響的明細數量
    error_code = Column(String(50))  # 錯誤代碼
    error_message = Column(Text)  # 錯誤訊息
    warning_message = Column(Text)  # 警告訊息

    # 額外資料
    audit_metadata = Column(JSON)  # 額外的元資料
    tags = Column(JSON)  # 標籤，用於分類和搜尋

    # 時間戳記
    created_at = Column(DateTime(timezone=True), default=func.now(), index=True)

    # 關聯
    roster = relationship("PaymentRoster", back_populates="audit_logs")
    user = relationship("User")

    def __repr__(self):
        return f"<RosterAuditLog(id={self.id}, action={self.action}, user={self.user_name})>"

    @classmethod
    def create_audit_log(
        cls,
        roster_id: int,
        action: RosterAuditAction,
        title: str,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        user_role: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        description: Optional[str] = None,
        old_values: Optional[dict] = None,
        new_values: Optional[dict] = None,
        level: RosterAuditLevel = RosterAuditLevel.INFO,
        api_endpoint: Optional[str] = None,
        request_method: Optional[str] = None,
        request_payload: Optional[dict] = None,
        response_status: Optional[int] = None,
        processing_time_ms: Optional[int] = None,
        affected_items_count: int = 0,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        warning_message: Optional[str] = None,
        audit_metadata: Optional[dict] = None,
        tags: Optional[list] = None,
    ) -> "RosterAuditLog":
        """建立稽核日誌記錄"""
        return cls(
            roster_id=roster_id,
            action=action,
            level=level,
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            client_ip=client_ip,
            user_agent=user_agent,
            title=title,
            description=description,
            old_values=old_values,
            new_values=new_values,
            api_endpoint=api_endpoint,
            request_method=request_method,
            request_payload=request_payload,
            response_status=response_status,
            processing_time_ms=processing_time_ms,
            affected_items_count=affected_items_count,
            error_code=error_code,
            error_message=error_message,
            warning_message=warning_message,
            audit_metadata=audit_metadata,
            tags=tags,
        )

    def is_error(self) -> bool:
        """檢查是否為錯誤記錄"""
        return self.level in [RosterAuditLevel.ERROR, RosterAuditLevel.CRITICAL]

    def is_warning(self) -> bool:
        """檢查是否為警告記錄"""
        return self.level == RosterAuditLevel.WARNING

    def get_display_message(self) -> str:
        """取得顯示用訊息"""
        message = self.title
        if self.description:
            message += f": {self.description}"
        if self.error_message:
            message += f" (錯誤: {self.error_message})"
        if self.warning_message:
            message += f" (警告: {self.warning_message})"
        return message


class RosterSchedule(Base):
    """造冊排程設定"""

    __tablename__ = "roster_schedules"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_configuration_id = Column(Integer, ForeignKey("scholarship_configurations.id"), nullable=False)

    # 排程基本設定
    schedule_name = Column(String(100), nullable=False)
    is_enabled = Column(JSON, default=True)  # 是否啟用
    cron_expression = Column(String(100), nullable=False)  # Cron表達式

    # 執行設定
    timezone = Column(String(50), default="Asia/Taipei")
    retry_count = Column(Integer, default=3)  # 失敗重試次數
    retry_delay_minutes = Column(Integer, default=30)  # 重試間隔(分鐘)

    # 通知設定
    notify_on_success = Column(JSON, default=True)
    notify_on_failure = Column(JSON, default=True)
    notification_emails = Column(JSON)  # 通知信箱列表

    # 進階設定
    student_verification_enabled = Column(JSON, default=True)
    auto_lock_after_completion = Column(JSON, default=False)
    max_execution_time_minutes = Column(Integer, default=60)

    # 建立與更新資訊
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # 最後執行資訊
    last_run_at = Column(DateTime(timezone=True))
    last_run_status = Column(String(20))  # success, failed, running
    last_run_roster_id = Column(Integer, ForeignKey("payment_rosters.id"))
    next_run_at = Column(DateTime(timezone=True))

    # 關聯
    scholarship_configuration = relationship("ScholarshipConfiguration")
    creator = relationship("User", foreign_keys=[created_by])
    last_run_roster = relationship("PaymentRoster", foreign_keys=[last_run_roster_id])

    def __repr__(self):
        return f"<RosterSchedule(id={self.id}, name={self.schedule_name}, enabled={self.is_enabled})>"

    @property
    def is_active(self) -> bool:
        """檢查排程是否啟用且有效"""
        return self.is_enabled and self.cron_expression

    def calculate_next_run_time(self) -> Optional[datetime]:
        """計算下次執行時間"""
        # 這裡需要整合cron解析器來計算下次執行時間
        # 實作時可以使用croniter或APScheduler
        pass

    def should_retry(self) -> bool:
        """檢查是否應該重試"""
        return self.last_run_status == "failed" and self.retry_count > 0
