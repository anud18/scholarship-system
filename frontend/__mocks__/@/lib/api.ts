// Mock API client for testing - matches the structure from lib/api.ts
const createMockFn = () => jest.fn()

// Export mutable mock functions
export const mockRequest = jest.fn().mockResolvedValue({ success: true, data: [], message: 'Mock request' })
export const mockGetMockUsers = jest.fn().mockResolvedValue({ success: true, data: [], message: 'Mock users' })
export const mockMockSSOLogin = jest.fn().mockResolvedValue({ success: true, data: { access_token: 'mock-token' }, message: 'Mock login' })

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

export default apiClient 