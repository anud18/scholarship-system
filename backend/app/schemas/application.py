"""
Application schemas for API requests and responses
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, validator

from app.models.application import ApplicationStatus


class StudentFinancialInfo(BaseModel):
    """Student financial information schema"""

    bank_postal_account: Optional[str] = Field(None, description="郵局帳號")
    bank_book_photo_url: Optional[str] = Field(None, description="郵局帳簿封面照片URL")
    account_holder_name: Optional[str] = Field(None, description="帳戶戶名")


class SupervisorInfo(BaseModel):
    """Supervisor information schema"""

    supervisor_employee_id: Optional[str] = Field(None, description="指導教授工號")
    supervisor_email: Optional[str] = Field(None, description="指導教授email")
    supervisor_name: Optional[str] = Field(None, description="指導教授姓名")
    supervisor_department: Optional[str] = Field(None, description="指導教授所屬系所")


class StudentDataSchema(BaseModel):
    """Comprehensive student data schema for applications"""

    # Basic student info (from external API)
    student_id: Optional[str] = Field(None, description="學號")
    name: Optional[str] = Field(None, description="姓名")
    email: Optional[str] = Field(None, description="Email")
    department: Optional[str] = Field(None, description="系所")
    degree: Optional[str] = Field(None, description="學位")

    # Financial information (user input)
    financial_info: Optional[StudentFinancialInfo] = Field(None, description="金融帳戶資訊")

    # Supervisor information (user input)
    supervisor_info: Optional[SupervisorInfo] = Field(None, description="指導教授資訊")

    # Contact information (user input)
    contact_phone: Optional[str] = Field(None, description="聯絡電話")
    contact_address: Optional[str] = Field(None, description="聯絡地址")

    # Academic information (from external API + user input)
    gpa: Optional[float] = Field(None, description="GPA")
    class_ranking: Optional[int] = Field(None, description="班級排名")
    class_total: Optional[int] = Field(None, description="班級總人數")
    dept_ranking: Optional[int] = Field(None, description="系所排名")
    dept_total: Optional[int] = Field(None, description="系所總人數")


class ApplicationBase(BaseModel):
    """Base application schema"""

    scholarship_type: str = Field(..., description="Scholarship type code")
    academic_year: str = Field(..., description="Academic year")
    semester: str = Field(..., description="Semester")

    # Student data (combines external API data + user input)
    student_data: Optional[StudentDataSchema] = Field(None, description="完整學生資料")

    # Application-specific data
    research_proposal: Optional[str] = Field(None, description="Research proposal")
    budget_plan: Optional[str] = Field(None, description="Budget plan")
    milestone_plan: Optional[str] = Field(None, description="Milestone plan")
    agree_terms: bool = Field(False, description="Agreement to terms")


class DynamicFormField(BaseModel):
    """動態表單欄位"""

    field_id: str = Field(..., description="欄位ID")
    field_type: str = Field(..., description="欄位類型 (text, number, select, etc.)")
    value: Any = Field(None, description="欄位值")
    required: bool = Field(default=True, description="是否必填")
    validation_rules: Optional[Dict[str, Any]] = Field(default=None, description="驗證規則")

    @validator("value")
    def validate_value_type(cls, v, values):
        """根據 field_type 驗證值的類型"""
        field_type = values.get("field_type")
        if field_type == "select" and not isinstance(v, (list, str)):
            raise ValueError("Select field value must be a string or list")
        elif field_type == "number" and not isinstance(v, (int, float)):
            raise ValueError("Number field value must be a number")
        return v


class DocumentData(BaseModel):
    """文件資料"""

    document_id: str = Field(..., description="文件ID")
    document_type: str = Field(..., description="文件類型")
    file_path: str = Field(..., description="檔案路徑")
    original_filename: str = Field(..., description="原始檔名")
    upload_time: str = Field(..., description="上傳時間 (ISO format string)")
    file_size: Optional[int] = Field(None, description="檔案大小")
    mime_type: Optional[str] = Field(None, description="檔案類型")


class ApplicationFormData(BaseModel):
    """申請表單資料"""

    fields: Dict[str, DynamicFormField] = Field(
        ...,
        description="動態表單欄位",
        example={
            "bank_account": {
                "field_id": "bank_account",
                "field_type": "text",
                "value": "123123",
                "required": True,
            }
        },
    )
    documents: List[DocumentData] = Field(
        default=[],
        description="文件列表",
        example=[
            {
                "document_id": "bank_account_cover",
                "document_type": "存摺封面",
                "file_path": "test.pdf",
                "original_filename": "test.pdf",
                "upload_time": "2024-03-19T10:00:00Z",
            }
        ],
    )

    @validator("fields")
    def validate_required_fields(cls, v):
        """驗證必填欄位"""
        for field_id, field in v.items():
            if field.required and (field.value is None or field.value == ""):
                raise ValueError(f"必填欄位 {field_id} 未填寫")

            # 根據 field_type 進行特定驗證
            if field.validation_rules:
                if field.field_type == "number":
                    min_val = field.validation_rules.get("min")
                    max_val = field.validation_rules.get("max")
                    if min_val is not None and field.value < min_val:
                        raise ValueError(f"欄位 {field_id} 值不可小於 {min_val}")
                    if max_val is not None and field.value > max_val:
                        raise ValueError(f"欄位 {field_id} 值不可大於 {max_val}")
                elif field.field_type == "text":
                    min_length = field.validation_rules.get("min_length")
                    max_length = field.validation_rules.get("max_length")
                    if min_length is not None and len(str(field.value)) < min_length:
                        raise ValueError(f"欄位 {field_id} 長度不可小於 {min_length}")
                    if max_length is not None and len(str(field.value)) > max_length:
                        raise ValueError(f"欄位 {field_id} 長度不可大於 {max_length}")
        return v


class ApplicationCreate(BaseModel):
    """建立申請"""

    scholarship_type: str = Field(..., description="獎學金類型代碼", example="undergraduate_freshman")
    configuration_id: int = Field(..., description="獎學金配置ID (必須從eligible scholarships取得，確保學生有申請資格)", example=1)
    scholarship_subtype_list: List[str] = Field(default=[], description="獎學金子類型列表", example=["general", "special"])
    form_data: ApplicationFormData = Field(..., description="表單資料")
    agree_terms: Optional[bool] = Field(False, description="同意條款")
    is_renewal: Optional[bool] = Field(False, description="是否為續領申請")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
        json_schema_extra = {
            "example": {
                "scholarship_type": "undergraduate_freshman",
                "scholarship_subtype_list": ["general"],
                "agree_terms": True,
                "form_data": {
                    "fields": {
                        "bank_account": {
                            "field_id": "bank_account",
                            "field_type": "text",
                            "value": "123123",
                            "required": True,
                        }
                    },
                    "documents": [
                        {
                            "document_id": "bank_account_cover",
                            "document_type": "存摺封面",
                            "file_path": "test.pdf",
                            "original_filename": "test.pdf",
                            "upload_time": "2024-03-19T10:00:00Z",
                        }
                    ],
                },
            }
        }


class ApplicationUpdate(BaseModel):
    """更新申請"""

    scholarship_subtype_list: Optional[List[str]] = Field(None, description="獎學金子類型列表")
    form_data: Optional[ApplicationFormData] = Field(None, description="表單資料")
    status: Optional[str] = Field(None, description="申請狀態")
    agree_terms: Optional[bool] = Field(None, description="同意條款")
    is_renewal: Optional[bool] = Field(None, description="是否為續領申請")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ApplicationFileResponse(BaseModel):
    """Application file response schema"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    file_type: str
    is_verified: Optional[bool] = False
    uploaded_at: datetime
    file_path: Optional[str] = None  # 預覽/下載URL
    download_url: Optional[str] = None  # 下載URL


