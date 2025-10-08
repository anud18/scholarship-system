"""
Scholarship type and rule models
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

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
from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester, SubTypeSelectionMode

if TYPE_CHECKING:
    from app.models.application import Application


class ScholarshipStatus(enum.Enum):
    """Scholarship status enum"""

    active = "active"
    inactive = "inactive"
    draft = "draft"


class ScholarshipSubType(enum.Enum):
    """Scholarship sub-type enum for combined scholarships"""

    general = "general"  # 作為無子獎學金類型時的預設值

    # For PhD scholarships
    nstc = "nstc"  # 國科會 (National Science and Technology Council)
    moe_1w = "moe_1w"  # 教育部 (Ministry of Education) + 指導教授配合款一萬
    moe_2w = "moe_2w"  # 教育部 (Ministry of Education) + 指導教授配合款兩萬


class ScholarshipType(Base):
    """
    Scholarship type configuration model

    This table stores the configuration for different types of scholarships,
    including eligibility criteria, application periods, and review workflows.
    Each scholarship type can have multiple sub-types and associated rules.
    """

    __tablename__ = "scholarship_types"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    name_en = Column(String(200))
    description = Column(Text)
    description_en = Column(Text)

    # 類別設定
    # category removed - no longer needed for classification
    sub_type_list = Column(JSON, default=[ScholarshipSubType.general.value])  # ["nstc", "moe_1w", "moe_2w"]
    sub_type_selection_mode = Column(
        Enum(SubTypeSelectionMode, values_callable=lambda obj: [e.value for e in obj]),
        default=SubTypeSelectionMode.single,
        nullable=False,
    )

    # 申請週期設定
    application_cycle = Column(
        Enum(ApplicationCycle, values_callable=lambda obj: [e.value for e in obj]),
        default=ApplicationCycle.semester,
        nullable=False,
    )

    # 白名單設定
    whitelist_enabled = Column(Boolean, default=False)  # 是否啟用白名單

    # 申請條款文件
    terms_document_url = Column(String(500), nullable=True)  # 申請條款文件 URL

    # 狀態與設定
    status = Column(String(20), default=ScholarshipStatus.active.value)

    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))

    # 關聯
    rules = relationship(
        "ScholarshipRule",
        back_populates="scholarship_type",
        cascade="all, delete-orphan",
    )
    applications = relationship(
        "Application",
        foreign_keys="[Application.scholarship_type_id]",
        overlaps="scholarship,scholarship_type_ref",
    )
    sub_type_configs = relationship(
        "ScholarshipSubTypeConfig",
        back_populates="scholarship_type",
        cascade="all, delete-orphan",
    )
    admins = relationship("AdminScholarship", back_populates="scholarship")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<ScholarshipType(id={self.id}, code={self.code}, name={self.name})>"

    @property
    def is_active(self) -> bool:
        """Check if scholarship type is active"""
        return bool(self.status == ScholarshipStatus.active.value)

    def is_renewal_college_review_period(self) -> bool:
        """Check if within renewal college review period"""
        now = datetime.now(timezone.utc)
        if not self.renewal_college_review_start or not self.renewal_college_review_end:
            return False
        return bool(self.renewal_college_review_start <= now <= self.renewal_college_review_end)

    def is_professor_review_period(self) -> bool:
        """Check if within professor review period (renewal or general)"""
        now = datetime.now(timezone.utc)

        # 檢查續領教授審查期間
        if self.is_renewal_professor_review_period():
            return True

        # 檢查一般教授審查期間
        if not self.professor_review_start or not self.professor_review_end:
            return False
        return bool(self.professor_review_start <= now <= self.professor_review_end)

    def is_college_review_period(self) -> bool:
        """Check if within college review period (renewal or general)"""
        now = datetime.now(timezone.utc)

        # 檢查續領學院審查期間
        if self.is_renewal_college_review_period():
            return True

        # 檢查一般學院審查期間
        if not self.college_review_start or not self.college_review_end:
            return False
        return bool(self.college_review_start <= now <= self.college_review_end)

    def get_current_review_stage(self) -> Optional[str]:
        """Get current review stage: 'renewal_professor', 'renewal_college', 'general_professor', 'general_college' or None"""
        # 續領階段
        if self.is_renewal_professor_review_period():
            return "renewal_professor"
        elif self.is_renewal_college_review_period():
            return "renewal_college"

        # 一般申請階段
        elif self.is_professor_review_period() and not self.is_renewal_professor_review_period():
            return "general_professor"
        elif self.is_college_review_period() and not self.is_renewal_college_review_period():
            return "general_college"

        return None

    def is_valid_sub_type_selection(self, selected: List[str]) -> bool:
        """Validate sub-type selection based on selection mode"""
        if self.sub_type_selection_mode == SubTypeSelectionMode.single:
            return len(selected) == 1 and selected[0] in self.sub_type_list
        elif self.sub_type_selection_mode == SubTypeSelectionMode.multiple:
            return all(s in self.sub_type_list for s in selected)
        elif self.sub_type_selection_mode == SubTypeSelectionMode.hierarchical:
            expected = self.sub_type_list[: len(selected)]
            return selected == expected
        return False

    def is_student_in_whitelist(self, student_id: int) -> bool:
        """Check if student is in whitelist"""
        # 如果未啟用白名單，則不限制申請（返回True表示通過檢查）
        if not self.whitelist_enabled:
            return True  # 未啟用白名單時，所有學生都可申請

        # 如果啟用白名單但列表為空，則無人可申請
        if not self.whitelist_student_ids:
            return False  # 啟用白名單但列表為空，無人可申請

        # 檢查學生是否在白名單中
        return student_id in self.whitelist_student_ids

    def get_main_type_from_code(self) -> str:
        """Extract main scholarship type from code"""
        if "UNDERGRADUATE_FRESHMAN" in self.code.upper():
            return "UNDERGRADUATE_FRESHMAN"
        elif "DIRECT_PHD" in self.code.upper():
            return "DIRECT_PHD"
        elif "PHD" in self.code.upper():
            return "PHD"
        return "GENERAL"

    def get_sub_type_from_code(self) -> str:
        """Extract sub scholarship type from code"""
        if "NSTC" in self.code.upper():
            return "NSTC"
        elif "MOE_1W" in self.code.upper():
            return "MOE_1W"
        elif "MOE_2W" in self.code.upper():
            return "MOE_2W"
        return "GENERAL"

    def validate_sub_type_list(self) -> bool:
        """Validate sub_type_list against ScholarshipSubType enum"""
        if not self.sub_type_list:
            return True  # 空列表是有效的
        valid_types = [e.value for e in ScholarshipSubType]
        return all(sub_type in valid_types for sub_type in self.sub_type_list)

    def get_sub_type_config(self, sub_type_code: str) -> Optional["ScholarshipSubTypeConfig"]:
        """Get sub-type configuration by code"""
        # 如果是 general 且沒有配置，返回 None（使用預設值）
        if sub_type_code == ScholarshipSubType.general.value:
            for config in self.sub_type_configs:
                if config.sub_type_code == sub_type_code and config.is_active:
                    return config
            return None  # general 沒有配置是正常的

        # 其他子類型必須有配置
        for config in self.sub_type_configs:
            if config.sub_type_code == sub_type_code and config.is_active:
                return config
        return None

    def get_active_sub_type_configs(self) -> List["ScholarshipSubTypeConfig"]:
        """Get all active sub-type configurations ordered by display_order"""
        return sorted(
            [config for config in self.sub_type_configs if config.is_active],
            key=lambda x: x.display_order,
        )

    def get_sub_type_translations(self) -> Dict[str, Dict[str, str]]:
        """Get sub-type translations for all supported languages"""
        translations = {"zh": {}, "en": {}}

        # 只添加已配置的子類型，所有翻譯都從資料庫撈
        for config in self.get_active_sub_type_configs():
            translations["zh"][config.sub_type_code] = config.name
            translations["en"][config.sub_type_code] = config.name_en or config.name

        return translations

    def can_student_apply(
        self,
        student_id: int,
        existing_applications: List["Application"],
        is_renewal: bool = None,
    ) -> bool:
        """
        Check if student can apply for this scholarship based on semester limits and application type

        Args:
            student_id: Student ID to check
            existing_applications: List of existing applications for this student
            is_renewal: True for renewal, False for general, None to auto-detect based on current period

        Returns:
            bool: True if student can apply, False otherwise
        """
        # Check whitelist first
        if not self.is_student_in_whitelist(student_id):
            return False

        # Auto-detect application type if not provided
        if is_renewal is None:
            is_renewal = self.current_application_type == "renewal"

        # Check if we're in the correct application period
        if is_renewal and not self.is_renewal_application_period:
            return False
        elif not is_renewal and not self.is_general_application_period:
            return False

        # Check if student already has an application for this semester
        for application in existing_applications:
            if (
                application.scholarship_type_id == self.id
                and application.student_id == student_id
                and application.is_renewal == is_renewal
            ):
                return False

        return True

    def can_student_apply_renewal(self, student_id: int, existing_applications: List["Application"]) -> bool:
        """Check if student can apply for renewal"""
        return self.can_student_apply(student_id, existing_applications, True)

    def can_student_apply_general(self, student_id: int, existing_applications: List["Application"]) -> bool:
        """Check if student can apply for general application"""
        return self.can_student_apply(student_id, existing_applications, False)

    def get_application_timeline(self) -> Dict[str, Dict[str, datetime]]:
        """Get complete application timeline"""
        timeline = {
            "renewal": {
                "application_start": self.renewal_application_start_date,
                "application_end": self.renewal_application_end_date,
                "professor_review_start": self.renewal_professor_review_start,
                "professor_review_end": self.renewal_professor_review_end,
                "college_review_start": self.renewal_college_review_start,
                "college_review_end": self.renewal_college_review_end,
            },
            "general": {
                "application_start": self.application_start_date,
                "application_end": self.application_end_date,
                "professor_review_start": self.professor_review_start,
                "professor_review_end": self.professor_review_end,
                "college_review_start": self.college_review_start,
                "college_review_end": self.college_review_end,
            },
        }
        return timeline

    def get_next_deadline(self) -> Optional[datetime]:
        """Get the next upcoming deadline"""
        now = datetime.now(timezone.utc)
        deadlines = []

        # Collect all deadlines
        if self.renewal_application_end_date and self.renewal_application_end_date > now:
            deadlines.append(("續領申請截止", self.renewal_application_end_date))
        if self.renewal_professor_review_end and self.renewal_professor_review_end > now:
            deadlines.append(("續領教授審查截止", self.renewal_professor_review_end))
        if self.renewal_college_review_end and self.renewal_college_review_end > now:
            deadlines.append(("續領學院審查截止", self.renewal_college_review_end))
        if self.application_end_date and self.application_end_date > now:
            deadlines.append(("一般申請截止", self.application_end_date))
        if self.professor_review_end and self.professor_review_end > now:
            deadlines.append(("一般教授審查截止", self.professor_review_end))
        if self.college_review_end and self.college_review_end > now:
            deadlines.append(("一般學院審查截止", self.college_review_end))
        if self.review_deadline and self.review_deadline > now:
            deadlines.append(("總審查截止", self.review_deadline))

        if not deadlines:
            return None

        # Return the earliest deadline
        return min(deadlines, key=lambda x: x[1])[1]


class ScholarshipSubTypeConfig(Base):
    """
    Scholarship sub-type configuration model

    This table stores the configuration for scholarship sub-types,
    including display names, descriptions, and specific settings.
    """

    __tablename__ = "scholarship_sub_type_configs"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)
    sub_type_code = Column(String(50), nullable=False)  # "nstc", "moe_1w", "moe_2w"

    # 顯示名稱
    name = Column(String(200), nullable=False)  # 中文名稱
    name_en = Column(String(200))  # 英文名稱

    # 描述
    description = Column(Text)
    description_en = Column(Text)

    # 子類型特定設定
    amount = Column(Numeric(10, 2))  # 子類型特定金額，如果為 None 則使用主獎學金金額
    currency = Column(String(10), default="TWD")

    # 顯示設定
    display_order = Column(Integer, default=0)  # 顯示順序
    is_active = Column(Boolean, default=True)  # 是否啟用

    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))

    # 關聯
    scholarship_type = relationship("ScholarshipType", back_populates="sub_type_configs")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<ScholarshipSubTypeConfig(id={self.id}, sub_type_code={self.sub_type_code}, name={self.name})>"

    @property
    def display_name(self) -> str:
        """Get display name based on current locale"""
        return self.name_en or self.name

    @property
    def effective_amount(self) -> Optional[int]:
        """Get effective amount (sub-type specific or fallback to main scholarship)"""
        if self.amount is not None:
            return self.amount
        # Note: ScholarshipType no longer has amount field - this should come from configuration
        return None


class ScholarshipRule(Base):
    """
    Scholarship eligibility and validation rules

    This table stores the validation rules for scholarship applications.
    Each rule defines a specific condition that must be met for eligibility,
    such as GPA requirements, ranking criteria, or nationality restrictions.
    Rules can be contextualized by academic year and semester for period-specific requirements.
    """

    __tablename__ = "scholarship_rules"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)
    # 如果獎學金類型沒有子類型，則為 None，此規則為通用規則，適用於所有子類型
    sub_type = Column(String(50), nullable=True, default=None)

    # Academic context - rules can be specific to academic year and semester
    academic_year = Column(Integer, nullable=True, index=True)  # 民國年，如 113 表示 113 學年度
    semester = Column(
        Enum(Semester, values_callable=lambda obj: [e.value for e in obj]), nullable=True, index=True
    )  # 學期，學年制可為 NULL

    # Rule template information
    is_template = Column(Boolean, default=False, nullable=False)  # 是否為規則模板
    template_name = Column(String(100), nullable=True)  # 模板名稱
    template_description = Column(Text)  # 模板描述

    # 規則基本資訊
    rule_name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)  # gpa, ranking, term_count, nationality, etc.
    tag = Column(String(20))  # 博士生 非陸生 中華民國國籍 等等
    description = Column(Text)

    # 規則條件
    condition_field = Column(String(100))  # 檢查的欄位名稱
    operator = Column(String(20))  # >=, <=, ==, !=, in, not_in
    expected_value = Column(String(500))  # 期望值
    message = Column(Text)  # 驗證訊息
    message_en = Column(Text)  # 英文訊息

    # 規則設定
    is_hard_rule = Column(Boolean, default=False)  # 是否為硬性規則，硬性規則必須滿足，否則無法申請
    is_warning = Column(Boolean, default=False)  # 是否為警告規則
    priority = Column(Integer, default=0)  # 優先級

    # 狀態
    is_active = Column(Boolean, default=True)
    is_initial_enabled = Column(Boolean, default=True, nullable=False)  # 初領是否啟用
    is_renewal_enabled = Column(Boolean, default=True, nullable=False)  # 續領是否啟用

    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))

    # 關聯
    scholarship_type = relationship("ScholarshipType", back_populates="rules")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<ScholarshipRule(id={self.id}, rule_name={self.rule_name}, rule_type={self.rule_type}, scholarship_type_id={self.scholarship_type_id}, sub_type={self.sub_type})>"

    def validate_sub_type(self) -> bool:
        """Validate sub_type against ScholarshipSubType enum and the scholarship_type's sub_type_list"""
        if not self.sub_type:
            return False
        valid_types = [e.value for e in ScholarshipSubType]
        if self.sub_type not in valid_types:
            return False
        if not self.scholarship_type or not self.scholarship_type.sub_type_list:
            return False
        return self.sub_type in self.scholarship_type.sub_type_list

    @property
    def academic_period_label(self) -> str:
        """Get academic period label for display"""
        if self.is_template:
            return "模板"
        if not self.academic_year:
            return "通用"
        if self.semester:
            semester_label = {
                Semester.first: "第一學期",
                Semester.second: "第二學期",
            }.get(self.semester, "")
            return f"{self.academic_year}學年度 {semester_label}"
        return f"{self.academic_year}學年度"

    def is_applicable_to_period(self, academic_year: int, semester: Optional[Semester] = None) -> bool:
        """Check if this rule is applicable to the given academic period"""
        # Templates are not applicable to specific periods
        if self.is_template:
            return False

        # Universal rules (no academic context) apply to all periods
        if not self.academic_year:
            return True

        # Check academic year match
        if self.academic_year != academic_year:
            return False

        # Check semester match (None means yearly rule)
        if self.semester is None:  # Yearly rule
            return True

        return self.semester == semester

    def create_copy_for_period(self, academic_year: int, semester: Optional[Semester] = None) -> "ScholarshipRule":
        """Create a copy of this rule for a different academic period"""
        return ScholarshipRule(
            scholarship_type_id=self.scholarship_type_id,
            sub_type=self.sub_type,
            academic_year=academic_year,
            semester=semester,
            is_template=False,  # Copies are not templates
            rule_name=self.rule_name,
            rule_type=self.rule_type,
            tag=self.tag,
            description=self.description,
            condition_field=self.condition_field,
            operator=self.operator,
            expected_value=self.expected_value,
            message=self.message,
            message_en=self.message_en,
            is_hard_rule=self.is_hard_rule,
            is_warning=self.is_warning,
            priority=self.priority,
            is_active=self.is_active,
        )


