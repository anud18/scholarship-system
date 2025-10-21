/**
 * API client for scholarship management system
 * Follows backend camelCase endpoint naming conventions
 */

export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data?: T;
  errors?: string[];
  trace_id?: string;
}

export interface User {
  id: string;
  nycu_id: string; // 改為 nycu_id
  email: string;
  name: string; // 改為 name
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // 向後相容性欄位
  username?: string; // 映射到 nycu_id
  full_name?: string; // 映射到 name
  is_active?: boolean; // 所有用戶都視為活躍
}

export interface Student {
  id: string;
  user_id: string;
  student_id: string;
  student_type: "undergraduate" | "graduate" | "phd";
  department: string;
  gpa: number;
  nationality: string;
  phone_number?: string;
  address?: string;
  bank_account?: string;
  created_at: string;
  updated_at: string;
}

export interface StudentInfoResponse {
  student: Record<string, any>;
  semesters: Array<Record<string, any>>;
}

export interface ApplicationFile {
  id: number;
  filename: string;
  original_filename?: string;
  file_size?: number;
  mime_type?: string;
  file_type: string;
  file_path?: string;
  is_verified?: boolean;
  uploaded_at: string;
}

export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "pending_review"
  | "pending_recommendation"
  | "under_review"
  | "professor_review_pending"
  | "professor_reviewed"
  | "college_review_pending"
  | "college_reviewed"
  | "recommended"
  | "approved"
  | "rejected"
  | "returned"
  | "withdrawn"
  | "cancelled"
  | "pending"
  | "completed"
  | "deleted";

export interface Application {
  id: number;
  app_id?: string; // 申請編號，格式如 APP-2025-000001
  student_id: string;
  scholarship_type: string;
  scholarship_type_zh?: string; // 中文獎學金類型名稱
  status: ApplicationStatus;
  is_renewal?: boolean; // 是否為續領申請
  personal_statement?: string;
  gpa_requirement_met: boolean;
  submitted_at?: string;
  reviewed_at?: string;
  approved_at?: string;
  created_at: string;
  updated_at: string;
  is_recommended?: boolean;
  professor_review_completed?: boolean;
  college_review_completed?: boolean;

  // 動態表單資料
  form_data?: Record<string, any>; // 動態表單資料 (前端格式)
  submitted_form_data?: Record<string, any>; // 後端格式的表單資料，包含整合後的文件資訊
  meta_data?: Record<string, any>; // 額外的元資料
  student_data?: Record<string, any>; // 學生資料

  // 後端 ApplicationResponse 實際返回的欄位
  user_id?: number;
  scholarship_type_id?: number; // 主獎學金ID
  scholarship_name?: string;
  amount?: number;
  status_name?: string;
  status_zh?: string; // 中文狀態名稱
  student_name?: string;
  student_no?: string;
  student_termcount?: number; // 學生學期數
  gpa?: number;
  department?: string;
  nationality?: string;
  class_ranking_percent?: number;
  dept_ranking_percent?: number;
  days_waiting?: number;
  scholarship_subtype_list?: string[];
  sub_type_labels?: Record<string, { zh: string; en: string }>; // 子類型中英文名稱對照
  agree_terms?: boolean; // 同意條款

  // Extended properties for dashboard display (保留向後兼容)
  user?: User; // 關聯的使用者資訊
  student?: Student; // 關聯的學生資訊
  scholarship?: ScholarshipType; // 關聯的獎學金資訊

  // Professor assignment fields
  professor_id?: number | string; // 指導教授ID
  professor?: {
    id: number;
    nycu_id: string;
    name: string;
    email: string;
    dept_name?: string;
  }; // 關聯的教授資訊

  // Scholarship configuration
  scholarship_configuration?: {
    requires_professor_recommendation: boolean;
    requires_college_review: boolean;
    config_name: string;
  }; // 獎學金配置資訊

  // Academic information
  academic_year?: number;
  semester?: string;

  recent_terms?: Array<{
    academic_year?: number;
    semester?: number;
    gpa?: number;
    term_count?: number;
    status?: number;
  }>;
}

export interface ApplicationCreate {
  scholarship_type: string;
  configuration_id: number; // Required: ID from eligible scholarships
  scholarship_subtype_list?: string[];
  form_data: {
    fields: Record<
      string,
      {
        field_id: string;
        field_type: string;
        value: string;
        required: boolean;
      }
    >;
    documents: Array<{
      document_id: string;
      document_type: string;
      file_path: string;
      original_filename: string;
      upload_time: string;
    }>;
  };
  agree_terms?: boolean;
  is_renewal?: boolean; // 是否為續領申請
  [key: string]: any; // 允許動態欄位
}

export interface DashboardStats {
  total_applications: number;
  pending_review: number;
  approved: number;
  rejected: number;
  avg_processing_time: string;
}

export interface RecipientOption {
  value: string;
  label: string;
  description: string;
}

export interface EmailTemplate {
  key: string;
  subject_template: string;
  body_template: string;
  cc?: string | null;
  bcc?: string | null;
  sending_type?: "single" | "bulk";
  recipient_options?: RecipientOption[] | null;
  requires_approval?: boolean;
  max_recipients?: number | null;
  updated_at?: string | null;
}

export interface SystemSetting {
  key: string;
  value: string;
}

// === System Configuration Management Types === //
export interface SystemConfiguration {
  id: number;
  key: string;
  value: string;
  category:
    | "FEATURES"
    | "SECURITY"
    | "EMAIL"
    | "DATABASE"
    | "API_KEYS"
    | "FILE_STORAGE"
    | "NOTIFICATION"
    | "OCR"
    | "INTEGRATIONS";
  data_type: "string" | "integer" | "float" | "boolean" | "json";
  is_sensitive: boolean;
  is_readonly: boolean;
  description?: string;
  validation_regex?: string;
  default_value?: string;
  last_modified_by?: number;
  created_at: string;
  updated_at?: string;
}

export interface SystemConfigurationCreate {
  key: string;
  value: string;
  category:
    | "FEATURES"
    | "SECURITY"
    | "EMAIL"
    | "DATABASE"
    | "API_KEYS"
    | "FILE_STORAGE"
    | "NOTIFICATION"
    | "OCR"
    | "INTEGRATIONS";
  data_type: "string" | "integer" | "float" | "boolean" | "json";
  is_sensitive?: boolean;
  description?: string;
  validation_regex?: string;
}

export interface SystemConfigurationUpdate {
  value?: string;
  category?:
    | "FEATURES"
    | "SECURITY"
    | "EMAIL"
    | "DATABASE"
    | "API_KEYS"
    | "FILE_STORAGE"
    | "NOTIFICATION"
    | "OCR"
    | "INTEGRATIONS";
  data_type?: "string" | "integer" | "float" | "boolean" | "json";
  is_sensitive?: boolean;
  description?: string;
  validation_regex?: string;
}

export interface SystemConfigurationValidation {
  value: string;
  data_type: "string" | "integer" | "float" | "boolean" | "json";
  validation_regex?: string;
}

export interface ConfigurationValidationResult {
  is_valid: boolean;
  error_message?: string;
}

// === Bank Verification Types === //
export interface BankVerificationResult {
  application_id: number;
  verification_status: "verified" | "failed" | "partial" | "no_document";
  verification_details: {
    account_number?: {
      form_value: string;
      ocr_value: string;
      similarity: number;
      match: boolean;
    };
    account_holder?: {
      form_value: string;
      ocr_value: string;
      similarity: number;
      match: boolean;
    };
    branch_name?: {
      form_value: string;
      ocr_value: string;
      similarity: number;
      match: boolean;
    };
  };
  overall_confidence: number;
  recommendations: string[];
  processed_at: string;
}

export interface BankVerificationBatchResult {
  total_applications: number;
  processed_count: number;
  verified_count: number;
  failed_count: number;
  results: BankVerificationResult[];
  processing_time: number;
}

// === Professor-Student Relationship Types === //
export interface ProfessorStudentRelationship {
  id: number;
  professor_id: number;
  student_id: number;
  relationship_type:
    | "advisor"
    | "supervisor"
    | "committee_member"
    | "co_advisor";
  status: "active" | "inactive" | "pending" | "terminated";
  start_date: string;
  end_date?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
  professor?: {
    id: number;
    name: string;
    nycu_id?: string;
    email?: string;
    department?: string;
  };
  student?: {
    id: number;
    name: string;
    student_no?: string;
    email?: string;
    department?: string;
  };
}

export interface ProfessorStudentRelationshipCreate {
  professor_id: number;
  student_id: number;
  relationship_type:
    | "advisor"
    | "supervisor"
    | "committee_member"
    | "co_advisor";
  status: "active" | "inactive" | "pending" | "terminated";
  start_date: string;
  end_date?: string;
  notes?: string;
}

export interface ProfessorStudentRelationshipUpdate {
  id: number;
  professor_id?: number;
  student_id?: number;
  relationship_type?:
    | "advisor"
    | "supervisor"
    | "committee_member"
    | "co_advisor";
  status?: "active" | "inactive" | "pending" | "terminated";
  start_date?: string;
  end_date?: string;
  notes?: string;
}

export interface AnnouncementCreate {
  title: string;
  title_en?: string;
  message: string;
  message_en?: string;
  notification_type?: "info" | "warning" | "error" | "success" | "reminder";
  priority?: "low" | "normal" | "high" | "urgent";
  action_url?: string;
  expires_at?: string;
  metadata?: Record<string, any>;
}

export interface AnnouncementUpdate {
  title?: string;
  title_en?: string;
  message?: string;
  message_en?: string;
  notification_type?: "info" | "warning" | "error" | "success" | "reminder";
  priority?: "low" | "normal" | "high" | "urgent";
  action_url?: string;
  expires_at?: string;
  metadata?: Record<string, any>;
  is_dismissed?: boolean;
}

export interface NotificationResponse {
  id: number;
  title: string;
  title_en?: string;
  message: string;
  message_en?: string;
  notification_type: string;
  priority: string;
  related_resource_type?: string;
  related_resource_id?: number;
  action_url?: string;
  is_read: boolean;
  is_dismissed: boolean;
  scheduled_at?: string;
  expires_at?: string;
  read_at?: string;
  created_at: string;
  metadata?: Record<string, any>;
}

export interface ScholarshipType {
  id: number;
  configuration_id?: number; // ID of the specific configuration this eligibility is for
  code: string;
  name: string;
  name_en?: string;
  description?: string;
  description_en?: string;
  amount?: string;
  currency?: string;
  application_cycle?: "semester" | "yearly";
  application_start_date?: string;
  application_end_date?: string;
  sub_type_selection_mode?: "single" | "multiple" | "hierarchical";
  terms_document_url?: string;
  whitelist_enabled?: boolean;
  eligible_sub_types?: Array<{
    value: string | null;
    label: string;
    label_en: string;
    is_default: boolean;
  }>;
  passed?: Array<{
    rule_id: number;
    rule_name: string;
    rule_type: string;
    tag: string;
    message: string;
    message_en: string;
    sub_type: string | null;
    priority: number;
    is_warning: boolean;
    is_hard_rule: boolean;
    status?: 'data_unavailable' | 'passed' | 'failed';
    system_message?: string;
  }>;
  warnings?: Array<{
    rule_id: number;
    rule_name: string;
    rule_type: string;
    tag: string;
    message: string;
    message_en: string;
    sub_type: string | null;
    priority: number;
    is_warning: boolean;
    is_hard_rule: boolean;
    status?: 'data_unavailable' | 'passed' | 'failed';
    system_message?: string;
  }>;
  errors?: Array<{
    rule_id: number;
    rule_name: string;
    rule_type: string;
    tag: string;
    message: string;
    message_en: string;
    sub_type: string | null;
    priority: number;
    is_warning: boolean;
    is_hard_rule: boolean;
    status?: 'data_unavailable' | 'passed' | 'failed';
    system_message?: string;
  }>;
  created_at?: string;
}

