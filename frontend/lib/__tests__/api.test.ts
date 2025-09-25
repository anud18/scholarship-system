import { apiClient } from '../api'

// Mock fetch
const mockFetch = jest.fn()
global.fetch = mockFetch

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
}
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage
})

function getHeader(headers: any, name: string): string | null {
  if (headers instanceof Headers) {
    return headers.get(name)
  } else if (headers && typeof headers === 'object') {
    return headers[name] || headers[name.toLowerCase()] || null
  }
  return null
}

describe('API Client', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockLocalStorage.getItem.mockReturnValue(null)
  })

  describe('Authentication', () => {
    it('should login successfully with valid credentials', async () => {
      const mockResponse = {
        success: true,
        message: 'Login successful',
        data: {
          access_token: 'test-token',
          token_type: 'Bearer'
        }
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await apiClient.auth.login('testuser', 'password')

      const fetchCall = mockFetch.mock.calls[0]
      expect(fetchCall[0]).toBe('http://localhost:8000/api/v1/auth/login')
      expect(fetchCall[1].method).toBe('POST')
      expect(fetchCall[1].body).toBe(JSON.stringify({ username: 'testuser', password: 'password' }))
      expect(result).toEqual(mockResponse)
    })

    it('should handle login failure', async () => {
      const mockErrorResponse = {
        success: false,
        message: 'Invalid credentials'
      }

      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: () => Promise.resolve(mockErrorResponse)
      })

      await expect(
        apiClient.auth.login('invalid', 'credentials')
      ).rejects.toThrow('Invalid credentials')
    })

    it('should get current user with valid token', async () => {
      const mockUser = {
        id: '1',
        username: 'testuser',
        email: 'test@example.com',
        role: 'student',
        full_name: 'Test User',
        is_active: true,
        created_at: '2025-01-01',
        updated_at: '2025-01-01'
      }

      const mockResponse = {
        success: true,
        message: 'User retrieved',
        data: mockUser
      }

      // Set token
      apiClient.setToken('test-token')

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await apiClient.auth.getCurrentUser()

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers

      expect(getHeader(headers, 'Authorization')).toBe('Bearer test-token')
      expect(result.data).toEqual(mockUser)
    })
  })

  describe('Applications', () => {
    beforeEach(() => {
      apiClient.setToken('test-token')
    })

    it('should fetch user applications', async () => {
      const mockApplications = [
        {
          id: 1,
          student_id: 'student1',
          scholarship_type: 'academic_excellence',
          status: 'submitted',
          personal_statement: 'Test statement',
          gpa_requirement_met: true,
          created_at: '2025-01-01',
          updated_at: '2025-01-01'
        }
      ]

      const mockResponse = {
        success: true,
        message: 'Applications retrieved',
        data: mockApplications
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await apiClient.applications.getMyApplications()

      const fetchCall = mockFetch.mock.calls[0]
      expect(fetchCall[0]).toContain('/applications')
      expect(getHeader(fetchCall[1]?.headers, 'Authorization')).toBe('Bearer test-token')
      expect(result.data).toEqual(mockApplications)
    })

    it('should create new application', async () => {
      const applicationData = {
        scholarship_type: 'academic_excellence',
        personal_statement: 'I am a dedicated student...',
        expected_graduation_date: '2025-06-15'
      }

      const mockCreatedApplication = {
        id: 1,
        student_id: 'student1',
        ...applicationData,
        status: 'draft',
        gpa_requirement_met: true,
        created_at: '2025-01-01',
        updated_at: '2025-01-01'
      }

      const mockResponse = {
        success: true,
        message: 'Application created',
        data: mockCreatedApplication
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await apiClient.applications.createApplication(applicationData)

      const fetchCall = mockFetch.mock.calls[0]
      const headers = fetchCall[1]?.headers

      expect(fetchCall[0]).toContain('/applications')
      expect(fetchCall[1].method).toBe('POST')
      expect(fetchCall[1].body).toBe(JSON.stringify(applicationData))
      expect(getHeader(headers, 'Content-Type')).toBe('application/json')
      expect(getHeader(headers, 'Authorization')).toBe('Bearer test-token')
      expect(result.data).toEqual(mockCreatedApplication)
    })

    it('should submit application', async () => {
      const applicationId = 1
      const mockSubmittedApplication = {
        id: applicationId,
        status: 'submitted',
        submitted_at: '2025-01-01T10:00:00Z'
      }

      const mockResponse = {
        success: true,
        message: 'Application submitted',
        data: mockSubmittedApplication
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse)
      })

      const result = await apiClient.applications.submitApplication(applicationId)

      const fetchCall = mockFetch.mock.calls[0]
      expect(fetchCall[0]).toBe(`http://localhost:8000/api/v1/applications/${applicationId}/submit`)
      expect(fetchCall[1].method).toBe('POST')
      expect(getHeader(fetchCall[1]?.headers, 'Authorization')).toBe('Bearer test-token')

      expect(result.data?.status).toBe('submitted')
    })
  })

  describe('Token Management', () => {
    it('should set and clear tokens correctly', () => {
      const testToken = 'test-token-123'

      apiClient.setToken(testToken)
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('auth_token', testToken)

      apiClient.clearToken()
      expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth_token')
    })
  })

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network error'))

      await expect(
        apiClient.auth.getCurrentUser()
      ).rejects.toThrow('Network error')
    })

    it('should handle HTTP errors', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({
          success: false,
          message: 'Internal server error'
        })
      })

      await expect(
        apiClient.auth.getCurrentUser()
      ).rejects.toThrow('Internal server error')
    })
  })
})
