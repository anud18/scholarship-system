import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useRouter } from "next/navigation";
import { DevLoginPage } from "../dev-login-page";
import { apiClient } from "@/lib/api";
import type { User } from "@/lib/api";

// Mock Next.js router (per-test push assertions)
jest.mock("next/navigation", () => ({
  useRouter: jest.fn(),
}));

// PR #906 pattern: stable useAuth mock — component reads login() from context
const mockAuthLogin = jest.fn();
jest.mock("@/hooks/use-auth", () => ({
  useAuth: () => ({
    login: mockAuthLogin,
    logout: jest.fn(),
    isAuthenticated: false,
    user: null,
    isLoading: false,
    error: null,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

// Silence component debug logging
jest.mock("@/lib/utils/logger", () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

const mockUserData = [
  {
    id: "student_001",
    nycu_id: "student_dev",
    name: "張小明",
    email: "student@example.com",
    role: "student" as const,
    description: "Test student account",
    raw_data: {
      chinese_name: "張小明",
      english_name: "Zhang Xiaoming",
    },
  },
  {
    id: "professor_001",
    nycu_id: "professor_dev",
    name: "王教授 (Prof. Wang)",
    email: "professor@example.com",
    role: "professor" as const,
    description: "Test professor account",
  },
];

const loggedInUser: User = {
  id: "student_001",
  nycu_id: "student_dev",
  email: "student@example.com",
  name: "張小明",
  role: "student",
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

const mockPush = jest.fn();

// PR #911 pattern: spy on the REAL @/lib/api module object — module-factory
// mocks break because internal call sites hold direct references.
let getMockUsersSpy: jest.SpyInstance;
let mockSSOLoginSpy: jest.SpyInstance;

function installApiSpies() {
  getMockUsersSpy = jest
    .spyOn(apiClient.auth, "getMockUsers")
    .mockResolvedValue({ success: true, message: "", data: mockUserData });
  mockSSOLoginSpy = jest.spyOn(apiClient.auth, "mockSSOLogin").mockResolvedValue({
    success: true,
    message: "",
    data: {
      access_token: "mock_token_123",
      token_type: "bearer",
      expires_in: 3600,
      user: loggedInUser,
    },
  });
}

describe("DevLoginPage Component", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    installApiSpies();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("should render development login interface with loaded users", async () => {
    render(<DevLoginPage />);

    expect(screen.getByText("Development Login")).toBeInTheDocument();
    expect(
      screen.getByText(/Select a user to simulate login/)
    ).toBeInTheDocument();
    expect(screen.getByText(/Development Only:/)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("張小明 (Zhang Xiaoming)")).toBeInTheDocument();
    });
    expect(getMockUsersSpy).toHaveBeenCalledTimes(1);
  });

  it("should show loading state while users load", () => {
    getMockUsersSpy.mockImplementation(
      () => new Promise(() => {}) // never resolves
    );
    render(<DevLoginPage />);

    expect(screen.getByText("Loading users...")).toBeInTheDocument();
  });

  it("should display mock users with roles, names and emails", async () => {
    render(<DevLoginPage />);

    await waitFor(() => {
      expect(screen.getByText("Student")).toBeInTheDocument();
    });

    // Badge labels
    expect(screen.getByText("Professor")).toBeInTheDocument();
    // Display name: prefers raw_data chinese (english), else plain name
    expect(screen.getByText("張小明 (Zhang Xiaoming)")).toBeInTheDocument();
    expect(screen.getByText("王教授 (Prof. Wang)")).toBeInTheDocument();
    // nycu_id and email shown on cards
    expect(screen.getByText("student_dev")).toBeInTheDocument();
    expect(screen.getByText("student@example.com")).toBeInTheDocument();
    // Per-card login buttons
    expect(
      screen.getByRole("button", { name: "Login as Student" })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Login as Professor" })
    ).toBeInTheDocument();
  });

  it("should show empty state when API returns no users", async () => {
    getMockUsersSpy.mockResolvedValue({ success: true, message: "", data: [] });
    render(<DevLoginPage />);

    await waitFor(() => {
      expect(screen.getByText(/No users found/)).toBeInTheDocument();
    });
  });

  it("should show error when loading users fails with network error", async () => {
    getMockUsersSpy.mockRejectedValue(new Error("Failed to fetch"));
    render(<DevLoginPage />);

    await waitFor(() => {
      expect(
        screen.getByText(/Backend server is not running or not accessible/)
      ).toBeInTheDocument();
    });
  });

  it("should show error when API responds with success=false", async () => {
    getMockUsersSpy.mockResolvedValue({
      success: false,
      message: "database offline",
      data: undefined,
    });
    render(<DevLoginPage />);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load users: database offline")
      ).toBeInTheDocument();
    });
  });

  it("should log in via card click and redirect to main page", async () => {
    render(<DevLoginPage />);

    const studentName = await screen.findByText("張小明 (Zhang Xiaoming)");
    const studentCard = studentName.closest(".cursor-pointer");
    expect(studentCard).toBeInTheDocument();

    fireEvent.click(studentCard!);

    await waitFor(() => {
      expect(mockSSOLoginSpy).toHaveBeenCalledWith("student_dev");
      expect(mockAuthLogin).toHaveBeenCalledWith(
        "mock_token_123",
        loggedInUser
      );
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });

  it("should log in via the card login button", async () => {
    render(<DevLoginPage />);

    const loginButton = await screen.findByRole("button", {
      name: "Login as Professor",
    });
    fireEvent.click(loginButton);

    await waitFor(() => {
      expect(mockSSOLoginSpy).toHaveBeenCalledWith("professor_dev");
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });

  it("should show error when mock login responds with success=false", async () => {
    mockSSOLoginSpy.mockResolvedValue({
      success: false,
      message: "user disabled",
      data: undefined,
    });
    render(<DevLoginPage />);

    const studentName = await screen.findByText("張小明 (Zhang Xiaoming)");
    fireEvent.click(studentName.closest(".cursor-pointer")!);

    await waitFor(() => {
      expect(
        screen.getByText("Mock login failed: user disabled")
      ).toBeInTheDocument();
    });
    expect(mockAuthLogin).not.toHaveBeenCalled();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("should show error when mock login rejects", async () => {
    mockSSOLoginSpy.mockRejectedValue(new Error("Failed to fetch"));
    render(<DevLoginPage />);

    const studentName = await screen.findByText("張小明 (Zhang Xiaoming)");
    fireEvent.click(studentName.closest(".cursor-pointer")!);

    await waitFor(() => {
      expect(
        screen.getByText(/Backend server is not running or not accessible/)
      ).toBeInTheDocument();
    });
  });

  it("should reload the user list via Refresh Users button", async () => {
    render(<DevLoginPage />);

    await screen.findByText("張小明 (Zhang Xiaoming)");
    expect(getMockUsersSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "Refresh Users" }));

    await waitFor(() => {
      expect(getMockUsersSpy).toHaveBeenCalledTimes(2);
    });
  });

  it("should display instructions clearly", async () => {
    render(<DevLoginPage />);

    await screen.findByText("張小明 (Zhang Xiaoming)");
    expect(screen.getByText("Instructions:")).toBeInTheDocument();
    expect(
      screen.getByText(/Click any user card to simulate login/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/You'll be automatically redirected to the main page/)
    ).toBeInTheDocument();
  });
});

describe("DevLoginPage Production Mode", () => {
  // The component checks NODE_ENV + hostname + pathname at RENDER time
  // (not module load), so we can flip process.env.NODE_ENV per test.
  // jsdom defaults to localhost which the component treats as a dev host,
  // so we must also swap window.location to a production-looking host.
  const originalLocation = window.location;
  const originalNodeEnv = process.env.NODE_ENV;

  beforeEach(() => {
    jest.clearAllMocks();
    (useRouter as jest.Mock).mockReturnValue({ push: mockPush });
    installApiSpies();

    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: {
        ...originalLocation,
        hostname: "ss.nycu.edu.tw",
        pathname: "/",
        origin: "https://ss.nycu.edu.tw",
      },
    });
    Object.defineProperty(process.env, "NODE_ENV", {
      value: "production",
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      configurable: true,
      writable: true,
      value: originalLocation,
    });
    Object.defineProperty(process.env, "NODE_ENV", {
      value: originalNodeEnv,
      writable: true,
      configurable: true,
    });
    jest.restoreAllMocks();
  });

  it("should not render in production mode on a non-dev host", () => {
    const { container } = render(<DevLoginPage />);
    expect(container.firstChild).toBeNull();
    expect(getMockUsersSpy).not.toHaveBeenCalled();
  });

  it("should redirect to home page in production", async () => {
    render(<DevLoginPage />);
    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/");
    });
  });
});
