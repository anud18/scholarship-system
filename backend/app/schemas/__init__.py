from .user import UserCreate, UserUpdate, UserResponse, UserLogin
# Student schemas removed - student data now handled via external API
from .application import (
    ApplicationCreate, ApplicationUpdate, ApplicationResponse, 
    ApplicationFileResponse, ApplicationReviewCreate, ApplicationReviewResponse,
    StudentDataSchema, StudentFinancialInfo, SupervisorInfo
)
from .scholarship import (
    ScholarshipTypeResponse, ScholarshipRuleResponse, 
    SemesterEnum, ApplicationCycleEnum, SubTypeSelectionModeEnum
)
from .notification import NotificationResponse
from .common import MessageResponse, PaginationParams, PaginatedResponse
from .settings import (
    SystemSettingCreate, SystemSettingUpdate, SystemSettingResponse,
    EmailTemplateCreate, EmailTemplateUpdate, EmailTemplateResponse,
    EmailConfig, EmailSendRequest
)

__all__ = [
    "UserCreate", "UserUpdate", "UserResponse", "UserLogin",
    # Student schemas removed - student data now handled via external API
    "ApplicationCreate", "ApplicationUpdate", "ApplicationResponse",
    "ApplicationFileResponse", "ApplicationReviewCreate", "ApplicationReviewResponse",
    "StudentDataSchema", "StudentFinancialInfo", "SupervisorInfo",
    "ScholarshipTypeResponse", "ScholarshipRuleResponse",
    "SemesterEnum", "ApplicationCycleEnum", "SubTypeSelectionModeEnum",
    "NotificationResponse",
    "MessageResponse", "PaginationParams", "PaginatedResponse",
    "SystemSettingCreate", "SystemSettingUpdate", "SystemSettingResponse",
    "EmailTemplateCreate", "EmailTemplateUpdate", "EmailTemplateResponse",
    "EmailConfig", "EmailSendRequest"
]
