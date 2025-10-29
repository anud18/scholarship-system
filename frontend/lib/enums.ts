/**
 * Enum definitions that match backend Python enums
 * These should stay in sync with backend/app/models/enums.py
 */

export enum Semester {
  FIRST = "first",
  SECOND = "second",
  YEARLY = "yearly",
}

export enum SubTypeSelectionMode {
  SINGLE = "single", // 僅能選擇一個子項目
  MULTIPLE = "multiple", // 可自由多選
  HIERARCHICAL = "hierarchical", // 需依序選取：A → AB → ABC
}

export enum ApplicationCycle {
  SEMESTER = "semester",
  YEARLY = "yearly",
}

export enum QuotaManagementMode {
  NONE = "none", // 無配額限制
  SIMPLE = "simple", // 簡單總配額
  COLLEGE_BASED = "college_based", // 學院分配配額
  MATRIX_BASED = "matrix_based", // 矩陣配額管理 (子類型×學院)
}

// Application Status - User-facing outcome
export enum ApplicationStatus {
  DRAFT = "draft",
  SUBMITTED = "submitted",
  UNDER_REVIEW = "under_review",
  PENDING_DOCUMENTS = "pending_documents",
  APPROVED = "approved",
  PARTIAL_APPROVED = "partial_approved",
  REJECTED = "rejected",
  RETURNED = "returned",
  WITHDRAWN = "withdrawn",
  CANCELLED = "cancelled",
  MANUAL_EXCLUDED = "manual_excluded",
  DELETED = "deleted",
}

// Review Stage - Internal workflow position
export enum ReviewStage {
  STUDENT_DRAFT = "student_draft",
  STUDENT_SUBMITTED = "student_submitted",
  PROFESSOR_REVIEW = "professor_review",
  PROFESSOR_REVIEWED = "professor_reviewed",
  COLLEGE_REVIEW = "college_review",
  COLLEGE_REVIEWED = "college_reviewed",
  COLLEGE_RANKING = "college_ranking",
  COLLEGE_RANKED = "college_ranked",
  ADMIN_REVIEW = "admin_review",
  ADMIN_REVIEWED = "admin_reviewed",
  QUOTA_DISTRIBUTION = "quota_distribution",
  QUOTA_DISTRIBUTED = "quota_distributed",
  ROSTER_PREPARATION = "roster_preparation",
  ROSTER_PREPARED = "roster_prepared",
  ROSTER_SUBMITTED = "roster_submitted",
  COMPLETED = "completed",
  ARCHIVED = "archived",
}

export enum UserRole {
  STUDENT = "student",
  PROFESSOR = "professor",
  COLLEGE = "college",
  ADMIN = "admin",
  SUPER_ADMIN = "super_admin",
}

export enum RelationshipType {
  ADVISOR = "advisor",
  SUPERVISOR = "supervisor",
  COMMITTEE_MEMBER = "committee_member",
  CO_ADVISOR = "co_advisor",
}

export enum RelationshipStatus {
  ACTIVE = "active",
  INACTIVE = "inactive",
  PENDING = "pending",
  TERMINATED = "terminated",
}

export enum BankVerificationStatus {
  NOT_VERIFIED = "not_verified",
  PENDING = "pending",
  VERIFIED = "verified",
  FAILED = "failed",
}

// Helper functions for enum labels
export const getSemesterLabel = (
  semester: Semester,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [Semester.FIRST]: "第一學期",
      [Semester.SECOND]: "第二學期",
      [Semester.YEARLY]: "全年",
    },
    en: {
      [Semester.FIRST]: "First Semester",
      [Semester.SECOND]: "Second Semester",
      [Semester.YEARLY]: "Yearly",
    },
  };
  return labels[locale][semester];
};

export const getSubTypeSelectionModeLabel = (
  mode: SubTypeSelectionMode,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [SubTypeSelectionMode.SINGLE]: "單選模式",
      [SubTypeSelectionMode.MULTIPLE]: "多選模式",
      [SubTypeSelectionMode.HIERARCHICAL]: "階層選擇模式",
    },
    en: {
      [SubTypeSelectionMode.SINGLE]: "Single Selection",
      [SubTypeSelectionMode.MULTIPLE]: "Multiple Selection",
      [SubTypeSelectionMode.HIERARCHICAL]: "Hierarchical Selection",
    },
  };
  return labels[locale][mode];
};

