# Student schemas removed - student data now handled via external API
from .application import (
    ApplicationCreate,
    ApplicationFileResponse,
    ApplicationResponse,
    ApplicationReviewCreate,
    ApplicationReviewResponse,
    ApplicationUpdate,
    StudentDataSchema,
    StudentFinancialInfo,
    SupervisorInfo,
)
from .common import MessageResponse, PaginatedResponse, PaginationParams
from .notification import NotificationResponse
from .scholarship import (
    ApplicationCycleEnum,
    ScholarshipRuleResponse,
    ScholarshipTypeResponse,
    SubTypeSelectionModeEnum,
)
from .settings import (
    EmailConfig,
    EmailSendRequest,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    SystemSettingCreate,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from .user import UserCreate, UserLogin, UserResponse, UserUpdate

__all__ = [
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserLogin",
    # Student schemas removed - student data now handled via external API
    "ApplicationCreate",
    "ApplicationUpdate",
    "ApplicationResponse",
    "ApplicationFileResponse",
    "ApplicationReviewCreate",
    "ApplicationReviewResponse",
    "StudentDataSchema",
    "StudentFinancialInfo",
    "SupervisorInfo",
    "ScholarshipTypeResponse",
    "ScholarshipRuleResponse",
    "ApplicationCycleEnum",
    "SubTypeSelectionModeEnum",
    "NotificationResponse",
    "MessageResponse",
    "PaginationParams",
    "PaginatedResponse",
    "SystemSettingCreate",
    "SystemSettingUpdate",
    "SystemSettingResponse",
    "EmailTemplateCreate",
    "EmailTemplateUpdate",
    "EmailTemplateResponse",
    "EmailConfig",
    "EmailSendRequest",
]
