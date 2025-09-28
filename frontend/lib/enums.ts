/**
 * Enum definitions that match backend Python enums
 * These should stay in sync with backend/app/models/enums.py
 */

export enum Semester {
  FIRST = "first",
  SECOND = "second",
  ANNUAL = "annual",
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

// Additional enums that might be used in the frontend
export enum ApplicationStatus {
  DRAFT = "draft",
  SUBMITTED = "submitted",
  UNDER_REVIEW = "under_review",
  APPROVED = "approved",
  REJECTED = "rejected",
  WITHDRAWN = "withdrawn",
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
      [Semester.ANNUAL]: "全年",
    },
    en: {
      [Semester.FIRST]: "First Semester",
      [Semester.SECOND]: "Second Semester",
      [Semester.ANNUAL]: "Annual",
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
      [ApplicationStatus.SUBMITTED]: "已提交",
      [ApplicationStatus.UNDER_REVIEW]: "審核中",
      [ApplicationStatus.APPROVED]: "已核准",
      [ApplicationStatus.REJECTED]: "已拒絕",
      [ApplicationStatus.WITHDRAWN]: "已撤回",
    },
    en: {
      [ApplicationStatus.DRAFT]: "Draft",
      [ApplicationStatus.SUBMITTED]: "Submitted",
      [ApplicationStatus.UNDER_REVIEW]: "Under Review",
      [ApplicationStatus.APPROVED]: "Approved",
      [ApplicationStatus.REJECTED]: "Rejected",
      [ApplicationStatus.WITHDRAWN]: "Withdrawn",
    },
  };
  return labels[locale][status];
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
  CRITICAL = "critical",
  HIGH = "high",
  NORMAL = "normal",
  LOW = "low",
}

export enum EmailStatus {
  SENT = "sent",
  FAILED = "failed",
  BOUNCED = "bounced",
  PENDING = "pending",
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
  SEMI_ANNUAL = "semi_annual",
  ANNUAL = "annual",
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
      [RosterCycle.SEMI_ANNUAL]: "半年",
      [RosterCycle.ANNUAL]: "年度",
    },
    en: {
      [RosterCycle.MONTHLY]: "Monthly",
      [RosterCycle.SEMI_ANNUAL]: "Semi-annual",
      [RosterCycle.ANNUAL]: "Annual",
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
