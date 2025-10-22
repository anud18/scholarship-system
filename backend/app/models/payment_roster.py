"""
Payment roster models for scholarship system
造冊相關資料模型
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.college_review import get_json_type


class RosterCycle(enum.Enum):
    """造冊週期枚舉"""

    MONTHLY = "monthly"  # 每月
    SEMI_YEARLY = "semi_yearly"  # 半年
    YEARLY = "yearly"  # 年度


class RosterStatus(enum.Enum):
    """造冊狀態枚舉"""

    DRAFT = "draft"  # 草稿
    PROCESSING = "processing"  # 處理中
    COMPLETED = "completed"  # 已完成
    LOCKED = "locked"  # 已鎖定
    FAILED = "failed"  # 失敗


class RosterTriggerType(enum.Enum):
    """造冊觸發方式"""

    MANUAL = "manual"  # 手動觸發
    SCHEDULED = "scheduled"  # 排程觸發
    DRY_RUN = "dry_run"  # 預覽模式


class StudentVerificationStatus(enum.Enum):
    """學生身分驗證狀態"""

    VERIFIED = "verified"  # 已驗證通過
    GRADUATED = "graduated"  # 已畢業
    SUSPENDED = "suspended"  # 休學中
    WITHDRAWN = "withdrawn"  # 退學
    API_ERROR = "api_error"  # API錯誤
    NOT_FOUND = "not_found"  # 查無此人


class PaymentRoster(Base):
    """造冊主檔"""

    __tablename__ = "payment_rosters"

    id = Column(Integer, primary_key=True, index=True)

    # 造冊基本資訊
    roster_code = Column(String(50), unique=True, nullable=False, index=True)  # ROSTER-2025-01-PHD001
    scholarship_configuration_id = Column(Integer, ForeignKey("scholarship_configurations.id"), nullable=False)

    # 期間標記
    period_label = Column(String(20), nullable=False, index=True)  # 2025-01, 2025-H1, 2025
    academic_year = Column(Integer, nullable=False)  # 113
    roster_cycle = Column(Enum(RosterCycle, values_callable=lambda obj: [e.value for e in obj]), nullable=False)

    # 造冊狀態與觸發方式
    status = Column(
        Enum(RosterStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=RosterStatus.DRAFT,
        nullable=False,
    )
    trigger_type = Column(Enum(RosterTriggerType, values_callable=lambda obj: [e.value for e in obj]), nullable=False)

    # 執行資訊
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), default=func.now())
    completed_at = Column(DateTime(timezone=True))
    locked_at = Column(DateTime(timezone=True))
    locked_by = Column(Integer, ForeignKey("users.id"))

    # 統計資訊
    total_applications = Column(Integer, default=0)  # 總申請數
    qualified_count = Column(Integer, default=0)  # 合格人數
    disqualified_count = Column(Integer, default=0)  # 不合格人數
    total_amount = Column(Numeric(12, 2), default=0)  # 總金額

    # 檔案資訊
    excel_filename = Column(String(255))
    excel_file_path = Column(String(500))
    excel_file_size = Column(Integer)
    excel_file_hash = Column(String(64))  # SHA256

    # 學籍驗證設定
    student_verification_enabled = Column(Boolean, default=True)
    verification_api_failures = Column(Integer, default=0)  # API失敗次數

    # 備註與處理記錄
    notes = Column(Text)
    processing_log = Column(JSON)  # 處理過程日誌

    # 時間戳記
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # 關聯
    scholarship_configuration = relationship("ScholarshipConfiguration")
    creator = relationship("User", foreign_keys=[created_by])
    locker = relationship("User", foreign_keys=[locked_by])
    items = relationship("PaymentRosterItem", back_populates="roster", cascade="all, delete-orphan")
    audit_logs = relationship("RosterAuditLog", back_populates="roster", cascade="all, delete-orphan")

    # 唯一約束：每個獎學金配置+期間標記只能有一個造冊（除非明確覆蓋）
    __table_args__ = (
        UniqueConstraint("scholarship_configuration_id", "period_label", name="uq_roster_scholarship_period"),
    )

    def __repr__(self):
        return f"<PaymentRoster(id={self.id}, code={self.roster_code}, status={self.status})>"

    @property
    def is_locked(self) -> bool:
        """檢查是否已鎖定"""
        return self.status == RosterStatus.LOCKED

    @property
    def can_be_modified(self) -> bool:
        """檢查是否可以修改"""
        return self.status in [RosterStatus.DRAFT, RosterStatus.FAILED]

    @property
    def is_completed(self) -> bool:
        """檢查是否已完成"""
        return self.status in [RosterStatus.COMPLETED, RosterStatus.LOCKED]

    def lock(self, locked_by_user_id: int):
        """鎖定造冊"""
        if self.is_locked:
            raise ValueError("Roster is already locked")

        self.status = RosterStatus.LOCKED
        self.locked_at = datetime.now(timezone.utc)
        self.locked_by = locked_by_user_id

    def generate_excel_filename(self) -> str:
        """產生Excel檔案名稱"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"roster_{self.roster_code}_{timestamp}.xlsx"


