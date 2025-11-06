/**
 * Shared API types for the scholarship management system
 *
 * This file contains common types used across all API modules,
 * extracted from api.legacy.ts as part of OpenAPI migration.
 */

/**
 * Standard API response format
 * All backend endpoints return responses in this format
 */
export interface ApiResponse<T> {
  success: boolean;
  message: string;
  data?: T;
  errors?: string[];
  trace_id?: string;
}

/**
 * Paginated response wrapper
 * Used for endpoints that return paginated data
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/**
 * User interface
 * Represents a system user (student, professor, admin, etc.)
 */
export interface User {
  id: string;
  nycu_id: string;
  email: string;
  name: string;
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
  // Backward compatibility fields
  username?: string; // Maps to nycu_id
  full_name?: string; // Maps to name
  is_active?: boolean; // All users are considered active
}

/**
 * Student interface
 * Represents student-specific information
 */
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

/**
 * Student info response from API
 * Contains student data and semester information
 */
export interface StudentInfoResponse {
  student: Record<string, any>;
  semesters: Array<Record<string, any>>;
}

/**
 * Application file attachment
 */
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

/**
 * Application status enum
 */
export type ApplicationStatus =
  | "draft"
  | "submitted"
  | "pending_review"
  | "under_review"
  | "professor_review_pending"
  | "professor_reviewed"
  | "college_review_pending"
  | "college_reviewed"
  | "approved"
  | "rejected"
  | "returned"
  | "withdrawn"
  | "cancelled"
  | "pending"
  | "completed"
  | "deleted";

/**
 * Scholarship application
 */
export interface Application {
  id: number;
  app_id?: string;
  student_id: string;
  scholarship_type: string;
  scholarship_type_zh?: string;
  status: ApplicationStatus;
  is_renewal?: boolean;
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
  form_data?: Record<string, any>;
  submitted_form_data?: Record<string, any>;
  meta_data?: Record<string, any>;
  student_data?: Record<string, any>;
  user_id?: number;
  scholarship_type_id?: number;
  scholarship_name?: string;
  amount?: number;
  status_name?: string;
  status_zh?: string;
  student_name?: string;
  student_no?: string;
  student_termcount?: number;
  gpa?: number;
  department?: string;
  nationality?: string;
  class_ranking_percent?: number;
  dept_ranking_percent?: number;
  days_waiting?: number;
  scholarship_subtype_list?: string[];
  sub_type_labels?: Record<string, { zh: string; en: string }>;
  agree_terms?: boolean;
  academy_code?: string;
  department_code?: string;
  scholarship_period_status?: number;
  scholarship_period_gpa?: number;
  user?: User;
  student?: Student;
  scholarship?: ScholarshipType;
  professor_id?: number | string;
  professor?: {
    id: number;
    nycu_id: string;
    name: string;
    email: string;
    dept_name?: string;
  };
  scholarship_configuration?: {
    requires_professor_recommendation: boolean;
    requires_college_review: boolean;
    config_name: string;
  };
  academic_year?: number;
  semester?: string | null;
}

/**
 * Scholarship type/configuration
 */
export interface ScholarshipType {
  id: number;
  configuration_id?: number;
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

/**
 * Whitelist student info
 */
export interface WhitelistStudentInfo {
  student_id: number | null;
  nycu_id: string;
  name: string | null;
  sub_type: string;
  note?: string | null;
  is_registered?: boolean;
}

/**
 * Whitelist response
 */
export interface WhitelistResponse {
  sub_type: string;
  students: WhitelistStudentInfo[];
  total: number;
}


// ============================================
// Additional types for backward compatibility
// ============================================

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

/**
 * User Creation Schema
 * Note: System uses SSO-only authentication via NYCU Portal
 * No password field - authentication is handled externally
 */
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
