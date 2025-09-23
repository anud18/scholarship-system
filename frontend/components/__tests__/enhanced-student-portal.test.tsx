import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EnhancedStudentPortal } from '../enhanced-student-portal'
import { useApplications } from '../../hooks/use-applications'
import { useAuth } from '../../hooks/use-auth'

// Mock the hooks
jest.mock('../../hooks/use-applications')
jest.mock('../../hooks/use-auth')

const mockUseApplications = useApplications as jest.MockedFunction<typeof useApplications>
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>

const mockUser = {
  id: '1',
  username: 'testuser',
  email: 'test@example.com',
  role: 'student' as const,
  full_name: 'Test User',
  name: 'Test User', // Added for component compatibility
  is_active: true,
  created_at: '2025-01-01',
  updated_at: '2025-01-01',
}

const mockApplication = {
  id: 1,
  student_id: 'student1',
  scholarship_type: 'academic_excellence',
  status: 'submitted' as const,
  personal_statement: 'I am a dedicated student...',
  gpa_requirement_met: true,
  submitted_at: '2025-01-01T10:00:00Z',
  created_at: '2025-01-01',
  updated_at: '2025-01-01',
}

// TODO: Fix API mocking
describe.skip('EnhancedStudentPortal', () => {
  const defaultApplicationsHook = {
    applications: [],
    isLoading: false,
    error: null,
    fetchApplications: jest.fn(),
    createApplication: jest.fn(),
    submitApplication: jest.fn(),
    withdrawApplication: jest.fn(),
    updateApplication: jest.fn(),
    uploadDocument: jest.fn(),
  }

  beforeEach(() => {
    jest.clearAllMocks()
    
    mockUseAuth.mockReturnValue({
      user: mockUser,
      isLoading: false,
      isAuthenticated: true,
      login: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      error: null,
    })

    mockUseApplications.mockReturnValue(defaultApplicationsHook)
  })

  it('should render scholarship information', async () => {
    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    })
    
    // Check for the actual displayed text
    expect(screen.getByText('Academic Excellence Scholarship')).toBeInTheDocument()
    expect(screen.getByText('NT$ 50,000')).toBeInTheDocument()
    expect(screen.getByText('Eligibility')).toBeInTheDocument()
  })

  it('should render scholarship information in Chinese', async () => {
    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="zh" />)
    })
    
    // Check for Chinese text content
    expect(screen.getByText('學術優秀獎學金')).toBeInTheDocument()
    expect(screen.getByText('申請資格')).toBeInTheDocument()
  })

  it('should show empty state when no applications exist', async () => {
    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    })
    
    expect(screen.getByText('No application records yet')).toBeInTheDocument()
    expect(screen.getByText("Click 'New Application' to start applying for scholarship")).toBeInTheDocument()
  })

  it('should display applications when they exist', async () => {
    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      applications: [mockApplication],
    })

    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    })
    
    expect(screen.getByText('academic_excellence')).toBeInTheDocument()
    expect(screen.getByText('Application ID: 1')).toBeInTheDocument()
    expect(screen.getByText('Submitted')).toBeInTheDocument()
  })

  it('should show loading state', async () => {
    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      isLoading: true,
    })

    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    })
    
    // Look for loading spinner by test ID
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
  })

  it('should show error state', async () => {
    const errorMessage = 'Failed to fetch applications'
    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      error: errorMessage,
    })

    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    })
    
    expect(screen.getByText(errorMessage)).toBeInTheDocument()
  })

  it('should allow switching to new application tab', async () => {
    const user = userEvent.setup()
    
    await act(async () => {
      render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    })
    
    // Switch to new application tab
    await act(async () => {
      await user.click(screen.getByText('New Application'))
    })
    
    // Should show the form elements
    expect(screen.getByText('Apply for Academic Excellence Scholarship')).toBeInTheDocument()
    expect(screen.getByText('Form Completion')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('should show form fields in new application tab', async () => {
    const user = userEvent.setup()
    
    render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    
    // Switch to new application tab
    await user.click(screen.getByText('New Application'))
    
    // Check that we're in the new application tab by looking for form completion text
    expect(screen.getByText('Form Completion')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
    
    // Check for at least one form element
    expect(screen.getByRole('button', { name: /submit application/i })).toBeInTheDocument()
  })

  it('should show Chinese text when locale is zh', () => {
    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      applications: [mockApplication],
    })

    render(<EnhancedStudentPortal user={mockUser} locale="zh" />)
    
    expect(screen.getByText('我的申請')).toBeInTheDocument()
    expect(screen.getByText('新增申請')).toBeInTheDocument()
    expect(screen.getByText('申請記錄')).toBeInTheDocument()
  })

  it('should handle withdraw application action', async () => {
    const user = userEvent.setup()
    const withdrawApplicationMock = jest.fn().mockResolvedValue({
      ...mockApplication,
      status: 'withdrawn',
    })
    
    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      applications: [mockApplication],
      withdrawApplication: withdrawApplicationMock,
    })

    render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    
    // Find and click withdraw button
    const withdrawButton = screen.getByText('Withdraw')
    await user.click(withdrawButton)
    
    await waitFor(() => {
      expect(withdrawApplicationMock).toHaveBeenCalledWith(1)
    })
  })

  it('should show progress timeline for applications', () => {
    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      applications: [mockApplication],
    })

    render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    
    expect(screen.getByText('Review Progress')).toBeInTheDocument()
    expect(screen.getByText('Submit Application')).toBeInTheDocument()
    expect(screen.getByText('Initial Review')).toBeInTheDocument()
  })

  it('should handle different application statuses', () => {
    const approvedApplication = {
      ...mockApplication,
      status: 'approved' as const,
    }

    mockUseApplications.mockReturnValue({
      ...defaultApplicationsHook,
      applications: [approvedApplication],
    })

    render(<EnhancedStudentPortal user={mockUser} locale="en" />)
    
    expect(screen.getByText('Approved')).toBeInTheDocument()
  })
}) 