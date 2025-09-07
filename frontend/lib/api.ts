/**
 * API client for scholarship management system
 * Follows backend camelCase endpoint naming conventions
 */

import { ScholarshipCategory } from '@/types/scholarship'

export interface ApiResponse<T> {
  success: boolean
  message: string
  data?: T
  errors?: string[]
  trace_id?: string
}

export interface User {
  id: string
  nycu_id: string  // 改為 nycu_id
  email: string
  name: string  // 改為 name
  role: 'student' | 'professor' | 'college' | 'admin' | 'super_admin'
  user_type?: 'student' | 'employee'
  status?: '在學' | '畢業' | '在職' | '退休'
  dept_code?: string
  dept_name?: string
  comment?: string
  last_login_at?: string
  created_at: string
  updated_at: string
  raw_data?: {
    chinese_name?: string
    english_name?: string
    [key: string]: any
  }
  // 向後相容性欄位
  username?: string  // 映射到 nycu_id
  full_name?: string  // 映射到 name
  is_active?: boolean  // 所有用戶都視為活躍
}

export interface Student {
  id: string
  user_id: string
  student_id: string
  student_type: 'undergraduate' | 'graduate' | 'phd'
  department: string
  gpa: number
  nationality: string
  phone_number?: string
  address?: string
  bank_account?: string
  created_at: string
  updated_at: string
}

export interface ApplicationFile {
  id: number
  filename: string
  original_filename?: string
  file_size?: number
  mime_type?: string
  file_type: string
  file_path?: string
  is_verified?: boolean
  uploaded_at: string
}

export interface Application {
  id: number
  app_id?: string  // 申請編號，格式如 APP-2025-000001
  student_id: string
  scholarship_type: string
  scholarship_type_zh?: string  // 中文獎學金類型名稱
  status: 'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'withdrawn'
  is_renewal?: boolean  // 是否為續領申請
  personal_statement?: string
  gpa_requirement_met: boolean
  submitted_at?: string
  reviewed_at?: string
  approved_at?: string
  created_at: string
  updated_at: string
  
  // 動態表單資料
  form_data?: Record<string, any>  // 動態表單資料 (前端格式)
  submitted_form_data?: Record<string, any>  // 後端格式的表單資料，包含整合後的文件資訊
  meta_data?: Record<string, any>  // 額外的元資料
  
  // 後端 ApplicationResponse 實際返回的欄位
  user_id?: number
  scholarship_type_id?: number  // 主獎學金ID
  scholarship_name?: string
  amount?: number
  status_name?: string
  student_name?: string
  student_no?: string
  gpa?: number
  department?: string
  nationality?: string
  class_ranking_percent?: number
  dept_ranking_percent?: number
  days_waiting?: number
  scholarship_subtype_list?: string[]
  agree_terms?: boolean  // 同意條款
  
  // Extended properties for dashboard display (保留向後兼容)
  user?: User  // 關聯的使用者資訊
  student?: Student  // 關聯的學生資訊
  scholarship?: ScholarshipType  // 關聯的獎學金資訊
  
  // Professor assignment fields
  professor_id?: number | string  // 指導教授ID
  professor?: {
    id: number
    nycu_id: string
    name: string
    email: string
  }  // 關聯的教授資訊
  
  // Scholarship configuration
  scholarship_configuration?: {
    requires_professor_recommendation: boolean
    requires_college_review: boolean
    config_name: string
  }  // 獎學金配置資訊
}

export interface ApplicationCreate {
  scholarship_type: string
  configuration_id: number  // Required: ID from eligible scholarships
  scholarship_subtype_list?: string[]
  form_data: {
    fields: Record<string, {
      field_id: string
      field_type: string
      value: string
      required: boolean
    }>
    documents: Array<{
      document_id: string
      document_type: string
      file_path: string
      original_filename: string
      upload_time: string
    }>
  }
  agree_terms?: boolean
  is_renewal?: boolean  // 是否為續領申請
  [key: string]: any  // 允許動態欄位
}

export interface DashboardStats {
  total_applications: number
  pending_review: number
  approved: number
  rejected: number
  avg_processing_time: string
}

export interface EmailTemplate {
  key: string
  subject_template: string
  body_template: string
  cc?: string | null
  bcc?: string | null
  updated_at?: string | null
}

export interface SystemSetting {
  key: string
  value: string
}

export interface AnnouncementCreate {
  title: string
  title_en?: string
  message: string
  message_en?: string
  notification_type?: 'info' | 'warning' | 'error' | 'success' | 'reminder'
  priority?: 'low' | 'normal' | 'high' | 'urgent'
  action_url?: string
  expires_at?: string
  metadata?: Record<string, any>
}

export interface AnnouncementUpdate {
  title?: string
  title_en?: string
  message?: string
  message_en?: string
  notification_type?: 'info' | 'warning' | 'error' | 'success' | 'reminder'
  priority?: 'low' | 'normal' | 'high' | 'urgent'
  action_url?: string
  expires_at?: string
  metadata?: Record<string, any>
  is_dismissed?: boolean
}

export interface NotificationResponse {
  id: number
  title: string
  title_en?: string
  message: string
  message_en?: string
  notification_type: string
  priority: string
  related_resource_type?: string
  related_resource_id?: number
  action_url?: string
  is_read: boolean
  is_dismissed: boolean
  scheduled_at?: string
  expires_at?: string
  read_at?: string
  created_at: string
  metadata?: Record<string, any>
}

export interface ScholarshipType {
  id: number
  configuration_id: number  // ID of the specific configuration this eligibility is for
  code: string
  name: string
  name_en?: string
  description: string
  description_en?: string
  amount: string
  currency: string
  application_cycle: 'semester' | 'yearly'
  application_start_date: string
  application_end_date: string
  sub_type_selection_mode: 'single' | 'multiple' | 'hierarchical'
  eligible_sub_types: Array<{
    value: string | null
    label: string
    label_en: string
    is_default: boolean
  }>
  passed: Array<{
    rule_id: number
    rule_name: string
    rule_type: string
    tag: string
    message: string
    message_en: string
    sub_type: string | null
    priority: number
    is_warning: boolean
    is_hard_rule: boolean
  }>
  warnings: Array<{
    rule_id: number
    rule_name: string
    rule_type: string
    tag: string
    message: string
    message_en: string
    sub_type: string | null
    priority: number
    is_warning: boolean
    is_hard_rule: boolean
  }>
  errors: Array<{
    rule_id: number
    rule_name: string
    rule_type: string
    tag: string
    message: string
    message_en: string
    sub_type: string | null
    priority: number
    is_warning: boolean
    is_hard_rule: boolean
  }>
  created_at: string
}

export interface ScholarshipRule {
  id: number
  scholarship_type_id: number
  sub_type?: string
  academic_year?: number
  semester?: string
  is_template?: boolean
  template_name?: string
  template_description?: string
  rule_name: string
  rule_type: string
  tag?: string
  description?: string
  condition_field: string
  operator: string
  expected_value: string
  message?: string
  message_en?: string
  is_hard_rule: boolean
  is_warning: boolean
  priority: number
  is_active: boolean
  is_initial_enabled: boolean   // 初領是否啟用
  is_renewal_enabled: boolean   // 續領是否啟用
  created_by?: number
  updated_by?: number
  academic_period_label?: string
  created_at: string
  updated_at: string
}

