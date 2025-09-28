"""
Roster schedule models for automatic roster generation
造冊排程模型，用於自動造冊產生
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import JSON, Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.payment_roster import RosterCycle

if TYPE_CHECKING:
    from app.models.payment_roster import PaymentRoster
    from app.models.scholarship import ScholarshipConfiguration
    from app.models.user import User


class RosterScheduleStatus(enum.Enum):
    """排程狀態"""

    ACTIVE = "active"  # 啟用中
    PAUSED = "paused"  # 暫停
    DISABLED = "disabled"  # 停用
    ERROR = "error"  # 錯誤


class RosterSchedule(Base):
    """
    造冊排程設定

    用於設定自動產生造冊的排程規則
    """

    __tablename__ = "roster_schedules"

    id = Column(Integer, primary_key=True, index=True)

    # 基本資訊
    schedule_name = Column(String(100), nullable=False, comment="排程名稱")
    description = Column(Text, comment="排程說明")

    # 獎學金配置關聯
    scholarship_configuration_id = Column(
        Integer, ForeignKey("scholarship_configurations.id"), nullable=False, comment="獎學金配置ID"
    )

    # 排程設定
    roster_cycle = Column(
        Enum(RosterCycle, values_callable=lambda obj: [e.value for e in obj]), nullable=False, comment="造冊週期"
    )

    # Cron 表達式用於精確時間控制
    cron_expression = Column(String(100), comment="Cron表達式")

    # 排程執行參數
    auto_lock = Column(Boolean, default=False, comment="自動鎖定產生的造冊")
    student_verification_enabled = Column(Boolean, default=True, comment="是否啟用學籍驗證")
    notification_enabled = Column(Boolean, default=True, comment="是否發送通知")

    # 排程狀態
    status = Column(
        Enum(RosterScheduleStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=RosterScheduleStatus.ACTIVE,
        nullable=False,
        comment="排程狀態",
    )

    # 執行記錄
    last_run_at = Column(DateTime(timezone=True), comment="上次執行時間")
    next_run_at = Column(DateTime(timezone=True), comment="下次執行時間")
    last_run_result = Column(String(50), comment="上次執行結果")
    last_error_message = Column(Text, comment="上次執行錯誤訊息")

    # 執行統計
    total_runs = Column(Integer, default=0, comment="總執行次數")
    successful_runs = Column(Integer, default=0, comment="成功執行次數")
    failed_runs = Column(Integer, default=0, comment="失敗執行次數")

    # 通知設定
    notification_emails = Column(JSON, comment="通知信箱清單")
    notification_settings = Column(JSON, comment="通知設定")

    # 建立者和時間戳
    created_by_user_id = Column(Integer, ForeignKey("users.id"), comment="建立者ID")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="建立時間")
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), comment="更新時間")

    # 關聯
    scholarship_configuration = relationship("ScholarshipConfiguration", back_populates="roster_schedules")
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    def __repr__(self):
        return f"<RosterSchedule(id={self.id}, name='{self.schedule_name}', status='{self.status.value}')>"

    def to_dict(self):
        """轉換為字典格式"""
        return {
            "id": self.id,
            "schedule_name": self.schedule_name,
            "description": self.description,
            "scholarship_configuration_id": self.scholarship_configuration_id,
            "roster_cycle": self.roster_cycle.value if self.roster_cycle else None,
            "cron_expression": self.cron_expression,
            "auto_lock": self.auto_lock,
            "student_verification_enabled": self.student_verification_enabled,
            "notification_enabled": self.notification_enabled,
            "status": self.status.value if self.status else None,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "next_run_at": self.next_run_at.isoformat() if self.next_run_at else None,
            "last_run_result": self.last_run_result,
            "last_error_message": self.last_error_message,
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "notification_emails": self.notification_emails,
            "notification_settings": self.notification_settings,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def update_execution_stats(self, success: bool, error_message: Optional[str] = None):
        """更新執行統計"""
        self.total_runs = (self.total_runs or 0) + 1
        self.last_run_at = datetime.now(timezone.utc)

        if success:
            self.successful_runs = (self.successful_runs or 0) + 1
            self.last_run_result = "success"
            self.last_error_message = None
            # 如果先前是錯誤狀態，恢復為啟用狀態
            if self.status == RosterScheduleStatus.ERROR:
                self.status = RosterScheduleStatus.ACTIVE
        else:
            self.failed_runs = (self.failed_runs or 0) + 1
            self.last_run_result = "failed"
            self.last_error_message = error_message
            self.status = RosterScheduleStatus.ERROR

    def calculate_next_run_time(self) -> Optional[datetime]:
        """計算下次執行時間"""
        if not self.cron_expression or self.status != RosterScheduleStatus.ACTIVE:
            return None

        # 這裡應該使用 croniter 或類似的庫來計算下次執行時間
        # 目前先返回 None，待後續實作
        return None

    def is_active(self) -> bool:
        """檢查排程是否啟用"""
        return self.status == RosterScheduleStatus.ACTIVE

    def pause(self):
        """暫停排程"""
        self.status = RosterScheduleStatus.PAUSED

    def resume(self):
        """恢復排程"""
        if self.status == RosterScheduleStatus.PAUSED:
            self.status = RosterScheduleStatus.ACTIVE

    def disable(self):
        """停用排程"""
        self.status = RosterScheduleStatus.DISABLED