export const getQuotaManagementModeLabel = (
  mode: QuotaManagementMode,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [QuotaManagementMode.NONE]: "無配額限制",
      [QuotaManagementMode.SIMPLE]: "簡單配額",
      [QuotaManagementMode.COLLEGE_BASED]: "學院配額",
      [QuotaManagementMode.MATRIX_BASED]: "矩陣配額",
    },
    en: {
      [QuotaManagementMode.NONE]: "No Quota",
      [QuotaManagementMode.SIMPLE]: "Simple Quota",
      [QuotaManagementMode.COLLEGE_BASED]: "College-based Quota",
      [QuotaManagementMode.MATRIX_BASED]: "Matrix-based Quota",
    },
  };
  return labels[locale][mode];
};

export const getApplicationStatusLabel = (
  status: ApplicationStatus,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [ApplicationStatus.DRAFT]: "草稿",
      [ApplicationStatus.SUBMITTED]: "已送出",
      [ApplicationStatus.UNDER_REVIEW]: "審批中",
      [ApplicationStatus.PENDING_DOCUMENTS]: "補件中",
      [ApplicationStatus.APPROVED]: "已核准",
      [ApplicationStatus.PARTIAL_APPROVED]: "部分核准",
      [ApplicationStatus.REJECTED]: "已駁回",
      [ApplicationStatus.RETURNED]: "已退回",
      [ApplicationStatus.WITHDRAWN]: "已撤回",
      [ApplicationStatus.CANCELLED]: "已取消",
      [ApplicationStatus.MANUAL_EXCLUDED]: "手動排除",
      [ApplicationStatus.DELETED]: "已刪除",
    },
    en: {
      [ApplicationStatus.DRAFT]: "Draft",
      [ApplicationStatus.SUBMITTED]: "Submitted",
      [ApplicationStatus.UNDER_REVIEW]: "Under Review",
      [ApplicationStatus.PENDING_DOCUMENTS]: "Pending Documents",
      [ApplicationStatus.APPROVED]: "Approved",
      [ApplicationStatus.PARTIAL_APPROVED]: "Partially Approved",
      [ApplicationStatus.REJECTED]: "Rejected",
      [ApplicationStatus.RETURNED]: "Returned",
      [ApplicationStatus.WITHDRAWN]: "Withdrawn",
      [ApplicationStatus.CANCELLED]: "Cancelled",
      [ApplicationStatus.MANUAL_EXCLUDED]: "Manually Excluded",
      [ApplicationStatus.DELETED]: "Deleted",
    },
  };
  return labels[locale][status];
};

export const getApplicationStatusBadgeVariant = (
  status: ApplicationStatus
): "default" | "secondary" | "outline" | "destructive" => {
  switch (status) {
    // 草稿狀態 - secondary (灰色)
    case ApplicationStatus.DRAFT:
      return "secondary";

    // 已提交/審核中 - default (藍色)
    case ApplicationStatus.SUBMITTED:
    case ApplicationStatus.APPROVED:
      return "default";

    // 審核中/部分核准 - outline (淺色邊框)
    case ApplicationStatus.UNDER_REVIEW:
    case ApplicationStatus.PENDING_DOCUMENTS:
    case ApplicationStatus.PARTIAL_APPROVED:
      return "outline";

    // 拒絕/刪除 - destructive (紅色)
    case ApplicationStatus.REJECTED:
    case ApplicationStatus.DELETED:
      return "destructive";

    // 退回/撤回/取消/排除 - secondary (灰色)
    case ApplicationStatus.RETURNED:
    case ApplicationStatus.WITHDRAWN:
    case ApplicationStatus.CANCELLED:
    case ApplicationStatus.MANUAL_EXCLUDED:
      return "secondary";

    default:
      return "secondary";
  }
};

