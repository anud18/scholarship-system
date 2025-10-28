"""
Application models for scholarship applications
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

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
from app.models.enums import ApplicationStatus, ReviewStage, Semester
from app.models.scholarship import SubTypeSelectionMode

if TYPE_CHECKING:
    pass


# ScholarshipMainType enum removed - use scholarship_type_id instead


class ReviewCycle(enum.Enum):
    """Review cycle types"""

    SEMESTER = "SEMESTER"
    MONTHLY = "MONTHLY"


class ReviewStatus(enum.Enum):
    """Review status enum"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"


class FileType(enum.Enum):
    """File type enum"""

    TRANSCRIPT = "transcript"  # 成績單
    RESEARCH_PROPOSAL = "research_proposal"  # 研究計畫
    RECOMMENDATION_LETTER = "recommendation_letter"  # 推薦信
    CERTIFICATE = "certificate"  # 證書
    INSURANCE_RECORD = "insurance_record"  # 投保紀錄
    AGREEMENT = "agreement"  # 切結書
    BANK_ACCOUNT_COVER = "bank_account_cover"  # 銀行帳號封面
    OTHER = "other"  # 其他


class Application(Base):
    """Scholarship application model"""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(String(20), unique=True, index=True, nullable=False)  # APP-2025-000001

    # 申請人資訊
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # student_id removed - student data now comes from external API via student_data JSON field

    # 獎學金類型 - Enhanced for issue #10
    scholarship_type_id = Column(
        Integer, ForeignKey("scholarship_types.id"), nullable=True
    )  # Reference to ScholarshipType
    scholarship_configuration_id = Column(
        Integer, ForeignKey("scholarship_configurations.id"), nullable=True
    )  # Specific configuration applied for
    scholarship_name = Column(String(200))
    amount = Column(Numeric(10, 2))
    scholarship_subtype_list = Column(JSON, nullable=False, default=[])
    sub_type_selection_mode = Column(
        Enum(SubTypeSelectionMode, values_callable=lambda obj: [e.value for e in obj]), nullable=False
    )

    # New fields for comprehensive scholarship system (Issue #10)
    # Sub type is configuration-driven (dynamic), use String for flexibility
    # Convention: lowercase with underscore (e.g., "nstc", "moe_1w")
    # Defined in scholarship_configurations.quotas JSON field
    sub_scholarship_type = Column(
        String(50),
        default="general",
        nullable=False,
    )
    is_renewal = Column(Boolean, default=False, nullable=False)  # 是否為續領申請
    previous_application_id = Column(Integer, ForeignKey("applications.id"))
    review_deadline = Column(DateTime(timezone=True))
    decision_date = Column(DateTime(timezone=True))

    # 申請狀態（用戶可見）
    status = Column(
        Enum(ApplicationStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ApplicationStatus.draft.value,
        nullable=False,
    )
    status_name = Column(String(100))

    # 審核階段（內部流程）
    review_stage = Column(
        Enum(ReviewStage, values_callable=lambda obj: [e.value for e in obj]),
        default=ReviewStage.student_draft.value,
        nullable=False,
    )

    # 學期資訊 (申請當時的學期)
    academic_year = Column(Integer, nullable=False)  # 民國年，例如 113
    semester = Column(
        Enum(Semester, values_callable=lambda obj: [e.value for e in obj]), nullable=True
    )  # Can be NULL for yearly scholarships

    # 申請資料 (申請當時)
    student_data = Column(JSON)  # Student 資料
    submitted_form_data = Column(JSON)  # Field, Document 資料

    # 同意條款
    agree_terms = Column(Boolean, default=False)

    # 審核相關
    professor_id = Column(Integer, ForeignKey("users.id"))  # 指導教授
    reviewer_id = Column(Integer, ForeignKey("users.id"))  # 審核者
    final_approver_id = Column(Integer, ForeignKey("users.id"))  # 最終核准者

    # 學院審查相關 (College Review)
    # Note: 評分欄位已移除 (review_score, college_ranking_score)
    # 審核意見和拒絕原因改從 ApplicationReview 表取得
    decision_reason = Column(Text)  # 累積的拒絕原因（來自所有審查者的拒絕意見）
    final_ranking_position = Column(Integer)  # 最終排名位置
    quota_allocation_status = Column(String(20))  # 'allocated', 'rejected', 'waitlisted'

    # 時間戳記
    submitted_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 刪除追蹤 (Deletion tracking for soft delete)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deletion_reason = Column(Text, nullable=True)

    # 批次匯入相關 (Batch Import)
    imported_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 匯入者
    batch_import_id = Column(Integer, ForeignKey("batch_imports.id"), nullable=True)  # 批次匯入紀錄
    import_source = Column(String(20), nullable=True, default="online")  # 'online' | 'batch_import'
    document_status = Column(String(30), nullable=True, default="complete")  # 'complete' | 'pending_documents'

    # 其他資訊
    meta_data = Column(JSON)  # 額外的元資料

    # 關聯
    student = relationship("User", foreign_keys=[user_id], back_populates="applications")
    # studentProfile relationship removed - student data accessed via external API
    professor = relationship("User", foreign_keys=[professor_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    final_approver = relationship("User", foreign_keys=[final_approver_id])
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])  # Who deleted this application

    # Enhanced relationships for issue #10
    scholarship_type_ref = relationship(
        "ScholarshipType",
        foreign_keys=[scholarship_type_id],
        overlaps="applications,scholarship",
    )
    scholarship = relationship(
        "ScholarshipType",
        foreign_keys=[scholarship_type_id],
        overlaps="applications,scholarship_type_ref",
    )
    scholarship_configuration = relationship("ScholarshipConfiguration", foreign_keys=[scholarship_configuration_id])
    previous_application = relationship("Application", remote_side=[id])

    files = relationship("ApplicationFile", back_populates="application", cascade="all, delete-orphan")
    reviews = relationship("ApplicationReview", back_populates="application", cascade="all, delete-orphan")
    document_requests = relationship("DocumentRequest", back_populates="application", cascade="all, delete-orphan")
    # Note: college_review relationship removed - replaced by unified ApplicationReview system

    # Batch import relationships
    imported_by = relationship("User", foreign_keys=[imported_by_id])
    batch_import = relationship("BatchImport", back_populates="applications", foreign_keys=[batch_import_id])

    # 唯一約束：確保每個用戶在每個學年、學期、獎學金組合下只能有一個申請
    # Use user_id instead of student_id since students are now from external API
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "scholarship_type_id",
            "academic_year",
            "semester",
            name="uq_user_scholarship_academic_term",
        ),
    )

    def __repr__(self):
        return f"<Application(id={self.id}, app_id={self.app_id}, status={self.status})>"

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
                ApplicationStatus.recommended.value,
            ]
        )

    @property
    def is_overdue(self) -> bool:
        """Check if application review is overdue"""
        if not self.review_deadline:
            return False
        return bool(datetime.now().replace(tzinfo=None) > self.review_deadline.replace(tzinfo=None))

    # get_main_type_enum() removed - main_scholarship_type field no longer exists

    # get_sub_type_enum() removed - sub_scholarship_type is now a plain string
    # Use self.sub_scholarship_type directly instead of converting to enum

    @property
    def academic_term_label(self) -> str:
        """Get academic term label in Chinese"""
        return f"{self.academic_year}學年度 {self.get_semester_label()}"

    def get_semester_label(self) -> str:
        """Get semester label in Chinese"""
        return {
            Semester.first: "第一學期",
            Semester.second: "第二學期",
        }.get(self.semester, "")

    @property
    def is_renewal_application(self) -> bool:
        """Check if this is a renewal application"""
        return self.is_renewal

    @property
    def is_general_application(self) -> bool:
        """Check if this is a general application"""
        return not self.is_renewal

    @property
    def application_type_label(self) -> str:
        """Get application type label in Chinese"""
        return "續領申請" if self.is_renewal else "一般申請"

    def get_review_stage(self) -> Optional[str]:
        """Get current review stage based on application type and status"""
        if self.is_renewal:
            if self.status == ApplicationStatus.submitted.value:
                return "renewal_professor"
            elif self.status == ApplicationStatus.recommended.value:
                return "renewal_college"
        else:
            if self.status == ApplicationStatus.submitted.value:
                return "general_professor"
            elif self.status == ApplicationStatus.recommended.value:
                return "general_college"
        return None