class ApplicationReviewResponse(BaseModel):
    """Application review response schema (unified review system)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    reviewer_id: int
    recommendation: str  # 'approve' | 'partial_approve' | 'reject'
    comments: Optional[str] = None
    reviewed_at: datetime
    created_at: datetime

    # Optional: reviewer information
    reviewer_name: Optional[str] = None
    reviewer_role: Optional[str] = None


# DELETED: Old ProfessorReview schemas removed - using unified review system
# See app.schemas.review for new unified review schemas


class ApplicationResponse(BaseModel):
    """Full application response schema"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: str
    user_id: int
    student_id: Optional[str] = None
    scholarship_type_id: int
    scholarship_type: Optional[str] = None  # Scholarship type code
    scholarship_type_zh: Optional[str] = None  # Chinese scholarship type name
    scholarship_name: Optional[str] = None  # Full scholarship configuration name
    amount: Optional[Decimal] = None  # Scholarship amount
    currency: Optional[str] = "TWD"  # Scholarship currency
    scholarship_subtype_list: Optional[List[str]] = []
    status: str
    status_name: Optional[str]
    is_renewal: bool = Field(False, description="是否為續領申請")
    academic_year: int
    semester: Optional[str] = None
    student_data: Dict[str, Any]
    submitted_form_data: Dict[str, Any]  # 包含整合後的文件資訊
    agree_terms: bool = False
    professor_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    final_approver_id: Optional[int] = None
    # Note: review_score, review_comments, rejection_reason removed
    # Get these from reviews relationship if needed
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    meta_data: Optional[Dict[str, Any]] = None

    reviews: List[ApplicationReviewResponse] = []

    # Additional display fields
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    student_name_en: Optional[str] = None  # std_ename
    student_pid: Optional[str] = None  # std_pid
    student_email: Optional[str] = None  # com_email
    student_phone: Optional[str] = None  # com_cellphone

    # === Academic Organization ===
    academy_code: Optional[str] = None  # std_academyno / trm_academyno
    academy_name: Optional[str] = None  # trm_academyname
    department_code: Optional[str] = None  # std_depno / trm_depno
    department_name: Optional[str] = None  # trm_depname
    degree: Optional[int] = None  # std_degree / trm_degree
    studying_status: Optional[int] = None  # std_studingstatus
    studying_status_name: Optional[str] = None  # mgd_title

    # === Enrollment Information ===
    enroll_year: Optional[int] = None  # std_enrollyear
    enroll_term: Optional[int] = None  # std_enrollterm
    enroll_type: Optional[int] = None  # std_enrolltype
    term_count: Optional[int] = None  # std_termcount / trm_termcount

    # === Identity & Status ===
    student_identity: Optional[int] = None  # std_identity
    school_identity: Optional[int] = None  # std_schoolid
    gender: Optional[int] = None  # std_sex

    # === Academic Performance ===
    gpa: Optional[float] = None  # trm_ascore_gpa
    class_ranking: Optional[int] = None  # trm_placings
    class_ranking_percent: Optional[float] = None  # trm_placingsrate
    dept_ranking: Optional[int] = None  # trm_depplacing
    dept_ranking_percent: Optional[float] = None  # trm_depplacingrate

    @property
    def is_editable(self) -> bool:
        """Check if application can be edited"""
        return bool(self.status in [ApplicationStatus.draft.value, ApplicationStatus.returned.value])

    @property
    def is_submitted(self) -> bool:
        """Check if application is submitted"""
        return bool(self.status != ApplicationStatus.draft.value)

    @property
    def can_be_reviewed(self) -> bool:
        """Check if application can be reviewed"""
        return bool(
            self.status
            in [
                ApplicationStatus.submitted.value,
                ApplicationStatus.under_review.value,
            ]
        )