export const getReviewStageLabel = (
  stage: ReviewStage,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [ReviewStage.STUDENT_DRAFT]: "學生編輯中",
      [ReviewStage.STUDENT_SUBMITTED]: "學生已送出",
      [ReviewStage.PROFESSOR_REVIEW]: "教授審核中",
      [ReviewStage.PROFESSOR_REVIEWED]: "教授已審核",
      [ReviewStage.COLLEGE_REVIEW]: "學院審核中",
      [ReviewStage.COLLEGE_REVIEWED]: "學院已審核",
      [ReviewStage.COLLEGE_RANKING]: "學院排名中",
      [ReviewStage.COLLEGE_RANKED]: "學院已排名",
      [ReviewStage.ADMIN_REVIEW]: "管理員審核中",
      [ReviewStage.ADMIN_REVIEWED]: "管理員已審核",
      [ReviewStage.QUOTA_DISTRIBUTION]: "配額分發中",
      [ReviewStage.QUOTA_DISTRIBUTED]: "配額已分發",
      [ReviewStage.ROSTER_PREPARATION]: "造冊準備中",
      [ReviewStage.ROSTER_PREPARED]: "造冊已完成",
      [ReviewStage.ROSTER_SUBMITTED]: "造冊已送出",
      [ReviewStage.COMPLETED]: "流程完成",
      [ReviewStage.ARCHIVED]: "已歸檔",
    },
    en: {
      [ReviewStage.STUDENT_DRAFT]: "Student Drafting",
      [ReviewStage.STUDENT_SUBMITTED]: "Student Submitted",
      [ReviewStage.PROFESSOR_REVIEW]: "Professor Reviewing",
      [ReviewStage.PROFESSOR_REVIEWED]: "Professor Reviewed",
      [ReviewStage.COLLEGE_REVIEW]: "College Reviewing",
      [ReviewStage.COLLEGE_REVIEWED]: "College Reviewed",
      [ReviewStage.COLLEGE_RANKING]: "College Ranking",
      [ReviewStage.COLLEGE_RANKED]: "College Ranked",
      [ReviewStage.ADMIN_REVIEW]: "Admin Reviewing",
      [ReviewStage.ADMIN_REVIEWED]: "Admin Reviewed",
      [ReviewStage.QUOTA_DISTRIBUTION]: "Quota Distributing",
      [ReviewStage.QUOTA_DISTRIBUTED]: "Quota Distributed",
      [ReviewStage.ROSTER_PREPARATION]: "Roster Preparing",
      [ReviewStage.ROSTER_PREPARED]: "Roster Prepared",
      [ReviewStage.ROSTER_SUBMITTED]: "Roster Submitted",
      [ReviewStage.COMPLETED]: "Completed",
      [ReviewStage.ARCHIVED]: "Archived",
    },
  };
  return labels[locale][stage];
};

export const getReviewStageBadgeVariant = (
  stage: ReviewStage
): "default" | "secondary" | "outline" | "destructive" => {
  switch (stage) {
    // 學生階段 - secondary (灰色)
    case ReviewStage.STUDENT_DRAFT:
    case ReviewStage.STUDENT_SUBMITTED:
      return "secondary";

    // 進行中階段 - default (藍色)
    case ReviewStage.PROFESSOR_REVIEW:
    case ReviewStage.COLLEGE_REVIEW:
    case ReviewStage.COLLEGE_RANKING:
    case ReviewStage.ADMIN_REVIEW:
    case ReviewStage.QUOTA_DISTRIBUTION:
    case ReviewStage.ROSTER_PREPARATION:
      return "default";

    // 已完成階段 - outline (淺色邊框)
    case ReviewStage.PROFESSOR_REVIEWED:
    case ReviewStage.COLLEGE_REVIEWED:
    case ReviewStage.COLLEGE_RANKED:
    case ReviewStage.ADMIN_REVIEWED:
    case ReviewStage.QUOTA_DISTRIBUTED:
      return "outline";

    // 造冊完成階段 - default (強調)
    case ReviewStage.ROSTER_PREPARED:
    case ReviewStage.ROSTER_SUBMITTED:
      return "default";

    // 完成階段 - outline
    case ReviewStage.COMPLETED:
    case ReviewStage.ARCHIVED:
      return "outline";

    default:
      return "secondary";
  }
};