class PaymentRosterItem(Base):
    """造冊明細檔"""

    __tablename__ = "payment_roster_items"

    id = Column(Integer, primary_key=True, index=True)
    roster_id = Column(Integer, ForeignKey("payment_rosters.id"), nullable=False, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)

    # 學生基本資料（造冊當時快照）
    student_id_number = Column(String(20), nullable=False)  # 身分證字號
    student_name = Column(String(100), nullable=False)  # 姓名
    student_email = Column(String(255))  # Email

    # 郵局帳號資訊
    bank_account = Column(String(20))  # 郵局帳號

    # 地址資訊
    permanent_address = Column(String(500))  # 戶籍地址
    mailing_address = Column(String(500))  # 通訊地址

    # 獎學金資訊
    scholarship_name = Column(String(200), nullable=False)
    scholarship_amount = Column(Numeric(10, 2), nullable=False)
    scholarship_subtype = Column(String(50))

    # 學籍驗證結果
    verification_status = Column(
        Enum(StudentVerificationStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=StudentVerificationStatus.VERIFIED,
        nullable=False,
    )
    verification_message = Column(String(500))  # 驗證訊息
    verification_at = Column(DateTime(timezone=True))  # 驗證時間
    verification_snapshot = Column(JSON)  # 驗證時的完整資料快照

    # 是否納入造冊
    is_included = Column(Boolean, default=True, nullable=False)
    exclusion_reason = Column(String(500))  # 排除原因

    # Excel匯出欄位
    excel_row_data = Column(JSON)  # 完整的Excel行資料
    excel_remarks = Column(Text)  # 說明欄內容

    # 身分識別
    nationality_code = Column(String(2), default="1")  # 1:本國人,2:外國人,3:大陸人
    residence_days_over_183 = Column(String(2), default="是")  # 居留天數是否滿183天

    # 獎學金規則驗證結果
    rule_validation_result = Column(JSON)  # 完整的規則驗證結果
    failed_rules = Column(JSON)  # 未通過的規則清單
    warning_rules = Column(JSON)  # 警告規則清單

    # 備取資訊（結構化）
    backup_info = Column(get_json_type(), nullable=True)  # 備取位置資訊
    # Format: [
    #   {
    #     "sub_type": "nstc",
    #     "backup_position": 1,
    #     "college": "EE",
    #     "allocation_reason": "備取第1名 nstc-EE"
    #   },
    #   ...
    # ]

    # 時間戳記
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # 關聯
    roster = relationship("PaymentRoster", back_populates="items")
    application = relationship("Application")

    def __repr__(self):
        return f"<PaymentRosterItem(id={self.id}, student={self.student_name}, amount={self.scholarship_amount})>"

    @property
    def is_qualified(self) -> bool:
        """檢查是否合格"""
        return self.verification_status == StudentVerificationStatus.VERIFIED and self.is_included and self.bank_account

    def generate_excel_remarks(self, period_label: str, scholarship_code: str) -> str:
        """產生Excel說明欄內容"""
        remarks = [f"造冊期間: {period_label}", f"獎學金: {scholarship_code}"]

        if not self.is_included:
            remarks.append(f"排除原因: {self.exclusion_reason}")
        elif self.verification_status != StudentVerificationStatus.VERIFIED:
            remarks.append(f"學籍狀態: {self.verification_status.value}")
        elif not self.bank_account:
            remarks.append("缺少郵局帳號資訊")
        else:
            remarks.append("合格")

        # 添加規則驗證警告（如果有）
        if self.warning_rules:
            warning_msg = "警告: " + "; ".join(self.warning_rules)
            remarks.append(warning_msg)

        return "; ".join(remarks)
