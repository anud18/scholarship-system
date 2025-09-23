// Mock API client for testing - matches the structure from lib/api.ts
const createMockFn = () => jest.fn()

// Export mutable mock functions
export const mockRequest = jest.fn().mockResolvedValue({ success: true, data: [], message: 'Mock request' })
export const mockGetMockUsers = jest.fn().mockResolvedValue({ success: true, data: [], message: 'Mock users' })
export const mockMockSSOLogin = jest.fn().mockResolvedValue({ success: true, data: { access_token: 'mock-token' }, message: 'Mock login' })

export const mockGetEligible = jest.fn().mockResolvedValue({
  success: true,
  data: [
    {
      id: 1,
      code: 'academic_excellence',
      name: 'Academic Excellence Scholarship',
      name_zh: '學術優秀獎學金',
      category: 'undergraduate',
      academic_year: '113',
      semester: 'first',
      amount: 50000,
      description: 'For students with excellent academic performance',
      description_zh: '優秀學術表現學生獎學金',
      requirements: {
        gpa: 3.5,
        credits: 12
      },
      is_active: true
    }
  ]
})

export const apiClient = {
  auth: {
    getCurrentUser: createMockFn(),
    login: createMockFn(),
    register: createMockFn(),
    refreshToken: createMockFn(),
    getMockUsers: mockGetMockUsers,
    mockSSOLogin: mockMockSSOLogin,
  },
  users: {
    updateProfile: createMockFn(),
    getProfile: createMockFn(),
    getStudentInfo: createMockFn(),
    updateStudentInfo: createMockFn(),
  },
  applications: {
    getMyApplications: createMockFn(),
    createApplication: createMockFn(),
    getApplication: createMockFn(),
    updateApplication: createMockFn(),
    submitApplication: createMockFn(),
    withdrawApplication: createMockFn(),
    uploadDocument: createMockFn(),
  },
  scholarships: {
    getEligible: mockGetEligible,
    getById: createMockFn(),
    getAll: createMockFn(),
  },
  admin: {
    getDashboardStats: createMockFn(),
    getAllApplications: createMockFn(),
    updateApplicationStatus: createMockFn(),
    getMyScholarships: createMockFn(),
  },
  request: mockRequest,
  setToken: createMockFn(),
  clearToken: createMockFn(),
}

export const api = apiClient

export default apiClient 