export const getUserRoleLabel = (
  role: UserRole,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [UserRole.STUDENT]: "學生",
      [UserRole.PROFESSOR]: "教授",
      [UserRole.COLLEGE]: "學院審核員",
      [UserRole.ADMIN]: "管理員",
      [UserRole.SUPER_ADMIN]: "超級管理員",
    },
    en: {
      [UserRole.STUDENT]: "Student",
      [UserRole.PROFESSOR]: "Professor",
      [UserRole.COLLEGE]: "College Reviewer",
      [UserRole.ADMIN]: "Admin",
      [UserRole.SUPER_ADMIN]: "Super Admin",
    },
  };
  return labels[locale][role];
};

export const getRelationshipTypeLabel = (
  type: RelationshipType,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RelationshipType.ADVISOR]: "指導教授",
      [RelationshipType.SUPERVISOR]: "監督教授",
      [RelationshipType.COMMITTEE_MEMBER]: "委員會成員",
      [RelationshipType.CO_ADVISOR]: "共同指導教授",
    },
    en: {
      [RelationshipType.ADVISOR]: "Advisor",
      [RelationshipType.SUPERVISOR]: "Supervisor",
      [RelationshipType.COMMITTEE_MEMBER]: "Committee Member",
      [RelationshipType.CO_ADVISOR]: "Co-Advisor",
    },
  };
  return labels[locale][type];
};

export const getRelationshipStatusLabel = (
  status: RelationshipStatus,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RelationshipStatus.ACTIVE]: "活躍",
      [RelationshipStatus.INACTIVE]: "非活躍",
      [RelationshipStatus.PENDING]: "待確認",
      [RelationshipStatus.TERMINATED]: "已終止",
    },
    en: {
      [RelationshipStatus.ACTIVE]: "Active",
      [RelationshipStatus.INACTIVE]: "Inactive",
      [RelationshipStatus.PENDING]: "Pending",
      [RelationshipStatus.TERMINATED]: "Terminated",
    },
  };
  return labels[locale][status];
};

export const getBankVerificationStatusLabel = (
  status: BankVerificationStatus,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [BankVerificationStatus.NOT_VERIFIED]: "未驗證",
      [BankVerificationStatus.PENDING]: "驗證中",
      [BankVerificationStatus.VERIFIED]: "已驗證",
      [BankVerificationStatus.FAILED]: "驗證失敗",
    },
    en: {
      [BankVerificationStatus.NOT_VERIFIED]: "Not Verified",
      [BankVerificationStatus.PENDING]: "Pending",
      [BankVerificationStatus.VERIFIED]: "Verified",
      [BankVerificationStatus.FAILED]: "Failed",
    },
  };
  return labels[locale][status];
};

// Additional enums from backend models

export enum UserType {
  STUDENT = "student",
  EMPLOYEE = "employee",
}

export enum EmployeeStatus {
  ACTIVE = "在職",
  RETIRED = "退休",
  STUDENT = "在學",
  GRADUATED = "畢業",
}

export enum NotificationChannel {
  IN_APP = "in_app",
  EMAIL = "email",
  SMS = "sms",
  PUSH = "push",
}

export enum NotificationType {
  // Legacy types
  INFO = "info",
  WARNING = "warning",
  ERROR = "error",
  SUCCESS = "success",
  REMINDER = "reminder",

  // Application lifecycle
  APPLICATION_SUBMITTED = "application_submitted",
  APPLICATION_APPROVED = "application_approved",
  APPLICATION_REJECTED = "application_rejected",
  APPLICATION_REQUIRES_REVIEW = "application_requires_review",
  APPLICATION_UNDER_REVIEW = "application_under_review",

  // Document management
  DOCUMENT_REQUIRED = "document_required",
  DOCUMENT_APPROVED = "document_approved",
  DOCUMENT_REJECTED = "document_rejected",

  // Deadlines and reminders
  DEADLINE_APPROACHING = "deadline_approaching",
  DEADLINE_EXTENDED = "deadline_extended",
  REVIEW_DEADLINE = "review_deadline",
  APPLICATION_DEADLINE = "application_deadline",

  // New opportunities
  NEW_SCHOLARSHIP_AVAILABLE = "new_scholarship_available",
  MATCHING_SCHOLARSHIP = "matching_scholarship",
  SCHOLARSHIP_OPENING_SOON = "scholarship_opening_soon",

