import React from "react";
import { renderHook, render, act, waitFor } from "@testing-library/react";
import { ReactNode, Component, ErrorInfo } from "react";
import { AuthProvider, useAuth } from "../use-auth";
import { apiClient, User, ApiResponse } from "@/lib/api";

// jest.mock("@/lib/api") is NOT hoisted above ESM imports in this setup, so the
// hook captures the real apiClient — spy on its methods instead of mocking the module.

// SSO callbacks build the user from token claims only — no college_code.
const makeStubUser = (): User => ({
  id: "5",
  nycu_id: "collegeuser",
  role: "college",
  name: "collegeuser",
  email: "collegeuser@nycu.edu.tw",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
});

// /auth/me payload: the backend serializes id as a NUMBER and includes the
// college fields the JWT stub lacks.
const makeServerUserResponse = (): ApiResponse<User> => ({
  success: true,
  message: "ok",
  data: {
    id: 5 as unknown as string,
    nycu_id: "collegeuser",
    name: "資訊學院承辦人",
    email: "collegeuser@nycu.edu.tw",
    role: "college",
    college_code: "C",
    college_name: "資訊學院",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
});

// Test wrapper with AuthProvider
const wrapper = ({ children }: { children: ReactNode }) => (
  <AuthProvider>{children}</AuthProvider>
);

// Error boundary component for testing error cases
class TestErrorBoundary extends Component<
  {
    children: ReactNode;
    onError: (error: Error, errorInfo: ErrorInfo) => void;
  },
  { hasError: boolean; error?: Error }
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.props.onError(error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return <div>Error caught</div>;
    }
    return this.props.children;
  }
}

// Component that uses the hook (for error boundary testing)
function TestComponent() {
  useAuth();
  return <div>Test</div>;
}

describe("useAuth Hook", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("should provide auth context", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current).toBeDefined();
    expect(typeof result.current.login).toBe("function");
    expect(typeof result.current.logout).toBe("function");
    expect(typeof result.current.updateUser).toBe("function");
    expect(typeof result.current.isAuthenticated).toBe("boolean");
    expect(typeof result.current.isLoading).toBe("boolean");
  });

  it("should initialize with correct default state", () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    expect(result.current.user).toBe(null);
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.error).toBe(null);
  });

  it("should throw error when used outside provider", () => {
    let caughtError: Error | null = null;

    const handleError = (error: Error) => {
      caughtError = error;
    };

    // Suppress console.error for this test
    const consoleSpy = jest
      .spyOn(console, "error")
      .mockImplementation(() => {});

    render(
      <TestErrorBoundary onError={handleError}>
        <TestComponent />
      </TestErrorBoundary>
    );

    expect(caughtError).not.toBeNull();
    expect(caughtError!.message).toBe(
      "useAuth must be used within AuthProvider"
    );

    // Restore console.error
    consoleSpy.mockRestore();
  });

  it("refreshes the JWT-derived stub user from /auth/me after login", async () => {
    jest
      .spyOn(apiClient.auth, "getCurrentUser")
      .mockResolvedValue(makeServerUserResponse());

    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login("mock-token", makeStubUser());
    });

    await waitFor(() => {
      expect(result.current.user?.college_code).toBe("C");
    });
    expect(result.current.user?.name).toBe("資訊學院承辦人");
    // The backend sends a numeric id; normalizeUser must coerce it to string.
    expect(result.current.user?.id).toBe("5");
    expect(result.current.isAuthenticated).toBe(true);
  });

  it("keeps the stored user when /auth/me refresh fails", async () => {
    jest
      .spyOn(apiClient.auth, "getCurrentUser")
      .mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login("mock-token", makeStubUser());
    });

    await waitFor(() => {
      expect(result.current.isAuthenticated).toBe(true);
    });
    expect(result.current.user?.nycu_id).toBe("collegeuser");
    expect(result.current.error).toBe(null);
  });

  it("does not resurrect the session when /auth/me resolves after logout", async () => {
    let resolveMe: (value: ApiResponse<User>) => void = () => {};
    jest.spyOn(apiClient.auth, "getCurrentUser").mockReturnValue(
      new Promise<ApiResponse<User>>(resolve => {
        resolveMe = resolve;
      })
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => {
      result.current.login("mock-token", makeStubUser());
    });
    act(() => {
      result.current.logout();
    });

    await act(async () => {
      resolveMe(makeServerUserResponse());
      await Promise.resolve();
    });

    expect(result.current.user).toBe(null);
    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem("user")).toBe(null);
    expect(localStorage.getItem("dev_user")).toBe(null);
  });
});