export interface SubTypeOption {
  value: string | null
  label: string
  label_en: string
  is_default: boolean
}

// User management types
export interface UserListResponse {
  id: number
  nycu_id: string
  email: string
  name: string
  user_type?: string
  status?: string
  dept_code?: string
  dept_name?: string
  role: string
  comment?: string
  created_at: string
  updated_at?: string
  last_login_at?: string
  raw_data?: {
    chinese_name?: string
    english_name?: string
    [key: string]: any
  }
  // 向後相容性欄位
  username?: string
  full_name?: string
  chinese_name?: string
  english_name?: string
  is_active?: boolean
  is_verified?: boolean
  student_no?: string
}

export interface UserResponse {
  id: number
  nycu_id: string
  email: string
  name: string
  user_type?: string
  status?: string
  dept_code?: string
  dept_name?: string
  role: string
  comment?: string
  created_at: string
  updated_at?: string
  last_login_at?: string
  raw_data?: {
    chinese_name?: string
    english_name?: string
    [key: string]: any
  }
  // 向後相容性欄位
  username?: string
  full_name?: string
  chinese_name?: string
  english_name?: string
  is_active?: boolean
  is_verified?: boolean
  student_no?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export interface UserCreate {
  nycu_id: string
  email: string
  name: string
  user_type?: 'student' | 'employee'
  status?: '在學' | '畢業' | '在職' | '退休'
  dept_code?: string
  dept_name?: string
  role: "student" | "professor" | "college" | "admin" | "super_admin"
  comment?: string
  raw_data?: {
    chinese_name?: string
    english_name?: string
    [key: string]: any
  }
  // 向後相容性欄位
  username?: string
  full_name?: string
  chinese_name?: string
  english_name?: string
  password?: string  // 不再需要，但保留向後相容性
  student_no?: string
  is_active?: boolean
}

export interface UserUpdate {
  nycu_id?: string
  email?: string
  name?: string
  user_type?: 'student' | 'employee'
  status?: '在學' | '畢業' | '在職' | '退休'
  dept_code?: string
  dept_name?: string
  role?: "student" | "professor" | "college" | "admin" | "super_admin"
  comment?: string
  raw_data?: {
    chinese_name?: string
    english_name?: string
    [key: string]: any
  }
  // 向後相容性欄位
  username?: string
  full_name?: string
  chinese_name?: string
  english_name?: string
  is_active?: boolean
  is_verified?: boolean
  student_no?: string
}

export interface UserStats {
  total_users: number
  role_distribution: Record<string, number>
  active_users: number
  inactive_users: number
  recent_registrations: number
}

// Application Fields Configuration interfaces
export interface ApplicationField {
  id: number
  scholarship_type: string
  field_name: string
  field_label: string
  field_label_en?: string
  field_type: string
  is_required: boolean
  placeholder?: string
  placeholder_en?: string
  max_length?: number
  min_value?: number
  max_value?: number
  step_value?: number
  field_options?: Array<{value: string, label: string, label_en?: string}>
  display_order: number
  is_active: boolean
  help_text?: string
  help_text_en?: string
  validation_rules?: Record<string, any>
  conditional_rules?: Record<string, any>
  created_at: string
  updated_at: string
  created_by?: number
  updated_by?: number
  // Fixed field properties
  is_fixed?: boolean
  prefill_value?: string
  bank_code?: string
  existing_file_url?: string
}

export interface ApplicationFieldCreate {
  scholarship_type: string
  field_name: string
  field_label: string
  field_label_en?: string
  field_type: string
  is_required?: boolean
  placeholder?: string
  placeholder_en?: string
  max_length?: number
  min_value?: number
  max_value?: number
  step_value?: number
  field_options?: Array<{value: string, label: string, label_en?: string}>
  display_order?: number
  is_active?: boolean
  help_text?: string
  help_text_en?: string
  validation_rules?: Record<string, any>
  conditional_rules?: Record<string, any>
}

export interface ApplicationFieldUpdate {
  field_label?: string
  field_label_en?: string
  field_type?: string
  is_required?: boolean
  placeholder?: string
  placeholder_en?: string
  max_length?: number
  min_value?: number
  max_value?: number
  step_value?: number
  field_options?: Array<{value: string, label: string, label_en?: string}>
  display_order?: number
  is_active?: boolean
  help_text?: string
  help_text_en?: string
  validation_rules?: Record<string, any>
  conditional_rules?: Record<string, any>
}

export interface ApplicationDocument {
  id: number
  scholarship_type: string
  document_name: string
  document_name_en?: string
  description?: string
  description_en?: string
  is_required: boolean
  accepted_file_types: string[]
  max_file_size: string
  max_file_count: number
  display_order: number
  is_active: boolean
  upload_instructions?: string
  upload_instructions_en?: string
  validation_rules?: Record<string, any>
  created_at: string
  updated_at: string
  created_by?: number
  updated_by?: number
  // Fixed document properties
  is_fixed?: boolean
  existing_file_url?: string
}

export interface ApplicationDocumentCreate {
  scholarship_type: string
  document_name: string
  document_name_en?: string
  description?: string
  description_en?: string
  is_required?: boolean
  accepted_file_types?: string[]
  max_file_size?: string
  max_file_count?: number
  display_order?: number
  is_active?: boolean
  upload_instructions?: string
  upload_instructions_en?: string
  validation_rules?: Record<string, any>
}

export interface ApplicationDocumentUpdate {
  document_name?: string
  document_name_en?: string
  description?: string
  description_en?: string
  is_required?: boolean
  accepted_file_types?: string[]
  max_file_size?: string
  max_file_count?: number
  display_order?: number
  is_active?: boolean
  upload_instructions?: string
  upload_instructions_en?: string
  validation_rules?: Record<string, any>
}

export interface ScholarshipFormConfig {
  scholarship_type: string
  fields: ApplicationField[]
  documents: ApplicationDocument[]
}

export interface FormConfigSaveRequest {
  fields: Array<{
    field_name: string
    field_label: string
    field_label_en?: string
    field_type: string
    is_required?: boolean
    placeholder?: string
    placeholder_en?: string
    max_length?: number
    min_value?: number
    max_value?: number
    step_value?: number
    field_options?: Array<{value: string, label: string, label_en?: string}>
    display_order?: number
    is_active?: boolean
    help_text?: string
    help_text_en?: string
    validation_rules?: Record<string, any>
    conditional_rules?: Record<string, any>
  }>
  documents: Array<{
    document_name: string
    document_name_en?: string
    description?: string
    description_en?: string
    is_required?: boolean
    accepted_file_types?: string[]
    max_file_size?: string
    max_file_count?: number
    display_order?: number
    is_active?: boolean
    upload_instructions?: string
    upload_instructions_en?: string
    validation_rules?: Record<string, any>
  }>
}

export interface ScholarshipStats {
  id: number
  name: string
  name_en?: string
  total_applications: number
  pending_review: number
  avg_wait_days: number
  sub_types: string[]
  has_sub_types: boolean
}

export interface SubTypeStats {
  sub_type: string
  total_applications: number
  pending_review: number
  avg_wait_days: number
}

// 新增系統管理相關介面
export interface Workflow {
  id: string
  name: string
  version: string
  status: 'active' | 'draft' | 'inactive'
  lastModified: string
  steps: number
  description?: string
  created_at: string
  updated_at: string
}


export interface SystemStats {
  totalUsers: number
  activeApplications: number
  completedReviews: number
  systemUptime: string
  avgResponseTime: string
  storageUsed: string
  pendingReviews: number
  totalScholarships: number
}

export interface ScholarshipPermission {
  id: number
  user_id: number
  scholarship_id: number
  scholarship_name: string
  scholarship_name_en?: string
  comment?: string
  created_at: string
  updated_at: string
}

export interface ScholarshipPermissionCreate {
  user_id: number
  scholarship_id: number
  comment?: string
}

export interface ScholarshipConfiguration {
  id: number
  scholarship_type_id: number
  scholarship_type_name: string
  academic_year: number
  semester: string | null
  config_name: string
  config_code: string
  description?: string
  description_en?: string
  amount: number
  currency: string
  // Quota management fields
  has_quota_limit?: boolean
  has_college_quota?: boolean
  quota_management_mode?: string
  total_quota?: number
  quotas?: Record<string, any>
  whitelist_student_ids: Record<string, number[]>
  renewal_application_start_date?: string
  renewal_application_end_date?: string
  application_start_date?: string
  application_end_date?: string
  renewal_professor_review_start?: string
  renewal_professor_review_end?: string
  renewal_college_review_start?: string
  renewal_college_review_end?: string
  requires_professor_recommendation: boolean
  professor_review_start?: string
  professor_review_end?: string
  requires_college_review: boolean
  college_review_start?: string
  college_review_end?: string
  review_deadline?: string
  is_active: boolean
  effective_start_date?: string
  effective_end_date?: string
  version: string
  created_at: string
  updated_at: string
}

export interface ScholarshipConfigurationFormData {
  scholarship_type_id: number
  academic_year: number
  semester: string | null
  config_name: string
  config_code: string
  description?: string
  description_en?: string
  amount: number
  currency?: string
  // Quota management fields
  has_quota_limit?: boolean
  has_college_quota?: boolean
  quota_management_mode?: string
  total_quota?: number
  quotas?: Record<string, any> | string
  whitelist_student_ids?: Record<string, number[]> | string
  renewal_application_start_date?: string
  renewal_application_end_date?: string
  application_start_date?: string
  application_end_date?: string
  renewal_professor_review_start?: string
  renewal_professor_review_end?: string
  renewal_college_review_start?: string
  renewal_college_review_end?: string
  requires_professor_recommendation?: boolean
  professor_review_start?: string
  professor_review_end?: string
  requires_college_review?: boolean
  college_review_start?: string
  college_review_end?: string
  review_deadline?: string
  is_active?: boolean
  effective_start_date?: string
  effective_end_date?: string
  version?: string
}

// User Profile interfaces
export interface UserProfile {
  id: number
  user_id: number
  bank_name?: string
  bank_code?: string
  bank_branch?: string
  account_number?: string
  account_holder_name?: string
  advisor_name?: string
  advisor_name_en?: string
  advisor_email?: string
  advisor_phone?: string
  advisor_department?: string
  advisor_title?: string
  preferred_email?: string
  phone_number?: string
  mobile_number?: string
  current_address?: string
  permanent_address?: string
  postal_code?: string
  emergency_contact_name?: string
  emergency_contact_relationship?: string
  emergency_contact_phone?: string
  preferred_language: string
  bio?: string
  interests?: string
  social_links?: Record<string, string>
  profile_photo_url?: string
  has_complete_bank_info: boolean
  has_advisor_info: boolean
  profile_completion_percentage: number
  created_at: string
  updated_at: string
}

export interface CompleteUserProfile {
  user_info: UserResponse
  profile: UserProfile | null
  student_info?: any
}

export interface UserProfileUpdate {
  bank_name?: string
  bank_code?: string
  bank_branch?: string
  account_number?: string
  account_holder_name?: string
  advisor_name?: string
  advisor_name_en?: string
  advisor_email?: string
  advisor_phone?: string
  advisor_department?: string
  advisor_title?: string
  preferred_email?: string
  phone_number?: string
  mobile_number?: string
  current_address?: string
  permanent_address?: string
  postal_code?: string
  emergency_contact_name?: string
  emergency_contact_relationship?: string
  emergency_contact_phone?: string
  preferred_language?: string
  bio?: string
  interests?: string
  social_links?: Record<string, string>
  privacy_settings?: Record<string, any>
  custom_fields?: Record<string, any>
}

export interface BankInfoUpdate {
  bank_name?: string
  bank_code?: string
  bank_branch?: string
  account_number?: string
  account_holder_name?: string
  change_reason?: string
}

export interface AdvisorInfoUpdate {
  advisor_name?: string
  advisor_name_en?: string
  advisor_email?: string
  advisor_phone?: string
  advisor_department?: string
  advisor_title?: string
  change_reason?: string
}

export interface ContactInfoUpdate {
  preferred_email?: string
  phone_number?: string
  mobile_number?: string
  current_address?: string
  permanent_address?: string
  postal_code?: string
  change_reason?: string
}

export interface EmergencyContactUpdate {
  emergency_contact_name?: string
  emergency_contact_relationship?: string
  emergency_contact_phone?: string
  change_reason?: string
}

export interface ProfileHistory {
  id: number
  user_id: number
  field_name: string
  old_value?: string
  new_value?: string
  change_reason?: string
  changed_at: string
}

class ApiClient {
  private baseURL: string
  private token: string | null = null

