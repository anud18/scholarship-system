import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useRouter } from 'next/navigation';
import { DevLoginPage } from '../dev-login-page';

// Mock Next.js router
jest.mock('next/navigation', () => ({
  useRouter: jest.fn(),
}));

// Mock useAuth hook
jest.mock('@/hooks/use-auth', () => ({
  useAuth: jest.fn(() => ({
    login: jest.fn(),
    logout: jest.fn(),
    isAuthenticated: false,
    user: null,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock API module
jest.mock('@/lib/api', () => ({
  apiClient: {
    auth: {
      mockSSOLogin: jest.fn(),
    },
    setToken: jest.fn(),
  },
}));

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};
Object.defineProperty(window, 'localStorage', {
  value: mockLocalStorage,
});

// Mock process.env for development mode
const originalEnv = process.env.NODE_ENV;

beforeAll(() => {
  process.env.NODE_ENV = 'development';
});

afterAll(() => {
  process.env.NODE_ENV = originalEnv;
});

describe('DevLoginPage Component', () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });
    // Set auth token for authenticated flows
    window.localStorage.setItem('auth_token', 'unit-test-token');
  });

  it('should render development login interface correctly', () => {
    render(<DevLoginPage />);
    
    expect(screen.getByText('Development Login')).toBeInTheDocument();
    expect(screen.getByText(/Select a user to simulate login/)).toBeInTheDocument();
    expect(screen.getByText(/Development Only:/)).toBeInTheDocument();
  });

  it('should display all mock users with correct roles', () => {
    render(<DevLoginPage />);
    
    // Check that all role types are displayed
    expect(screen.getByText('Student')).toBeInTheDocument();
    expect(screen.getByText('Professor')).toBeInTheDocument();
    expect(screen.getByText('College Reviewer')).toBeInTheDocument();
    expect(screen.getByText('Administrator')).toBeInTheDocument();
    expect(screen.getByText('Super Administrator')).toBeInTheDocument();
    
    // Check that user names are displayed
    expect(screen.getByText('張小明 (Zhang Xiaoming)')).toBeInTheDocument();
    expect(screen.getByText('王教授 (Prof. Wang)')).toBeInTheDocument();
  });

  it('should handle user login correctly', async () => {
    // Mock the API response
    const mockApiResponse = {
      success: true,
      data: {
        access_token: 'mock_token_123',
        user: {
          id: 'student_001',
          username: 'student_dev',
          full_name: '張小明 (Zhang Xiaoming)',
          email: 'student001@university.edu',
          role: 'student'
        }
      }
    };
    
    // Mock the API call
    const mockMockSSOLogin = jest.fn().mockResolvedValue(mockApiResponse);
    require('@/lib/api').apiClient.auth.mockSSOLogin = mockMockSSOLogin;
    
    render(<DevLoginPage />);
    
    // Find and click the student login button
    const studentCard = screen.getByText('張小明 (Zhang Xiaoming)').closest('.cursor-pointer');
    expect(studentCard).toBeInTheDocument();
    
    fireEvent.click(studentCard!);
    
    // Check loading state
    await waitFor(() => {
      expect(screen.getByText('Logging in...')).toBeInTheDocument();
    });
    
    // Wait for login to complete
    await waitFor(() => {
      expect(mockMockSSOLogin).toHaveBeenCalledWith('student_dev');
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('auth_token', 'mock_token_123');
      expect(mockLocalStorage.setItem).toHaveBeenCalledWith('user', expect.stringContaining('"role":"student"'));
      expect(mockPush).toHaveBeenCalledWith('/dashboard');
    }, { timeout: 1000 });
  });

  it('should store correct user data in localStorage', async () => {
    render(<DevLoginPage />);
    
    // Click on admin user
    const adminCard = screen.getByText('管理員 (Admin User)').closest('.cursor-pointer');
    fireEvent.click(adminCard!);
    
    await waitFor(() => {
      const setItemCalls = mockLocalStorage.setItem.mock.calls;
      const devUserCall = setItemCalls.find(call => call[0] === 'dev_user');
      expect(devUserCall).toBeTruthy();
      
      if (devUserCall) {
        const userData = JSON.parse(devUserCall[1]);
        expect(userData).toMatchObject({
          id: 'admin_001',
          name: '管理員 (Admin User)',
          email: 'admin@university.edu',
          role: 'admin',
          full_name: '管理員 (Admin User)',
          username: 'admin',
          is_active: true,
        });
        expect(userData.created_at).toBeTruthy();
        expect(userData.updated_at).toBeTruthy();
      }
    });
  });

  it('should display instructions clearly', () => {
    render(<DevLoginPage />);
    
    expect(screen.getByText('Instructions:')).toBeInTheDocument();
    expect(screen.getByText(/Click any user card to simulate login/)).toBeInTheDocument();
    expect(screen.getByText(/User data will be stored in localStorage/)).toBeInTheDocument();
    expect(screen.getByText(/You'll be automatically redirected to \/dashboard/)).toBeInTheDocument();
  });

  it('should show proper role colors and icons', () => {
    render(<DevLoginPage />);
    
    // Check that badges with different colors are present
    const badges = screen.getAllByTestId('badge') || screen.getAllByText(/Student|Professor|College Reviewer|Administrator|Super Administrator/);
    expect(badges.length).toBeGreaterThan(0);
  });

  it('should disable buttons during login process', async () => {
    render(<DevLoginPage />);
    
    const studentCard = screen.getByText('張小明 (Zhang Xiaoming)').closest('.cursor-pointer');
    const loginButton = studentCard?.querySelector('button');
    
    expect(loginButton).not.toBeDisabled();
    
    fireEvent.click(studentCard!);
    
    await waitFor(() => {
      expect(loginButton).toBeDisabled();
    });
  });
});

describe('DevLoginPage Production Mode', () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });
    
    // Mock production environment
    process.env.NODE_ENV = 'production';
  });

  it('should not render in production mode', () => {
    const { container } = render(<DevLoginPage />);
    expect(container.firstChild).toBeNull();
  });

  afterEach(() => {
    // Reset to development mode after each test
    process.env.NODE_ENV = 'development';
  });

  it('should redirect to home page in production', () => {
    render(<DevLoginPage />);
    expect(mockPush).toHaveBeenCalledWith('/');
  });
}); 