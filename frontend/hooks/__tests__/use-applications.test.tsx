import React from 'react'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useApplications } from '../use-applications'
import { useAuth } from '../use-auth'

// Mock the useAuth hook
jest.mock('../use-auth')
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    hasToken: jest.fn(() => true),
    getToken: jest.fn(() => 'mock-token'),
    applications: {
      getMyApplications: jest.fn(),
      createApplication: jest.fn(),
      submitApplication: jest.fn(),
      withdrawApplication: jest.fn(),
      updateApplication: jest.fn(),
      uploadDocument: jest.fn(),
      saveApplicationDraft: jest.fn(),
      deleteApplication: jest.fn(),
    }
  }
}))

const mockApiClient = require('@/lib/api').apiClient

// Test wrapper that provides auth context
const wrapper = ({ children }: { children: React.ReactNode }) => {
  return <div>{children}</div>
}

describe('useApplications Hook', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    // Default auth state
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: '1', username: 'testuser' },
      login: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      isLoading: false,
      error: null
    } as any)
  })

  describe('fetchApplications', () => {
    it('should fetch applications successfully', async () => {
      const mockApplications = [
        { id: 1, status: 'draft', created_at: '2025-01-01' },
        { id: 2, status: 'submitted', created_at: '2025-01-02' }
      ]

      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: true,
        data: mockApplications
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.applications).toEqual(mockApplications)
        expect(result.current.isLoading).toBe(false)
        expect(result.current.error).toBeNull()
      })
    })

    it('should handle array response format', async () => {
      const mockApplications = [
        { id: 1, status: 'draft' }
      ]

      mockApiClient.applications.getMyApplications.mockResolvedValue(mockApplications)

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.applications).toEqual(mockApplications)
      })
    })

    it('should not fetch when user is not authenticated', async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        login: jest.fn(),
        logout: jest.fn(),
        updateUser: jest.fn(),
        isLoading: false,
        error: null
      } as any)

      const { result } = renderHook(() => useApplications(), { wrapper })

      expect(mockApiClient.applications.getMyApplications).not.toHaveBeenCalled()
      expect(result.current.applications).toEqual([])
    })

    it('should handle fetch error', async () => {
      mockApiClient.applications.getMyApplications.mockRejectedValue(
        new Error('Network error')
      )

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.error).toBe('Network error')
        expect(result.current.isLoading).toBe(false)
      })
    })

    it('should handle API response without success flag', async () => {
      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: false,
        message: 'Failed to fetch'
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.error).toBe('Failed to fetch')
      })
    })
  })

  describe('createApplication', () => {
    it('should create application successfully', async () => {
      const newApplication = { id: 3, status: 'draft', created_at: '2025-01-03' }
      const applicationData = { scholarship_type: 'academic_excellence' }

      mockApiClient.applications.createApplication.mockResolvedValue({
        success: true,
        data: newApplication
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      let createdApp: any
      await act(async () => {
        createdApp = await result.current.createApplication(applicationData as any)
      })

      expect(createdApp).toEqual(newApplication)
      expect(result.current.applications).toContain(newApplication)
    })

    it('should handle create application error', async () => {
      const applicationData = { scholarship_type: 'academic_excellence' }

      mockApiClient.applications.createApplication.mockRejectedValue(
        new Error('Create failed')
      )

      const { result } = renderHook(() => useApplications(), { wrapper })

      await act(async () => {
        try {
          await result.current.createApplication(applicationData as any)
        } catch (error) {
          expect(error).toBeInstanceOf(Error)
        }
      })

      expect(result.current.error).toBe('Create failed')
    })
  })

  describe('submitApplication', () => {
    it('should submit application successfully', async () => {
      const submittedApp = { id: 1, status: 'submitted', submitted_at: '2025-01-01' }
      
      // Set initial applications
      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: true,
        data: [{ id: 1, status: 'draft' }]
      })

      mockApiClient.applications.submitApplication.mockResolvedValue({
        success: true,
        data: submittedApp
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(1)
      })

      await act(async () => {
        await result.current.submitApplication(1)
      })

      expect(result.current.applications[0]).toEqual(submittedApp)
    })

    it('should handle submit application error', async () => {
      mockApiClient.applications.submitApplication.mockRejectedValue(
        new Error('Submit failed')
      )

      const { result } = renderHook(() => useApplications(), { wrapper })

      await act(async () => {
        try {
          await result.current.submitApplication(1)
        } catch (error) {
          expect(error).toBeInstanceOf(Error)
        }
      })

      expect(result.current.error).toBe('Submit failed')
    })
  })

  describe('withdrawApplication', () => {
    it('should withdraw application successfully', async () => {
      const withdrawnApp = { id: 1, status: 'withdrawn' }
      
      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: true,
        data: [{ id: 1, status: 'submitted' }]
      })

      mockApiClient.applications.withdrawApplication.mockResolvedValue({
        success: true,
        data: withdrawnApp
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(1)
      })

      await act(async () => {
        await result.current.withdrawApplication(1)
      })

      expect(result.current.applications[0]).toEqual(withdrawnApp)
    })
  })

  describe('updateApplication', () => {
    it('should update application successfully', async () => {
      const updatedApp = { id: 1, status: 'draft', personal_statement: 'Updated statement' }
      
      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: true,
        data: [{ id: 1, status: 'draft', personal_statement: 'Original' }]
      })

      mockApiClient.applications.updateApplication.mockResolvedValue({
        success: true,
        data: updatedApp
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(1)
      })

      await act(async () => {
        await result.current.updateApplication(1, { personal_statement: 'Updated statement' })
      })

      expect(result.current.applications[0]).toEqual(updatedApp)
    })
  })

  describe('uploadDocument', () => {
    it('should upload document successfully', async () => {
      const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
      
      mockApiClient.applications.uploadDocument.mockResolvedValue({
        success: true,
        data: { file_id: 'file123' }
      })

      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: true,
        data: []
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await act(async () => {
        const uploadResult = await result.current.uploadDocument(1, file, 'transcript')
        expect(uploadResult).toEqual({ file_id: 'file123' })
      })

      // Should refresh applications after upload
      expect(mockApiClient.applications.getMyApplications).toHaveBeenCalledTimes(2)
    })
  })

  describe('saveApplicationDraft', () => {
    it('should save draft successfully', async () => {
      const draftApp = { id: 3, status: 'draft' }
      const draftData = { scholarship_type: 'research' }

      mockApiClient.applications.saveApplicationDraft.mockResolvedValue({
        success: true,
        data: draftApp
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await act(async () => {
        const savedDraft = await result.current.saveApplicationDraft(draftData as any)
        expect(savedDraft).toEqual(draftApp)
      })

      expect(result.current.applications).toContain(draftApp)
    })
  })

  describe('deleteApplication', () => {
    it('should delete application successfully', async () => {
      mockApiClient.applications.getMyApplications.mockResolvedValue({
        success: true,
        data: [
          { id: 1, status: 'draft' },
          { id: 2, status: 'draft' }
        ]
      })

      mockApiClient.applications.deleteApplication.mockResolvedValue({
        success: true,
        data: null
      })

      const { result } = renderHook(() => useApplications(), { wrapper })

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(2)
      })

      await act(async () => {
        await result.current.deleteApplication(1)
      })

      expect(result.current.applications).toHaveLength(1)
      expect(result.current.applications[0].id).toBe(2)
    })
  })

  describe('error handling', () => {
    it('should set error state when API calls fail', async () => {
      mockApiClient.applications.createApplication.mockRejectedValue(
        new Error('API Error')
      )

      const { result } = renderHook(() => useApplications(), { wrapper })

      await act(async () => {
        try {
          await result.current.createApplication({ scholarship_type: 'test' } as any)
        } catch (e) {
          // Expected to throw
        }
      })

      expect(result.current.error).toBe('API Error')
    })

    it('should clear error on successful operation', async () => {
      const { result } = renderHook(() => useApplications(), { wrapper })

      // First set an error
      mockApiClient.applications.createApplication.mockRejectedValue(
        new Error('First error')
      )

      await act(async () => {
        try {
          await result.current.createApplication({ scholarship_type: 'test' } as any)
        } catch (e) {
          // Expected
        }
      })

      expect(result.current.error).toBe('First error')

      // Then clear it with successful operation
      mockApiClient.applications.createApplication.mockResolvedValue({
        success: true,
        data: { id: 1, status: 'draft' }
      })

      await act(async () => {
        await result.current.createApplication({ scholarship_type: 'test' } as any)
      })

      expect(result.current.error).toBeNull()
    })
  })
})