class ScholarshipConfiguration(Base):
    """
    動態獎學金配置表

    This table stores dynamic configuration settings for scholarships,
    including application cycles, quota management, and other characteristics
    that can be modified without changing the core scholarship type structure.
    Each configuration is unique per scholarship type and cycle (e.g., "113-1", "113-2", "114" for academic year)
    """

    __tablename__ = "scholarship_configurations"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)

    # 週期識別 - 作為唯一標識符
    academic_year = Column(Integer, nullable=False, index=True)  # 民國年，如 113 表示 113 學年度
    semester = Column(
        Enum(Semester, values_callable=lambda obj: [e.value for e in obj]), nullable=True, index=True
    )  # 學期制獎學金需要，學年制可為 NULL

    # 基本配置資訊
    config_name = Column(String(200), nullable=False)  # 配置名稱
    config_code = Column(String(50), unique=True, index=True, nullable=False)  # 配置代碼
    description = Column(Text)  # 配置描述
    description_en = Column(Text)  # 英文描述

    # 配額限制配置
    has_quota_limit = Column(Boolean, default=False, nullable=False)  # 是否有配額限制
    has_college_quota = Column(Boolean, default=False, nullable=False)  # 是否有學院配額
    quota_management_mode = Column(
        Enum(QuotaManagementMode, values_callable=lambda obj: [e.value for e in obj]),
        default=QuotaManagementMode.none,
        nullable=False,
    )

    # 配額詳細設定
    total_quota = Column(Integer, nullable=True)  # 總配額數量
    quotas = Column(JSON, nullable=True)  # 配額配置，矩陣格式 {"nstc": {"EE": 5, "EN": 4}, "moe_1w": {"EE": 6, "EN": 5}}

    # 金額設定 (從 ScholarshipType 移至此處)
    amount = Column(Integer, nullable=False)  # 獎學金金額（整數）
    currency = Column(String(10), default="TWD")

    whitelist_student_ids = Column(
        JSON, default={}
    )  # 白名單學號列表，依子獎學金區分 {"general": ["0856001", "0856002"], "nstc": ["0856003"]}

    # 申請時間 (從 ScholarshipType 移至此處)
    # 續領申請期間（優先處理）
    renewal_application_start_date = Column(DateTime(timezone=True), nullable=True)
    renewal_application_end_date = Column(DateTime(timezone=True), nullable=True)

    # 一般申請期間（續領處理完畢後）
    application_start_date = Column(DateTime(timezone=True), nullable=True)
    application_end_date = Column(DateTime(timezone=True), nullable=True)

    # 續領審查期間 (從 ScholarshipType 移至此處)
    renewal_professor_review_start = Column(DateTime(timezone=True), nullable=True)
    renewal_professor_review_end = Column(DateTime(timezone=True), nullable=True)
    renewal_college_review_start = Column(DateTime(timezone=True), nullable=True)
    renewal_college_review_end = Column(DateTime(timezone=True), nullable=True)

    # 一般申請審查期間 (從 ScholarshipType 移至此處)
    requires_professor_recommendation = Column(Boolean, default=False)
    professor_review_start = Column(DateTime(timezone=True), nullable=True)
    professor_review_end = Column(DateTime(timezone=True), nullable=True)

    requires_college_review = Column(Boolean, default=False)
    college_review_start = Column(DateTime(timezone=True), nullable=True)
    college_review_end = Column(DateTime(timezone=True), nullable=True)

    review_deadline = Column(DateTime(timezone=True), nullable=True)

    # 狀態與有效性
    is_active = Column(Boolean, default=True, nullable=False)
    effective_start_date = Column(DateTime(timezone=True), nullable=True)  # 生效開始日期
    effective_end_date = Column(DateTime(timezone=True), nullable=True)  # 生效結束日期

    # 版本控制
    version = Column(String(20), default="1.0")  # 配置版本
    previous_config_id = Column(Integer, ForeignKey("scholarship_configurations.id"), nullable=True)

    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))

    # 關聯
    scholarship_type = relationship("ScholarshipType", backref="configurations")
    previous_config = relationship("ScholarshipConfiguration", remote_side=[id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    roster_schedules = relationship("RosterSchedule", back_populates="scholarship_configuration")

    # 唯一性約束：每個獎學金類型在每個學年度/學期只能有一個配置
    __table_args__ = (
        UniqueConstraint(
            "scholarship_type_id",
            "academic_year",
            "semester",
            name="uq_scholarship_config_type_year_semester",
        ),
    )

    def __repr__(self):
        return f"<ScholarshipConfiguration(id={self.id}, config_code={self.config_code}, name={self.config_name})>"

    @property
    def cycle(self) -> str:
        """Get cycle string representation for compatibility"""
        if self.semester:
            return f"{self.academic_year}-{self.semester.value}"
        return str(self.academic_year)

    @property
    def academic_year_label(self) -> str:
        """Get academic year label for display"""
        if self.semester:
            semester_label = {
                Semester.first: "第一學期",
                Semester.second: "第二學期",
            }.get(self.semester, "")
            return f"{self.academic_year}學年度 {semester_label}"
        return f"{self.academic_year}學年度"

    @property
    def is_effective(self) -> bool:
        """Check if configuration is currently effective"""
        now = datetime.now(timezone.utc)

        if not self.is_active:
            return False

        # Handle timezone-aware and naive datetime comparison
        if self.effective_start_date:
            start_date = self.effective_start_date
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if now < start_date:
                return False

        if self.effective_end_date:
            end_date = self.effective_end_date
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            if now > end_date:
                return False

        return True

    def get_quota_for_college(self, college_code: str) -> Optional[int]:
        """Get quota allocation for specific college (simple mode)"""
        if not self.has_college_quota or not self.quotas:
            return None
        return self.quotas.get(college_code)

    def get_matrix_quota(self, sub_type: str, college_code: str) -> Optional[int]:
        """Get quota allocation for specific sub-type and college (matrix mode)"""
        if not self.has_college_quota or not self.quotas:
            return None

        sub_type_quotas = self.quotas.get(sub_type, {})
        return sub_type_quotas.get(college_code)

    def set_matrix_quota(self, sub_type: str, college_code: str, quota: int) -> None:
        """Set quota allocation for specific sub-type and college"""
        if not self.quotas:
            self.quotas = {}

        if sub_type not in self.quotas:
            self.quotas[sub_type] = {}

        self.quotas[sub_type][college_code] = quota

    def get_sub_type_total_quota(self, sub_type: str) -> int:
        """Get total quota for a specific sub-type across all colleges"""
        if not self.has_college_quota or not self.quotas:
            return 0

        sub_type_quotas = self.quotas.get(sub_type, {})
        return sum(sub_type_quotas.values())

    def get_college_total_quota(self, college_code: str) -> int:
        """Get total quota for a specific college across all sub-types"""
        if not self.has_college_quota or not self.quotas:
            return 0

        total = 0
        for sub_type_quotas in self.quotas.values():
            total += sub_type_quotas.get(college_code, 0)
        return total

    def get_matrix_quota_summary(self) -> Dict[str, Any]:
        """Get complete matrix quota summary"""
        if not self.has_college_quota or not self.quotas:
            return {"sub_types": {}, "colleges": {}, "grand_total": 0}

        # Calculate totals by sub-type
        sub_type_totals = {}
        for sub_type in self.quotas:
            sub_type_totals[sub_type] = self.get_sub_type_total_quota(sub_type)

        # Calculate totals by college
        all_colleges = set()
        for sub_type_quotas in self.quotas.values():
            all_colleges.update(sub_type_quotas.keys())

        college_totals = {}
        for college_code in all_colleges:
            college_totals[college_code] = self.get_college_total_quota(college_code)

        # Calculate grand total
        grand_total = sum(sub_type_totals.values())

        return {
            "matrix": self.quotas,
            "sub_type_totals": sub_type_totals,
            "college_totals": college_totals,
            "grand_total": grand_total,
        }

    def get_total_available_quota(self) -> int:
        """Get total available quota considering all restrictions"""
        if not self.has_quota_limit:
            return -1  # Unlimited

        if self.quota_management_mode == QuotaManagementMode.none:
            return -1  # Unlimited

        return self.total_quota or 0

    def validate_quota_config(self) -> List[str]:
        """Validate quota configuration and return list of errors"""
        errors = []

        if self.has_quota_limit and not self.total_quota:
            errors.append("總配額不能為空當啟用配額限制時")

        if self.has_college_quota and not self.quotas:
            errors.append("學院配額配置不能為空當啟用學院配額時")

        if self.has_college_quota and self.quotas:
            # For matrix structure: {sub_type: {college: quota}}
            college_total = sum(
                sum(college_quotas.values())
                for college_quotas in self.quotas.values()
                if isinstance(college_quotas, dict)
            )
            if self.total_quota and college_total > self.total_quota:
                errors.append(f"學院配額總和 ({college_total}) 超過總配額 ({self.total_quota})")

        # Validate renewal review dates
        if not self.requires_professor_recommendation:
            if self.renewal_professor_review_start or self.renewal_professor_review_end:
                errors.append("續領教授審查時間不應設定當不需要教授推薦時")

        if not self.requires_college_review:
            if self.renewal_college_review_start or self.renewal_college_review_end:
                errors.append("續領學院審查時間不應設定當不需要學院審查時")

        return errors

    def export_config(self) -> Dict[str, Any]:
        """Export configuration as dictionary for backup/migration"""
        return {
            "config_code": self.config_code,
            "config_name": self.config_name,
            "description": self.description,
            "description_en": self.description_en,
            "academic_year": self.academic_year,
            "semester": self.semester.value if self.semester else None,
            "has_quota_limit": self.has_quota_limit,
            "has_college_quota": self.has_college_quota,
            "quota_management_mode": self.quota_management_mode.value if self.quota_management_mode else None,
            "total_quota": self.total_quota,
            "quotas": self.quotas,
            "version": self.version,
            "is_active": self.is_active,
            "effective_start_date": self.effective_start_date.isoformat() if self.effective_start_date else None,
            "effective_end_date": self.effective_end_date.isoformat() if self.effective_end_date else None,
            "amount": self.amount,  # Already integer
            "currency": self.currency,
            "whitelist_student_ids": self.whitelist_student_ids,
        }

    # Time-related methods moved from ScholarshipType
    @property
    def is_application_period(self) -> bool:
        """Check if within application period (renewal or general)"""
        now = datetime.now(timezone.utc)

        # 檢查續領申請期間
        if self.is_renewal_application_period:
            return True

        # 檢查一般申請期間
        if not self.application_start_date or not self.application_end_date:
            return False

        # Handle timezone-aware and naive datetime comparison
        start_date = self.application_start_date
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        end_date = self.application_end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        return bool(start_date <= now <= end_date)

    @property
    def is_renewal_application_period(self) -> bool:
        """Check if within renewal application period"""
        now = datetime.now(timezone.utc)
        if not self.renewal_application_start_date or not self.renewal_application_end_date:
            return False

        # Handle timezone-aware and naive datetime comparison
        start_date = self.renewal_application_start_date
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        end_date = self.renewal_application_end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        return bool(start_date <= now <= end_date)

    @property
    def is_general_application_period(self) -> bool:
        """Check if within general application period"""
        now = datetime.now(timezone.utc)
        if not self.application_start_date or not self.application_end_date:
            return False

        # Handle timezone-aware and naive datetime comparison
        start_date = self.application_start_date
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)

        end_date = self.application_end_date
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)

        return bool(start_date <= now <= end_date)

    @property
    def current_application_type(self) -> Optional[str]:
        """Get current application type: 'renewal' or 'general' or None"""
        if self.is_renewal_application_period:
            return "renewal"
        elif self.is_general_application_period:
            return "general"
        return None

    def is_renewal_professor_review_period(self) -> bool:
        """Check if within renewal professor review period"""
        now = datetime.now(timezone.utc)
        if not self.renewal_professor_review_start or not self.renewal_professor_review_end:
            return False
        return bool(self.renewal_professor_review_start <= now <= self.renewal_professor_review_end)

    def is_renewal_college_review_period(self) -> bool:
        """Check if within renewal college review period"""
        now = datetime.now(timezone.utc)
        if not self.renewal_college_review_start or not self.renewal_college_review_end:
            return False
        return bool(self.renewal_college_review_start <= now <= self.renewal_college_review_end)

    def is_professor_review_period(self) -> bool:
        """Check if within professor review period (renewal or general)"""
        now = datetime.now(timezone.utc)

        # 檢查續領教授審查期間
        if self.is_renewal_professor_review_period():
            return True

        # 檢查一般教授審查期間
        if not self.professor_review_start or not self.professor_review_end:
            return False
        return bool(self.professor_review_start <= now <= self.professor_review_end)

    def is_college_review_period(self) -> bool:
        """Check if within college review period (renewal or general)"""
        now = datetime.now(timezone.utc)

        # 檢查續領學院審查期間
        if self.is_renewal_college_review_period():
            return True

        # 檢查一般學院審查期間
        if not self.college_review_start or not self.college_review_end:
            return False
        return bool(self.college_review_start <= now <= self.college_review_end)

    def get_current_review_stage(self) -> Optional[str]:
        """Get current review stage: 'renewal_professor', 'renewal_college', 'general_professor', 'general_college' or None"""
        # 續領階段
        if self.is_renewal_professor_review_period():
            return "renewal_professor"
        elif self.is_renewal_college_review_period():
            return "renewal_college"

        # 一般申請階段
        elif self.is_professor_review_period() and not self.is_renewal_professor_review_period():
            return "general_professor"
        elif self.is_college_review_period() and not self.is_renewal_college_review_period():
            return "general_college"

        return None

    def is_student_in_whitelist(self, nycu_id: str, sub_type: str = None) -> bool:
        """Check if student is in whitelist for specific sub-scholarship type

        Args:
            nycu_id: 學號 (e.g., "0856001")
            sub_type: 子獎學金類型 (e.g., "general", "nstc")

        Returns:
            bool: True if student is in whitelist or whitelist is disabled
        """
        # 如果未啟用白名單，則不限制申請（返回True表示通過檢查）
        if not hasattr(self.scholarship_type, "whitelist_enabled") or not self.scholarship_type.whitelist_enabled:
            return True  # 未啟用白名單時，所有學生都可申請

        # 如果啟用白名單但配置為空，則無人可申請
        if not self.whitelist_student_ids:
            return False  # 啟用白名單但配置為空，無人可申請

        # 如果未指定子類型，檢查是否在任何子類型的白名單中
        if sub_type is None:
            for sub_list in self.whitelist_student_ids.values():
                if nycu_id in sub_list:
                    return True
            return False

        # 檢查學生是否在特定子類型的白名單中
        sub_whitelist = self.whitelist_student_ids.get(sub_type, [])
        return nycu_id in sub_whitelist

    def add_student_to_whitelist(self, nycu_id: str, sub_type: str) -> None:
        """Add student to whitelist for specific sub-scholarship type

        Args:
            nycu_id: 學號 (e.g., "0856001")
            sub_type: 子獎學金類型 (e.g., "general", "nstc")
        """
        if not self.whitelist_student_ids:
            self.whitelist_student_ids = {}

        if sub_type not in self.whitelist_student_ids:
            self.whitelist_student_ids[sub_type] = []

        if nycu_id not in self.whitelist_student_ids[sub_type]:
            self.whitelist_student_ids[sub_type].append(nycu_id)

    def remove_student_from_whitelist(self, nycu_id: str, sub_type: str = None) -> bool:
        """Remove student from whitelist. If sub_type is None, remove from all sub-types

        Args:
            nycu_id: 學號 (e.g., "0856001")
            sub_type: 子獎學金類型，None 表示從所有子類型移除

        Returns:
            bool: True if student was removed, False otherwise
        """
        if not self.whitelist_student_ids:
            return False

        removed = False
        if sub_type is None:
            # Remove from all sub-types
            for sub_list in self.whitelist_student_ids.values():
                if nycu_id in sub_list:
                    sub_list.remove(nycu_id)
                    removed = True
        else:
            # Remove from specific sub-type
            if sub_type in self.whitelist_student_ids and nycu_id in self.whitelist_student_ids[sub_type]:
                self.whitelist_student_ids[sub_type].remove(nycu_id)
                removed = True

        return removed

    def get_whitelist_for_subtype(self, sub_type: str) -> List[str]:
        """Get whitelist student nycu_ids for specific sub-scholarship type

        Returns:
            List[str]: List of nycu_ids (e.g., ["0856001", "0856002"])
        """
        return self.whitelist_student_ids.get(sub_type, [])

    def get_all_whitelisted_students(self) -> Dict[str, List[str]]:
        """Get all whitelisted students organized by sub-type

        Returns:
            Dict[str, List[str]]: {"general": ["0856001"], "nstc": ["0856002"]}
        """
        return dict(self.whitelist_student_ids) if self.whitelist_student_ids else {}

    def get_application_timeline(self) -> Dict[str, Dict[str, datetime]]:
        """Get complete application timeline"""
        timeline = {
            "renewal": {
                "application_start": self.renewal_application_start_date,
                "application_end": self.renewal_application_end_date,
                "professor_review_start": self.renewal_professor_review_start,
                "professor_review_end": self.renewal_professor_review_end,
                "college_review_start": self.renewal_college_review_start,
                "college_review_end": self.renewal_college_review_end,
            },
            "general": {
                "application_start": self.application_start_date,
                "application_end": self.application_end_date,
                "professor_review_start": self.professor_review_start,
                "professor_review_end": self.professor_review_end,
                "college_review_start": self.college_review_start,
                "college_review_end": self.college_review_end,
            },
        }
        return timeline

    def get_next_deadline(self) -> Optional[datetime]:
        """Get the next upcoming deadline"""
        now = datetime.now(timezone.utc)
        deadlines = []

        # Collect all deadlines
        if self.renewal_application_end_date and self.renewal_application_end_date > now:
            deadlines.append(("續領申請截止", self.renewal_application_end_date))
        if self.renewal_professor_review_end and self.renewal_professor_review_end > now:
            deadlines.append(("續領教授審查截止", self.renewal_professor_review_end))
        if self.renewal_college_review_end and self.renewal_college_review_end > now:
            deadlines.append(("續領學院審查截止", self.renewal_college_review_end))
        if self.application_end_date and self.application_end_date > now:
            deadlines.append(("一般申請截止", self.application_end_date))
        if self.professor_review_end and self.professor_review_end > now:
            deadlines.append(("一般教授審查截止", self.professor_review_end))
        if self.college_review_end and self.college_review_end > now:
            deadlines.append(("一般學院審查截止", self.college_review_end))
        if self.review_deadline and self.review_deadline > now:
            deadlines.append(("總審查截止", self.review_deadline))

        if not deadlines:
            return None

        # Return the earliest deadline
        return min(deadlines, key=lambda x: x[1])[1]
