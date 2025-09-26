import { render, screen, waitFor } from '@testing-library/react'
import { ScholarshipTimeline } from '../scholarship-timeline'

// Mock functions
const mockUseScholarshipPermissions = jest.fn()
const mockUseAuth = jest.fn()

// Mock the hooks
jest.mock('@/hooks/use-auth', () => ({
  useAuth: () => mockUseAuth(),
}))

jest.mock('@/hooks/use-scholarship-permissions', () => ({
  useScholarshipPermissions: () => mockUseScholarshipPermissions(),
}))

// Mock API
jest.mock('@/lib/api')

describe('ScholarshipTimeline Component', () => {
  const mockUser = {
    id: '1',
    name: 'Test User',
    email: 'test@example.com',
    role: 'admin' as const
  }

  const mockScholarships = [
    {
      id: 1,
      code: 'ACADEMIC_EXCELLENCE',
      name: '學業優秀獎學金',
      name_en: 'Academic Excellence Scholarship',
      academic_year: 113,
      semester: 'first',
      application_start_date: '2024-09-01T00:00:00Z',
      application_end_date: '2024-09-30T23:59:59Z',
      professor_review_start: '2024-10-01T00:00:00Z',
      professor_review_end: '2024-10-15T23:59:59Z',
      college_review_start: '2024-10-16T00:00:00Z',
      college_review_end: '2024-10-31T23:59:59Z'
    },
    {
      id: 2,
      code: 'NEED_BASED',
      name: '清寒獎學金',
      name_en: 'Need-Based Scholarship',
      academic_year: 113,
      semester: 'first',
      application_start_date: '2024-09-01T00:00:00Z',
      application_end_date: '2024-09-30T23:59:59Z'
    }
  ]

  beforeEach(() => {
    // Configure mocked API
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { mockRequest } = require('@/lib/api')
    mockRequest.mockResolvedValue({
      success: true,
      data: mockScholarships,
      message: 'Success'
    })

    // Default mock for useAuth
    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true,
    })
  })

  // TODO: Fix API mocking - fetch returns empty array, mockRequest not being used
  it.skip('should show all scholarships for super admin', async () => {
    const superAdminUser = { ...mockUser, role: 'super_admin' as const }

    mockUseScholarshipPermissions.mockImplementation(() => ({
      permissions: [],
      isLoading: false,
      error: null,
      hasPermission: jest.fn().mockReturnValue(true),
      getAllowedScholarshipIds: jest.fn().mockReturnValue([]),
      filterScholarshipsByPermission: jest.fn().mockReturnValue(mockScholarships),
      refetch: jest.fn()
    }))

    render(<ScholarshipTimeline user={superAdminUser} />)

    await waitFor(() => {
      expect(screen.getByText('獎學金時間軸')).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByText('學業優秀獎學金')).toBeInTheDocument()
      expect(screen.getByText('清寒獎學金')).toBeInTheDocument()
    })
  })

  it.skip('should filter scholarships based on admin permissions', async () => {
    mockUseScholarshipPermissions.mockImplementation(() => ({
      permissions: [
        { id: 1, user_id: 1, scholarship_id: 1, scholarship_name: '學業優秀獎學金', created_at: '', updated_at: '' }
      ],
      isLoading: false,
      error: null,
      hasPermission: jest.fn().mockImplementation((id) => id === 1),
      getAllowedScholarshipIds: jest.fn().mockReturnValue([1]),
      filterScholarshipsByPermission: jest.fn().mockReturnValue([mockScholarships[0]]),
      refetch: jest.fn()
    }))

    render(<ScholarshipTimeline user={mockUser} />)

    await waitFor(() => {
      expect(screen.getByText('獎學金時間軸')).toBeInTheDocument()
    })

    await waitFor(() => {
      expect(screen.getByText('學業優秀獎學金')).toBeInTheDocument()
      expect(screen.queryByText('清寒獎學金')).not.toBeInTheDocument()
    })
  })

  it('should show no permissions message for admin with no permissions', async () => {
    mockUseScholarshipPermissions.mockImplementation(() => ({
      permissions: [],
      isLoading: false,
      error: null,
      hasPermission: jest.fn().mockReturnValue(false),
      getAllowedScholarshipIds: jest.fn().mockReturnValue([]),
      filterScholarshipsByPermission: jest.fn().mockReturnValue([]),
      refetch: jest.fn()
    }))

    render(<ScholarshipTimeline user={mockUser} />)

    await waitFor(() => {
      expect(screen.getByText('您沒有獎學金權限')).toBeInTheDocument()
      expect(screen.getByText('您目前沒有被分配任何獎學金權限，請聯繫管理員')).toBeInTheDocument()
    })
  })

  it('should not render for student role', () => {
    const studentUser = { ...mockUser, role: 'student' as const }

    mockUseScholarshipPermissions.mockImplementation(() => ({
      permissions: [],
      isLoading: false,
      error: null,
      hasPermission: jest.fn().mockReturnValue(false),
      getAllowedScholarshipIds: jest.fn().mockReturnValue([]),
      filterScholarshipsByPermission: jest.fn().mockReturnValue([]),
      refetch: jest.fn()
    }))

    const { container } = render(<ScholarshipTimeline user={studentUser} />)
    expect(container.firstChild).toBeNull()
  })

  it('should show loading state while permissions are loading', () => {
    mockUseScholarshipPermissions.mockImplementation(() => ({
      permissions: [],
      isLoading: true,
      error: null,
      hasPermission: jest.fn().mockReturnValue(false),
      getAllowedScholarshipIds: jest.fn().mockReturnValue([]),
      filterScholarshipsByPermission: jest.fn().mockReturnValue([]),
      refetch: jest.fn()
    }))

    render(<ScholarshipTimeline user={mockUser} />)

    expect(screen.getByText('載入獎學金時間軸中...')).toBeInTheDocument()
  })

  it.skip('should handle API errors gracefully', async () => {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const { mockRequest } = require('@/lib/api')
    mockRequest.mockRejectedValue(new Error('API Error'))

    mockUseScholarshipPermissions.mockImplementation(() => ({
      permissions: [],
      isLoading: false,
      error: null,
      hasPermission: jest.fn().mockReturnValue(false),
      getAllowedScholarshipIds: jest.fn().mockReturnValue([]),
      filterScholarshipsByPermission: jest.fn().mockReturnValue([]),
      refetch: jest.fn()
    }))

    render(<ScholarshipTimeline user={mockUser} />)

    await waitFor(() => {
      expect(screen.getByText('載入獎學金時間軸失敗')).toBeInTheDocument()
      expect(screen.getByText('重試')).toBeInTheDocument()
    })
  })
})
