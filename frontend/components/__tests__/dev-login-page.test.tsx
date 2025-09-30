import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import { DevLoginPage } from "../dev-login-page";

// Mock Next.js router
jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

// Mock useAuth hook
jest.mock("@/hooks/use-auth", () => ({
  useAuth: jest.fn(() => ({
    login: jest.fn(),
    logout: jest.fn(),
    isAuthenticated: false,
    user: null,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

// Create mutable mock functions with default responses
const mockGetMockUsers = jest
  .fn()
  .mockResolvedValue({ success: true, data: [] });
const mockMockSSOLogin = jest
  .fn()
  .mockResolvedValue({ success: true, data: { access_token: "mock-token" } });

// Mock API module
jest.mock("@/lib/api", () => ({
  apiClient: {
    auth: {
      getMockUsers: (...args: any[]) => mockGetMockUsers(...args),
      mockSSOLogin: (...args: any[]) => mockMockSSOLogin(...args),
    },
  },
  api: {
    auth: {
      getMockUsers: (...args: any[]) => mockGetMockUsers(...args),
      mockSSOLogin: (...args: any[]) => mockMockSSOLogin(...args),
    },
  },
}));

import { apiClient, api } from "@/lib/api";

// Override with mutable mocks
apiClient.auth.getMockUsers = mockGetMockUsers;
apiClient.auth.mockSSOLogin = mockMockSSOLogin;
if (api) {
  api.auth = {
    ...api.auth,
    getMockUsers: mockGetMockUsers,
    mockSSOLogin: mockMockSSOLogin,
  } as any;
}

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  clear: jest.fn(),
};
Object.defineProperty(window, "localStorage", {
  value: mockLocalStorage,
});

// Mock process.env for development mode
const originalEnv = process.env.NODE_ENV;

beforeAll(() => {
  Object.defineProperty(process.env, "NODE_ENV", {
    value: "development",
    writable: true,
    configurable: true,
  });
});

afterAll(() => {
  Object.defineProperty(process.env, "NODE_ENV", {
    value: originalEnv,
    writable: true,
    configurable: true,
  });
});

// TODO: Fix API mocking - component uses apiClient which calls real implementation despite mocks
describe.skip("DevLoginPage Component", () => {
  const mockPush = jest.fn();

  const mockUserData = [
    {
      id: "student_001",
      username: "student_dev",
      full_name: "張小明 (Zhang Xiaoming)",
      role: "student",
      email: "student@example.com",
    },
    {
      id: "professor_001",
      username: "professor_dev",
      full_name: "王教授 (Prof. Wang)",
      role: "professor",
      email: "professor@example.com",
    },
    {
      id: "college_001",
      username: "college_dev",
      full_name: "College Reviewer",
      role: "college",
      email: "college@example.com",
    },
    {
      id: "admin_001",
      username: "admin_dev",
      full_name: "Administrator",
      role: "admin",
      email: "admin@example.com",
    },
    {
      id: "super_admin_001",
      username: "super_admin_dev",
      full_name: "Super Administrator",
      role: "super_admin",
      email: "superadmin@example.com",
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });

    // Mock getMockUsers to return test data
    mockGetMockUsers.mockResolvedValue({
      success: true,
      data: mockUserData,
    });

    // Set auth token for authenticated flows
    window.localStorage.setItem("auth_token", "unit-test-token");
  });

  it("should render development login interface correctly", () => {
    render(<DevLoginPage />);

    expect(screen.getByText("Development Login")).toBeInTheDocument();
    expect(
      screen.getByText(/Select a user to simulate login/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Development Only:/)).toBeInTheDocument();
  });

  it("should display all mock users with correct roles", () => {
    render(<DevLoginPage />);

    // Check that all role types are displayed
    expect(screen.getByText("Student")).toBeInTheDocument();
    expect(screen.getByText("Professor")).toBeInTheDocument();
    expect(screen.getByText("College Reviewer")).toBeInTheDocument();
    expect(screen.getByText("Administrator")).toBeInTheDocument();
    expect(screen.getByText("Super Administrator")).toBeInTheDocument();

    // Check that user names are displayed
    expect(screen.getByText("張小明 (Zhang Xiaoming)")).toBeInTheDocument();
    expect(screen.getByText("王教授 (Prof. Wang)")).toBeInTheDocument();
  });

  it("should handle user login correctly", async () => {
    // Mock the API response
    const mockApiResponse = {
      success: true,
      data: {
        access_token: "mock_token_123",
        user: {
          id: "student_001",
          username: "student_dev",
          full_name: "張小明 (Zhang Xiaoming)",
          email: "student001@university.edu",
          role: "student",
        },
      },
    };

    // Mock the API call
    const mockMockSSOLogin = jest.fn().mockResolvedValue(mockApiResponse);
    apiClient.auth.mockSSOLogin = mockMockSSOLogin;

    render(<DevLoginPage />);

    // Find and click the student login button
    const studentCard = screen
      .getByText("張小明 (Zhang Xiaoming)")
      .closest(".cursor-pointer");
    expect(studentCard).toBeInTheDocument();

    fireEvent.click(studentCard!);

    // Check loading state
    await waitFor(() => {
      expect(screen.getByText("Logging in...")).toBeInTheDocument();
    });

    // Wait for login to complete
    await waitFor(
      () => {
        expect(mockMockSSOLogin).toHaveBeenCalledWith("student_dev");
        expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
          "auth_token",
          "mock_token_123"
        );
        expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
          "user",
          expect.stringContaining('"role":"student"')
        );
        expect(mockPush).toHaveBeenCalledWith("/dashboard");
      },
      { timeout: 1000 }
    );
  });

  it("should store correct user data in localStorage", async () => {
    render(<DevLoginPage />);

    // Click on admin user
    const adminCard = screen
      .getByText("管理員 (Admin User)")
      .closest(".cursor-pointer");
    fireEvent.click(adminCard!);

    await waitFor(() => {
      const setItemCalls = mockLocalStorage.setItem.mock.calls;
      const devUserCall = setItemCalls.find(call => call[0] === "dev_user");
      expect(devUserCall).toBeTruthy();

      if (devUserCall) {
        const userData = JSON.parse(devUserCall[1]);
        expect(userData).toMatchObject({
          id: "admin_001",
          name: "管理員 (Admin User)",
          email: "admin@university.edu",
          role: "admin",
          full_name: "管理員 (Admin User)",
          username: "admin",
          is_active: true,
        });
        expect(userData.created_at).toBeTruthy();
        expect(userData.updated_at).toBeTruthy();
      }
    });
  });

  it("should display instructions clearly", () => {
    render(<DevLoginPage />);

    expect(screen.getByText("Instructions:")).toBeInTheDocument();
    expect(
      screen.getByText(/Click any user card to simulate login/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/User data will be stored in localStorage/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/You'll be automatically redirected to \/dashboard/)
    ).toBeInTheDocument();
  });

  it("should show proper role colors and icons", () => {
    render(<DevLoginPage />);

    // Check that badges with different colors are present
    const badges =
      screen.getAllByTestId("badge") ||
      screen.getAllByText(
        /Student|Professor|College Reviewer|Administrator|Super Administrator/
      );
    expect(badges.length).toBeGreaterThan(0);
  });

  it("should disable buttons during login process", async () => {
    render(<DevLoginPage />);

    const studentCard = screen
      .getByText("張小明 (Zhang Xiaoming)")
      .closest(".cursor-pointer");
    const loginButton = studentCard?.querySelector("button");

    expect(loginButton).not.toBeDisabled();

    fireEvent.click(studentCard!);

    await waitFor(() => {
      expect(loginButton).toBeDisabled();
    });
  });
});

describe.skip("DevLoginPage Production Mode", () => {
  const mockPush = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({
      push: mockPush,
    });

    // Mock production environment
    Object.defineProperty(process.env, "NODE_ENV", {
      value: "production",
      writable: true,
      configurable: true,
    });
  });

  // TODO: Fix NODE_ENV mocking - component checks NODE_ENV at module load time
  it.skip("should not render in production mode", () => {
    const { container } = render(<DevLoginPage />);
    expect(container.firstChild).toBeNull();
  });

  afterEach(() => {
    // Reset to development mode after each test
    Object.defineProperty(process.env, "NODE_ENV", {
      value: "development",
      writable: true,
      configurable: true,
    });
  });

  it.skip("should redirect to home page in production", () => {
    render(<DevLoginPage />);
    expect(mockPush).toHaveBeenCalledWith("/");
  });
});