class ApplicationFile(Base):
    """Application file attachment model"""

    __tablename__ = "application_files"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)

    # 檔案資訊
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    object_name = Column(String(500))  # MinIO object name
    file_size = Column(Integer)
    mime_type = Column(String(100))
    content_type = Column(String(100))  # For MinIO
    file_type = Column(String(50), default=FileType.OTHER.value)

    # OCR 處理結果
    ocr_processed = Column(Boolean, default=False)
    ocr_text = Column(Text)
    ocr_confidence = Column(Numeric(5, 2))

    # 檔案狀態
    is_verified = Column(Boolean, default=False)
    verification_notes = Column(Text)

    # 時間戳記
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    upload_date = Column(DateTime(timezone=True), server_default=func.now())  # Alias for MinIO service
    processed_at = Column(DateTime(timezone=True))

    # 關聯
    application = relationship("Application", back_populates="files")

    def __repr__(self):
        return f"<ApplicationFile(id={self.id}, filename={self.filename}, application_id={self.application_id})>"

    @property
    def file_path(self) -> Optional[str]:
        """Dynamic property for file preview URL"""
        return getattr(self, "_file_path", None)

    @file_path.setter
    def file_path(self, value: Optional[str]):
        """Set file preview URL"""
        self._file_path = value

    @property
    def download_url(self) -> Optional[str]:
        """Dynamic property for file download URL"""
        return getattr(self, "_download_url", None)

    @download_url.setter
    def download_url(self, value: Optional[str]):
        """Set file download URL"""
        self._download_url = value
