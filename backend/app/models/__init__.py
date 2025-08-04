"""
Import all models here for easy access
"""

from app.models.user import User, UserRole
from app.models.student import (
    # 查詢表模型
    Degree,
    Identity, 
    StudyingStatus,
    SchoolIdentity,
    Academy,
    Department,
    EnrollType,
    
    # 學生資料模型
    Student,
    
    # Enum 類別
    StudentType,
    StudyStatus
)
from app.models.scholarship import ScholarshipType, ScholarshipRule, ScholarshipConfiguration
from app.models.enums import Semester, SubTypeSelectionMode, ApplicationCycle, QuotaManagementMode
from app.models.application import (
    Application, 
    ApplicationStatus, 
    ApplicationReview, 
    ProfessorReview, 
    ProfessorReviewItem,
    ApplicationFile,
    ReviewStatus,
    FileType
)
from app.models.notification import Notification, NotificationType
from app.models.audit_log import AuditLog, AuditAction
from app.models.system_setting import SystemSetting
from app.models.application_field import ApplicationField, ApplicationDocument, FieldType

__all__ = [
    "User",
    "UserRole",
    
    # Student models
    "Degree",
    "Identity", 
    "StudyingStatus",
    "SchoolIdentity",
    "Academy",
    "Department",
    "EnrollType",
    "Student",
    "StudentType",
    "StudyStatus",
    
    # Application models
    "Application",
    "ApplicationStatus",
    "ApplicationReview",
    "ProfessorReview",
    "ProfessorReviewItem",
    "ApplicationFile",
    "ReviewStatus",
    "FileType",
    
    # Shared enums
    "Semester",
    "SubTypeSelectionMode",
    "ApplicationCycle",
    "QuotaManagementMode",
    
    # Application Field models
    "ApplicationField",
    "ApplicationDocument",
    "FieldType",
    
    # Scholarship models
    "ScholarshipType",
    "ScholarshipRule",
    "ScholarshipConfiguration",
    
    # Other models
    "Notification",
    "NotificationType",
    "AuditLog",
    "AuditAction",
    "SystemSetting"
]