  // Review process
  PROFESSOR_REVIEW_REQUESTED = "professor_review_requested",
  PROFESSOR_REVIEW_COMPLETED = "professor_review_completed",
  PROFESSOR_ASSIGNMENT = "professor_assignment",
  ADMIN_REVIEW_REQUESTED = "admin_review_requested",

  // System and admin
  SYSTEM_MAINTENANCE = "system_maintenance",
  ADMIN_MESSAGE = "admin_message",
  ACCOUNT_UPDATE = "account_update",
  SECURITY_ALERT = "security_alert",
}

export enum NotificationPriority {
  LOW = "low",
  NORMAL = "normal",
  HIGH = "high",
  URGENT = "urgent",  // Renamed from CRITICAL to match backend
}

export enum EmailStatus {
  PENDING = "pending",
  SENT = "sent",
  CANCELLED = "cancelled",
  FAILED = "failed",
  BOUNCED = "bounced",
}

export enum EmailCategory {
  APPLICATION_WHITELIST = "application_whitelist",
  APPLICATION_STUDENT = "application_student",
  RECOMMENDATION_PROFESSOR = "recommendation_professor",
  REVIEW_COLLEGE = "review_college",
  SUPPLEMENT_STUDENT = "supplement_student",
  RESULT_PROFESSOR = "result_professor",
  RESULT_COLLEGE = "result_college",
  RESULT_STUDENT = "result_student",
  ROSTER_STUDENT = "roster_student",
  SYSTEM = "system",
  OTHER = "other",
}

// Payment Roster Enums
export enum RosterCycle {
  MONTHLY = "monthly",
  SEMI_YEARLY = "semi_yearly",
  YEARLY = "yearly",
}

export enum RosterStatus {
  DRAFT = "draft",
  PROCESSING = "processing",
  COMPLETED = "completed",
  LOCKED = "locked",
  FAILED = "failed",
}

export enum RosterTriggerType {
  MANUAL = "manual",
  SCHEDULED = "scheduled",
  DRY_RUN = "dry_run",
}

export enum StudentVerificationStatus {
  VERIFIED = "verified",
  GRADUATED = "graduated",
  SUSPENDED = "suspended",
  WITHDRAWN = "withdrawn",
  API_ERROR = "api_error",
  NOT_FOUND = "not_found",
}

export enum RosterAuditAction {
  CREATE = "create",
  UPDATE = "update",
  DELETE = "delete",
  LOCK = "lock",
  UNLOCK = "unlock",
  EXPORT = "export",
  DOWNLOAD = "download",
  STUDENT_VERIFY = "student_verify",
  SCHEDULE_RUN = "schedule_run",
  MANUAL_RUN = "manual_run",
  DRY_RUN = "dry_run",
  STATUS_CHANGE = "status_change",
  ITEM_ADD = "item_add",
  ITEM_REMOVE = "item_remove",
  ITEM_UPDATE = "item_update",
}

export enum RosterAuditLevel {
  INFO = "info",
  WARNING = "warning",
  ERROR = "error",
  CRITICAL = "critical",
}

// Payment Roster Label Functions
export const getRosterCycleLabel = (
  cycle: RosterCycle,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RosterCycle.MONTHLY]: "每月",
      [RosterCycle.SEMI_YEARLY]: "半年",
      [RosterCycle.YEARLY]: "年度",
    },
    en: {
      [RosterCycle.MONTHLY]: "Monthly",
      [RosterCycle.SEMI_YEARLY]: "Semi-yearly",
      [RosterCycle.YEARLY]: "Yearly",
    },
  };
  return labels[locale][cycle];
};

export const getRosterStatusLabel = (
  status: RosterStatus,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RosterStatus.DRAFT]: "草稿",
      [RosterStatus.PROCESSING]: "處理中",
      [RosterStatus.COMPLETED]: "已完成",
      [RosterStatus.LOCKED]: "已鎖定",
      [RosterStatus.FAILED]: "失敗",
    },
    en: {
      [RosterStatus.DRAFT]: "Draft",
      [RosterStatus.PROCESSING]: "Processing",
      [RosterStatus.COMPLETED]: "Completed",
      [RosterStatus.LOCKED]: "Locked",
      [RosterStatus.FAILED]: "Failed",
    },
  };
  return labels[locale][status];
};

