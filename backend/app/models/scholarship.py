"""
Scholarship type and rule models
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, Text, JSON, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from decimal import Decimal
from typing import Optional, List, Dict

from app.db.base_class import Base
from app.models.enums import Semester, SubTypeSelectionMode, CycleType


class ScholarshipStatus(enum.Enum):
    """Scholarship status enum"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class ScholarshipCategory(enum.Enum):
    """Scholarship category enum"""
    UNDERGRADUATE_FRESHMAN = "undergraduate_freshman"  # 學士班新生獎學金
    PHD = "phd"  # 國科會/教育部博士生獎學金
    DIRECT_PHD = "direct_phd"  # 逕讀博士獎學金

class ScholarshipSubType(enum.Enum):
    """Scholarship sub-type enum for combined scholarships"""

    GENERAL = "general"  # 作為無子獎學金類型時的預設值

    # For PhD scholarships
    NSTC = "nstc"  # 國科會 (National Science and Technology Council)
    MOE_1W = "moe_1w"    # 教育部 (Ministry of Education) + 指導教授配合款一萬
    MOE_2W = "moe_2w"  # 教育部 (Ministry of Education) + 指導教授配合款兩萬

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
    category = Column(String(50), nullable=False)
    sub_type_list = Column(JSON, default=[ScholarshipSubType.GENERAL.value]) # ["nstc", "moe_1w", "moe_2w"]
    sub_type_selection_mode = Column(Enum(SubTypeSelectionMode), default=SubTypeSelectionMode.SINGLE, nullable=False)
    
    # 學年度與學期設定
    academic_year = Column(Integer, nullable=False)  # 民國年，如 113 表示 113 學年度
    semester = Column(Enum(Semester), nullable=False)
    application_cycle = Column(Enum(CycleType), default=CycleType.SEMESTER, nullable=False)
    
    # 金額設定
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(10), default="TWD")
    
    # 白名單設定
    whitelist_enabled = Column(Boolean, default=False)  # 是否啟用白名單
    whitelist_student_ids = Column(JSON, default=[])  # 白名單學生ID列表
    
    # 申請時間
    # 續領申請期間（優先處理）
    renewal_application_start_date = Column(DateTime(timezone=True), nullable=True)
    renewal_application_end_date = Column(DateTime(timezone=True), nullable=True)
    
    # 一般申請期間（續領處理完畢後）
    application_start_date = Column(DateTime(timezone=True), nullable=True)
    application_end_date = Column(DateTime(timezone=True), nullable=True)

    # 續領審查期間
    renewal_professor_review_start = Column(DateTime(timezone=True), nullable=True)
    renewal_professor_review_end = Column(DateTime(timezone=True), nullable=True)
    renewal_college_review_start = Column(DateTime(timezone=True), nullable=True)
    renewal_college_review_end = Column(DateTime(timezone=True), nullable=True)

    # 一般申請審查期間
    requires_professor_recommendation = Column(Boolean, default=False)
    professor_review_start = Column(DateTime(timezone=True), nullable=True)
    professor_review_end = Column(DateTime(timezone=True), nullable=True)

    requires_college_review = Column(Boolean, default=False)
    college_review_start = Column(DateTime(timezone=True), nullable=True)
    college_review_end = Column(DateTime(timezone=True), nullable=True)

    review_deadline = Column(DateTime(timezone=True), nullable=True)

    # 狀態與設定
    status = Column(String(20), default=ScholarshipStatus.ACTIVE.value)
        
    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))
    
    # 關聯
    rules = relationship("ScholarshipRule", back_populates="scholarship_type", cascade="all, delete-orphan")
    applications = relationship("Application", foreign_keys="[Application.scholarship_type_id]")
    sub_type_configs = relationship("ScholarshipSubTypeConfig", back_populates="scholarship_type", cascade="all, delete-orphan")
    admins = relationship("AdminScholarship", back_populates="scholarship")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<ScholarshipType(id={self.id}, code={self.code}, name={self.name})>"
    
    @property
    def is_active(self) -> bool:
        """Check if scholarship type is active"""
        return bool(self.status == ScholarshipStatus.ACTIVE.value)
    
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
        return bool(self.application_start_date <= now <= self.application_end_date)
    
    @property
    def is_renewal_application_period(self) -> bool:
        """Check if within renewal application period"""
        now = datetime.now(timezone.utc)
        if not self.renewal_application_start_date or not self.renewal_application_end_date:
            return False
        return bool(self.renewal_application_start_date <= now <= self.renewal_application_end_date)
    
    @property
    def is_general_application_period(self) -> bool:
        """Check if within general application period"""
        now = datetime.now(timezone.utc)
        if not self.application_start_date or not self.application_end_date:
            return False
        return bool(self.application_start_date <= now <= self.application_end_date)
    
    @property
    def current_application_type(self) -> Optional[str]:
        """Get current application type: 'renewal' or 'general' or None"""
        if self.is_renewal_application_period:
            return "renewal"
        elif self.is_general_application_period:
            return "general"
        return None
    
    @property
    def academic_year_label(self) -> str:
        """Get academic year label for display"""
        return f"{self.academic_year}學年度 {self.get_semester_label()}"
    
    def get_semester_label(self) -> str:
        """Get semester label"""
        return {
            Semester.FIRST: "第一學期",
            Semester.SECOND: "第二學期",
        }.get(self.semester, "")
    
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
        now = datetime.now(timezone.utc)
        
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
        if self.sub_type_selection_mode == SubTypeSelectionMode.SINGLE:
            return len(selected) == 1 and selected[0] in self.sub_type_list
        elif self.sub_type_selection_mode == SubTypeSelectionMode.MULTIPLE:
            return all(s in self.sub_type_list for s in selected)
        elif self.sub_type_selection_mode == SubTypeSelectionMode.HIERARCHICAL:
            expected = self.sub_type_list[:len(selected)]
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
    
    def can_student_apply(self, student_id: int, semester: str) -> tuple[bool, str]:
        """Check if student can apply for this scholarship"""
        # Check if scholarship is active
        if not self.is_active:
            return False, "獎學金目前未開放申請"
        
        # Check application period
        if not self.is_application_period:
            return False, "目前不在申請期間內"
        
        # Check whitelist
        if not self.is_student_in_whitelist(student_id):
            return False, "您不在此獎學金的申請名單中"
        
        # Check if student already has an application for this semester
        from sqlalchemy.orm import Session
        # This would need to be implemented with proper session management
        # existing_app = session.query(Application).filter(
        #     Application.student_id == student_id,
        #     Application.scholarship_type_id == self.id,
        #     Application.semester == semester
        # ).first()
        # if existing_app:
        #     return False, "您已經在本學期申請過此獎學金"
        
        return True, ""

    def validate_sub_type_list(self) -> bool:
        """Validate sub_type_list against ScholarshipSubType enum"""
        if not self.sub_type_list:
            return True  # 空列表是有效的
        valid_types = [e.value for e in ScholarshipSubType]
        return all(sub_type in valid_types for sub_type in self.sub_type_list)

    def get_sub_type_config(self, sub_type_code: str) -> Optional['ScholarshipSubTypeConfig']:
        """Get sub-type configuration by code"""
        # 如果是 general 且沒有配置，返回 None（使用預設值）
        if sub_type_code == ScholarshipSubType.GENERAL.value:
            for config in self.sub_type_configs:
                if config.sub_type_code == sub_type_code and config.is_active:
                    return config
            return None  # general 沒有配置是正常的
        
        # 其他子類型必須有配置
        for config in self.sub_type_configs:
            if config.sub_type_code == sub_type_code and config.is_active:
                return config
        return None

    def get_active_sub_type_configs(self) -> List['ScholarshipSubTypeConfig']:
        """Get all active sub-type configurations ordered by display_order"""
        return sorted(
            [config for config in self.sub_type_configs if config.is_active],
            key=lambda x: x.display_order
        )

    def get_sub_type_translations(self) -> Dict[str, Dict[str, str]]:
        """Get sub-type translations for all supported languages"""
        translations = {"zh": {}, "en": {}}
        
        # 添加已配置的子類型
        for config in self.get_active_sub_type_configs():
            translations["zh"][config.sub_type_code] = config.name
            translations["en"][config.sub_type_code] = config.name_en or config.name
        
        # 為 general 子類型添加預設翻譯（如果沒有配置）
        if ScholarshipSubType.GENERAL.value in self.sub_type_list:
            general_config = self.get_sub_type_config(ScholarshipSubType.GENERAL.value)
            if not general_config:
                # 使用預設翻譯
                translations["zh"][ScholarshipSubType.GENERAL.value] = "一般獎學金"
                translations["en"][ScholarshipSubType.GENERAL.value] = "General Scholarship"
        
        return translations
    
    def get_semester_key(self) -> str:
        """Get unique key for this scholarship semester (for application limit checking)"""
        return f"{self.academic_year}_{self.semester.value}"
    
    def can_student_apply(self, student_id: int, existing_applications: List['Application'], is_renewal: bool = None) -> bool:
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
        semester_key = self.get_semester_key()
        for application in existing_applications:
            if (application.scholarship_type_id == self.id and 
                application.student_id == student_id and
                application.is_renewal == is_renewal):
                return False
        
        return True
    
    def can_student_apply_renewal(self, student_id: int, existing_applications: List['Application']) -> bool:
        """Check if student can apply for renewal"""
        return self.can_student_apply(student_id, existing_applications, True)
    
    def can_student_apply_general(self, student_id: int, existing_applications: List['Application']) -> bool:
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
            }
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
    def effective_amount(self) -> Optional[Decimal]:
        """Get effective amount (sub-type specific or fallback to main scholarship)"""
        if self.amount is not None:
            return self.amount
        elif self.scholarship_type:
            return self.scholarship_type.amount
        return None

class ScholarshipRule(Base):
    """
    Scholarship eligibility and validation rules
    
    This table stores the validation rules for scholarship applications.
    Each rule defines a specific condition that must be met for eligibility,
    such as GPA requirements, ranking criteria, or nationality restrictions.
    """
    __tablename__ = "scholarship_rules"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)
    # 如果獎學金類型沒有子類型，則為 None，此規則為通用規則，適用於所有子類型
    sub_type = Column(String(50), nullable=True, default=None) 
    
    # 規則基本資訊
    rule_name = Column(String(100), nullable=False)
    rule_type = Column(String(50), nullable=False)  # gpa, ranking, term_count, nationality, etc.
    tag = Column(String(20)) # 博士生 非陸生 中華民國國籍 等等
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
    
    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 關聯
    scholarship_type = relationship("ScholarshipType", back_populates="rules")

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