class RedistributionRankingResult(BaseModel):
    """Individual ranking redistribution result"""

    ranking_id: int = Field(..., description="Ranking ID")
    sub_type_code: Optional[str] = Field(None, description="Sub-type code")
    status: str = Field(..., description="Status: success, failed, or skipped")
    allocated: Optional[int] = Field(None, description="Number of students allocated (if successful)")
    error: Optional[str] = Field(None, description="Error message (if failed)")
    reason: Optional[str] = Field(None, description="Reason for skip (if skipped)")
    roster_code: Optional[str] = Field(None, description="Roster code (if roster exists)")


class RedistributionInfo(BaseModel):
    """Auto-redistribution information after status change"""

    auto_redistributed: bool = Field(..., description="Whether any redistribution was executed")
    total_allocated: Optional[int] = Field(None, description="Total number of students allocated across all rankings")
    rankings_processed: Optional[int] = Field(None, description="Number of rankings processed")
    successful_count: Optional[int] = Field(None, description="Number of rankings successfully redistributed")
    results: Optional[List[RedistributionRankingResult]] = Field(None, description="List of results for each ranking")
    reason: Optional[str] = Field(None, description="Reason for redistribution or skip")


class ApplicationStatusUpdateResponse(BaseModel):
    """Response for application status update with redistribution info"""

    model_config = ConfigDict(from_attributes=True)

    # Include all ApplicationResponse fields
    id: int
    app_id: str
    user_id: int
    student_id: Optional[str] = None
    scholarship_type_id: int
    scholarship_type: Optional[str] = None
    scholarship_type_zh: Optional[str] = None
    scholarship_name: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: Optional[str] = "TWD"
    scholarship_subtype_list: Optional[List[str]] = []
    status: str
    status_name: Optional[str]
    is_renewal: bool = Field(False, description="是否為續領申請")
    academic_year: int
    semester: Optional[str] = None
    student_data: Dict[str, Any]
    submitted_form_data: Dict[str, Any]
    agree_terms: bool = False
    professor_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    final_approver_id: Optional[int] = None
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    meta_data: Optional[Dict[str, Any]] = None
    reviews: List[ApplicationReviewResponse] = []

    # Additional display fields
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    student_name_en: Optional[str] = None
    student_pid: Optional[str] = None
    student_email: Optional[str] = None
    student_phone: Optional[str] = None

    # === Academic Organization ===
    academy_code: Optional[str] = None
    academy_name: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    degree: Optional[int] = None
    studying_status: Optional[int] = None
    studying_status_name: Optional[str] = None

    # === Enrollment Information ===
    enroll_year: Optional[int] = None
    enroll_term: Optional[int] = None
    enroll_type: Optional[int] = None
    term_count: Optional[int] = None

    # === Identity & Status ===
    student_identity: Optional[int] = None
    school_identity: Optional[int] = None
    gender: Optional[int] = None

    # === Academic Performance ===
    gpa: Optional[float] = None
    class_ranking: Optional[int] = None
    class_ranking_percent: Optional[float] = None
    dept_ranking: Optional[int] = None
    dept_ranking_percent: Optional[float] = None

    # Auto-redistribution info (only present for status updates)
    redistribution_info: Optional[RedistributionInfo] = Field(
        None, description="Auto-redistribution information (present after status change to approved/rejected)"
    )


