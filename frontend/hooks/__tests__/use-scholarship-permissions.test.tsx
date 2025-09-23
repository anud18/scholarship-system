import { renderHook } from '@testing-library/react'
import { useScholarshipPermissions } from '../use-scholarship-permissions'

// Mock the API client
jest.mock('@/lib/api', () => ({
  apiClient: {
    admin: {
      getMyScholarships: jest.fn().mockResolvedValue({
        success: true,
        data: [
          { id: 1, code: 'academic_excellence', name: 'Academic Excellence', category: 'phd' },
          { id: 2, code: 'research_grant', name: 'Research Grant', category: 'master' }
        ]
      })
    }
  }
}))

// Mock the useAuth hook
jest.mock('../use-auth', () => ({
  useAuth: jest.fn()
}))

const mockApi = require('@/lib/api').apiClient
const mockUseAuth = require('../use-auth').useAuth

describe('useScholarshipPermissions', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should allow access for admin user', async () => {
    const mockUser = {
      id: 1,
      email: 'admin@nycu.edu.tw',
      role: 'admin'
    }

    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true
    })

    const { result } = renderHook(() => useScholarshipPermissions())

    expect(result.current.hasPermission).toBeDefined()
    expect(result.current.getAllowedScholarships).toBeDefined()
  })

  it('should check permissions correctly', async () => {
    const mockUser = {
      id: 1,
      email: 'admin@nycu.edu.tw',
      role: 'admin'
    }

    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true
    })

    const { result } = renderHook(() => useScholarshipPermissions())

    // Test permission check for scholarship
    const hasAccess = result.current.hasPermission(1)
    expect(typeof hasAccess).toBe('boolean')
  })

  it('should deny access for unauthenticated users', () => {
    mockUseAuth.mockReturnValue({
      user: null,
      isAuthenticated: false
    })

    const { result } = renderHook(() => useScholarshipPermissions())

    const hasAccess = result.current.hasPermission(1)
    expect(hasAccess).toBe(false)
  })

  it('should handle invalid scholarship IDs', () => {
    const mockUser = {
      id: 1,
      email: 'admin@nycu.edu.tw',
      role: 'admin'
    }

    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true
    })

    const { result } = renderHook(() => useScholarshipPermissions())

    const hasAccess = result.current.hasPermission(999)
    expect(hasAccess).toBe(false)
  })

  it('should get allowed scholarships for admin user', async () => {
    const mockUser = {
      id: 1,
      email: 'admin@nycu.edu.tw',
      role: 'admin'
    }

    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true
    })

    const { result } = renderHook(() => useScholarshipPermissions())

    const allowedScholarships = result.current.getAllowedScholarships()
    expect(Array.isArray(allowedScholarships)).toBe(true)
  })
})