export interface ScholarshipRule {
  id?: number;
  scholarship_type_id?: number;
  sub_type?: string;
  academic_year?: number;
  semester?: string;
  is_template?: boolean;
  template_name?: string;
  template_description?: string;
  rule_name: string;
  rule_type: string;
  tag?: string;
  description?: string;
  condition_field: string;
  operator: string;
  expected_value: string;
  message?: string;
  message_en?: string;
  is_hard_rule: boolean;
  is_warning: boolean;
  priority: number;
  is_active: boolean;
  is_initial_enabled: boolean; // 初領是否啟用
  is_renewal_enabled: boolean; // 續領是否啟用
  created_by?: number;
  updated_by?: number;
  academic_period_label?: string;
  created_at?: string;
  updated_at?: string;
}

export interface SubTypeOption {
  value: string | null;
  label: string;
  label_en: string;
  is_default: boolean;
}

// User management types
export interface UserListResponse {
  id: number;
  nycu_id: string;
  email: string;
  name: string;
  user_type?: string;
  status?: string;
  dept_code?: string;
  dept_name?: string;
  college_code?: string; // 系統內學院管理權限
  role: string;
  comment?: string;
  created_at: string;
  updated_at?: string;
  last_login_at?: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // 向後相容性欄位
  username?: string;
  full_name?: string;
  chinese_name?: string;
  english_name?: string;
  is_active?: boolean;
  is_verified?: boolean;
  student_no?: string;
}

export interface UserResponse {
  id: number;
  nycu_id: string;
  email: string;
  name: string;
  user_type?: string;
  status?: string;
  dept_code?: string;
  dept_name?: string;
  role: string;
  comment?: string;
  created_at: string;
  updated_at?: string;
  last_login_at?: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // 向後相容性欄位
  username?: string;
  full_name?: string;
  chinese_name?: string;
  english_name?: string;
  is_active?: boolean;
  is_verified?: boolean;
  student_no?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface UserCreate {
  nycu_id: string;
  email: string;
  name: string;
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  college_code?: string; // 系統內學院管理權限
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  comment?: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // 向後相容性欄位
  username?: string;
  full_name?: string;
  chinese_name?: string;
  english_name?: string;
  password?: string; // 不再需要，但保留向後相容性
  student_no?: string;
  is_active?: boolean;
}

export interface UserUpdate {
  nycu_id?: string;
  email?: string;
  name?: string;
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  role?: "student" | "professor" | "college" | "admin" | "super_admin";
  comment?: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // 向後相容性欄位
  username?: string;
  full_name?: string;
  chinese_name?: string;
  english_name?: string;
  is_active?: boolean;
  is_verified?: boolean;
  student_no?: string;
}

export interface UserStats {
  total_users: number;
  role_distribution: Record<string, number>;
  user_type_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  recent_registrations: number;
}

// Application Fields Configuration interfaces
export interface ApplicationField {
  id: number;
  scholarship_type: string;
  field_name: string;
  field_label: string;
  field_label_en?: string;
  field_type: string;
  is_required: boolean;
  placeholder?: string;
  placeholder_en?: string;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  step_value?: number;
  field_options?: Array<{ value: string; label: string; label_en?: string }>;
  display_order: number;
  is_active: boolean;
  help_text?: string;
  help_text_en?: string;
  validation_rules?: Record<string, any>;
  conditional_rules?: Record<string, any>;
  created_at: string;
  updated_at: string;
  created_by?: number;
  updated_by?: number;
  // Fixed field properties
  is_fixed?: boolean;
  prefill_value?: string;
  existing_file_url?: string;
}

export interface ApplicationFieldCreate {
  scholarship_type: string;
  field_name: string;
  field_label: string;
  field_label_en?: string;
  field_type: string;
  is_required?: boolean;
  placeholder?: string;
  placeholder_en?: string;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  step_value?: number;
  field_options?: Array<{ value: string; label: string; label_en?: string }>;
  display_order?: number;
  is_active?: boolean;
  help_text?: string;
  help_text_en?: string;
  validation_rules?: Record<string, any>;
  conditional_rules?: Record<string, any>;
}

export interface ApplicationFieldUpdate {
  field_label?: string;
  field_label_en?: string;
  field_type?: string;
  is_required?: boolean;
  placeholder?: string;
  placeholder_en?: string;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  step_value?: number;
  field_options?: Array<{ value: string; label: string; label_en?: string }>;
  display_order?: number;
  is_active?: boolean;
  help_text?: string;
  help_text_en?: string;
  validation_rules?: Record<string, any>;
  conditional_rules?: Record<string, any>;
}

export interface ApplicationDocument {
  id: number;
  scholarship_type: string;
  document_name: string;
  document_name_en?: string;
  description?: string;
  description_en?: string;
  is_required: boolean;
  accepted_file_types: string[];
  max_file_size: string;
  max_file_count: number;
  display_order: number;
  is_active: boolean;
  upload_instructions?: string;
  upload_instructions_en?: string;
  example_file_url?: string; // MinIO object name for example file
  validation_rules?: Record<string, any>;
  created_at: string;
  updated_at: string;
  created_by?: number;
  updated_by?: number;
  // Fixed document properties
  is_fixed?: boolean;
  existing_file_url?: string;
}

export interface HistoricalApplication {
  id: number;
  app_id: string;
  status: string;
  status_name?: string;

  // Student information
  student_name?: string;
  student_id?: string;
  student_email?: string;
  student_department?: string;

  // Scholarship information
  scholarship_name?: string;
  scholarship_type_code?: string;
  amount?: number;
  main_scholarship_type?: string;
  sub_scholarship_type?: string;
  is_renewal?: boolean;

  // Academic information
  academic_year?: number;
  semester?: string;

  // Important dates
  submitted_at?: string;
  reviewed_at?: string;
  approved_at?: string;
  created_at: string;
  updated_at?: string;

  // Review information
  professor_name?: string;
  reviewer_name?: string;
  review_score?: number;
  review_comments?: string;
  rejection_reason?: string;
}

export interface HistoricalApplicationFilters {
  page?: number;
  size?: number;
  status?: string;
  scholarship_type?: string;
  academic_year?: number;
  semester?: string;
  search?: string;
}

export interface ApplicationDocumentCreate {
  scholarship_type: string;
  document_name: string;
  document_name_en?: string;
  description?: string;
  description_en?: string;
  is_required?: boolean;
  accepted_file_types?: string[];
  max_file_size?: string;
  max_file_count?: number;
  display_order?: number;
  is_active?: boolean;
  upload_instructions?: string;
  upload_instructions_en?: string;
  validation_rules?: Record<string, any>;
}

export interface ApplicationDocumentUpdate {
  document_name?: string;
  document_name_en?: string;
  description?: string;
  description_en?: string;
  is_required?: boolean;
  accepted_file_types?: string[];
  max_file_size?: string;
  max_file_count?: number;
  display_order?: number;
  is_active?: boolean;
  upload_instructions?: string;
  upload_instructions_en?: string;
  validation_rules?: Record<string, any>;
}

export interface ScholarshipFormConfig {
  scholarship_type: string;
  fields: ApplicationField[];
  documents: ApplicationDocument[];
  title?: string;
  title_en?: string;
  color?: string;
  hasWhitelist?: boolean;
  whitelist_student_ids?: Record<string, number[]>;
  terms_document_url?: string;
}

export interface FormConfigSaveRequest {
  fields: Array<{
    field_name: string;
    field_label: string;
    field_label_en?: string;
    field_type: string;
    is_required?: boolean;
    placeholder?: string;
    placeholder_en?: string;
    max_length?: number;
    min_value?: number;
    max_value?: number;
    step_value?: number;
    field_options?: Array<{ value: string; label: string; label_en?: string }>;
    display_order?: number;
    is_active?: boolean;
    help_text?: string;
    help_text_en?: string;
    validation_rules?: Record<string, any>;
    conditional_rules?: Record<string, any>;
  }>;
  documents: Array<{
    document_name: string;
    document_name_en?: string;
    description?: string;
    description_en?: string;
    is_required?: boolean;
    accepted_file_types?: string[];
    max_file_size?: string;
    max_file_count?: number;
    display_order?: number;
    is_active?: boolean;
    upload_instructions?: string;
    upload_instructions_en?: string;
    validation_rules?: Record<string, any>;
  }>;
}

export interface ScholarshipStats {
  id: number;
  name: string;
  name_en?: string;
  total_applications: number;
  pending_review: number;
  avg_wait_days: number;
  sub_types: string[];
  has_sub_types: boolean;
}

export interface SubTypeStats {
  sub_type: string;
  total_applications: number;
  pending_review: number;
  avg_wait_days: number;
}

// 新增系統管理相關介面
export interface Workflow {
  id: string;
  name: string;
  version: string;
  status: "active" | "draft" | "inactive";
  lastModified: string;
  steps: number;
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface SystemStats {
  totalUsers: number;
  activeApplications: number;
  completedReviews: number;
  systemUptime: string;
  avgResponseTime: string;
  storageUsed: string;
  pendingReviews: number;
  totalScholarships: number;
}

export interface ScholarshipPermission {
  id: number;
  user_id: number;
  scholarship_id: number;
  scholarship_name: string;
  scholarship_name_en?: string;
  comment?: string;
  created_at: string;
  updated_at: string;
}

export interface ScholarshipPermissionCreate {
  user_id: number;
  scholarship_id: number;
  comment?: string;
}

export interface ScholarshipConfiguration {
  id: number;
  scholarship_type_id: number;
  scholarship_type_name: string;
  scholarship_type_code: string;
  academic_year: number;
  semester: string | null;
  config_name: string;
  config_code: string;
  description?: string;
  description_en?: string;
  amount: number;
  currency: string;
  title?: string;
  title_en?: string;
  color?: string;
  // Quota management fields
  has_quota_limit?: boolean;
  has_college_quota?: boolean;
  quota_management_mode?: string;
  total_quota?: number;
  quotas?: Record<string, any>;
  whitelist_student_ids?: Record<string, number[]>;
  hasWhitelist?: boolean;
  renewal_application_start_date?: string;
  renewal_application_end_date?: string;
  application_start_date?: string;
  application_end_date?: string;
  renewal_professor_review_start?: string;
  renewal_professor_review_end?: string;
  renewal_college_review_start?: string;
  renewal_college_review_end?: string;
  requires_professor_recommendation: boolean;
  professor_review_start?: string;
  professor_review_end?: string;
  requires_college_review: boolean;
  college_review_start?: string;
  college_review_end?: string;
  review_deadline?: string;
  is_active: boolean;
  effective_start_date?: string;
  effective_end_date?: string;
  version: string;
  created_at: string;
  updated_at: string;
}

// Whitelist Management Interfaces
export interface WhitelistStudentInfo {
  student_id: number | null;
  nycu_id: string;
  name: string | null;
  sub_type: string;
  note?: string | null;
  is_registered?: boolean;
}

export interface WhitelistResponse {
  sub_type: string;
  students: WhitelistStudentInfo[];
  total: number;
}

export interface WhitelistBatchAddRequest {
  students: { nycu_id: string; sub_type: string }[];
}

export interface WhitelistBatchRemoveRequest {
  nycu_ids: string[];
  sub_type?: string;
}

export interface WhitelistImportResult {
  success_count: number;
  error_count: number;
  errors: { row: string; nycu_id: string; error: string }[];
  warnings: string[];
}

export interface WhitelistToggleRequest {
  enabled: boolean;
}

export interface ScholarshipConfigurationFormData {
  scholarship_type_id: number;
  academic_year: number;
  semester: string | null;
  config_name: string;
  config_code: string;
  description?: string;
  description_en?: string;
  amount: number;
  currency?: string;
  // Quota management fields
  has_quota_limit?: boolean;
  has_college_quota?: boolean;
  quota_management_mode?: string;
  total_quota?: number;
  quotas?: Record<string, any> | string;
  whitelist_student_ids?: Record<string, number[]> | string;
  renewal_application_start_date?: string;
  renewal_application_end_date?: string;
  application_start_date?: string;
  application_end_date?: string;
  renewal_professor_review_start?: string;
  renewal_professor_review_end?: string;
  renewal_college_review_start?: string;
  renewal_college_review_end?: string;
  requires_professor_recommendation?: boolean;
  professor_review_start?: string;
  professor_review_end?: string;
  requires_college_review?: boolean;
  college_review_start?: string;
  college_review_end?: string;
  review_deadline?: string;
  is_active?: boolean;
  effective_start_date?: string;
  effective_end_date?: string;
  version?: string;
}

// User Profile interfaces
export interface UserProfile {
  id: number;
  user_id: number;
  account_number?: string;
  account_holder_name?: string;
  advisor_name?: string;
  advisor_name_en?: string;
  advisor_email?: string;
  advisor_phone?: string;
  advisor_department?: string;
  advisor_title?: string;
  preferred_email?: string;
  phone_number?: string;
  mobile_number?: string;
  current_address?: string;
  permanent_address?: string;
  postal_code?: string;
  emergency_contact_name?: string;
  emergency_contact_relationship?: string;
  emergency_contact_phone?: string;
  preferred_language: string;
  bio?: string;
  interests?: string;
  social_links?: Record<string, string>;
  profile_photo_url?: string;
  has_complete_bank_info: boolean;
  has_advisor_info: boolean;
  profile_completion_percentage: number;
  created_at: string;
  updated_at: string;
}

export interface CompleteUserProfile {
  user_info: Record<string, any>; // From User model API
  profile: UserProfile | null;
  student_info?: Record<string, any>; // Student-specific data if applicable
}

export interface UserProfileUpdate {
  account_number?: string;
  account_holder_name?: string;
  advisor_name?: string;
  advisor_name_en?: string;
  advisor_email?: string;
  advisor_phone?: string;
  advisor_department?: string;
  advisor_title?: string;
  preferred_email?: string;
  phone_number?: string;
  mobile_number?: string;
  current_address?: string;
  permanent_address?: string;
  postal_code?: string;
  emergency_contact_name?: string;
  emergency_contact_relationship?: string;
  emergency_contact_phone?: string;
  preferred_language?: string;
  bio?: string;
  interests?: string;
  social_links?: Record<string, string>;
  privacy_settings?: Record<string, any>;
  custom_fields?: Record<string, any>;
}

export interface BankInfoUpdate {
  account_number?: string;
  account_holder_name?: string;
  change_reason?: string;
}

export interface AdvisorInfoUpdate {
  advisor_name?: string;
  advisor_name_en?: string;
  advisor_email?: string;
  advisor_phone?: string;
  advisor_department?: string;
  advisor_title?: string;
  change_reason?: string;
}

export interface ContactInfoUpdate {
  preferred_email?: string;
  phone_number?: string;
  mobile_number?: string;
  current_address?: string;
  permanent_address?: string;
  postal_code?: string;
  change_reason?: string;
}

export interface EmergencyContactUpdate {
  emergency_contact_name?: string;
  emergency_contact_relationship?: string;
  emergency_contact_phone?: string;
  change_reason?: string;
}

export interface ProfileHistory {
  id: number;
  user_id: number;
  field_name: string;
  old_value?: string;
  new_value?: string;
  change_reason?: string;
  changed_at: string;
}

class ApiClient {
  private baseURL: string;
  private token: string | null = null;

