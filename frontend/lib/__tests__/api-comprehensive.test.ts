import apiClient from '../api'

// Mock fetch globally
global.fetch = jest.fn()

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
}

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock
})

describe('API Client', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    localStorageMock.getItem.mockReturnValue('mock-token')
    ;(fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ success: true, data: [] }),
      text: () => Promise.resolve('success')
    })
  })

  describe('Authentication', () => {
    it('should include auth token in requests', async () => {
      await apiClient.scholarships.getAll()

      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock-token'
          })
        })
      )
    })

    it('should handle requests without auth token', async () => {
      localStorageMock.getItem.mockReturnValue(null)

      await apiClient.scholarships.getAll()

      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.not.objectContaining({
            'Authorization': expect.any(String)
          })
        })
      )
    })

    it('should handle token refresh on 401 response', async () => {
      ;(fetch as jest.Mock)
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
          json: () => Promise.resolve({ error: 'Unauthorized' })
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ success: true, data: [] })
        })

      const result = await apiClient.scholarships.getAll()

      expect(fetch).toHaveBeenCalledTimes(2)
      expect(result.success).toBe(true)
    })
  })

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      ;(fetch as jest.Mock).mockRejectedValue(new Error('Network error'))

      const result = await apiClient.scholarships.getAll()

      expect(result.success).toBe(false)
      expect(result.error).toContain('Network error')
    })

    it('should handle HTTP error responses', async () => {
      ;(fetch as jest.Mock).mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: () => Promise.resolve({ error: 'Server error' })
      })

      const result = await apiClient.scholarships.getAll()

      expect(result.success).toBe(false)
      expect(result.error).toContain('500')
    })

    it('should handle malformed JSON responses', async () => {
      ;(fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error('Invalid JSON'))
      })

      const result = await apiClient.scholarships.getAll()

      expect(result.success).toBe(false)
    })
  })

  describe('Scholarship APIs', () => {
    it('should get all scholarships', async () => {
      const mockScholarships = [
        { id: 1, code: 'academic_excellence', name: 'Academic Excellence' },
        { id: 2, code: 'research_grant', name: 'Research Grant' }
      ]

      ;(fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: mockScholarships })
      })

      const result = await apiClient.scholarships.getAll()

      expect(result.success).toBe(true)
      expect(result.data).toEqual(mockScholarships)
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/scholarships'),
        expect.any(Object)
      )
    })

    it('should get eligible scholarships', async () => {
      await apiClient.scholarships.getEligible()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/scholarships/eligible'),
        expect.any(Object)
      )
    })

    it('should get scholarship by ID', async () => {
      await apiClient.scholarships.getById(1)

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/scholarships/1'),
        expect.any(Object)
      )
    })
  })

  describe('Application APIs', () => {
    it('should create application', async () => {
      const applicationData = {
        scholarship_type_id: 1,
        form_data: { name: 'John Doe' },
        files: []
      }

      await apiClient.applications.create(applicationData)

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/applications'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(applicationData),
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      )
    })

    it('should get user applications', async () => {
      await apiClient.applications.getUserApplications()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/applications/user'),
        expect.any(Object)
      )
    })

    it('should update application', async () => {
      const updateData = { form_data: { name: 'Updated Name' } }

      await apiClient.applications.update(1, updateData)

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/applications/1'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify(updateData)
        })
      )
    })

    it('should delete application', async () => {
      await apiClient.applications.delete(1)

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/applications/1'),
        expect.objectContaining({
          method: 'DELETE'
        })
      )
    })
  })

  describe('Admin APIs', () => {
    it('should get dashboard stats', async () => {
      await apiClient.admin.getDashboardStats()

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/dashboard/stats'),
        expect.any(Object)
      )
    })

    it('should get all applications with filters', async () => {
      await apiClient.admin.getAllApplications(1, 10, 'submitted')

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/applications?page=1&size=10&status=submitted'),
        expect.any(Object)
      )
    })

    it('should update application status', async () => {
      await apiClient.admin.updateApplicationStatus(1, 'approved', 'Looks good')

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/admin/applications/1/status'),
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({
            status: 'approved',
            review_notes: 'Looks good'
          })
        })
      )
    })
  })

  describe('File APIs', () => {
    it('should upload file', async () => {
      const formData = new FormData()
      formData.append('file', new File(['test'], 'test.pdf'))

      await apiClient.files.upload(formData)

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/files/upload'),
        expect.objectContaining({
          method: 'POST',
          body: formData
        })
      )
    })

    it('should delete file', async () => {
      await apiClient.files.delete('file-123')

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/files/file-123'),
        expect.objectContaining({
          method: 'DELETE'
        })
      )
    })

    it('should get file by ID', async () => {
      await apiClient.files.getById('file-123')

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/files/file-123'),
        expect.any(Object)
      )
    })
  })

  describe('Request Configuration', () => {
    it('should set correct Content-Type for JSON requests', async () => {
      await apiClient.applications.create({ scholarship_type_id: 1 })

      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      )
    })

    it('should handle FormData without Content-Type header', async () => {
      const formData = new FormData()
      await apiClient.files.upload(formData)

      const fetchCall = (fetch as jest.Mock).mock.calls[0][1]
      expect(fetchCall.headers['Content-Type']).toBeUndefined()
    })

    it('should include request ID for tracking', async () => {
      await apiClient.scholarships.getAll()

      expect(fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'X-Request-ID': expect.any(String)
          })
        })
      )
    })
  })

  describe('Response Processing', () => {
    it('should parse successful JSON responses', async () => {
      const mockData = { id: 1, name: 'Test' }
      ;(fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ success: true, data: mockData })
      })

      const result = await apiClient.scholarships.getById(1)

      expect(result.success).toBe(true)
      expect(result.data).toEqual(mockData)
    })

    it('should handle empty responses', async () => {
      ;(fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 204,
        json: () => Promise.resolve()
      })

      const result = await apiClient.applications.delete(1)

      expect(result.success).toBe(true)
    })

    it('should handle text responses', async () => {
      ;(fetch as jest.Mock).mockResolvedValue({
        ok: true,
        status: 200,
        json: () => Promise.reject(new Error('Not JSON')),
        text: () => Promise.resolve('Operation successful')
      })

      const result = await apiClient.scholarships.getAll()

      expect(result.success).toBe(true)
    })
  })
})