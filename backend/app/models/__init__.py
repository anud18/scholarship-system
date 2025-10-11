"""
Import all models here for easy access
"""

from app.models.application import (
    Application,
    ApplicationFile,
    ApplicationReview,
    ApplicationStatus,
    FileType,
    ProfessorReview,
    ProfessorReviewItem,
    ReviewStatus,
)
from app.models.application_field import ApplicationDocument, ApplicationField, FieldType
from app.models.audit_log import AuditAction, AuditLog
from app.models.batch_import import BatchImport
from app.models.college_review import CollegeRanking, CollegeRankingItem, CollegeReview, QuotaDistribution
from app.models.document_request import DocumentRequest, DocumentRequestStatus
from app.models.email_management import EmailCategory, EmailHistory, EmailStatus, ScheduledEmail, ScheduleStatus
from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester, SubTypeSelectionMode
from app.models.notification import Notification, NotificationType
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.professor_student import ProfessorStudentRelationship
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel, RosterAuditLog
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule, ScholarshipType
from app.models.student import (  # 查詢表模型 (Reference data only); Helper functions
    Academy,
    Degree,
    Department,
    EnrollType,
    Identity,
    SchoolIdentity,
    StudyingStatus,
    get_student_type_from_degree,
)
from app.models.system_setting import SystemSetting
from app.models.user import User, UserRole
from app.models.user_profile import UserProfile, UserProfileHistory

__all__ = [
    "User",
    "UserRole",
    # Student reference data models
    "Degree",
    "Identity",
    "StudyingStatus",
    "SchoolIdentity",
    "Academy",
    "Department",
    "EnrollType",
    "get_student_type_from_degree",
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
    "SystemSetting",
    # Document request models
    "DocumentRequest",
    "DocumentRequestStatus",
    # Batch import models
    "BatchImport",
    # User profile models
    "UserProfile",
    "UserProfileHistory",
    # College review models
    "CollegeReview",
    "CollegeRanking",
    "CollegeRankingItem",
    "QuotaDistribution",
    # Professor-Student relationship model
    "ProfessorStudentRelationship",
    # Roster schedule models
    "RosterSchedule",
    "RosterScheduleStatus",
    # Payment roster models
    "PaymentRoster",
    "PaymentRosterItem",
    "RosterCycle",
    "RosterStatus",
    "RosterTriggerType",
    "StudentVerificationStatus",
    # Roster audit models
    "RosterAuditLog",
    "RosterAuditAction",
    "RosterAuditLevel",
    # Email management models
    "EmailHistory",
    "ScheduledEmail",
    "EmailStatus",
    "ScheduleStatus",
    "EmailCategory",
]
