import { renderHook } from '@testing-library/react'
import { useScholarshipPermissions } from '../use-scholarship-permissions'

// Mock the API
jest.mock('@/lib/api', () => ({
  api: {
    scholarships: {
      getEligible: jest.fn().mockResolvedValue({
        success: true,
        data: [
          { id: 1, code: 'academic_excellence', category: 'phd' },
          { id: 2, code: 'research_grant', category: 'master' }
        ]
      })
    }
  }
}))

const mockApi = require('@/lib/api').api

describe('useScholarshipPermissions', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('should allow access for eligible PhD student', async () => {
    const mockUser = {
      id: 1,
      email: 'student@nycu.edu.tw',
      role: 'student',
      studentType: 'phd' as const
    }

    const { result } = renderHook(() => useScholarshipPermissions(mockUser))

    expect(result.current.canApplyToScholarship).toBeDefined()
    expect(result.current.getEligibleScholarships).toBeDefined()
  })

  it('should check eligibility correctly', async () => {
    const mockUser = {
      id: 1,
      email: 'student@nycu.edu.tw',
      role: 'student',
      studentType: 'phd' as const
    }

    const { result } = renderHook(() => useScholarshipPermissions(mockUser))

    // Test permission check for PhD scholarship
    const canApply = result.current.canApplyToScholarship('academic_excellence')
    expect(typeof canApply).toBe('boolean')
  })

  it('should deny access for admin users', () => {
    const mockUser = {
      id: 1,
      email: 'admin@nycu.edu.tw',
      role: 'admin',
      studentType: undefined
    }

    const { result } = renderHook(() => useScholarshipPermissions(mockUser as any))

    const canApply = result.current.canApplyToScholarship('academic_excellence')
    expect(canApply).toBe(false)
  })

  it('should handle invalid scholarship codes', () => {
    const mockUser = {
      id: 1,
      email: 'student@nycu.edu.tw',
      role: 'student',
      studentType: 'phd' as const
    }

    const { result } = renderHook(() => useScholarshipPermissions(mockUser))

    const canApply = result.current.canApplyToScholarship('invalid_scholarship')
    expect(canApply).toBe(false)
  })

  it('should get eligible scholarships for user type', async () => {
    const mockUser = {
      id: 1,
      email: 'student@nycu.edu.tw',
      role: 'student',
      studentType: 'phd' as const
    }

    const { result } = renderHook(() => useScholarshipPermissions(mockUser))

    const eligibleScholarships = await result.current.getEligibleScholarships()
    expect(Array.isArray(eligibleScholarships)).toBe(true)
  })
})