  constructor() {
    // Dynamically determine backend URL
    if (typeof window !== 'undefined') {
      // Browser environment - use current host with port 8000
      const protocol = window.location.protocol
      const hostname = window.location.hostname
      this.baseURL = process.env.NEXT_PUBLIC_API_URL || `${protocol}//${hostname}:8000`
    } else {
      // Server-side environment - use environment variable or localhost
      this.baseURL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    }
    
    // Try to get token from localStorage on client side
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('auth_token')
    }
  }

  setToken(token: string) {
    this.token = token
    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_token', token)
    }
  }

  clearToken() {
    this.token = null
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token')
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { params?: Record<string, any> } = {}
  ): Promise<ApiResponse<T>> {
    // Handle query parameters
    let url = `${this.baseURL}/api/v1${endpoint}`
    if (options.params) {
      const searchParams = new URLSearchParams()
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          searchParams.append(key, String(value))
        }
      })
      const queryString = searchParams.toString()
      if (queryString) {
        url += `?${queryString}`
      }
    }
    
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    }

    // Only set Content-Type if it's not FormData (detected by empty headers object)
    const isFormData = options.body instanceof FormData
    if (!isFormData && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json'
    }

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`
    } else {
      console.warn('No auth token available for request to:', endpoint)
    }

    // Remove params from options before passing to fetch
    const { params, ...fetchOptions } = options
    const config: RequestInit = {
      ...fetchOptions,
      headers,
    }

    try {
      const response = await fetch(url, config)
      
      
      let data: any
      const contentType = response.headers.get('content-type')
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
      } else {
        const text = await response.text()
        throw new Error(`Expected JSON response but got ${contentType}: ${text}`)
      }

      if (!response.ok) {
        console.error(`API request failed: ${response.status} ${response.statusText}`, {
          url,
          status: response.status,
          data
        })
        
        // Handle specific error codes
        if (response.status === 401) {
          console.error('Authentication failed - clearing token')
          this.clearToken()
        } else if (response.status === 403) {
          console.error('Authorization denied - user may not have proper permissions')
        } else if (response.status === 429) {
          console.warn('Rate limit exceeded - request throttled')
          // Add user-friendly rate limit message
          const rateLimitMessage = data.detail || data.message || 'Too many requests. Please wait a moment and try again.'
          throw new Error(`請稍候再試：${rateLimitMessage}`)
        }
        
        throw new Error(data.message || data.detail || `HTTP error! status: ${response.status}`)
      }

      
      // Handle different response formats from backend
      if (data && typeof data === 'object') {
        // If response already has success/message structure, return as-is
        if ('success' in data && 'message' in data) {
          return data as ApiResponse<T>
        }
        // If it's a direct object (like Application), wrap it
        else if ('id' in data) {
          return {
            success: true,
            message: 'Request completed successfully',
            data: data as T
          } as ApiResponse<T>
        }
        // If it's an array, wrap it
        else if (Array.isArray(data)) {
          return {
            success: true,
            message: 'Request completed successfully',
            data: data as T
          } as ApiResponse<T>
        }
      }
      
      return data
    } catch (error) {
      console.error('API request failed:', error)
      throw error
    }
  }

  // Authentication endpoints
  auth = {
    login: async (username: string, password: string): Promise<ApiResponse<{ access_token: string; token_type: string; expires_in: number; user: User }>> => {
      return this.request('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
    },

    register: async (userData: {
      username: string
      email: string
      password: string
      full_name: string
    }): Promise<ApiResponse<User>> => {
      return this.request('/auth/register', {
        method: 'POST',
        body: JSON.stringify(userData),
      })
    },

    getCurrentUser: async (): Promise<ApiResponse<User>> => {
      return this.request('/auth/me')
    },

    refreshToken: async (): Promise<ApiResponse<{ access_token: string; token_type: string }>> => {
      return this.request('/auth/refresh', {
        method: 'POST',
      })
    },

    // Mock SSO endpoints for development
    getMockUsers: async (): Promise<ApiResponse<any[]>> => {
      return this.request('/auth/mock-sso/users')
    },

    mockSSOLogin: async (nycu_id: string): Promise<ApiResponse<{ access_token: string; token_type: string; expires_in: number; user: User }>> => {
      return this.request('/auth/mock-sso/login', {
        method: 'POST',
        body: JSON.stringify({ nycu_id }),
      })
    },
  }

  // User management endpoints
  users = {
    getProfile: async (): Promise<ApiResponse<User>> => {
      return this.request('/users/me')
    },

    updateProfile: async (userData: Partial<User>): Promise<ApiResponse<User>> => {
      return this.request('/users/me', {
        method: 'PUT',
        body: JSON.stringify(userData),
      })
    },

    getStudentInfo: async (): Promise<ApiResponse<Student>> => {
      return this.request('/users/student-info')
    },

    updateStudentInfo: async (studentData: Partial<Student>): Promise<ApiResponse<Student>> => {
      return this.request('/users/student-info', {
        method: 'PUT',
        body: JSON.stringify(studentData),
      })
    },

    // Get all users with pagination and filters
    getAll: (params?: {
      page?: number
      size?: number
      role?: string
      search?: string
    }) => this.request<PaginatedResponse<UserListResponse>>('/users', {
      method: 'GET',
      params
    }),

    // Get user by ID
    getById: (userId: number) => this.request<UserResponse>(`/users/${userId}`, {
      method: 'GET'
    }),

    // Create new user
    create: (userData: UserCreate) => this.request<UserResponse>('/users', {
      method: 'POST',
      body: JSON.stringify(userData)
    }),

    // Update user
    update: (userId: number, userData: UserUpdate) => this.request<UserResponse>(`/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(userData)
    }),

    // Delete user (hard delete)
    delete: (userId: number) => this.request<{ success: boolean; message: string; data: { user_id: number } }>(`/users/${userId}`, {
      method: 'DELETE'
    }),

    // Reset user password (not supported in SSO model)
    resetPassword: (userId: number) => this.request<{ success: boolean; message: string; data: { user_id: number } }>(`/users/${userId}/reset-password`, {
      method: 'POST'
    }),

    // Get user statistics
    getStats: () => this.request<UserStats>('/users/stats/overview', {
      method: 'GET'
    })
  }

  // Scholarship endpoints
  scholarships = {
    getEligible: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      return this.request('/scholarships/eligible')
    },
    
    getById: async (id: number): Promise<ApiResponse<ScholarshipType>> => {
      return this.request(`/scholarships/${id}`)
    },
    
    getAll: async (): Promise<ApiResponse<any[]>> => {
      return this.request('/scholarships')
    },
    
    // Get combined scholarships
    getCombined: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      return this.request('/scholarships/combined/list')
    },
    
    // Create combined PhD scholarship
    createCombinedPhd: async (data: {
      name: string
      name_en: string
      description: string
      description_en: string
      category: ScholarshipCategory
      sub_scholarships: Array<{
        code: string
        name: string
        name_en: string
        description: string
        description_en: string
        sub_type: 'nstc' | 'moe'
        amount: number
        min_gpa?: number
        max_ranking_percent?: number
        required_documents?: string[]
        application_start_date?: string
        application_end_date?: string
      }>
    }): Promise<ApiResponse<ScholarshipType>> => {
      return this.request('/scholarships/combined/phd', {
        method: 'POST',
        body: JSON.stringify(data),
      })
    },
  }

  // Application management endpoints
  applications = {
    getMyApplications: async (status?: string): Promise<ApiResponse<Application[]>> => {
      const params = status ? `?status=${encodeURIComponent(status)}` : ''
      return this.request(`/applications/${params}`)
    },

    getCollegeReview: async (status?: string, scholarshipType?: string): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams()
      if (status) params.append('status', status)
      if (scholarshipType) params.append('scholarship_type', scholarshipType)
      
      const queryString = params.toString()
      return this.request(`/applications/college/review${queryString ? `?${queryString}` : ''}`)
    },

    getByScholarshipType: async (scholarshipType: string, status?: string): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams()
      params.append('scholarship_type', scholarshipType)
      if (status) params.append('status', status)
      
      const queryString = params.toString()
      return this.request(`/applications/review/list${queryString ? `?${queryString}` : ''}`)
    },

    createApplication: async (applicationData: ApplicationCreate, isDraft: boolean = false): Promise<ApiResponse<Application>> => {
      const url = isDraft ? '/applications/?is_draft=true' : '/applications/'
      return this.request(url, {
        method: 'POST',
        body: JSON.stringify(applicationData)
      })
    },

    getApplicationById: async (id: number): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${id}`)
    },

    updateApplication: async (id: number, applicationData: Partial<ApplicationCreate>): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${id}`, {
        method: 'PUT',
        body: JSON.stringify(applicationData)
      })
    },

    updateStatus: async (id: number, statusData: { status: string; comments?: string }): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${id}/status`, {
        method: 'PATCH',
        body: JSON.stringify(statusData)
      })
    },

    uploadFile: async (applicationId: number, file: File, fileType: string): Promise<ApiResponse<any>> => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('file_type', fileType)
      
      return this.request(`/applications/${applicationId}/files`, {
        method: 'POST',
        body: formData
      })
    },

    submitApplication: async (applicationId: number): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${applicationId}/submit`, {
        method: 'POST',
      })
    },

    deleteApplication: async (applicationId: number): Promise<ApiResponse<{ success: boolean; message: string }>> => {
      return this.request(`/applications/${applicationId}`, {
        method: 'DELETE',
      })
    },

    withdrawApplication: async (applicationId: number): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${applicationId}/withdraw`, {
        method: 'POST',
      })
    },

    uploadDocument: async (applicationId: number, file: File, fileType: string = 'other'): Promise<ApiResponse<any>> => {
      const formData = new FormData()
      formData.append('file', file)

      return this.request(`/applications/${applicationId}/files/upload?file_type=${encodeURIComponent(fileType)}`, {
        method: 'POST',
        body: formData,
        headers: {}, // Remove Content-Type to let browser set it for FormData
      })
    },

    getApplicationFiles: async (applicationId: number): Promise<ApiResponse<ApplicationFile[]>> => {
      return this.request(`/applications/${applicationId}/files`)
    },

    // 新增暫存申請功能
    saveApplicationDraft: async (applicationData: ApplicationCreate): Promise<ApiResponse<Application>> => {
      const response = await this.request('/applications/?is_draft=true', {
        method: 'POST',
        body: JSON.stringify(applicationData),
      })
      
      // Handle direct Application response vs wrapped ApiResponse
      if (response && typeof response === 'object' && 'id' in response && !('success' in response)) {
        // Direct Application object - wrap it in ApiResponse format
        return {
          success: true,
          message: 'Draft saved successfully',
          data: response as unknown as Application
        }
      }
      
      // Already in ApiResponse format
      return response as ApiResponse<Application>
    },

    submitRecommendation: async (
      applicationId: number,
      reviewStage: string,
      recommendation: string,
      selectedAwards?: string[]
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/applications/${applicationId}/review`, {
        method: 'POST',
        body: JSON.stringify({
          application_id: applicationId,
          review_stage: reviewStage,
          recommendation,
          ...(selectedAwards ? { selected_awards: selectedAwards } : {})
        }),
      });
    },
  }

  // Notification endpoints
  notifications = {
    getNotifications: async (
      skip?: number,
      limit?: number,
      unreadOnly?: boolean,
      notificationType?: string
    ): Promise<ApiResponse<NotificationResponse[]>> => {
      const params = new URLSearchParams()
      if (skip) params.append('skip', skip.toString())
      if (limit) params.append('limit', limit.toString())
      if (unreadOnly) params.append('unread_only', 'true')
      if (notificationType) params.append('notification_type', notificationType)
      
      const queryString = params.toString()
      return this.request(`/notifications${queryString ? `?${queryString}` : ''}`)
    },

    getUnreadCount: async (): Promise<ApiResponse<number>> => {
      return this.request('/notifications/unread-count')
    },

    markAsRead: async (notificationId: number): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/notifications/${notificationId}/read`, {
        method: 'PATCH',
      })
    },

    markAllAsRead: async (): Promise<ApiResponse<{ updated_count: number }>> => {
      return this.request('/notifications/mark-all-read', {
        method: 'PATCH',
      })
    },

    dismiss: async (notificationId: number): Promise<ApiResponse<{ notification_id: number }>> => {
      return this.request(`/notifications/${notificationId}/dismiss`, {
        method: 'PATCH',
      })
    },

    getNotificationDetail: async (notificationId: number): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/notifications/${notificationId}`)
    },

    // Admin-only notification endpoints
    createSystemAnnouncement: async (announcementData: AnnouncementCreate): Promise<ApiResponse<NotificationResponse>> => {
      return this.request('/notifications/admin/create-system-announcement', {
        method: 'POST',
        body: JSON.stringify(announcementData),
      })
    },

    createTestNotifications: async (): Promise<ApiResponse<{ created_count: number; notification_ids: number[] }>> => {
      return this.request('/notifications/admin/create-test-notifications', {
        method: 'POST',
      })
    },
  }

  // Admin endpoints
  admin = {
    getDashboardStats: async (): Promise<ApiResponse<DashboardStats>> => {
      return this.request('/admin/dashboard/stats')
    },

    getRecentApplications: async (limit?: number): Promise<ApiResponse<Application[]>> => {
      const params = limit ? `?limit=${limit}` : ''
      return this.request(`/admin/recent-applications${params}`)
    },

    getSystemAnnouncements: async (limit?: number): Promise<ApiResponse<NotificationResponse[]>> => {
      const params = limit ? `?limit=${limit}` : ''
      return this.request(`/admin/system-announcements${params}`)
    },

    getAllApplications: async (
      page?: number,
      size?: number,
      status?: string
    ): Promise<ApiResponse<{ items: Application[]; total: number; page: number; size: number }>> => {
      const params = new URLSearchParams()
      if (page) params.append('page', page.toString())
      if (size) params.append('size', size.toString())
      if (status) params.append('status', status)
      
      const queryString = params.toString()
      return this.request(`/admin/applications${queryString ? `?${queryString}` : ''}`)
    },

    updateApplicationStatus: async (
      applicationId: number,
      status: string,
      reviewNotes?: string
    ): Promise<ApiResponse<Application>> => {
      return this.request(`/admin/applications/${applicationId}/status`, {
        method: 'PATCH',
        body: JSON.stringify({ status, review_notes: reviewNotes }),
      })
    },

    getEmailTemplate: async (key: string): Promise<ApiResponse<EmailTemplate>> => {
      return this.request(`/admin/email-template?key=${encodeURIComponent(key)}`)
    },

    updateEmailTemplate: async (template: EmailTemplate): Promise<ApiResponse<EmailTemplate>> => {
      return this.request('/admin/email-template', {
        method: 'PUT',
        body: JSON.stringify(template),
      })
    },

    getSystemSetting: async (key: string): Promise<ApiResponse<SystemSetting>> => {
      return this.request(`/admin/system-setting?key=${encodeURIComponent(key)}`)
    },

    updateSystemSetting: async (setting: SystemSetting): Promise<ApiResponse<SystemSetting>> => {
      return this.request(`/admin/system-setting`, {
        method: 'PUT',
        body: JSON.stringify(setting),
      })
    },

    // === 系統公告管理 === //
    
    getAllAnnouncements: async (
      page?: number,
      size?: number,
      notificationType?: string,
      priority?: string
    ): Promise<ApiResponse<{ items: NotificationResponse[]; total: number; page: number; size: number }>> => {
      const params = new URLSearchParams()
      if (page) params.append('page', page.toString())
      if (size) params.append('size', size.toString())
      if (notificationType) params.append('notification_type', notificationType)
      if (priority) params.append('priority', priority)
      
      const queryString = params.toString()
      return this.request(`/admin/announcements${queryString ? `?${queryString}` : ''}`)
    },

    getAnnouncement: async (id: number): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/admin/announcements/${id}`)
    },

    createAnnouncement: async (announcementData: AnnouncementCreate): Promise<ApiResponse<NotificationResponse>> => {
      return this.request('/admin/announcements', {
        method: 'POST',
        body: JSON.stringify(announcementData),
      })
    },

    updateAnnouncement: async (id: number, announcementData: AnnouncementUpdate): Promise<ApiResponse<NotificationResponse>> => {
      return this.request(`/admin/announcements/${id}`, {
        method: 'PUT',
        body: JSON.stringify(announcementData),
      })
    },

    deleteAnnouncement: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/announcements/${id}`, {
        method: 'DELETE',
      })
    },

    // Scholarship management endpoints
    getScholarshipStats: async (): Promise<ApiResponse<Record<string, ScholarshipStats>>> => {
      return this.request('/admin/scholarships/stats')
    },

    getApplicationsByScholarship: async (
      scholarshipCode: string,
      subType?: string,
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams()
      if (subType) params.append('sub_type', subType)
      if (status) params.append('status', status)
      
      const queryString = params.toString()
      return this.request(`/admin/scholarships/${scholarshipCode}/applications${queryString ? `?${queryString}` : ''}`)
    },

    getScholarshipSubTypes: async (scholarshipCode: string): Promise<ApiResponse<SubTypeStats[]>> => {
      return this.request(`/admin/scholarships/${scholarshipCode}/sub-types`)
    },

    getSubTypeTranslations: async (): Promise<ApiResponse<Record<string, Record<string, string>>>> => {
      return this.request('/admin/scholarships/sub-type-translations')
    },

    // === 系統管理相關 API === //
    
    // 工作流程管理
    getWorkflows: async (): Promise<ApiResponse<Workflow[]>> => {
      return this.request('/admin/workflows')
    },

    createWorkflow: async (workflow: Omit<Workflow, 'id' | 'created_at' | 'updated_at'>): Promise<ApiResponse<Workflow>> => {
      return this.request('/admin/workflows', {
        method: 'POST',
        body: JSON.stringify(workflow),
      })
    },

    updateWorkflow: async (id: string, workflow: Partial<Workflow>): Promise<ApiResponse<Workflow>> => {
      return this.request(`/admin/workflows/${id}`, {
        method: 'PUT',
        body: JSON.stringify(workflow),
      })
    },

    deleteWorkflow: async (id: string): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/workflows/${id}`, {
        method: 'DELETE',
      })
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
      return this.request(`/admin/scholarship-rules${queryString ? `?${queryString}` : ''}`);
    },

    getScholarshipRule: async (id: number): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request(`/admin/scholarship-rules/${id}`);
    },

    createScholarshipRule: async (rule: Omit<ScholarshipRule, 'id' | 'created_at' | 'updated_at'>): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request('/admin/scholarship-rules', {
        method: 'POST',
        body: JSON.stringify(rule),
      })
    },

    updateScholarshipRule: async (id: number, rule: Partial<ScholarshipRule>): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request(`/admin/scholarship-rules/${id}`, {
        method: 'PUT',
        body: JSON.stringify(rule),
      })
    },

    deleteScholarshipRule: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/scholarship-rules/${id}`, {
        method: 'DELETE',
      })
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
      const response = await this.request('/admin/scholarship-rules/copy', {
        method: 'POST',
        body: JSON.stringify(copyRequest),
      });
      return response;
    },

    bulkRuleOperation: async (operation: {
      operation: string;
      rule_ids: number[];
      parameters?: Record<string, any>;
    }): Promise<ApiResponse<{ operation: string; affected_rules: number; details: string[] }>> => {
      return this.request('/admin/scholarship-rules/bulk-operation', {
        method: 'POST',
        body: JSON.stringify(operation),
      });
    },

    // 規則模板管理
    getRuleTemplates: async (scholarship_type_id?: number): Promise<ApiResponse<ScholarshipRule[]>> => {
      const queryParams = scholarship_type_id ? `?scholarship_type_id=${scholarship_type_id}` : '';
      return this.request(`/admin/scholarship-rules/templates${queryParams}`);
    },

    createRuleTemplate: async (templateRequest: {
      template_name: string;
      template_description?: string;
      scholarship_type_id: number;
      rule_ids: number[];
    }): Promise<ApiResponse<ScholarshipRule[]>> => {
      return this.request('/admin/scholarship-rules/create-template', {
        method: 'POST',
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
      return this.request('/admin/scholarship-rules/apply-template', {
        method: 'POST',
        body: JSON.stringify(templateRequest),
      });
    },

    deleteRuleTemplate: async (templateName: string, scholarshipTypeId: number): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/scholarship-rules/templates/${encodeURIComponent(templateName)}?scholarship_type_id=${scholarshipTypeId}`, {
        method: 'DELETE',
      });
    },

    // Get available sub-types for a scholarship type
    getScholarshipRuleSubTypes: async (scholarshipTypeId: number): Promise<ApiResponse<SubTypeOption[]>> => {
      return this.request(`/scholarship-rules/scholarship-types/${scholarshipTypeId}/sub-types`);
    },

    // 系統統計
    getSystemStats: async (): Promise<ApiResponse<SystemStats>> => {
      return this.request('/admin/system-stats')
    },

    // 獎學金權限管理
    getScholarshipPermissions: async (userId?: number): Promise<ApiResponse<ScholarshipPermission[]>> => {
      const params = userId ? `?user_id=${userId}` : ''
      return this.request(`/admin/scholarship-permissions${params}`)
    },

    // 獲取當前用戶的獎學金權限
    getCurrentUserScholarshipPermissions: async (): Promise<ApiResponse<ScholarshipPermission[]>> => {
      return this.request('/admin/scholarship-permissions/current-user')
    },

    createScholarshipPermission: async (permission: ScholarshipPermissionCreate): Promise<ApiResponse<ScholarshipPermission>> => {
      return this.request('/admin/scholarship-permissions', {
        method: 'POST',
        body: JSON.stringify(permission),
      })
    },

    updateScholarshipPermission: async (id: number, permission: Partial<ScholarshipPermissionCreate>): Promise<ApiResponse<ScholarshipPermission>> => {
      return this.request(`/admin/scholarship-permissions/${id}`, {
        method: 'PUT',
        body: JSON.stringify(permission),
      })
    },

    deleteScholarshipPermission: async (id: number): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/scholarship-permissions/${id}`, {
        method: 'DELETE',
      })
    },

    // 獲取所有獎學金列表（用於權限管理）
    getAllScholarshipsForPermissions: async (): Promise<ApiResponse<Array<{ id: number; name: string; name_en?: string; code: string }>>> => {
      return this.request('/admin/scholarships/all-for-permissions')
    },

    // 獲取當前用戶有權限管理的獎學金列表
    getMyScholarships: async (): Promise<ApiResponse<Array<{ 
      id: number; 
      name: string; 
      name_en?: string; 
      code: string;
      category?: string;
      application_cycle?: string;
      status?: string;
    }>>> => {
      return this.request('/admin/scholarships/my-scholarships')
    },

    // 獲取 ScholarshipConfiguration 中實際配置的學期
    getAvailableSemesters: async (scholarshipCode?: string): Promise<ApiResponse<string[]>> => {
      const params = scholarshipCode ? `?scholarship_code=${encodeURIComponent(scholarshipCode)}` : ''
      return this.request(`/scholarship-configurations/available-semesters${params}`)
    },

    // 獲取可用年份
    getAvailableYears: async (): Promise<ApiResponse<number[]>> => {
      return this.request('/admin/scholarships/available-years')
    },

    // Scholarship Configuration Management
    getScholarshipConfigTypes: async (): Promise<ApiResponse<any[]>> => {
      return this.request('/scholarship-configurations/scholarship-types')
    },
    getScholarshipConfigurations: async (params?: {
      scholarship_type_id?: number;
      academic_year?: number;
      semester?: string;
      is_active?: boolean;
    }): Promise<ApiResponse<ScholarshipConfiguration[]>> => {
      const queryParams = new URLSearchParams()
      if (params?.scholarship_type_id) queryParams.append('scholarship_type_id', params.scholarship_type_id.toString())
      if (params?.academic_year) queryParams.append('academic_year', params.academic_year.toString())
      if (params?.semester) queryParams.append('semester', params.semester)
      if (params?.is_active !== undefined) queryParams.append('is_active', params.is_active.toString())
      
      const queryString = queryParams.toString()
      return this.request(`/scholarship-configurations/configurations/${queryString ? `?${queryString}` : ''}`)
    },
    getScholarshipConfiguration: async (id: number): Promise<ApiResponse<ScholarshipConfiguration>> => {
      return this.request(`/scholarship-configurations/configurations/${id}`)
    },
    createScholarshipConfiguration: async (configData: ScholarshipConfigurationFormData): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request('/scholarship-configurations/configurations/', {
        method: 'POST',
        body: JSON.stringify(configData)
      })
    },
    updateScholarshipConfiguration: async (id: number, configData: Partial<ScholarshipConfigurationFormData>): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request(`/scholarship-configurations/configurations/${id}`, {
        method: 'PUT',
        body: JSON.stringify(configData)
      })
    },
    deleteScholarshipConfiguration: async (id: number): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request(`/scholarship-configurations/configurations/${id}`, {
        method: 'DELETE'
      })
    },
    duplicateScholarshipConfiguration: async (id: number, targetData: {
      academic_year: number;
      semester?: string | null;
      config_code: string;
      config_name?: string;
    }): Promise<ApiResponse<{ id: number; config_code: string }>> => {
      return this.request(`/scholarship-configurations/configurations/${id}/duplicate`, {
        method: 'POST',
        body: JSON.stringify(targetData)
      })
    },

    // Professor management endpoints
    getProfessors: async (search?: string): Promise<ApiResponse<Array<{
      nycu_id: string;
      name: string;
      dept_code: string;
      dept_name: string;
      email?: string;
    }>>> => {
      const params = search ? { search } : {}
      return this.request('/admin/professors', {
        method: 'GET',
        params
      })
    },

    assignProfessor: async (applicationId: number, professorNycuId: string): Promise<ApiResponse<Application>> => {
      return this.request(`/admin/applications/${applicationId}/assign-professor`, {
        method: 'PUT',
        body: JSON.stringify({ professor_nycu_id: professorNycuId })
      })
    },
  }

  // Application Fields Configuration
  applicationFields = {
    // Form configuration
    getFormConfig: (scholarshipType: string, includeInactive: boolean = false) => 
      this.request<ScholarshipFormConfig>(`/application-fields/form-config/${scholarshipType}?include_inactive=${includeInactive}`),
    
    saveFormConfig: (scholarshipType: string, config: FormConfigSaveRequest) => 
      this.request<ScholarshipFormConfig>(`/application-fields/form-config/${scholarshipType}`, {
        method: 'POST',
        body: JSON.stringify(config)
      }),
    
    // Fields management
    getFields: (scholarshipType: string) => 
      this.request<ApplicationField[]>(`/application-fields/fields/${scholarshipType}`),
    
    createField: (fieldData: ApplicationFieldCreate) => 
      this.request<ApplicationField>('/application-fields/fields', {
        method: 'POST',
        body: JSON.stringify(fieldData)
      }),
    
    updateField: (fieldId: number, fieldData: ApplicationFieldUpdate) => 
      this.request<ApplicationField>(`/application-fields/fields/${fieldId}`, {
        method: 'PUT',
        body: JSON.stringify(fieldData)
      }),
    
    deleteField: (fieldId: number) => 
      this.request<boolean>(`/application-fields/fields/${fieldId}`, {
        method: 'DELETE'
      }),
    
    // Documents management
    getDocuments: (scholarshipType: string) => 
      this.request<ApplicationDocument[]>(`/application-fields/documents/${scholarshipType}`),
    
    createDocument: (documentData: ApplicationDocumentCreate) => 
      this.request<ApplicationDocument>('/application-fields/documents', {
        method: 'POST',
        body: JSON.stringify(documentData)
      }),
    
    updateDocument: (documentId: number, documentData: ApplicationDocumentUpdate) => 
      this.request<ApplicationDocument>(`/application-fields/documents/${documentId}`, {
        method: 'PUT',
        body: JSON.stringify(documentData)
      }),
    
    deleteDocument: (documentId: number) => 
      this.request<boolean>(`/application-fields/documents/${documentId}`, {
        method: 'DELETE'
      }),
  }

  // User Profile management endpoints
  userProfiles = {
    // Get complete user profile (read-only + editable data)
    getMyProfile: async (): Promise<ApiResponse<CompleteUserProfile>> => {
      return this.request('/user-profiles/me')
    },

    // Create user profile
    createProfile: async (profileData: UserProfileUpdate): Promise<ApiResponse<UserProfile>> => {
      return this.request('/user-profiles/me', {
        method: 'POST',
        body: JSON.stringify(profileData),
      })
    },

    // Update complete profile
    updateProfile: async (profileData: UserProfileUpdate): Promise<ApiResponse<UserProfile>> => {
      return this.request('/user-profiles/me', {
        method: 'PUT',
        body: JSON.stringify(profileData),
      })
    },

    // Update bank account information
    updateBankInfo: async (bankData: BankInfoUpdate): Promise<ApiResponse<any>> => {
      return this.request('/user-profiles/me/bank-info', {
        method: 'PUT',
        body: JSON.stringify(bankData),
      })
    },

    // Update advisor information
    updateAdvisorInfo: async (advisorData: AdvisorInfoUpdate): Promise<ApiResponse<any>> => {
      return this.request('/user-profiles/me/advisor-info', {
        method: 'PUT',
        body: JSON.stringify(advisorData),
      })
    },

    // Upload bank document (base64)
    uploadBankDocument: async (photoData: string, filename: string, contentType: string): Promise<ApiResponse<{ document_url: string }>> => {
      return this.request('/user-profiles/me/bank-document', {
        method: 'POST',
        body: JSON.stringify({
          photo_data: photoData,
          filename,
          content_type: contentType
        }),
      })
    },

    // Upload bank document (file)
    uploadBankDocumentFile: async (file: File): Promise<ApiResponse<{ document_url: string }>> => {
      const formData = new FormData()
      formData.append('file', file)
      
      return this.request('/user-profiles/me/bank-document/file', {
        method: 'POST',
        body: formData,
      })
    },

    // Delete bank document
    deleteBankDocument: async (): Promise<ApiResponse<any>> => {
      return this.request('/user-profiles/me/bank-document', {
        method: 'DELETE',
      })
    },

    // Get profile change history
    getHistory: async (): Promise<ApiResponse<ProfileHistory[]>> => {
      return this.request('/user-profiles/me/history')
    },

    // Delete entire profile
    deleteProfile: async (): Promise<ApiResponse<any>> => {
      return this.request('/user-profiles/me', {
        method: 'DELETE',
      })
    },

    // Admin endpoints
    admin: {
      // Get incomplete profiles
      getIncompleteProfiles: async (): Promise<ApiResponse<any>> => {
        return this.request('/user-profiles/admin/incomplete')
      },

      // Get user profile by ID
      getUserProfile: async (userId: number): Promise<ApiResponse<CompleteUserProfile>> => {
        return this.request(`/user-profiles/admin/${userId}`)
      },

      // Get user profile history by ID
      getUserHistory: async (userId: number): Promise<ApiResponse<ProfileHistory[]>> => {
        return this.request(`/user-profiles/admin/${userId}/history`)
      },
    }
  }

  // Reference Data endpoints
  referenceData = {
    // Get all academies/colleges
    getAcademies: async (): Promise<ApiResponse<Array<{ id: number; code: string; name: string }>>> => {
      return this.request('/reference-data/academies')
    },

    // Get all departments
    getDepartments: async (): Promise<ApiResponse<Array<{ id: number; code: string; name: string }>>> => {
      return this.request('/reference-data/departments')
    },

    // Get all reference data in one request
    getAll: async (): Promise<ApiResponse<{
      academies: Array<{ id: number; code: string; name: string }>
      departments: Array<{ id: number; code: string; name: string }>
      degrees: Array<{ id: number; name: string }>
      identities: Array<{ id: number; name: string }>
      studying_statuses: Array<{ id: number; name: string }>
      school_identities: Array<{ id: number; name: string }>
      enroll_types: Array<{ degree_id: number; code: string; name: string; name_en?: string; degree_name?: string }>
    }>> => {
      return this.request('/reference-data/all')
    }
  }

  // Professor review endpoints
  professor = {
    // Get applications requiring professor review
    getApplications: async (statusFilter?: string): Promise<ApiResponse<Application[]>> => {
      try {
        const params = statusFilter ? `?status_filter=${statusFilter}` : '';
        console.log('🔍 Requesting professor applications with params:', params);
        
        // The /professor/applications endpoint returns PaginatedResponse directly, not wrapped in ApiResponse
        const response = await this.request<PaginatedResponse<Application>>(`/professor/applications${params}`);
        console.log('📨 Professor applications raw response:', response);
        
        // Check if response is a direct PaginatedResponse (backend returns this directly)
        if (response && 'items' in response && 'total' in response && 'pages' in response) {
          console.log('✅ Got direct PaginatedResponse:', response.items.length, 'applications, total:', response.total);
          return {
            success: true,
            message: 'Applications loaded successfully',
            data: response.items
          };
        }
        // Handle wrapped ApiResponse format (fallback for consistency)
        else if (response && 'success' in response && response.success && response.data) {
          if ('items' in response.data && Array.isArray(response.data.items)) {
            console.log('✅ Got wrapped ApiResponse with paginated data:', response.data.items.length, 'applications');
            return {
              success: true,
              message: response.message || 'Applications loaded successfully',
              data: response.data.items
            };
          }
        }
        
        // Handle error or unexpected response format
        console.warn('⚠️ Unexpected response format:', response);
        return {
          success: false,
          message: 'Failed to load applications - unexpected response format',
          data: []
        };
      } catch (error: any) {
        console.error('❌ Error in professor.getApplications:', error);
        return {
          success: false,
          message: error.message || 'Failed to load applications',
          data: []
        };
      }
    },

    // Get existing professor review for an application
    getReview: async (applicationId: number): Promise<ApiResponse<any>> => {
      return this.request(`/professor/applications/${applicationId}/review`);
    },

    // Submit professor review for an application
    submitReview: async (applicationId: number, reviewData: {
      recommendation?: string;
      items: Array<{
        sub_type_code: string;
        is_recommended: boolean;
        comments?: string;
      }>;
    }): Promise<ApiResponse<any>> => {
      return this.request(`/professor/applications/${applicationId}/review`, {
        method: 'POST',
        body: JSON.stringify(reviewData),
      });
    },

    // Update existing professor review
    updateReview: async (applicationId: number, reviewId: number, reviewData: {
      recommendation?: string;
      items: Array<{
        sub_type_code: string;
        is_recommended: boolean;
        comments?: string;
      }>;
    }): Promise<ApiResponse<any>> => {
      return this.request(`/professor/applications/${applicationId}/review/${reviewId}`, {
        method: 'PUT',
        body: JSON.stringify(reviewData),
      });
    },

    // Get available sub-types for an application
    getSubTypes: async (applicationId: number): Promise<ApiResponse<Array<{
      value: string;
      label: string;
      label_en: string;
      is_default: boolean;
    }>>> => {
      return this.request(`/professor/applications/${applicationId}/sub-types`);
    },

    // Get basic review statistics
    getStats: async (): Promise<ApiResponse<{
      pending_reviews: number;
      completed_reviews: number;
      overdue_reviews: number;
    }>> => {
      return this.request('/professor/stats');
    }
  }

  // College Review endpoints
  college = {
    // Get rankings list
    getRankings: async (academicYear?: number, semester?: string): Promise<ApiResponse<any[]>> => {
      const params = new URLSearchParams()
      if (academicYear) params.append('academic_year', academicYear.toString())
      if (semester) params.append('semester', semester)
      return this.request(`/college/rankings${params.toString() ? `?${params.toString()}` : ''}`)
    },
    
    // Get ranking details
    getRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}`)
    },
    
    // Create new ranking
    createRanking: async (data: {
      scholarship_type_id: number;
      sub_type_code: string;
      academic_year: number;
      semester?: string;
      ranking_name?: string;
    }): Promise<ApiResponse<any>> => {
      return this.request('/college/rankings', {
        method: 'POST',
        body: JSON.stringify(data)
      })
    },
    
    // Update ranking order
    updateRankingOrder: async (rankingId: number, newOrder: Array<{item_id: number, position: number}>): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}/order`, {
        method: 'PUT',
        body: JSON.stringify(newOrder)
      })
    },
    
    // Execute distribution
    executeDistribution: async (rankingId: number, distributionRules?: any): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}/distribute`, {
        method: 'POST',
        body: JSON.stringify({ distribution_rules: distributionRules })
      })
    },
    
    // Finalize ranking
    finalizeRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      return this.request(`/college/rankings/${rankingId}/finalize`, {
        method: 'POST'
      })
    },
    
    // Get quota status
    getQuotaStatus: async (scholarshipTypeId: number, academicYear: number, semester?: string): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams({
        scholarship_type_id: scholarshipTypeId.toString(),
        academic_year: academicYear.toString()
      })
      if (semester) params.append('semester', semester)
      return this.request(`/college/quota-status?${params.toString()}`)
    },
    
    // Get college review statistics
    getStatistics: async (academicYear?: number, semester?: string): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams()
      if (academicYear) params.append('academic_year', academicYear.toString())
      if (semester) params.append('semester', semester)
      return this.request(`/college/statistics${params.toString() ? `?${params.toString()}` : ''}`)
    }
  }
}

// Create and export a singleton instance
export const apiClient = new ApiClient()
export default apiClient

// Alias for backward compatibility
export const api = apiClient 