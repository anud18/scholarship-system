"""
Application models for scholarship applications
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric, Text, JSON, Enum, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base
from app.models.scholarship import SubTypeSelectionMode

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.student import Student


class ApplicationStatus(enum.Enum):
    """Application status enum"""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    PENDING_RECOMMENDATION = "pending_recommendation"
    RECOMMENDED = "recommended"
    APPROVED = "approved"
    REJECTED = "rejected"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    RENEWAL_PENDING = "renewal_pending"
    RENEWAL_REVIEWED = "renewal_reviewed"
    MANUAL_EXCLUDED = "manual_excluded"


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


class Semester(enum.Enum):
    """Semester enum"""
    FIRST = "first"
    SECOND = "second"





class Application(Base):
    """Scholarship application model"""
    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(String(20), unique=True, index=True, nullable=False)  # APP-2025-000001
    
    # 申請人資訊
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    
    # 獎學金類型
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)  # 主獎學金ID
    scholarship_subtype_list = Column(JSON, nullable=False, default=[])
    sub_type_selection_mode = Column(Enum(SubTypeSelectionMode), nullable=False)
    
    # 申請狀態
    status = Column(String(50), default=ApplicationStatus.DRAFT.value)
    status_name = Column(String(100))
    
    # 續領申請標識
    is_renewal = Column(Boolean, default=False, nullable=False)  # 是否為續領申請
    
    # 學期資訊 (申請當時的學期)
    academic_year = Column(Integer, nullable=False)  # 民國年，例如 113
    semester = Column(Enum(Semester), nullable=False)
    
    # 申請資料 (申請當時)
    student_data = Column(JSON)  # Student 資料
    submitted_form_data = Column(JSON)  # Field, Document 資料
    
    # 同意條款
    agree_terms = Column(Boolean, default=False)
    
    # 審核相關
    professor_id = Column(Integer, ForeignKey("users.id"))  # 指導教授
    reviewer_id = Column(Integer, ForeignKey("users.id"))  # 審核者
    final_approver_id = Column(Integer, ForeignKey("users.id"))  # 最終核准者
    
    # 審核結果
    review_score = Column(Numeric(5, 2))
    review_comments = Column(Text)
    rejection_reason = Column(Text)
    
    # 時間戳記
    submitted_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    approved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # 其他資訊
    meta_data = Column(JSON)  # 額外的元資料
    
    # 關聯
    student = relationship("User", foreign_keys=[user_id], back_populates="applications")
    studentProfile = relationship("Student", foreign_keys=[student_id], back_populates="applications")
    professor = relationship("User", foreign_keys=[professor_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    final_approver = relationship("User", foreign_keys=[final_approver_id])
    
    # 獎學金關聯
    scholarship = relationship("ScholarshipType", foreign_keys=[scholarship_type_id])
    
    files = relationship("ApplicationFile", back_populates="application", cascade="all, delete-orphan")
    reviews = relationship("ApplicationReview", back_populates="application", cascade="all, delete-orphan")
    professor_reviews = relationship("ProfessorReview", back_populates="application", cascade="all, delete-orphan")

    # 唯一約束：確保每個學生在每個學年、學期、獎學金組合下只能有一個申請
    __table_args__ = (
        UniqueConstraint(
            'student_id', 'scholarship_type_id', 'academic_year', 'semester',
            name='uq_student_scholarship_academic_term'
        ),
    )

    def __repr__(self):
        return f"<Application(id={self.id}, app_id={self.app_id}, status={self.status})>"
    
    @property
    def is_editable(self) -> bool:
        """Check if application can be edited"""
        return bool(self.status in [ApplicationStatus.DRAFT.value, ApplicationStatus.RETURNED.value])
    
    @property
    def is_submitted(self) -> bool:
        """Check if application is submitted"""
        return bool(self.status != ApplicationStatus.DRAFT.value)
    
    @property
    def can_be_reviewed(self) -> bool:
        """Check if application can be reviewed"""
        return bool(self.status in [
            ApplicationStatus.SUBMITTED.value,
            ApplicationStatus.UNDER_REVIEW.value,
            ApplicationStatus.RECOMMENDED.value
        ])
    
    @property
    def academic_term_label(self) -> str:
        """Get academic term label in Chinese"""
        return f"{self.academic_year}學年度 {self.get_semester_label()}"
    
    def get_semester_label(self) -> str:
        """Get semester label in Chinese"""
        return {
            Semester.FIRST: "第一學期",
            Semester.SECOND: "第二學期",
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
            if self.status == ApplicationStatus.SUBMITTED.value:
                return "renewal_professor"
            elif self.status == ApplicationStatus.RECOMMENDED.value:
                return "renewal_college"
        else:
            if self.status == ApplicationStatus.SUBMITTED.value:
                return "general_professor"
            elif self.status == ApplicationStatus.RECOMMENDED.value:
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
        return getattr(self, '_file_path', None)
    
    @file_path.setter
    def file_path(self, value: Optional[str]):
        """Set file preview URL"""
        self._file_path = value
    
    @property
    def download_url(self) -> Optional[str]:
        """Dynamic property for file download URL"""
        return getattr(self, '_download_url', None)
    
    @download_url.setter
    def download_url(self, value: Optional[str]):
        """Set file download URL"""
        self._download_url = value


class ApplicationReview(Base):
    """Application review record model"""
    __tablename__ = "application_reviews"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 審核資訊
    review_stage = Column(String(50))  # professor_recommendation, department_review, final_approval
    review_status = Column(String(20), default=ReviewStatus.PENDING.value)
    
    # 審核結果
    score = Column(Numeric(5, 2))
    comments = Column(Text)
    recommendation = Column(Text)
    decision_reason = Column(Text)
    
    # 審核標準
    criteria_scores = Column(JSON)  # 各項評分標準的分數
    
    # 時間資訊
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True))
    due_date = Column(DateTime(timezone=True))
    
    # 關聯
    application = relationship("Application", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")

    def __repr__(self):
        return f"<ApplicationReview(id={self.id}, application_id={self.application_id}, reviewer_id={self.reviewer_id})>"


class ProfessorReview(Base):
    """Professor review model for scholarship applications"""
    __tablename__ = "professor_reviews"
    
    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 整體推薦意見
    recommendation = Column(Text)  # 對整體申請的意見（可留可不留）
    review_status = Column(String(20), default="pending")
    reviewed_at = Column(DateTime(timezone=True))
    
    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 關聯
    application = relationship("Application", back_populates="professor_reviews")
    professor = relationship("User")
    items = relationship("ProfessorReviewItem", back_populates="review", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ProfessorReview(id={self.id}, application_id={self.application_id}, professor_id={self.professor_id})>"


class ProfessorReviewItem(Base):
    """Professor review item for individual scholarship sub-types"""
    __tablename__ = "professor_review_items"
    
    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("professor_reviews.id"), nullable=False)
    sub_type_code = Column(String(50), nullable=False)  # e.g., "moe_1w"
    
    # 推薦結果
    is_recommended = Column(Boolean, nullable=False, default=False)
    comments = Column(Text)  # 教授針對該子項目的意見
    
    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # 關聯
    review = relationship("ProfessorReview", back_populates="items")

    def __repr__(self):
        return f"<ProfessorReviewItem(id={self.id}, review_id={self.review_id}, sub_type_code={self.sub_type_code})>" 