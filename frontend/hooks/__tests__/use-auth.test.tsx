import React from 'react'
import { renderHook, render } from '@testing-library/react'
import { ReactNode, Component, ErrorInfo } from 'react'
import { AuthProvider, useAuth } from '../use-auth'

// API client is automatically mocked by __mocks__ directory

// Test wrapper with AuthProvider
const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
)

// Error boundary component for testing error cases
class TestErrorBoundary extends Component<
  { children: ReactNode; onError: (error: Error, errorInfo: ErrorInfo) => void },
  { hasError: boolean; error?: Error }
> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.props.onError(error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return <div>Error caught</div>
    }
    return this.props.children
  }
}

// Component that uses the hook (for error boundary testing)
function TestComponent() {
  useAuth()
  return <div>Test</div>
}

describe('useAuth Hook', () => {
  it('should provide auth context', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current).toBeDefined()
    expect(typeof result.current.login).toBe('function')
    expect(typeof result.current.logout).toBe('function')
    expect(typeof result.current.updateUser).toBe('function')
    expect(typeof result.current.isAuthenticated).toBe('boolean')
    expect(typeof result.current.isLoading).toBe('boolean')
  })

  it('should initialize with correct default state', () => {
    const { result } = renderHook(() => useAuth(), { wrapper })

    expect(result.current.user).toBe(null)
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.error).toBe(null)
  })

  it('should throw error when used outside provider', () => {
    let caughtError: Error | null = null

    const handleError = (error: Error) => {
      caughtError = error
    }

    // Suppress console.error for this test
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <TestErrorBoundary onError={handleError}>
        <TestComponent />
      </TestErrorBoundary>
    )

    expect(caughtError).not.toBeNull()
    expect(caughtError!.message).toBe('useAuth must be used within AuthProvider')

    // Restore console.error
    consoleSpy.mockRestore()
  })
})