export const getRosterTriggerTypeLabel = (
  type: RosterTriggerType,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RosterTriggerType.MANUAL]: "手動觸發",
      [RosterTriggerType.SCHEDULED]: "排程觸發",
      [RosterTriggerType.DRY_RUN]: "預覽模式",
    },
    en: {
      [RosterTriggerType.MANUAL]: "Manual",
      [RosterTriggerType.SCHEDULED]: "Scheduled",
      [RosterTriggerType.DRY_RUN]: "Dry Run",
    },
  };
  return labels[locale][type];
};

export const getStudentVerificationStatusLabel = (
  status: StudentVerificationStatus,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [StudentVerificationStatus.VERIFIED]: "已驗證",
      [StudentVerificationStatus.GRADUATED]: "已畢業",
      [StudentVerificationStatus.SUSPENDED]: "休學中",
      [StudentVerificationStatus.WITHDRAWN]: "已退學",
      [StudentVerificationStatus.API_ERROR]: "驗證錯誤",
      [StudentVerificationStatus.NOT_FOUND]: "查無此人",
    },
    en: {
      [StudentVerificationStatus.VERIFIED]: "Verified",
      [StudentVerificationStatus.GRADUATED]: "Graduated",
      [StudentVerificationStatus.SUSPENDED]: "Suspended",
      [StudentVerificationStatus.WITHDRAWN]: "Withdrawn",
      [StudentVerificationStatus.API_ERROR]: "API Error",
      [StudentVerificationStatus.NOT_FOUND]: "Not Found",
    },
  };
  return labels[locale][status];
};

// Email Status Label Functions
export const getEmailStatusLabel = (
  status: EmailStatus,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [EmailStatus.PENDING]: "待發送",
      [EmailStatus.SENT]: "已發送",
      [EmailStatus.CANCELLED]: "已取消",
      [EmailStatus.FAILED]: "發送失敗",
      [EmailStatus.BOUNCED]: "退信",
    },
    en: {
      [EmailStatus.PENDING]: "Pending",
      [EmailStatus.SENT]: "Sent",
      [EmailStatus.CANCELLED]: "Cancelled",
      [EmailStatus.FAILED]: "Failed",
      [EmailStatus.BOUNCED]: "Bounced",
    },
  };
  return labels[locale][status];
};

export const getEmailStatusVariant = (
  status: EmailStatus
): "default" | "secondary" | "destructive" | "outline" => {
  switch (status) {
    case EmailStatus.PENDING:
      return "outline";
    case EmailStatus.SENT:
      return "default";
    case EmailStatus.CANCELLED:
      return "secondary";
    case EmailStatus.FAILED:
    case EmailStatus.BOUNCED:
      return "destructive";
    default:
      return "outline";
  }
};

export const getRosterAuditActionLabel = (
  action: RosterAuditAction,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RosterAuditAction.CREATE]: "建立",
      [RosterAuditAction.UPDATE]: "更新",
      [RosterAuditAction.DELETE]: "刪除",
      [RosterAuditAction.LOCK]: "鎖定",
      [RosterAuditAction.UNLOCK]: "解鎖",
      [RosterAuditAction.EXPORT]: "匯出",
      [RosterAuditAction.DOWNLOAD]: "下載",
      [RosterAuditAction.STUDENT_VERIFY]: "學籍驗證",
      [RosterAuditAction.SCHEDULE_RUN]: "排程執行",
      [RosterAuditAction.MANUAL_RUN]: "手動執行",
      [RosterAuditAction.DRY_RUN]: "預覽執行",
      [RosterAuditAction.STATUS_CHANGE]: "狀態變更",
      [RosterAuditAction.ITEM_ADD]: "新增明細",
      [RosterAuditAction.ITEM_REMOVE]: "移除明細",
      [RosterAuditAction.ITEM_UPDATE]: "更新明細",
    },
    en: {
      [RosterAuditAction.CREATE]: "Create",
      [RosterAuditAction.UPDATE]: "Update",
      [RosterAuditAction.DELETE]: "Delete",
      [RosterAuditAction.LOCK]: "Lock",
      [RosterAuditAction.UNLOCK]: "Unlock",
      [RosterAuditAction.EXPORT]: "Export",
      [RosterAuditAction.DOWNLOAD]: "Download",
      [RosterAuditAction.STUDENT_VERIFY]: "Student Verification",
      [RosterAuditAction.SCHEDULE_RUN]: "Scheduled Run",
      [RosterAuditAction.MANUAL_RUN]: "Manual Run",
      [RosterAuditAction.DRY_RUN]: "Dry Run",
      [RosterAuditAction.STATUS_CHANGE]: "Status Change",
      [RosterAuditAction.ITEM_ADD]: "Add Item",
      [RosterAuditAction.ITEM_REMOVE]: "Remove Item",
      [RosterAuditAction.ITEM_UPDATE]: "Update Item",
    },
  };
  return labels[locale][action];
};