  constructor() {
    // Use relative path in browser (Nginx will proxy /api/ to backend)
    // Use internal Docker network URL for server-side rendering
    if (typeof window !== "undefined") {
      // Browser environment - always use relative path
      // Nginx reverse proxy will handle routing /api/* to backend
      this.baseURL = "";
      console.log("🌐 API Client Browser mode - using relative path (Nginx proxy)");
    } else {
      // Server-side environment - use internal Docker network or localhost
      this.baseURL = process.env.INTERNAL_API_URL || "http://localhost:8000";
      console.log("🖥️ API Client Server-side mode - using:", this.baseURL);
    }

    // Try to get token from localStorage on client side with safe access
    if (typeof window !== "undefined") {
      this.token = window.localStorage?.getItem?.("auth_token") ?? null;
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("auth_token", token);
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
    }
  }

  hasToken(): boolean {
    return !!this.token;
  }

  getToken(): string | null {
    return this.token;
  }

  private getContentType(res: any): string {
    const h: any = res?.headers;
    if (h?.get) return h.get("content-type") || "";
    if (h && typeof h === "object") {
      return h["content-type"] || h["Content-Type"] || h["Content-type"] || "";
    }
    return "";
  }

  private async readTextSafe(res: any): Promise<string> {
    try {
      if (typeof res?.text === "function") return await res.text();
    } catch {}
    if (typeof res?.json === "function") {
      try {
        return JSON.stringify(await res.json());
      } catch {}
    }
    if (typeof res?.body === "string") return res.body;
    if (typeof (res as any)?._bodyInit === "string")
      return (res as any)._bodyInit;
    return "";
  }

  async request<T = any>(
    endpoint: string,
    options: RequestInit & { params?: Record<string, any> } = {}
  ): Promise<ApiResponse<T>> {
    // Handle query parameters
    let url = `${this.baseURL}/api/v1${endpoint}`;
    if (options.params) {
      const searchParams = new URLSearchParams();
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          searchParams.append(key, String(value));
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    // Normalize headers so .get/.set always exist
    const headers = new Headers(options.headers ?? {});

    // Only set Content-Type if it's not FormData
    const isFormData = options.body instanceof FormData;
    if (!isFormData && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    headers.set("Accept", "application/json");

    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
      // console.log('🔐 API Request with auth token to:', endpoint)
    } else {
      // Optional: keep these for local debugging; comment to reduce CI noise
      // console.warn('❌ No auth token available for request to:', endpoint)
      // console.warn('❌ localStorage auth_token:', typeof window !== 'undefined'
      //   ? window.localStorage?.getItem?.('auth_token') : 'N/A')
    }

    // Remove params from options before passing to fetch
    const { params, ...fetchOptions } = options;
    const config: RequestInit = {
      ...fetchOptions,
      headers,
    };

    try {
      const response: any = await fetch(url, config);

      const contentType = this.getContentType(response);
      const canJson =
        contentType.includes("application/json") ||
        typeof response?.json === "function";

      let data: any;
      if (canJson) {
        try {
          data = await response.json();
        } catch {
          const t = await this.readTextSafe(response);
          try {
            data = JSON.parse(t);
          } catch {
            data = t;
          }
        }
      } else {
        const t = await this.readTextSafe(response);
        try {
          data = JSON.parse(t);
        } catch {
          data = t;
        }
      }

      if (!response.ok) {
        // Handle specific error codes
        if (response.status === 401) {
          console.error("Authentication failed - clearing token");
          this.clearToken();
        } else if (response.status === 403) {
          console.error(
            "Authorization denied - user may not have proper permissions"
          );
        } else if (response.status === 429) {
          console.warn("Rate limit exceeded - request throttled");
        }

        const msg =
          (data && (data.detail || data.error || data.message || data.title)) ||
          (typeof data === "string" ? data : "") ||
          response.statusText ||
          `HTTP ${response.status}`;
        throw new Error(msg);
      }

      // Handle different response formats from backend
      if (data && typeof data === "object") {
        // If response already has success/message structure, return as-is
        if ("success" in data && "message" in data) {
          return data as ApiResponse<T>;
        }
        // If it's a PaginatedResponse (has items, total, page, size, pages), wrap it
        else if (
          "items" in data &&
          "total" in data &&
          "page" in data &&
          "size" in data &&
          "pages" in data
        ) {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
        // If it's a direct object (like Application), wrap it
        else if ("id" in data) {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
        // If it's an array, wrap it
        else if (Array.isArray(data)) {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
      }

      return data;
    } catch (error) {
      console.error("API request failed:", error);
      throw error;
    }
  }

  // Authentication endpoints
  auth = {
    login: async (
      username: string,
      password: string
    ): Promise<
      ApiResponse<{
        access_token: string;
        token_type: string;
        expires_in: number;
        user: User;
      }>
    > => {
      return this.request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
    },

    register: async (userData: {
      username: string;
      email: string;
      password: string;
      full_name: string;
    }): Promise<ApiResponse<User>> => {
      return this.request("/auth/register", {
        method: "POST",
        body: JSON.stringify(userData),
      });
    },

    getCurrentUser: async (): Promise<ApiResponse<User>> => {
      return this.request("/auth/me");
    },

    refreshToken: async (): Promise<
      ApiResponse<{ access_token: string; token_type: string }>
    > => {
      return this.request("/auth/refresh", {
        method: "POST",
      });
    },

    // Mock SSO endpoints for development
    getMockUsers: async (): Promise<ApiResponse<any[]>> => {
      return this.request("/auth/mock-sso/users");
    },

    mockSSOLogin: async (
      nycu_id: string
    ): Promise<
      ApiResponse<{
        access_token: string;
        token_type: string;
        expires_in: number;
        user: User;
      }>
    > => {
      return this.request("/auth/mock-sso/login", {
        method: "POST",
        body: JSON.stringify({ nycu_id }),
      });
    },
  };

  // User management endpoints
  users = {
    getProfile: async (): Promise<ApiResponse<User>> => {
      return this.request("/users/me");
    },

    updateProfile: async (
      userData: Partial<User>
    ): Promise<ApiResponse<User>> => {
      return this.request("/users/me", {
        method: "PUT",
        body: JSON.stringify(userData),
      });
    },

    getStudentInfo: async (): Promise<ApiResponse<StudentInfoResponse>> => {
      return this.request("/users/student-info");
    },

    updateStudentInfo: async (
      studentData: Partial<Student>
    ): Promise<ApiResponse<Student>> => {
      return this.request("/users/student-info", {
        method: "PUT",
        body: JSON.stringify(studentData),
      });
    },

    // Get all users with pagination and filters
    getAll: (params?: {
      page?: number;
      size?: number;
      role?: string;
      search?: string;
    }) =>
      this.request<PaginatedResponse<UserListResponse>>("/users", {
        method: "GET",
        params,
      }),

    // Get user by ID
    getById: (userId: number) =>
      this.request<UserResponse>(`/users/${userId}`, {
        method: "GET",
      }),

    // Create new user
    create: (userData: UserCreate) =>
      this.request<UserResponse>("/users", {
        method: "POST",
        body: JSON.stringify(userData),
      }),

    // Update user
    update: (userId: number, userData: UserUpdate) =>
      this.request<UserResponse>(`/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify(userData),
      }),

    // Delete user (hard delete)
    delete: (userId: number) =>
      this.request<{
        success: boolean;
        message: string;
        data: { user_id: number };
      }>(`/users/${userId}`, {
        method: "DELETE",
      }),

    // Reset user password (not supported in SSO model)
    resetPassword: (userId: number) =>
      this.request<{
        success: boolean;
        message: string;
        data: { user_id: number };
      }>(`/users/${userId}/reset-password`, {
        method: "POST",
      }),

    // Get user statistics
    getStats: () =>
      this.request<UserStats>("/users/stats/overview", {
        method: "GET",
      }),
  };

  // Scholarship endpoints
  scholarships = {
    getEligible: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      return this.request("/scholarships/eligible");
    },

    getById: async (id: number): Promise<ApiResponse<ScholarshipType>> => {
      return this.request(`/scholarships/${id}`);
    },

    getAll: async (): Promise<ApiResponse<any[]>> => {
      return this.request("/scholarships");
    },

    // Get combined scholarships
    getCombined: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      return this.request("/scholarships/combined/list");
    },

    // Create combined PhD scholarship
    createCombinedPhd: async (data: {
      name: string;
      name_en: string;
      description: string;
      description_en: string;
      sub_scholarships: Array<{
        code: string;
        name: string;
        name_en: string;
        description: string;
        description_en: string;
        sub_type: "nstc" | "moe";
        amount: number;
        min_gpa?: number;
        max_ranking_percent?: number;
        required_documents?: string[];
        application_start_date?: string;
        application_end_date?: string;
      }>;
    }): Promise<ApiResponse<ScholarshipType>> => {
      return this.request("/scholarships/combined/phd", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  };

  // Application management endpoints
  applications = {
    getMyApplications: async (
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = status ? `?status=${encodeURIComponent(status)}` : "";
      return this.request(`/applications${params}`);
    },

    getCollegeReview: async (
      status?: string,
      scholarshipType?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams();
      if (status) params.append("status", status);
      if (scholarshipType) params.append("scholarship_type", scholarshipType);

      const queryString = params.toString();
      return this.request(
        `/applications/college/review${queryString ? `?${queryString}` : ""}`
      );
    },

    getByScholarshipType: async (
      scholarshipType: string,
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams();
      params.append("scholarship_type", scholarshipType);
      if (status) params.append("status", status);

      const queryString = params.toString();
      return this.request(
        `/applications/review/list${queryString ? `?${queryString}` : ""}`
      );
    },

    createApplication: async (
      applicationData: ApplicationCreate,
      isDraft: boolean = false
    ): Promise<ApiResponse<Application>> => {
      const url = isDraft ? "/applications?is_draft=true" : "/applications";
      return this.request(url, {
        method: "POST",
        body: JSON.stringify(applicationData),
      });
    },

    getApplicationById: async (
      id: number
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${id}`);
    },

    updateApplication: async (
      id: number,
      applicationData: Partial<ApplicationCreate>
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${id}`, {
        method: "PUT",
        body: JSON.stringify(applicationData),
      });
    },

    updateStatus: async (
      id: number,
      statusData: { status: string; comments?: string }
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify(statusData),
      });
    },

    uploadFile: async (
      applicationId: number,
      file: File,
      fileType: string
    ): Promise<ApiResponse<any>> => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("file_type", fileType);

      return this.request(`/applications/${applicationId}/files`, {
        method: "POST",
        body: formData,
      });
    },

    submitApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${applicationId}/submit`, {
        method: "POST",
      });
    },

    deleteApplication: async (
      applicationId: number
    ): Promise<ApiResponse<{ success: boolean; message: string }>> => {
      return this.request(`/applications/${applicationId}`, {
        method: "DELETE",
      });
    },

    withdrawApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${applicationId}/withdraw`, {
        method: "POST",
      });
    },

    uploadDocument: async (
      applicationId: number,
      file: File,
      fileType: string = "other"
    ): Promise<ApiResponse<any>> => {
      const formData = new FormData();
      formData.append("file", file);

      return this.request(
        `/applications/${applicationId}/files/upload?file_type=${encodeURIComponent(fileType)}`,
        {
          method: "POST",
          body: formData,
          headers: {}, // Remove Content-Type to let browser set it for FormData
        }
      );
    },

    getApplicationFiles: async (
      applicationId: number
    ): Promise<ApiResponse<ApplicationFile[]>> => {
      return this.request(`/applications/${applicationId}/files`);
    },

    // 新增暫存申請功能
    saveApplicationDraft: async (
      applicationData: ApplicationCreate
    ): Promise<ApiResponse<Application>> => {
      const response = await this.request("/applications?is_draft=true", {
        method: "POST",
        body: JSON.stringify(applicationData),
      });

      // Handle direct Application response vs wrapped ApiResponse
      if (
        response &&
        typeof response === "object" &&
        "id" in response &&
        !("success" in response)
      ) {
        // Direct Application object - wrap it in ApiResponse format
        return {
          success: true,
          message: "Draft saved successfully",
          data: response as unknown as Application,
        };
      }

      // Already in ApiResponse format
      return response as ApiResponse<Application>;
    },

    submitRecommendation: async (
      applicationId: number,
      reviewStage: string,
      recommendation: string,
      selectedAwards?: string[]
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${applicationId}/review`, {
        method: "POST",
        body: JSON.stringify({
          application_id: applicationId,
          review_stage: reviewStage,
          recommendation,
          ...(selectedAwards ? { selected_awards: selectedAwards } : {}),
        }),
      });
    },
  };

