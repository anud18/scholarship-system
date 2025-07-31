// Mock API client for Jest tests
export const apiClient = {
  auth: {
    login: jest.fn().mockResolvedValue({ success: true, data: { access_token: 'mock-token', token_type: 'Bearer' }, message: 'Mock login' }),
    getCurrentUser: jest.fn().mockResolvedValue({ success: true, data: { id: '1', name: 'Test User', email: 'test@example.com' }, message: 'Mock user' }),
    register: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock register' }),
    refreshToken: jest.fn().mockResolvedValue({ success: true, data: { access_token: 'new-token' }, message: 'Mock refresh' }),
  },
  users: {
    getProfile: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock profile' }),
    updateProfile: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock update' }),
    getStudentInfo: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock student info' }),
    updateStudentInfo: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock student update' }),
  },
  applications: {
    getMyApplications: jest.fn().mockResolvedValue({ success: true, data: [], message: 'Mock applications' }),
    createApplication: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock create' }),
    getApplication: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock get application' }),
    updateApplication: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock update application' }),
    submitApplication: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock submit' }),
    withdrawApplication: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock withdraw' }),
    uploadDocument: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock upload' }),
  },
  admin: {
    getDashboardStats: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock stats' }),
    getAllApplications: jest.fn().mockResolvedValue({ success: true, data: [], message: 'Mock admin applications' }),
    updateApplicationStatus: jest.fn().mockResolvedValue({ success: true, data: null, message: 'Mock status update' }),
  },
  setToken: jest.fn(),
  clearToken: jest.fn(),
}

export default apiClient

// Re-export types and interfaces from the actual API module
export interface ApiResponse<T> {
  success: boolean
  message: string
  data?: T
  errors?: string[]
  trace_id?: string
}

export interface User {
  id: string
  nycu_id: string
  email: string
  name: string
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
  username?: string
  full_name?: string
  is_active?: boolean
}

export interface Application {
  id: number
  student_id: string
  scholarship_type: string
  status: 'draft' | 'submitted' | 'under_review' | 'approved' | 'rejected' | 'withdrawn'
  personal_statement: string
  gpa_requirement_met: boolean
  submitted_at?: string
  reviewed_at?: string
  approved_at?: string
  created_at: string
  updated_at: string
} 