"""
Scholarship type and rule schemas for API requests and responses
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum

# Import the actual enums from models to ensure consistency
from app.models.enums import Semester

class ScholarshipStatusEnum(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DRAFT = "draft"


class ScholarshipCategoryEnum(str, Enum):
    UNDERGRADUATE_FRESHMAN = "undergraduate_freshman"  # 學士班新生獎學金
    PHD = "phd"  # 國科會/教育部博士生獎學金
    DIRECT_PHD = "direct_phd"  # 逕讀博士獎學金


# Removed SemesterEnum - using Semester from models.enums instead


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

    @field_validator('sub_type_list')
    @classmethod
    def validate_sub_type_list(cls, v):
        if v is not None:
            valid_types = [e.value for e in ScholarshipSubTypeEnum]
            for sub_type in v:
                if sub_type not in valid_types:
                    raise ValueError(f"Invalid sub_type: {sub_type}")
        return v
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        if v <= 0:
            raise ValueError("Amount must be greater than 0")
        return v
    
    @model_validator(mode='after')
    def validate_date_ranges(self):
        # Validate application date range
        if self.application_end_date and self.application_start_date:
            if self.application_end_date <= self.application_start_date:
                raise ValueError("application_end_date must be after application_start_date")
        
        # Validate professor review period
        if self.professor_review_end and self.professor_review_start:
            if self.professor_review_end <= self.professor_review_start:
                raise ValueError("professor_review_end must be after professor_review_start")
        
        # Validate college review period
        if self.college_review_end and self.college_review_start:
            if self.college_review_end <= self.college_review_start:
                raise ValueError("college_review_end must be after college_review_start")
        
        return self


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
    rule_name: str = Field(..., min_length=1, max_length=100, description="Rule name")
    rule_type: str = Field(..., min_length=1, max_length=50, description="Rule type")
    tag: Optional[str] = Field(None, max_length=20, description="Rule tag")
    description: Optional[str] = Field(None, description="Rule description")
    condition_field: str = Field(..., min_length=1, max_length=100, description="Field to check")
    operator: str = Field(..., pattern=r'^(>=|<=|==|!=|>|<|in|not_in|contains|not_contains)$', description="Comparison operator")
    expected_value: str = Field(..., min_length=1, max_length=500, description="Expected value")
    message: Optional[str] = Field(None, description="Validation message")
    message_en: Optional[str] = Field(None, description="English validation message")
    is_hard_rule: bool = Field(False, description="Whether this is a hard requirement")
    is_warning: bool = Field(False, description="Whether this is a warning rule")
    priority: int = Field(0, ge=0, le=999, description="Rule priority (0-999)")
    is_active: bool = Field(True, description="Whether rule is active")
    is_initial_enabled: bool = Field(True, description="Whether rule is enabled for initial applications")
    is_renewal_enabled: bool = Field(True, description="Whether rule is enabled for renewal applications")
    sub_type: Optional[str] = Field(None, max_length=50, description="Sub-type this rule applies to")
    
    # Academic context fields
    academic_year: Optional[int] = Field(None, ge=100, le=200, description="Academic year (Taiwan calendar)")
    semester: Optional[Semester] = Field(None, description="Semester")
    
    # Template fields
    is_template: bool = Field(False, description="Whether this is a template rule")
    template_name: Optional[str] = Field(None, max_length=100, description="Template name")
    template_description: Optional[str] = Field(None, description="Template description")
    
    @field_validator('academic_year')
    @classmethod
    def validate_academic_year(cls, v):
        if v is not None and (v < 100 or v > 200):
            raise ValueError("Academic year must be between 100 and 200 (Taiwan calendar)")
        return v
    
    @model_validator(mode='after')
    def validate_template_and_rules(self):
        if self.is_template and not self.template_name:
            raise ValueError("Template name is required for template rules")
        if self.is_warning and self.is_hard_rule:
            raise ValueError("Rule cannot be both hard rule and warning")
        return self


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
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    academic_period_label: Optional[str] = None  # Computed field for display

    @field_validator('semester', mode='before')
    @classmethod
    def validate_semester(cls, v):
        if v is None:
            return None
        if hasattr(v, 'value'):  # It's an enum object
            return v.value
        return v  # It's already a string

    class Config:
        from_attributes = True


class RuleMessage(BaseModel):
    rule_id: Union[int, str]  # Can be int for normal rules or string for subtype unified errors
    rule_name: str
    rule_type: str
    tag: Optional[str] = None
    message: str
    message_en: Optional[str] = None
    sub_type: Optional[str] = None
    priority: int = 0
    is_warning: bool = False
    is_hard_rule: bool = False


class SubTypeOption(BaseModel):
    """Schema for scholarship sub-type options"""
    value: Optional[str]
    label: str
    label_en: str
    is_default: bool = False


class EligibleScholarshipResponse(BaseModel):
    id: int
    configuration_id: int  # Add configuration ID for application creation
    code: str
    name: str
    name_en: str
    eligible_sub_types: List[SubTypeOption]
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

    @field_validator('sub_type_code')
    @classmethod
    def validate_sub_type_code(cls, v):
        valid_types = [e.value for e in ScholarshipSubTypeEnum]
        if v not in valid_types:
            raise ValueError(f"Invalid sub_type_code: {v}")
        return v
    
    @model_validator(mode='after')
    def validate_name_for_general(self):
        # For general sub-type, use default name if not provided
        if self.sub_type_code == ScholarshipSubTypeEnum.GENERAL.value and not self.name:
            self.name = "一般獎學金"
        return self


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


# Rule filtering and bulk operation schemas
class ScholarshipRuleFilter(BaseModel):
    """Schema for filtering scholarship rules"""
    scholarship_type_id: Optional[int] = None
    academic_year: Optional[int] = None
    semester: Optional[Semester] = None
    sub_type: Optional[str] = None
    rule_type: Optional[str] = None
    is_template: Optional[bool] = None
    is_active: Optional[bool] = None
    tag: Optional[str] = None


class RuleCopyRequest(BaseModel):
    """Schema for copying rules between periods"""
    source_academic_year: Optional[int] = Field(None, description="Source academic year")
    source_semester: Optional[Semester] = Field(None, description="Source semester")
    target_academic_year: int = Field(..., description="Target academic year")
    target_semester: Optional[Semester] = Field(None, description="Target semester")
    scholarship_type_ids: Optional[List[int]] = Field(None, description="Scholarship type IDs to copy")
    rule_ids: Optional[List[int]] = Field(None, description="Specific rule IDs to copy")
    overwrite_existing: bool = Field(False, description="Whether to overwrite existing rules")
    
    @field_validator('source_academic_year', 'target_academic_year')
    @classmethod
    def validate_academic_years(cls, v):
        if v is not None:
            from datetime import datetime
            current_roc_year = datetime.now().year - 1911
            min_year = current_roc_year - 10
            max_year = current_roc_year + 5
            if v < min_year or v > max_year:
                raise ValueError(f"Academic year must be between {min_year} and {max_year} (current year: {current_roc_year})")
        return v
    
    @field_validator('scholarship_type_ids')
    @classmethod
    def validate_scholarship_type_ids(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("Scholarship type IDs list cannot be empty")
        return v
    
    @field_validator('rule_ids')
    @classmethod
    def validate_rule_ids(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError("Rule IDs list cannot be empty")
        return v


class RuleTemplateRequest(BaseModel):
    """Schema for creating rule templates"""
    template_name: str = Field(..., min_length=1, max_length=100, description="Template name")
    template_description: Optional[str] = Field(None, description="Template description")
    scholarship_type_id: int = Field(..., ge=1, description="Scholarship type ID")
    rule_ids: List[int] = Field(..., min_items=1, description="Rule IDs to include in template")
    
    @field_validator('rule_ids')
    @classmethod
    def validate_rule_ids(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Rule IDs must be unique")
        return v


class ApplyTemplateRequest(BaseModel):
    """Schema for applying rule templates"""
    template_id: int = Field(..., ge=1, description="Template rule ID")
    scholarship_type_id: int = Field(..., ge=1, description="Target scholarship type ID")
    academic_year: int = Field(..., description="Target academic year")
    semester: Optional[Semester] = Field(None, description="Target semester")
    overwrite_existing: bool = Field(False, description="Whether to overwrite existing rules")
    
    @field_validator('academic_year')
    @classmethod
    def validate_academic_year(cls, v):
        from datetime import datetime
        current_roc_year = datetime.now().year - 1911
        min_year = current_roc_year - 10
        max_year = current_roc_year + 5
        if v < min_year or v > max_year:
            raise ValueError(f"Academic year must be between {min_year} and {max_year} (current year: {current_roc_year})")
        return v


class BulkRuleOperation(BaseModel):
    """Schema for bulk rule operations"""
    operation: str = Field(..., pattern=r'^(activate|deactivate|delete)$', description="Operation type")
    rule_ids: List[int] = Field(..., min_items=1, description="Rule IDs to operate on")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Operation-specific parameters")
    
    @field_validator('rule_ids')
    @classmethod
    def validate_rule_ids(cls, v):
        if len(set(v)) != len(v):
            raise ValueError("Rule IDs must be unique")
        return v
