"""
Scholarship type and rule schemas for API requests and responses
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum

class ScholarshipStatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class ScholarshipCategoryEnum(str, Enum):
    UNDERGRADUATE_FRESHMAN = "undergraduate_freshman"  # 學士班新生獎學金
    PHD = "phd"  # 國科會/教育部博士生獎學金
    DIRECT_PHD = "direct_phd"  # 逕讀博士獎學金


class SemesterEnum(str, Enum):
    FIRST = "first"
    SECOND = "second"


class ApplicationCycleEnum(str, Enum):
    SEMESTER = "semester"
    YEARLY = "yearly"


class SubTypeSelectionModeEnum(str, Enum):
    SINGLE = "single"          # 僅能選擇一個子項目
    MULTIPLE = "multiple"      # 可自由多選
    HIERARCHICAL = "hierarchical"  # 需依序選取：A → AB → ABC


class ScholarshipSubTypeEnum(str, Enum):
    GENERAL = "general"  # 一般獎學金（無子類型時的預設值）
    NSTC = "nstc"  # 國科會
    MOE_1W = "moe_1w"  # 教育部+指導教授配合款一萬
    MOE_2W = "moe_2w"  # 教育部+指導教授配合款兩萬


class ScholarshipTypeBase(BaseModel):
    code: str
    name: str
    name_en: Optional[str] = None
    description: Optional[str] = None
    description_en: Optional[str] = None
    category: ScholarshipCategoryEnum
    application_cycle: ApplicationCycleEnum = ApplicationCycleEnum.SEMESTER
    sub_type_list: Optional[List[str]] = None  # ["nstc", "moe_1w", "moe_2w"]
    amount: Decimal
    currency: str = "TWD"
    whitelist_enabled: bool = False
    whitelist_student_ids: Optional[List[int]] = None
    application_start_date: Optional[datetime] = None
    application_end_date: Optional[datetime] = None
    review_deadline: Optional[datetime] = None
    professor_review_start: Optional[datetime] = None
    professor_review_end: Optional[datetime] = None
    college_review_start: Optional[datetime] = None
    college_review_end: Optional[datetime] = None
    sub_type_selection_mode: SubTypeSelectionModeEnum = SubTypeSelectionModeEnum.SINGLE
    status: ScholarshipStatusEnum = ScholarshipStatusEnum.ACTIVE
    requires_professor_recommendation: bool = False
    requires_college_review: bool = False
    review_workflow: Optional[Dict[str, Any]] = None
    auto_approval_rules: Optional[Dict[str, Any]] = None

    @validator('sub_type_list')
    def validate_sub_type_list(cls, v):
        if v is not None:
            valid_types = [e.value for e in ScholarshipSubTypeEnum]
            for sub_type in v:
                if sub_type not in valid_types:
                    raise ValueError(f"Invalid sub_type: {sub_type}")
        return v
    
    @validator('application_end_date')
    def validate_date_range(cls, v, values):
        if v and 'application_start_date' in values and values['application_start_date']:
            if v <= values['application_start_date']:
                raise ValueError("application_end_date must be after application_start_date")
        return v
    
    @validator('amount')
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v
    
    
    @validator('professor_review_end')
    def validate_professor_review_period(cls, v, values):
        if v and 'professor_review_start' in values and values['professor_review_start']:
            if v <= values['professor_review_start']:
                raise ValueError("professor_review_end must be after professor_review_start")
        return v
    
    @validator('college_review_end')
    def validate_college_review_period(cls, v, values):
        if v and 'college_review_start' in values and values['college_review_start']:
            if v <= values['college_review_start']:
                raise ValueError("college_review_end must be after college_review_start")
        return v


class ScholarshipTypeCreate(ScholarshipTypeBase):
    pass


class ScholarshipTypeUpdate(BaseModel):
    name: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    description_en: Optional[str] = None
    application_cycle: Optional[ApplicationCycleEnum] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    whitelist_enabled: Optional[bool] = None
    whitelist_student_ids: Optional[List[int]] = None
    application_start_date: Optional[datetime] = None
    application_end_date: Optional[datetime] = None
    review_deadline: Optional[datetime] = None
    professor_review_start: Optional[datetime] = None
    professor_review_end: Optional[datetime] = None
    college_review_start: Optional[datetime] = None
    college_review_end: Optional[datetime] = None
    sub_type_selection_mode: Optional[SubTypeSelectionModeEnum] = None
    status: Optional[ScholarshipStatusEnum] = None
    requires_professor_recommendation: Optional[bool] = None
    requires_college_review: Optional[bool] = None
    sub_type_list: Optional[List[str]] = None


class ScholarshipTypeResponse(ScholarshipTypeBase):
    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None

    class Config:
        from_attributes = True


class ScholarshipRuleBase(BaseModel):
    rule_name: str
    rule_type: str
    tag: Optional[str] = None
    description: Optional[str] = None
    condition_field: str
    operator: str
    expected_value: str
    message: Optional[str] = None
    message_en: Optional[str] = None
    is_hard_rule: bool = False
    is_warning: bool = False
    priority: int = 0
    is_active: bool = True
    sub_type: Optional[str] = None


class ScholarshipRuleCreate(ScholarshipRuleBase):
    scholarship_type_id: int


class ScholarshipRuleUpdate(ScholarshipRuleBase):
    pass


class ScholarshipRule(ScholarshipRuleBase):
    scholarship_type_id: int


class ScholarshipRuleResponse(ScholarshipRuleBase):
    id: int
    scholarship_type_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RuleMessage(BaseModel):
    rule_id: int
    rule_name: str
    rule_type: str
    tag: Optional[str] = None
    message: str
    message_en: Optional[str] = None
    sub_type: Optional[str] = None
    priority: int = 0
    is_warning: bool = False
    is_hard_rule: bool = False


class EligibleScholarshipResponse(BaseModel):
    id: int
    code: str
    name: str
    name_en: str
    eligible_sub_types: List[str]
    category: str
    application_cycle: ApplicationCycleEnum
    description: Optional[str] = None
    description_en: Optional[str] = None
    amount: Decimal
    currency: str
    application_start_date: Optional[datetime] = None
    application_end_date: Optional[datetime] = None
    professor_review_start: Optional[datetime] = None
    professor_review_end: Optional[datetime] = None
    college_review_start: Optional[datetime] = None
    college_review_end: Optional[datetime] = None
    sub_type_selection_mode: SubTypeSelectionModeEnum
    passed: List[RuleMessage]
    warnings: List[RuleMessage]
    errors: List[RuleMessage]
    created_at: datetime
    
    class Config:
        from_attributes = True


class ScholarshipSubTypeConfigBase(BaseModel):
    """Base schema for scholarship sub-type configuration"""
    sub_type_code: str
    name: str
    name_en: Optional[str] = None
    description: Optional[str] = None
    description_en: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: str = "TWD"
    display_order: int = 0
    is_active: bool = True

    @validator('sub_type_code')
    def validate_sub_type_code(cls, v):
        valid_types = [e.value for e in ScholarshipSubTypeEnum]
        if v not in valid_types:
            raise ValueError(f"Invalid sub_type_code: {v}")
        return v
    
    @validator('name')
    def validate_name_for_general(cls, v, values):
        # For general sub-type, use default name if not provided
        if values.get('sub_type_code') == ScholarshipSubTypeEnum.GENERAL.value and not v:
            return "一般獎學金"
        return v


class ScholarshipSubTypeConfigCreate(ScholarshipSubTypeConfigBase):
    """Schema for creating scholarship sub-type configuration"""
    pass


class ScholarshipSubTypeConfigUpdate(BaseModel):
    """Schema for updating scholarship sub-type configuration"""
    name: Optional[str] = None
    name_en: Optional[str] = None
    description: Optional[str] = None
    description_en: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ScholarshipSubTypeConfigResponse(ScholarshipSubTypeConfigBase):
    """Schema for scholarship sub-type configuration response"""
    id: int
    scholarship_type_id: int
    effective_amount: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