class ApplicationReviewCreate(BaseModel):
    """Application review creation schema"""

    application_id: int
    review_stage: str
    score: Optional[Decimal] = None
    comments: Optional[str] = None
    recommendation: Optional[str] = None


class ApplicationListResponse(BaseModel):
    """Application list response schema"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: str
    user_id: int
    student_id: Optional[str] = None
    scholarship_type: Optional[str] = None
    scholarship_type_id: int
    scholarship_type_zh: Optional[str] = None  # 中文獎學金類型名稱
    scholarship_name: Optional[str] = None  # Full scholarship configuration name
    amount: Optional[Decimal] = None  # Scholarship amount
    currency: Optional[str] = "TWD"  # Scholarship currency
    scholarship_subtype_list: Optional[List[str]] = []  # 獎學金子類型列表
    status: str
    status_name: Optional[str]
    is_renewal: bool = Field(False, description="是否為續領申請")
    academic_year: int
    semester: Optional[str] = None
    student_data: Dict[str, Any]
    submitted_form_data: Dict[str, Any]  # 包含整合後的文件資訊
    agree_terms: bool = False
    professor_id: Optional[int] = None
    reviewer_id: Optional[int] = None
    final_approver_id: Optional[int] = None
    # Note: review_score, review_comments, rejection_reason removed
    # Get these from ApplicationReview.reviews relationship if needed
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    meta_data: Optional[Dict[str, Any]] = None

    # Additional display fields
    student_name: Optional[str] = None
    student_no: Optional[str] = None
    student_name_en: Optional[str] = None  # std_ename
    student_pid: Optional[str] = None  # std_pid
    student_email: Optional[str] = None  # com_email
    student_phone: Optional[str] = None  # com_cellphone

    # === Academic Organization ===
    academy_code: Optional[str] = None  # std_academyno / trm_academyno
    academy_name: Optional[str] = None  # trm_academyname
    department_code: Optional[str] = None  # std_depno / trm_depno
    department_name: Optional[str] = None  # trm_depname
    degree: Optional[int] = None  # std_degree / trm_degree
    studying_status: Optional[int] = None  # std_studingstatus
    studying_status_name: Optional[str] = None  # mgd_title

    # === Enrollment Information ===
    enroll_year: Optional[int] = None  # std_enrollyear
    enroll_term: Optional[int] = None  # std_enrollterm
    enroll_type: Optional[int] = None  # std_enrolltype
    term_count: Optional[int] = None  # std_termcount / trm_termcount

    # === Identity & Status ===
    student_identity: Optional[int] = None  # std_identity
    school_identity: Optional[int] = None  # std_schoolid
    gender: Optional[int] = None  # std_sex

    # === Academic Performance ===
    gpa: Optional[float] = None  # trm_ascore_gpa
    class_ranking: Optional[int] = None  # trm_placings
    class_ranking_percent: Optional[float] = None  # trm_placingsrate
    dept_ranking: Optional[int] = None  # trm_depplacing
    dept_ranking_percent: Optional[float] = None  # trm_depplacingrate

    days_waiting: Optional[int] = None

    # Professor information
    professor: Optional[Dict[str, Any]] = None

    # Scholarship configuration for professor review requirements
    scholarship_configuration: Optional[Dict[str, Any]] = None

    @property
    def is_editable(self) -> bool:
        """Check if application can be edited"""
        return bool(self.status in [ApplicationStatus.draft.value, ApplicationStatus.returned.value])

    @property
    def is_submitted(self) -> bool:
        """Check if application is submitted"""
        return bool(self.status != ApplicationStatus.draft.value)

    @property
    def can_be_reviewed(self) -> bool:
        """Check if application can be reviewed"""
        return bool(
            self.status
            in [
                ApplicationStatus.submitted.value,
                ApplicationStatus.under_review.value,
            ]
        )


class ApplicationStatusUpdate(BaseModel):
    """Application status update schema"""

    status: str = Field(..., description="New status")
    comments: Optional[str] = Field(None, description="Review comments")
    rejection_reason: Optional[str] = Field(None, description="Reason for rejection")


class DashboardStats(BaseModel):
    """Dashboard statistics schema"""

    total_applications: int = Field(0, description="Total number of applications")
    draft_applications: int = Field(0, description="Number of draft applications")
    submitted_applications: int = Field(0, description="Number of submitted applications")
    approved_applications: int = Field(0, description="Number of approved applications")
    rejected_applications: int = Field(0, description="Number of rejected applications")
    pending_review: int = Field(0, description="Number of applications pending review")
    total_amount: Decimal = Field(0, description="Total scholarship amount approved")
    recent_activities: List[Dict[str, Any]] = Field([], description="Recent application activities")


class ProfessorAssignmentRequest(BaseModel):
    """Professor assignment request schema"""

    professor_nycu_id: str = Field(..., description="Professor NYCU ID to assign")


class BulkApproveRequest(BaseModel):
    """Schema for bulk approval requests."""

    application_ids: List[int] = Field(..., min_length=1, description="Application IDs to approve")
    comments: Optional[str] = Field(None, description="Optional approval notes")
    send_notifications: bool = Field(True, description="Whether to notify applicants")


class HistoricalApplicationResponse(BaseModel):
    """Historical application response schema for admin view"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    app_id: str
    status: str
    status_name: Optional[str] = None

    # Student information
    student_name: Optional[str] = None
    student_id: Optional[str] = None
    student_email: Optional[str] = None
    student_department: Optional[str] = None

    # Scholarship information
    scholarship_name: Optional[str] = None
    scholarship_type_code: Optional[str] = None
    amount: Optional[Decimal] = None
    # main_scholarship_type field removed - use scholarship_type_id instead
    sub_scholarship_type: Optional[str] = None
    is_renewal: Optional[bool] = False

    # Academic information
    academic_year: int
    semester: Optional[str] = None

    # Important dates
    submitted_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Review information
    professor_name: Optional[str] = None
    reviewer_name: Optional[str] = None
    # Note: review_score, review_comments, rejection_reason removed
    # Get these from ApplicationReview if needed

    # Status helpers
    @classmethod
    def get_status_label(cls, status: str) -> str:
        """Get Chinese status label using centralized i18n"""
        from app.utils.i18n import ScholarshipI18n

        return ScholarshipI18n.get_application_status_text(status)

    @classmethod
    def get_status_color(cls, status: str) -> str:
        """Get status color class"""
        status_colors = {
            "draft": "bg-gray-100 text-gray-700",
            "submitted": "bg-blue-100 text-blue-700",
            "under_review": "bg-yellow-100 text-yellow-700",
            "pending_recommendation": "bg-orange-100 text-orange-700",
            "recommended": "bg-indigo-100 text-indigo-700",
            "approved": "bg-green-100 text-green-700",
            "rejected": "bg-red-100 text-red-700",
            "returned": "bg-purple-100 text-purple-700",
            "cancelled": "bg-gray-100 text-gray-700",
            "renewal_pending": "bg-cyan-100 text-cyan-700",
            "renewal_reviewed": "bg-teal-100 text-teal-700",
            "manual_excluded": "bg-red-100 text-red-700",
            "professor_review": "bg-amber-100 text-amber-700",
            "withdrawn": "bg-gray-100 text-gray-700",
        }
        return status_colors.get(status, "bg-gray-100 text-gray-700")