  // Notification endpoints
  notifications = {
    getNotifications: async (
      skip?: number,
      limit?: number,
      unreadOnly?: boolean,
      notificationType?: string
    ): Promise<ApiResponse<NotificationResponse[]>> => {
      const params = new URLSearchParams();
      if (skip) params.append("skip", skip.toString());
      if (limit) params.append("limit", limit.toString());
      if (unreadOnly) params.append("unread_only", "true");
      if (notificationType)
        params.append("notification_type", notificationType);

      const queryString = params.toString();
      return this.request(
        `/notifications${queryString ? `?${queryString}` : ""}`
      );
    },

    getUnreadCount: async (): Promise<ApiResponse<number>> => {
      return this.request("/notifications/unread-count");
    },

    markAsRead: async (
      notificationId: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/notifications/${notificationId}/read`, {
        method: "PATCH",
      });
    },

    markAllAsRead: async (): Promise<
      ApiResponse<{ updated_count: number }>
    > => {
      return this.request("/notifications/mark-all-read", {
        method: "PATCH",
      });
    },

    dismiss: async (
      notificationId: number
    ): Promise<ApiResponse<{ notification_id: number }>> => {
      return this.request(`/notifications/${notificationId}/dismiss`, {
        method: "PATCH",
      });
    },

    getNotificationDetail: async (
      notificationId: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/notifications/${notificationId}`);
    },

    // Admin-only notification endpoints
    createSystemAnnouncement: async (
      announcementData: AnnouncementCreate
    ): Promise<ApiResponse<NotificationResponse>> => {
      return this.request("/notifications/admin/create-system-announcement", {
        method: "POST",
        body: JSON.stringify(announcementData),
      });
    },

    createTestNotifications: async (): Promise<
      ApiResponse<{ created_count: number; notification_ids: number[] }>
    > => {
      return this.request("/notifications/admin/create-test-notifications", {
        method: "POST",
      });
    },
  };

