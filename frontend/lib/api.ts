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
}

export interface ApplicationCreate {
  scholarship_type: string
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
  code: string
  name: string
  name_en?: string
  description: string
  description_en?: string
  amount: string
  currency: string
  application_start_date: string
  application_end_date: string
  eligible_sub_types: string[]
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
  rule_name: string
  rule_type: string
  condition_field: string
  operator: string
  expected_value: string
  error_message: string
  error_message_en: string
  is_required: boolean
  weight: number
  priority: number
  is_active: boolean
  created_at: string
  updated_at: string
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

export interface ScholarshipRule {
  id: string
  name: string
  type: string
  criteria: Record<string, any>
  active: boolean
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
      console.log(`Making API request: ${options.method || 'GET'} ${url}`)
      if (options.params) {
        console.log('Query parameters:', options.params)
      }
      const response = await fetch(url, config)
      
      // Log response details for debugging
      console.log(`Response status: ${response.status} ${response.statusText}`)
      console.log(`Response headers:`, Object.fromEntries(response.headers.entries()))
      
      let data: any
      const contentType = response.headers.get('content-type')
      
      if (contentType && contentType.includes('application/json')) {
        data = await response.json()
        console.log('Response data:', data)
      } else {
        const text = await response.text()
        console.log('Non-JSON response:', text)
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
        }
        
        throw new Error(data.message || data.detail || `HTTP error! status: ${response.status}`)
      }

      console.log(`API request successful: ${options.method || 'GET'} ${url}`)
      
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
    getScholarshipRules: async (): Promise<ApiResponse<ScholarshipRule[]>> => {
      return this.request('/admin/scholarship-rules')
    },

    createScholarshipRule: async (rule: Omit<ScholarshipRule, 'id' | 'created_at' | 'updated_at'>): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request('/admin/scholarship-rules', {
        method: 'POST',
        body: JSON.stringify(rule),
      })
    },

    updateScholarshipRule: async (id: string, rule: Partial<ScholarshipRule>): Promise<ApiResponse<ScholarshipRule>> => {
      return this.request(`/admin/scholarship-rules/${id}`, {
        method: 'PUT',
        body: JSON.stringify(rule),
      })
    },

    deleteScholarshipRule: async (id: string): Promise<ApiResponse<{ message: string }>> => {
      return this.request(`/admin/scholarship-rules/${id}`, {
        method: 'DELETE',
      })
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

    // 獲取 ScholarshipConfiguration 中實際配置的學期
    getAvailableSemesters: async (scholarshipCode?: string): Promise<ApiResponse<string[]>> => {
      const params = scholarshipCode ? `?scholarship_code=${encodeURIComponent(scholarshipCode)}` : ''
      return this.request(`/scholarship-configurations/available-semesters${params}`)
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
}

// Create and export a singleton instance
export const apiClient = new ApiClient()
export default apiClient

// Alias for backward compatibility
export const api = apiClient 