export const getRosterAuditLevelLabel = (
  level: RosterAuditLevel,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [RosterAuditLevel.INFO]: "資訊",
      [RosterAuditLevel.WARNING]: "警告",
      [RosterAuditLevel.ERROR]: "錯誤",
      [RosterAuditLevel.CRITICAL]: "嚴重錯誤",
    },
    en: {
      [RosterAuditLevel.INFO]: "Info",
      [RosterAuditLevel.WARNING]: "Warning",
      [RosterAuditLevel.ERROR]: "Error",
      [RosterAuditLevel.CRITICAL]: "Critical",
    },
  };
  return labels[locale][level];
};

// System Settings Enums
export enum ConfigCategory {
  DATABASE = "database",
  API_KEYS = "api_keys",
  EMAIL = "email",
  OCR = "ocr",
  FILE_STORAGE = "file_storage",
  SECURITY = "security",
  FEATURES = "features",
  INTEGRATIONS = "integrations",
  PERFORMANCE = "performance",
  LOGGING = "logging",
}

export enum ConfigDataType {
  STRING = "string",
  INTEGER = "integer",
  BOOLEAN = "boolean",
  JSON = "json",
  FLOAT = "float",
}

export enum SendingType {
  SINGLE = "single",
  BULK = "bulk",
}

export const getConfigCategoryLabel = (
  category: ConfigCategory,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [ConfigCategory.DATABASE]: "資料庫",
      [ConfigCategory.API_KEYS]: "API 金鑰",
      [ConfigCategory.EMAIL]: "電子郵件",
      [ConfigCategory.OCR]: "OCR 設定",
      [ConfigCategory.FILE_STORAGE]: "檔案儲存",
      [ConfigCategory.SECURITY]: "安全性",
      [ConfigCategory.FEATURES]: "功能設定",
      [ConfigCategory.INTEGRATIONS]: "整合設定",
      [ConfigCategory.PERFORMANCE]: "效能設定",
      [ConfigCategory.LOGGING]: "日誌設定",
    },
    en: {
      [ConfigCategory.DATABASE]: "Database",
      [ConfigCategory.API_KEYS]: "API Keys",
      [ConfigCategory.EMAIL]: "Email",
      [ConfigCategory.OCR]: "OCR",
      [ConfigCategory.FILE_STORAGE]: "File Storage",
      [ConfigCategory.SECURITY]: "Security",
      [ConfigCategory.FEATURES]: "Features",
      [ConfigCategory.INTEGRATIONS]: "Integrations",
      [ConfigCategory.PERFORMANCE]: "Performance",
      [ConfigCategory.LOGGING]: "Logging",
    },
  };
  return labels[locale][category];
};

export const getConfigDataTypeLabel = (
  dataType: ConfigDataType,
  locale: "zh" | "en" = "zh"
): string => {
  const labels = {
    zh: {
      [ConfigDataType.STRING]: "字串",
      [ConfigDataType.INTEGER]: "整數",
      [ConfigDataType.BOOLEAN]: "布林值",
      [ConfigDataType.JSON]: "JSON",
      [ConfigDataType.FLOAT]: "浮點數",
    },
    en: {
      [ConfigDataType.STRING]: "String",
      [ConfigDataType.INTEGER]: "Integer",
      [ConfigDataType.BOOLEAN]: "Boolean",
      [ConfigDataType.JSON]: "JSON",
      [ConfigDataType.FLOAT]: "Float",
    },
  };
  return labels[locale][dataType];
};