  // Admin endpoints
  admin = {
    getDashboardStats: async (): Promise<ApiResponse<DashboardStats>> => {
      return this.request("/admin/dashboard/stats");
    },

    getRecentApplications: async (
      limit?: number
    ): Promise<ApiResponse<Application[]>> => {
      const params = limit ? `?limit=${limit}` : "";
      return this.request(`/admin/recent-applications${params}`);
    },

    getSystemAnnouncements: async (
      limit?: number
    ): Promise<ApiResponse<NotificationResponse[]>> => {
      const params = limit ? `?limit=${limit}` : "";
      return this.request(`/admin/system-announcements${params}`);
    },

    getAllApplications: async (
      page?: number,
      size?: number,
      status?: string
    ): Promise<
      ApiResponse<{
        items: Application[];
        total: number;
        page: number;
        size: number;
      }>
    > => {
      const params = new URLSearchParams();
      if (page) params.append("page", page.toString());
      if (size) params.append("size", size.toString());
      if (status) params.append("status", status);

      const queryString = params.toString();
      return this.request(
        `/admin/applications${queryString ? `?${queryString}` : ""}`
      );
    },

    getHistoricalApplications: async (
      filters?: HistoricalApplicationFilters
    ): Promise<
      ApiResponse<{
        items: HistoricalApplication[];
        total: number;
        page: number;
        size: number;
        pages: number;
      }>
    > => {
      const params = new URLSearchParams();

      if (filters?.page) params.append("page", filters.page.toString());
      if (filters?.size) params.append("size", filters.size.toString());
      if (filters?.status) params.append("status", filters.status);
      if (filters?.scholarship_type)
        params.append("scholarship_type", filters.scholarship_type);
      if (filters?.academic_year)
        params.append("academic_year", filters.academic_year.toString());
      if (filters?.semester) params.append("semester", filters.semester);
      if (filters?.search) params.append("search", filters.search);

      const queryString = params.toString();
      return this.request(
        `/admin/applications/history${queryString ? `?${queryString}` : ""}`
      );
    },

    updateApplicationStatus: async (
      applicationId: number,
      status: string,
      reviewNotes?: string
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/admin/applications/${applicationId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status, review_notes: reviewNotes }),
      });
    },

    getEmailTemplate: async (
      key: string
    ): Promise<ApiResponse<EmailTemplate>> => {
      return this.request(
        `/admin/email-template?key=${encodeURIComponent(key)}`
      );
    },

    updateEmailTemplate: async (
      template: EmailTemplate
    ): Promise<ApiResponse<EmailTemplate>> => {
      return this.request("/admin/email-template", {
        method: "PUT",
        body: JSON.stringify(template),
      });
    },

    getEmailTemplatesBySendingType: async (
      sendingType?: string
    ): Promise<ApiResponse<EmailTemplate[]>> => {
      const params = sendingType
        ? `?sending_type=${encodeURIComponent(sendingType)}`
        : "";
      return this.request(`/admin/email-templates${params}`);
    },

    // Scholarship Email Template endpoints
    getScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<
      ApiResponse<{
        items: any[];
        total: number;
      }>
    > => {
      return this.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}`
      );
    },

    getScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string
    ): Promise<ApiResponse<any>> => {
      return this.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/${encodeURIComponent(templateKey)}`
      );
    },

    createScholarshipEmailTemplate: async (templateData: {
      scholarship_type_id: number;
      email_template_key: string;
      is_enabled?: boolean;
      priority?: number;
      custom_subject?: string;
      custom_body?: string;
      notes?: string;
    }): Promise<ApiResponse<any>> => {
      return this.request("/admin/scholarship-email-templates", {
        method: "POST",
        body: JSON.stringify(templateData),
      });
    },

    updateScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string,
      templateData: {
        is_enabled?: boolean;
        priority?: number;
        custom_subject?: string;
        custom_body?: string;
        notes?: string;
      }
    ): Promise<ApiResponse<any>> => {
      return this.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/${encodeURIComponent(templateKey)}`,
        {
          method: "PUT",
          body: JSON.stringify(templateData),
        }
      );
    },

    deleteScholarshipEmailTemplate: async (
      scholarshipTypeId: number,
      templateKey: string
    ): Promise<ApiResponse<boolean>> => {
      return this.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/${encodeURIComponent(templateKey)}`,
        {
          method: "DELETE",
        }
      );
    },

    bulkCreateScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<
      ApiResponse<{
        items: any[];
        total: number;
      }>
    > => {
      return this.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/bulk-create`,
        {
          method: "POST",
        }
      );
    },

    getAvailableScholarshipEmailTemplates: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<EmailTemplate[]>> => {
      return this.request(
        `/admin/scholarship-email-templates/${scholarshipTypeId}/available`
      );
    },

    getSystemSetting: async (
      key: string
    ): Promise<ApiResponse<SystemSetting>> => {
      return this.request(
        `/admin/system-setting?key=${encodeURIComponent(key)}`
      );
    },

    updateSystemSetting: async (
      setting: SystemSetting
    ): Promise<ApiResponse<SystemSetting>> => {
      return this.request(`/admin/system-setting`, {
        method: "PUT",
        body: JSON.stringify(setting),
      });
    },

    // === 系統公告管理 === //

    getAllAnnouncements: async (
      page?: number,
      size?: number,
      notificationType?: string,
      priority?: string
    ): Promise<
      ApiResponse<{
        items: NotificationResponse[];
        total: number;
        page: number;
        size: number;
      }>
    > => {
      const params = new URLSearchParams();
      if (page) params.append("page", page.toString());
      if (size) params.append("size", size.toString());
      if (notificationType)
        params.append("notification_type", notificationType);
      if (priority) params.append("priority", priority);

      const queryString = params.toString();
      return this.request(
        `/admin/announcements${queryString ? `?${queryString}` : ""}`
      );
    },

    getAnnouncement: async (
      id: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/admin/announcements/${id}`);
    },

    createAnnouncement: async (
      announcementData: AnnouncementCreate
    ): Promise<ApiResponse<NotificationResponse>> => {
      return this.request("/admin/announcements", {
        method: "POST",
        body: JSON.stringify(announcementData),
      });
    },

    updateAnnouncement: async (
      id: number,
      announcementData: AnnouncementUpdate
    ): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/admin/announcements/${id}`, {
        method: "PUT",
        body: JSON.stringify(announcementData),
      });
    },

    deleteAnnouncement: async (
      id: number
    ): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/announcements/${id}`, {
        method: "DELETE",
      });
    },

    // Scholarship management endpoints
    getScholarshipStats: async (): Promise<
      ApiResponse<Record<string, ScholarshipStats>>
    > => {
      return this.request("/admin/scholarships/stats");
    },

    getApplicationsByScholarship: async (
      scholarshipCode: string,
      subType?: string,
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams();
      if (subType) params.append("sub_type", subType);
      if (status) params.append("status", status);

      const queryString = params.toString();
      return this.request(
        `/admin/scholarships/${scholarshipCode}/applications${queryString ? `?${queryString}` : ""}`
      );
    },

    getScholarshipSubTypes: async (
      scholarshipCode: string
    ): Promise<ApiResponse<SubTypeStats[]>> => {
      return this.request(`/admin/scholarships/${scholarshipCode}/sub-types`);
    },

    getSubTypeTranslations: async (): Promise<
      ApiResponse<Record<string, Record<string, string>>>
    > => {
      return this.request("/admin/scholarships/sub-type-translations");
    },

    // === 系統管理相關 API === //

    // 工作流程管理 (temporarily disabled - endpoints not implemented)
    getWorkflows: async (): Promise<ApiResponse<Workflow[]>> => {
      return Promise.resolve({
        success: true,
        data: [],
        message: "Workflows feature coming soon",
      });
    },

    createWorkflow: async (
      workflow: Omit<Workflow, "id" | "created_at" | "updated_at">
    ): Promise<ApiResponse<Workflow>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    updateWorkflow: async (
      id: string,
      workflow: Partial<Workflow>
    ): Promise<ApiResponse<Workflow>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    deleteWorkflow: async (
      id: string
    ): Promise<ApiResponse<{ message: string }>> => {
      return Promise.resolve({
        success: false,
        message: "Workflows feature not implemented yet",
      });
    },

    // 獎學金規則管理
    getScholarshipRules: async (filters?: {
      scholarship_type_id?: number;
      academic_year?: number;
      semester?: string;
      sub_type?: string;
      rule_type?: string;
      is_template?: boolean;
      is_active?: boolean;
      tag?: string;
    }): Promise<ApiResponse<ScholarshipRule[]>> => {
      const queryParams = new URLSearchParams();
      if (filters) {
        Object.entries(filters).forEach(([key, value]) => {
          if (value !== undefined && value !== null) {
            queryParams.append(key, String(value));
          }
        });
      }
      const queryString = queryParams.toString();
      return this.request(
        `/admin/scholarship-rules${queryString ? `?${queryString}` : ""}`
      );
    },

    getScholarshipRule: async (
      id: number
    ): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request(`/admin/scholarship-rules/${id}`);
    },

    createScholarshipRule: async (
      rule: Partial<ScholarshipRule>
    ): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request("/admin/scholarship-rules", {
        method: "POST",
        body: JSON.stringify(rule),
      });
    },

    updateScholarshipRule: async (
      id: number,
      rule: Partial<ScholarshipRule>
    ): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request(`/admin/scholarship-rules/${id}`, {
        method: "PUT",
        body: JSON.stringify(rule),
      });
    },

    deleteScholarshipRule: async (
      id: number
    ): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/scholarship-rules/${id}`, {
        method: "DELETE",
      });
    },

    // 規則複製和批量操作
    copyRulesBetweenPeriods: async (copyRequest: {
      source_academic_year?: number;
      source_semester?: string;
      target_academic_year: number;
      target_semester?: string;
      scholarship_type_ids?: number[];
      rule_ids?: number[];
      overwrite_existing?: boolean;
    }): Promise<ApiResponse<ScholarshipRule[]>> => {
      const response = await this.request<ScholarshipRule[]>(
        "/admin/scholarship-rules/copy",
        {
          method: "POST",
          body: JSON.stringify(copyRequest),
        }
      );
      return response;
    },

    bulkRuleOperation: async (operation: {
      operation: string;
      rule_ids: number[];
      parameters?: Record<string, any>;
    }): Promise<
      ApiResponse<{
        operation: string;
        affected_rules: number;
        details: string[];
      }>
    > => {
      return this.request("/admin/scholarship-rules/bulk-operation", {
        method: "POST",
        body: JSON.stringify(operation),
      });
    },

    // 規則模板管理
    getRuleTemplates: async (
      scholarship_type_id?: number
    ): Promise<ApiResponse<ScholarshipRule[]>> => {
      const queryParams = scholarship_type_id
        ? `?scholarship_type_id=${scholarship_type_id}`
        : "";
      return this.request<ScholarshipRule[]>(
        `/admin/scholarship-rules/templates${queryParams}`
      );
    },

    createRuleTemplate: async (templateRequest: {
      template_name: string;
      template_description?: string;
      scholarship_type_id: number;
      rule_ids: number[];
    }): Promise<ApiResponse<ScholarshipRule[]>> => {
      return this.request("/admin/scholarship-rules/create-template", {
        method: "POST",
        body: JSON.stringify(templateRequest),
      });
    },

    applyRuleTemplate: async (templateRequest: {
      template_id: number;
      scholarship_type_id: number;
      academic_year: number;
      semester?: string;
      overwrite_existing?: boolean;
    }): Promise<ApiResponse<ScholarshipRule[]>> => {
      return this.request("/admin/scholarship-rules/apply-template", {
        method: "POST",
        body: JSON.stringify(templateRequest),
      });
    },

    deleteRuleTemplate: async (
      templateName: string,
      scholarshipTypeId: number
    ): Promise<ApiResponse<{ message: string }>> => {
      return this.request(
        `/admin/scholarship-rules/templates/${encodeURIComponent(templateName)}?scholarship_type_id=${scholarshipTypeId}`,
        {
          method: "DELETE",
        }
      );
    },

    // Get available sub-types for a scholarship type
    getScholarshipRuleSubTypes: async (
      scholarshipTypeId: number
    ): Promise<ApiResponse<SubTypeOption[]>> => {
      return this.request(
        `/scholarship-rules/scholarship-types/${scholarshipTypeId}/sub-types`
      );
    },

    // 系統統計
    getSystemStats: async (): Promise<ApiResponse<SystemStats>> => {
      return this.request("/admin/dashboard/stats");
    },

    // 獎學金權限管理
    getScholarshipPermissions: async (
      userId?: number
    ): Promise<ApiResponse<ScholarshipPermission[]>> => {
      const params = userId ? `?user_id=${userId}` : "";
      return this.request(`/admin/scholarship-permissions${params}`);
    },

    // 獲取當前用戶的獎學金權限
    getCurrentUserScholarshipPermissions: async (): Promise<
      ApiResponse<ScholarshipPermission[]>
    > => {
      return this.request("/admin/scholarship-permissions/current-user");
    },

    createScholarshipPermission: async (
      permission: ScholarshipPermissionCreate
    ): Promise<ApiResponse<ScholarshipPermission>> => {
      return this.request("/admin/scholarship-permissions", {
        method: "POST",
        body: JSON.stringify(permission),
      });
    },

    updateScholarshipPermission: async (
      id: number,
      permission: Partial<ScholarshipPermissionCreate>
    ): Promise<ApiResponse<ScholarshipPermission>> => {
      return this.request(`/admin/scholarship-permissions/${id}`, {
        method: "PUT",
        body: JSON.stringify(permission),
      });
    },

    deleteScholarshipPermission: async (
      id: number
    ): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/scholarship-permissions/${id}`, {
        method: "DELETE",
      });
    },

    // 獲取所有獎學金列表（用於權限管理）
    getAllScholarshipsForPermissions: async (): Promise<
      ApiResponse<
        Array<{ id: number; name: string; name_en?: string; code: string }>
      >
    > => {
      return this.request("/admin/scholarships/all-for-permissions");
    },

    // 獲取當前用戶有權限管理的獎學金列表
    getMyScholarships: async (): Promise<
      ApiResponse<
        Array<{
          id: number;
          name: string;
          name_en?: string;
          code: string;
          category?: string;
          application_cycle?: string;
          status?: string;
          whitelist_enabled?: boolean;
          sub_type_list?: string[];
        }>
      >
    > => {
      return this.request("/admin/scholarships/my-scholarships");
    },

    // 獲取 ScholarshipConfiguration 中實際配置的學期
    getAvailableSemesters: async (
      scholarshipCode?: string
    ): Promise<ApiResponse<string[]>> => {
      const params = scholarshipCode
        ? `?scholarship_code=${encodeURIComponent(scholarshipCode)}`
        : "";
      return this.request(
        `/scholarship-configurations/available-semesters${params}`
      );
    },

    // 獲取可用年份
    getAvailableYears: async (): Promise<ApiResponse<number[]>> => {
      return this.request("/admin/scholarships/available-years");
    },

    // Scholarship Configuration Management
    getScholarshipConfigTypes: async (): Promise<ApiResponse<any[]>> => {
      return this.request("/scholarship-configurations/scholarship-types");
    },
    getScholarshipConfigurations: async (params?: {
      scholarship_type_id?: number;
      academic_year?: number;
      semester?: string;
      is_active?: boolean;
    }): Promise<ApiResponse<ScholarshipConfiguration[]>> => {
      const queryParams = new URLSearchParams();
      if (params?.scholarship_type_id)
        queryParams.append(
          "scholarship_type_id",
          params.scholarship_type_id.toString()
        );
      if (params?.academic_year)
        queryParams.append("academic_year", params.academic_year.toString());
      if (params?.semester) queryParams.append("semester", params.semester);
      if (params?.is_active !== undefined)
        queryParams.append("is_active", params.is_active.toString());

      const queryString = queryParams.toString();
      return this.request(
        `/scholarship-configurations/configurations${queryString ? `?${queryString}` : ""}`
      );
    },
    getScholarshipConfiguration: async (
      id: number
    ): Promise<ApiResponse<ScholarshipConfiguration>> => {
      return this.request(`/scholarship-configurations/configurations/${id}`);
    },
    createScholarshipConfiguration: async (
      configData: ScholarshipConfigurationFormData
    ): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request("/scholarship-configurations/configurations", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },
    updateScholarshipConfiguration: async (
      id: number,
      configData: Partial<ScholarshipConfigurationFormData>
    ): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request(`/scholarship-configurations/configurations/${id}`, {
        method: "PUT",
        body: JSON.stringify(configData),
      });
    },
    deleteScholarshipConfiguration: async (
      id: number
    ): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request(`/scholarship-configurations/configurations/${id}`, {
        method: "DELETE",
      });
    },
    duplicateScholarshipConfiguration: async (
      id: number,
      targetData: {
        academic_year: number;
        semester?: string | null;
        config_code: string;
        config_name?: string;
      }
    ): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request(
        `/scholarship-configurations/configurations/${id}/duplicate`,
        {
          method: "POST",
          body: JSON.stringify(targetData),
        }
      );
    },

    // Professor management endpoints
    getProfessors: async (
      search?: string
    ): Promise<
      ApiResponse<
        Array<{
          nycu_id: string;
          name: string;
          dept_code: string;
          dept_name: string;
          email?: string;
        }>
      >
    > => {
      const params = search ? { search } : {};
      return this.request("/admin/professors", {
        method: "GET",
        params,
      });
    },

    assignProfessor: async (
      applicationId: number,
      professorNycuId: string
    ): Promise<ApiResponse<Application>> => {
      return this.request(
        `/admin/applications/${applicationId}/assign-professor`,
        {
          method: "PUT",
          body: JSON.stringify({ professor_nycu_id: professorNycuId }),
        }
      );
    },

    getAvailableProfessors: async (
      search?: string
    ): Promise<ApiResponse<any[]>> => {
      const params = search ? `?search=${encodeURIComponent(search)}` : "";
      return this.request(`/admin/professors${params}`);
    },

    // === System Configuration Management === //
    getConfigurations: async (): Promise<
      ApiResponse<SystemConfiguration[]>
    > => {
      return this.request("/admin/configurations");
    },

    createConfiguration: async (
      configData: SystemConfigurationCreate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      return this.request("/admin/configurations", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    updateConfigurationsBulk: async (
      configurations: SystemConfigurationUpdate[]
    ): Promise<ApiResponse<SystemConfiguration[]>> => {
      return this.request("/admin/configurations/bulk", {
        method: "PUT",
        body: JSON.stringify(configurations),
      });
    },

    validateConfiguration: async (
      configData: SystemConfigurationValidation
    ): Promise<ApiResponse<ConfigurationValidationResult>> => {
      return this.request("/admin/configurations/validate", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    deleteConfiguration: async (key: string): Promise<ApiResponse<string>> => {
      return this.request(`/admin/configurations/${encodeURIComponent(key)}`, {
        method: "DELETE",
      });
    },

    // === Bank Verification === //
    verifyBankAccount: async (
      applicationId: number
    ): Promise<ApiResponse<BankVerificationResult>> => {
      return this.request("/admin/bank-verification", {
        method: "POST",
        body: JSON.stringify({ application_id: applicationId }),
      });
    },

    verifyBankAccountsBatch: async (
      applicationIds: number[]
    ): Promise<ApiResponse<BankVerificationBatchResult>> => {
      return this.request("/admin/bank-verification/batch", {
        method: "POST",
        body: JSON.stringify({ application_ids: applicationIds }),
      });
    },

    // === Professor-Student Relationships === //
    getProfessorStudentRelationships: async (params?: {
      professor_id?: number;
      student_id?: number;
      is_active?: boolean;
    }): Promise<ApiResponse<ProfessorStudentRelationship[]>> => {
      const queryParams = new URLSearchParams();
      if (params?.professor_id)
        queryParams.append("professor_id", params.professor_id.toString());
      if (params?.student_id)
        queryParams.append("student_id", params.student_id.toString());
      if (params?.is_active !== undefined)
        queryParams.append("is_active", params.is_active.toString());

      const queryString = queryParams.toString();
      return this.request(
        `/admin/professor-student-relationships${queryString ? `?${queryString}` : ""}`
      );
    },

    createProfessorStudentRelationship: async (
      relationshipData: ProfessorStudentRelationshipCreate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      return this.request("/admin/professor-student-relationships", {
        method: "POST",
        body: JSON.stringify(relationshipData),
      });
    },

    updateProfessorStudentRelationship: async (
      id: number,
      relationshipData: ProfessorStudentRelationshipUpdate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      return this.request(`/admin/professor-student-relationships/${id}`, {
        method: "PUT",
        body: JSON.stringify(relationshipData),
      });
    },

    deleteProfessorStudentRelationship: async (
      id: number
    ): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/professor-student-relationships/${id}`, {
        method: "DELETE",
      });
    },
  };

  // Application Fields Configuration
  applicationFields = {
    // Form configuration
    getFormConfig: (
      scholarshipType: string,
      includeInactive: boolean = false
    ) =>
      this.request<ScholarshipFormConfig>(
        `/application-fields/form-config/${scholarshipType}?include_inactive=${includeInactive}`
      ),

    saveFormConfig: (scholarshipType: string, config: FormConfigSaveRequest) =>
      this.request<ScholarshipFormConfig>(
        `/application-fields/form-config/${scholarshipType}`,
        {
          method: "POST",
          body: JSON.stringify(config),
        }
      ),

    // Fields management
    getFields: (scholarshipType: string) =>
      this.request<ApplicationField[]>(
        `/application-fields/fields/${scholarshipType}`
      ),

    createField: (fieldData: ApplicationFieldCreate) =>
      this.request<ApplicationField>("/application-fields/fields", {
        method: "POST",
        body: JSON.stringify(fieldData),
      }),

    updateField: (fieldId: number, fieldData: ApplicationFieldUpdate) =>
      this.request<ApplicationField>(`/application-fields/fields/${fieldId}`, {
        method: "PUT",
        body: JSON.stringify(fieldData),
      }),

    deleteField: (fieldId: number) =>
      this.request<boolean>(`/application-fields/fields/${fieldId}`, {
        method: "DELETE",
      }),

    // Documents management
    getDocuments: (scholarshipType: string) =>
      this.request<ApplicationDocument[]>(
        `/application-fields/documents/${scholarshipType}`
      ),

    createDocument: (documentData: ApplicationDocumentCreate) =>
      this.request<ApplicationDocument>("/application-fields/documents", {
        method: "POST",
        body: JSON.stringify(documentData),
      }),

    updateDocument: (
      documentId: number,
      documentData: ApplicationDocumentUpdate
    ) =>
      this.request<ApplicationDocument>(
        `/application-fields/documents/${documentId}`,
        {
          method: "PUT",
          body: JSON.stringify(documentData),
        }
      ),

    deleteDocument: (documentId: number) =>
      this.request<boolean>(`/application-fields/documents/${documentId}`, {
        method: "DELETE",
      }),

    // Example file management
    uploadDocumentExample: async (documentId: number, file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const token =
        typeof window !== "undefined"
          ? window.localStorage?.getItem("auth_token")
          : null;

      const response = await fetch(
        `${this.baseURL}/api/v1/application-fields/documents/${documentId}/upload-example`,
        {
          method: "POST",
          body: formData,
          credentials: "include",
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to upload example file");
      }

      return response.json();
    },

    deleteDocumentExample: (documentId: number) =>
      this.request<boolean>(
        `/application-fields/documents/${documentId}/example`,
        {
          method: "DELETE",
        }
      ),
  };

  // User Profile management endpoints
  userProfiles = {
    // Get complete user profile (read-only + editable data)
    getMyProfile: async (): Promise<ApiResponse<CompleteUserProfile>> => {
      return this.request("/user-profiles/me");
    },

    // Create user profile
    createProfile: async (
      profileData: UserProfileUpdate
    ): Promise<ApiResponse<UserProfile>> => {
      return this.request("/user-profiles/me", {
        method: "POST",
        body: JSON.stringify(profileData),
      });
    },

    // Update complete profile
    updateProfile: async (
      profileData: UserProfileUpdate
    ): Promise<ApiResponse<UserProfile>> => {
      return this.request("/user-profiles/me", {
        method: "PUT",
        body: JSON.stringify(profileData),
      });
    },

    // Update bank account information
    updateBankInfo: async (
      bankData: BankInfoUpdate
    ): Promise<ApiResponse<any>> => {
      return this.request("/user-profiles/me/bank-info", {
        method: "PUT",
        body: JSON.stringify(bankData),
      });
    },

    // Update advisor information
    updateAdvisorInfo: async (
      advisorData: AdvisorInfoUpdate
    ): Promise<ApiResponse<any>> => {
      return this.request("/user-profiles/me/advisor-info", {
        method: "PUT",
        body: JSON.stringify(advisorData),
      });
    },

    // Upload bank document (base64)
    uploadBankDocument: async (
      photoData: string,
      filename: string,
      contentType: string
    ): Promise<ApiResponse<{ document_url: string }>> => {
      return this.request("/user-profiles/me/bank-document", {
        method: "POST",
        body: JSON.stringify({
          photo_data: photoData,
          filename,
          content_type: contentType,
        }),
      });
    },

    // Upload bank document (file)
    uploadBankDocumentFile: async (
      file: File
    ): Promise<ApiResponse<{ document_url: string }>> => {
      const formData = new FormData();
      formData.append("file", file);

      return this.request("/user-profiles/me/bank-document/file", {
        method: "POST",
        body: formData,
      });
    },

    // Delete bank document
    deleteBankDocument: async (): Promise<ApiResponse<any>> => {
      return this.request("/user-profiles/me/bank-document", {
        method: "DELETE",
      });
    },

    // Get profile change history
    getHistory: async (): Promise<ApiResponse<ProfileHistory[]>> => {
      return this.request("/user-profiles/me/history");
    },

    // Delete entire profile
    deleteProfile: async (): Promise<ApiResponse<any>> => {
      return this.request("/user-profiles/me", {
        method: "DELETE",
      });
    },

    // Admin endpoints
    admin: {
      // Get incomplete profiles
      getIncompleteProfiles: async (): Promise<ApiResponse<any>> => {
        return this.request("/user-profiles/admin/incomplete");
      },

      // Get user profile by ID
      getUserProfile: async (
        userId: number
      ): Promise<ApiResponse<CompleteUserProfile>> => {
        return this.request(`/user-profiles/admin/${userId}`);
      },

      // Get user profile history by ID
      getUserHistory: async (
        userId: number
      ): Promise<ApiResponse<ProfileHistory[]>> => {
        return this.request(`/user-profiles/admin/${userId}/history`);
      },
    },
  };

  // Whitelist Management endpoints
  whitelist = {
    // Toggle scholarship whitelist feature
    toggleScholarshipWhitelist: async (
      scholarshipId: number,
      enabled: boolean
    ): Promise<ApiResponse<{ success: boolean }>> => {
      return this.request(`/scholarships/${scholarshipId}/whitelist`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
    },

    // Get whitelist entries for a configuration
    getConfigurationWhitelist: async (
      configurationId: number,
      params?: {
        page?: number;
        size?: number;
        search?: string;
      }
    ): Promise<ApiResponse<WhitelistResponse[]>> => {
      const queryParams = new URLSearchParams();
      if (params?.page) queryParams.append("page", params.page.toString());
      if (params?.size) queryParams.append("size", params.size.toString());
      if (params?.search) queryParams.append("search", params.search);

      const queryString = queryParams.toString();
      const url = `/scholarship-configurations/${configurationId}/whitelist${
        queryString ? `?${queryString}` : ""
      }`;

      return this.request(url);
    },

    // Batch add students to whitelist
    batchAddWhitelist: async (
      configurationId: number,
      request: { students: Array<{ nycu_id: string; sub_type: string }> }
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_items: Array<{
          nycu_id: string;
          reason: string;
        }>;
      }>
    > => {
      return this.request(
        `/scholarship-configurations/${configurationId}/whitelist/batch`,
        {
          method: "POST",
          body: JSON.stringify(request),
        }
      );
    },

    // Batch remove students from whitelist
    batchRemoveWhitelist: async (
      configurationId: number,
      request: {
        nycu_ids: string[];
        sub_type?: string;
      }
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_items: Array<{
          id: number;
          reason: string;
        }>;
      }>
    > => {
      return this.request(
        `/scholarship-configurations/${configurationId}/whitelist/batch`,
        {
          method: "DELETE",
          body: JSON.stringify(request),
        }
      );
    },

    // Import whitelist from Excel
    importWhitelistExcel: async (
      configurationId: number,
      file: File
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_items: Array<{
          row: number;
          nycu_id: string;
          reason: string;
        }>;
      }>
    > => {
      const formData = new FormData();
      formData.append("file", file);

      return this.request(
        `/scholarship-configurations/${configurationId}/whitelist/import`,
        {
          method: "POST",
          body: formData,
          headers: {
            // Let browser set Content-Type with boundary for FormData
          },
        }
      );
    },

    // Export whitelist to Excel
    exportWhitelistExcel: async (
      configurationId: number
    ): Promise<Blob> => {
      const response = await fetch(
        `${this.baseURL}/scholarship-configurations/${configurationId}/whitelist/export`,
        {
          method: "GET",
          headers: {
            Authorization: `Bearer ${this.getToken()}`,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "匯出白名單失敗");
      }

      return response.blob();
    },

    // Download whitelist import template
    downloadTemplate: async (configurationId: number): Promise<Blob> => {
      const response = await fetch(
        `${this.baseURL}/scholarship-configurations/${configurationId}/whitelist/template`,
        {
          method: "GET",
          headers: {
            Authorization: `Bearer ${this.getToken()}`,
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "下載範本失敗");
      }

      return response.blob();
    },
  };

  // Reference Data endpoints
  referenceData = {
    // Get all academies/colleges
    getAcademies: async (): Promise<
      ApiResponse<Array<{ id: number; code: string; name: string }>>
    > => {
      return this.request("/reference-data/academies");
    },

    // Get all departments
    getDepartments: async (): Promise<
      ApiResponse<
        Array<{
          id: number;
          code: string;
          name: string;
          academy_code: string | null;
        }>
      >
    > => {
      return this.request("/reference-data/departments");
    },

    // Get all reference data in one request
    getAll: async (): Promise<
      ApiResponse<{
        academies: Array<{ id: number; code: string; name: string }>;
        departments: Array<{ id: number; code: string; name: string }>;
        degrees: Array<{ id: number; name: string }>;
        identities: Array<{ id: number; name: string }>;
        studying_statuses: Array<{ id: number; name: string }>;
        school_identities: Array<{ id: number; name: string }>;
        enroll_types: Array<{
          degree_id: number;
          code: string;
          name: string;
          name_en?: string;
          degree_name?: string;
        }>;
      }>
    > => {
      return this.request("/reference-data/all");
    },

    // Get scholarship periods based on application cycle
    getScholarshipPeriods: async (params?: {
      scholarship_id?: number;
      scholarship_code?: string;
      application_cycle?: string;
    }): Promise<
      ApiResponse<{
        periods: Array<{
          value: string;
          academic_year: number;
          semester: string | null;
          label: string;
          label_en: string;
          is_current: boolean;
          cycle: string;
          sort_order: number;
        }>;
        cycle: string;
        scholarship_name: string | null;
        current_period: string;
        total_periods: number;
      }>
    > => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return this.request(
        `/reference-data/scholarship-periods${query ? `?${query}` : ""}`
      );
    },
  };

  // Professor review endpoints
  professor = {
    // Get applications requiring professor review
    getApplications: async (
      statusFilter?: string
    ): Promise<ApiResponse<Application[]>> => {
      try {
        const params = statusFilter ? `?status_filter=${statusFilter}` : "";
        console.log(
          "🔍 Requesting professor applications with params:",
          params
        );

        const response = await this.request<PaginatedResponse<Application>>(
          `/professor/applications${params}`
        );
        console.log("📨 Professor applications raw response:", response);

        if (
          response.success &&
          response.data &&
          Array.isArray(response.data.items)
        ) {
          console.log(
            "✅ Loaded professor applications:",
            response.data.items.length
          );
          return {
            success: true,
            message: response.message || "Applications loaded successfully",
            data: response.data.items,
          };
        }

        console.warn("⚠️ Unexpected response format:", response);
        return {
          success: false,
          message:
            response.message ||
            "Failed to load applications - unexpected response format",
          data: [],
        };
      } catch (error: any) {
        console.error("❌ Error in professor.getApplications:", error);
        return {
          success: false,
          message: error.message || "Failed to load applications",
          data: [],
        };
      }
    },

    // Get existing professor review for an application
    getReview: async (applicationId: number): Promise<ApiResponse<any>> => {
      return this.request(`/professor/applications/${applicationId}/review`);
    },

    // Submit professor review for an application
    submitReview: async (
      applicationId: number,
      reviewData: {
        recommendation?: string;
        items: Array<{
          sub_type_code: string;
          is_recommended: boolean;
          comments?: string;
        }>;
      }
    ): Promise<ApiResponse<any>> => {
      return this.request(`/professor/applications/${applicationId}/review`, {
        method: "POST",
        body: JSON.stringify(reviewData),
      });
    },

    // Update existing professor review
    updateReview: async (
      applicationId: number,
      reviewId: number,
      reviewData: {
        recommendation?: string;
        items: Array<{
          sub_type_code: string;
          is_recommended: boolean;
          comments?: string;
        }>;
      }
    ): Promise<ApiResponse<any>> => {
      return this.request(
        `/professor/applications/${applicationId}/review/${reviewId}`,
        {
          method: "PUT",
          body: JSON.stringify(reviewData),
        }
      );
    },

    // Get available sub-types for an application
    getSubTypes: async (
      applicationId: number
    ): Promise<
      ApiResponse<
        Array<{
          value: string;
          label: string;
          label_en: string;
          is_default: boolean;
        }>
      >
    > => {
      return this.request(`/professor/applications/${applicationId}/sub-types`);
    },

    // Get basic review statistics
    getStats: async (): Promise<
      ApiResponse<{
        pending_reviews: number;
        completed_reviews: number;
        overdue_reviews: number;
      }>
    > => {
      return this.request("/professor/stats");
    },
  };

  // Email Management endpoints
  emailManagement = {
    // Get email history with filters
    getEmailHistory: async (params?: {
      skip?: number;
      limit?: number;
      email_category?: string;
      status?: string;
      scholarship_type_id?: number;
      recipient_email?: string;
      date_from?: string;
      date_to?: string;
    }): Promise<
      ApiResponse<{
        items: any[];
        total: number;
        skip: number;
        limit: number;
      }>
    > => {
      return this.request("/email-management/history", {
        method: "GET",
        params,
      });
    },

    // Get scheduled emails with filters
    getScheduledEmails: async (params?: {
      skip?: number;
      limit?: number;
      status?: string;
      scholarship_type_id?: number;
      requires_approval?: boolean;
      email_category?: string;
      scheduled_from?: string;
      scheduled_to?: string;
    }): Promise<
      ApiResponse<{
        items: any[];
        total: number;
        skip: number;
        limit: number;
      }>
    > => {
      return this.request("/email-management/scheduled", {
        method: "GET",
        params,
      });
    },

    // Get due scheduled emails (superadmin only)
    getDueScheduledEmails: async (
      limit?: number
    ): Promise<ApiResponse<any[]>> => {
      const params = limit ? { limit } : {};
      return this.request("/email-management/scheduled/due", {
        method: "GET",
        params,
      });
    },

    // Approve scheduled email
    approveScheduledEmail: async (
      emailId: number,
      approvalNotes?: string
    ): Promise<ApiResponse<any>> => {
      return this.request(`/email-management/scheduled/${emailId}/approve`, {
        method: "PATCH",
        body: JSON.stringify({
          approval_notes: approvalNotes,
        }),
      });
    },

    // Cancel scheduled email
    cancelScheduledEmail: async (
      emailId: number
    ): Promise<ApiResponse<any>> => {
      return this.request(`/email-management/scheduled/${emailId}/cancel`, {
        method: "PATCH",
      });
    },

    // Update scheduled email
    updateScheduledEmail: async (
      emailId: number,
      data: { subject: string; body: string }
    ): Promise<ApiResponse<any>> => {
      return this.request(`/email-management/scheduled/${emailId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    // Process due emails (superadmin only)
    processDueEmails: async (
      batchSize?: number
    ): Promise<
      ApiResponse<{
        processed: number;
        sent: number;
        failed: number;
        skipped: number;
      }>
    > => {
      const params = batchSize ? { batch_size: batchSize } : {};
      return this.request("/email-management/scheduled/process", {
        method: "POST",
        params,
      });
    },

    // Get email categories
    getEmailCategories: async (): Promise<ApiResponse<string[]>> => {
      return this.request("/email-management/categories");
    },

    // Get email and schedule statuses
    getEmailStatuses: async (): Promise<
      ApiResponse<{
        email_statuses: string[];
        schedule_statuses: string[];
      }>
    > => {
      return this.request("/email-management/statuses");
    },

    // ========== Email Test Mode Methods ==========

    // Get test mode status
    getTestModeStatus: async (): Promise<
      ApiResponse<{
        enabled: boolean;
        redirect_emails: string[];
        expires_at: string | null;
        enabled_by?: number;
        enabled_at?: string;
      }>
    > => {
      return this.request("/email-management/test-mode/status");
    },

    // Enable test mode
    enableTestMode: async (params: {
      redirect_emails: string | string[];
      duration_hours?: number;
    }): Promise<
      ApiResponse<{
        enabled: boolean;
        redirect_emails: string[];
        expires_at: string;
        enabled_by: number;
        enabled_at: string;
      }>
    > => {
      // Convert array to comma-separated string, or use as-is if already string
      const emailsStr = Array.isArray(params.redirect_emails)
        ? params.redirect_emails.join(",")
        : params.redirect_emails;

      const queryParams = new URLSearchParams({
        redirect_emails: emailsStr,
        duration_hours: (params.duration_hours || 24).toString(),
      });
      return this.request(
        `/email-management/test-mode/enable?${queryParams.toString()}`,
        {
          method: "POST",
        }
      );
    },

    // Disable test mode
    disableTestMode: async (): Promise<
      ApiResponse<{
        enabled: boolean;
        redirect_emails: string[];
        expires_at: null;
        disabled_by: number;
        disabled_at: string;
      }>
    > => {
      return this.request("/email-management/test-mode/disable", {
        method: "POST",
      });
    },

    // Get test mode audit logs
    getTestModeAuditLogs: async (params?: {
      limit?: number;
      event_type?: string;
    }): Promise<
      ApiResponse<{
        items: Array<{
          id: number;
          event_type: string;
          timestamp: string;
          user_id: number | null;
          config_before: any;
          config_after: any;
          original_recipient: string | null;
          actual_recipient: string | null;
          email_subject: string | null;
          session_id: string | null;
          ip_address: string | null;
        }>;
        total: number;
      }>
    > => {
      return this.request("/email-management/test-mode/audit", {
        method: "GET",
        params,
      });
    },

    // Send simple test email
    sendSimpleTestEmail: async (params: {
      recipient_email: string;
      subject: string;
      body: string;
    }): Promise<
      ApiResponse<{
        success: boolean;
        message: string;
        email_id: number | null;
        error?: string;
      }>
    > => {
      return this.request("/email-management/send-simple-test", {
        method: "POST",
        body: JSON.stringify(params),
      });
    },
  };

  college = {
    // Get applications for review
    getApplicationsForReview: async (
      params?: string
    ): Promise<ApiResponse<any[]>> => {
      return this.request(`/college/applications${params ? `?${params}` : ""}`);
    },

    // Get rankings list
    getRankings: async (
      academicYear?: number,
      semester?: string
    ): Promise<ApiResponse<any[]>> => {
      const params = new URLSearchParams();
      if (academicYear) params.append("academic_year", academicYear.toString());
      if (semester) params.append("semester", semester);
      return this.request(
        `/college/rankings${params.toString() ? `?${params.toString()}` : ""}`
      );
    },

    // Get ranking details
    getRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}`);
    },

    // Create new ranking
    createRanking: async (data: {
      scholarship_type_id: number;
      sub_type_code: string;
      academic_year: number;
      semester?: string;
      ranking_name?: string;
      force_new?: boolean;
    }): Promise<ApiResponse<any>> => {
      const payload = {
        ...data,
        force_new: data.force_new ?? false,
      };
      return this.request("/college/rankings", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    // Update ranking order
    updateRankingOrder: async (
      rankingId: number,
      newOrder: Array<{ item_id: number; position: number }>
    ): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}/order`, {
        method: "PUT",
        body: JSON.stringify(newOrder),
      });
    },

    // Execute distribution
    executeDistribution: async (
      rankingId: number,
      distributionRules?: any
    ): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}/distribute`, {
        method: "POST",
        body: JSON.stringify({ distribution_rules: distributionRules }),
      });
    },

    // Finalize ranking
    finalizeRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}/finalize`, {
        method: "POST",
      });
    },

    // Get quota status
    getQuotaStatus: async (
      scholarshipTypeId: number,
      academicYear: number,
      semester?: string
    ): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams({
        scholarship_type_id: scholarshipTypeId.toString(),
        academic_year: academicYear.toString(),
      });
      if (semester) params.append("semester", semester);
      return this.request(`/college/quota-status?${params.toString()}`);
    },

    // Get college review statistics
    getStatistics: async (
      academicYear?: number,
      semester?: string
    ): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams();
      if (academicYear) params.append("academic_year", academicYear.toString());
      if (semester) params.append("semester", semester);
      return this.request(
        `/college/statistics${params.toString() ? `?${params.toString()}` : ""}`
      );
    },

    // Get available combinations of scholarship types, years, and semesters
    getAvailableCombinations: async (): Promise<
      ApiResponse<{
        scholarship_types: Array<{
          code: string;
          name: string;
          name_en?: string;
        }>;
        academic_years: number[];
        semesters: string[];
      }>
    > => {
      return this.request("/college/available-combinations");
    },
  };

  // System Configuration Management endpoints
  system = {
    getConfigurations: async (
      category?: string,
      includeSensitive?: boolean
    ): Promise<ApiResponse<SystemConfiguration[]>> => {
      const params = new URLSearchParams();
      if (category) params.append("category", category);
      if (includeSensitive) params.append("include_sensitive", "true");
      const queryString = params.toString();
      return this.request(
        `/system-settings${queryString ? `?${queryString}` : ""}`
      );
    },

    getConfiguration: async (
      key: string,
      includeSensitive?: boolean
    ): Promise<ApiResponse<SystemConfiguration>> => {
      const params = includeSensitive ? "?include_sensitive=true" : "";
      return this.request(
        `/system-settings/${encodeURIComponent(key)}${params}`
      );
    },

    createConfiguration: async (
      configData: SystemConfigurationCreate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      return this.request("/system-settings", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    updateConfiguration: async (
      key: string,
      configData: SystemConfigurationUpdate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      return this.request(`/system-settings/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: JSON.stringify(configData),
      });
    },

    validateConfiguration: async (
      configData: SystemConfigurationValidation
    ): Promise<ApiResponse<ConfigurationValidationResult>> => {
      return this.request("/system-settings/validate", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    deleteConfiguration: async (
      key: string
    ): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/system-settings/${encodeURIComponent(key)}`, {
        method: "DELETE",
      });
    },

    getCategories: async (): Promise<ApiResponse<string[]>> => {
      return this.request("/system-settings/categories");
    },

    getDataTypes: async (): Promise<ApiResponse<string[]>> => {
      return this.request("/system-settings/data-types");
    },

    getAuditLogs: async (
      configKey: string,
      limit: number = 50
    ): Promise<ApiResponse<any[]>> => {
      return this.request(
        `/system-settings/audit-logs/${encodeURIComponent(configKey)}?limit=${limit}`
      );
    },
  };

  // Bank Verification endpoints
  bankVerification = {
    verifyBankAccount: async (
      applicationId: number
    ): Promise<ApiResponse<BankVerificationResult>> => {
      return this.request("/admin/bank-verification", {
        method: "POST",
        body: JSON.stringify({ application_id: applicationId }),
      });
    },

    verifyBankAccountsBatch: async (
      applicationIds: number[]
    ): Promise<ApiResponse<BankVerificationBatchResult>> => {
      return this.request("/admin/bank-verification/batch", {
        method: "POST",
        body: JSON.stringify({ application_ids: applicationIds }),
      });
    },
  };

  // Professor-Student Relationship endpoints
  professorStudent = {
    getProfessorStudentRelationships: async (params?: {
      professor_id?: number;
      student_id?: number;
      relationship_type?: string;
      status?: string;
      page?: number;
      size?: number;
    }): Promise<ApiResponse<ProfessorStudentRelationship[]>> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return this.request(`/professor-student${query ? `?${query}` : ""}`);
    },

    createProfessorStudentRelationship: async (
      relationshipData: ProfessorStudentRelationshipCreate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      return this.request("/professor-student", {
        method: "POST",
        body: JSON.stringify(relationshipData),
      });
    },

    updateProfessorStudentRelationship: async (
      id: number,
      relationshipData: ProfessorStudentRelationshipUpdate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      return this.request(`/professor-student/${id}`, {
        method: "PUT",
        body: JSON.stringify(relationshipData),
      });
    },

    deleteProfessorStudentRelationship: async (
      id: number
    ): Promise<ApiResponse<void>> => {
      return this.request(`/professor-student/${id}`, {
        method: "DELETE",
      });
    },
  };

  // Email Automation API
  emailAutomation = {
    getRules: async (params?: { is_active?: boolean; trigger_event?: string }): Promise<ApiResponse<any[]>> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return this.request(`/email-automation${query ? `?${query}` : ""}`);
    },

    createRule: async (ruleData: any): Promise<ApiResponse<any>> => {
      return this.request("/email-automation", {
        method: "POST",
        body: JSON.stringify(ruleData),
      });
    },

    updateRule: async (ruleId: number, ruleData: any): Promise<ApiResponse<any>> => {
      return this.request(`/email-automation/${ruleId}`, {
        method: "PUT",
        body: JSON.stringify(ruleData),
      });
    },

    deleteRule: async (ruleId: number): Promise<ApiResponse<void>> => {
      return this.request(`/email-automation/${ruleId}`, {
        method: "DELETE",
      });
    },

    toggleRule: async (ruleId: number): Promise<ApiResponse<any>> => {
      return this.request(`/email-automation/${ruleId}/toggle`, {
        method: "PATCH",
      });
    },

    getTriggerEvents: async (): Promise<ApiResponse<any[]>> => {
      return this.request("/email-automation/trigger-events");
    },
  };

  // Batch Import endpoints (College role)
  batchImport = {
    uploadData: async (
      file: File,
      scholarshipType: string,
      academicYear: number,
      semester: string
    ): Promise<
      ApiResponse<{
        batch_id: number;
        file_name: string;
        total_records: number;
        preview_data: Array<Record<string, any>>;
        validation_summary: {
          valid_count: number;
          invalid_count: number;
          warnings: string[];
          errors: Array<{
            row: number;
            field?: string;
            message: string;
          }>;
        };
      }>
    > => {
      const formData = new FormData();
      formData.append("file", file);

      return this.request("/college/batch-import/upload-data", {
        method: "POST",
        body: formData,
        headers: {}, // Let browser set Content-Type for FormData
        params: {
          scholarship_type: scholarshipType,
          academic_year: academicYear,
          semester: semester,
        },
      });
    },

    confirm: async (
      batchId: number,
      confirm: boolean = true
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_count: number;
        errors: Array<{
          row: number;
          student_id: string;
          error: string;
        }>;
        created_application_ids: number[];
      }>
    > => {
      return this.request(`/college/batch-import/${batchId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ batch_id: batchId, confirm }),
      });
    },

    updateRecord: async (
      batchId: number,
      recordIndex: number,
      updates: Record<string, any>
    ): Promise<ApiResponse<{ updated_record: Record<string, any> }>> => {
      return this.request(`/college/batch-import/${batchId}/records`, {
        method: "PATCH",
        body: JSON.stringify({ record_index: recordIndex, updates }),
      });
    },

    revalidate: async (
      batchId: number
    ): Promise<
      ApiResponse<{
        batch_id: number;
        total_records: number;
        valid_count: number;
        invalid_count: number;
        errors: Array<{
          row: number;
          field: string;
          message: string;
        }>;
      }>
    > => {
      return this.request(`/college/batch-import/${batchId}/validate`, {
        method: "POST",
      });
    },

    deleteRecord: async (
      batchId: number,
      recordIndex: number
    ): Promise<
      ApiResponse<{
        deleted_record: Record<string, any>;
        remaining_records: number;
      }>
    > => {
      return this.request(
        `/college/batch-import/${batchId}/records/${recordIndex}`,
        {
          method: "DELETE",
        }
      );
    },

    uploadDocuments: async (
      batchId: number,
      zipFile: File
    ): Promise<
      ApiResponse<{
        batch_id: number;
        total_files: number;
        matched_count: number;
        unmatched_count: number;
        error_count: number;
        results: Array<{
          student_id: string;
          file_name: string;
          document_type: string;
          status: string;
          message?: string;
          application_id?: number;
        }>;
      }>
    > => {
      const formData = new FormData();
      formData.append("file", zipFile);

      return this.request(`/college/batch-import/${batchId}/documents`, {
        method: "POST",
        body: formData,
        headers: {}, // Let browser set Content-Type for FormData
      });
    },

    getHistory: async (params?: {
      skip?: number;
      limit?: number;
      status?: string;
    }): Promise<
      ApiResponse<{
        items: Array<{
          id: number;
          file_name: string;
          importer_name?: string;
          created_at: string;
          total_records: number;
          success_count: number;
          failed_count: number;
          import_status: string;
          scholarship_type_id?: number;
          college_code: string;
          academic_year: number;
          semester: string | null;
        }>;
        total: number;
      }>
    > => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return this.request(
        `/college/batch-import/history${query ? `?${query}` : ""}`
      );
    },

    getDetails: async (
      batchId: number
    ): Promise<
      ApiResponse<{
        id: number;
        file_name: string;
        importer_name?: string;
        created_at: string;
        total_records: number;
        success_count: number;
        failed_count: number;
        import_status: string;
        scholarship_type_id?: number;
        college_code: string;
        academic_year: number;
        semester: string | null;
        validation_summary: {
          valid_count: number;
          invalid_count: number;
          warnings: string[];
          errors: Array<{
            row: number;
            field?: string;
            message: string;
          }>;
        };
        preview_data: Array<Record<string, any>>;
        processing_errors: Array<{
          row: number;
          student_id: string;
          error: string;
        }>;
      }>
    > => {
      return this.request(`/college/batch-import/${batchId}/details`);
    },

    downloadTemplate: async (scholarshipType: string): Promise<void> => {
      const token = localStorage.getItem("auth_token");
      const response = await fetch(
        `${this.baseURL}/api/v1/college/batch-import/template?scholarship_type=${encodeURIComponent(scholarshipType)}`,
        {
          method: "GET",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error("Failed to download template");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;

      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers.get("content-disposition");
      let filename = `batch_import_template_${scholarshipType}.xlsx`;
      if (contentDisposition) {
        // Match filename*=UTF-8''encoded_name (RFC 5987)
        const filenameMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/);
        if (filenameMatch) {
          filename = decodeURIComponent(filenameMatch[1].trim());
        }
      }

      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },
  };
}

// Create and export a singleton instance
export const apiClient = new ApiClient();
export default apiClient;

// Alias for backward compatibility
export const api = apiClient;
