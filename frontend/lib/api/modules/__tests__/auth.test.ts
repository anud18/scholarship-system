/**
 * Tests for `frontend/lib/api/modules/auth.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives all
 * authentication flows in the app — login, logout, mock SSO
 * (dev), token refresh, registration, getCurrentUser.
 *
 * SECURITY-critical side effects:
 *  - login / refreshToken / mockSSOLogin: must call
 *    typedClient.setToken(access_token) on success
 *  - logout: must call typedClient.clearToken()
 *  - On API failure, MUST NOT call setToken (otherwise a
 *    stale/null token gets persisted)
 *
 * Wave 6a116 pins these side-effect contracts + URL paths.
 *
 * 14 cases.
 */

import { createAuthApi } from "../auth";
import { typedClient } from "../../typed-client";

// Mock the typedClient module
jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
    },
    setToken: jest.fn(),
    clearToken: jest.fn(),
  },
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
};
const mockedSetToken = typedClient.setToken as jest.Mock;
const mockedClearToken = typedClient.clearToken as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createAuthApi", () => {
  // ─── login ──────────────────────────────────────────────────────────

  it("login POSTs to /api/v1/auth/login with username + password", async () => {
    mockedRaw.POST.mockResolvedValueOnce({
      data: {
        success: true,
        message: "",
        data: { access_token: "tok", token_type: "bearer", expires_in: 3600, user: {} },
      },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.login("alice", "secret");
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/auth/login", {
      body: { username: "alice", password: "secret" },
    });
  });

  it("login calls setToken on success", async () => {
    // SECURITY: token persisted to typedClient for subsequent
    // authed requests.
    mockedRaw.POST.mockResolvedValueOnce({
      data: {
        success: true,
        message: "",
        data: { access_token: "new-tok-xyz", token_type: "bearer", expires_in: 3600, user: {} },
      },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.login("a", "b");
    expect(mockedSetToken).toHaveBeenCalledWith("new-tok-xyz");
  });

  it("login does NOT call setToken on failure", async () => {
    // SECURITY: on auth failure, no stale token must be written.
    // Pin so a refactor doesn't accidentally setToken("") or
    // setToken(undefined).
    mockedRaw.POST.mockResolvedValueOnce({
      error: { detail: "Invalid credentials" },
      response: { status: 401, ok: false },
    });
    const api = createAuthApi();
    await api.login("a", "wrong");
    expect(mockedSetToken).not.toHaveBeenCalled();
  });

  it("login does NOT call setToken when access_token absent", async () => {
    // Pin: success=true but data.access_token missing → no token
    // write. Defensive against malformed backend responses.
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: {} },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.login("a", "b");
    expect(mockedSetToken).not.toHaveBeenCalled();
  });

  // ─── logout ─────────────────────────────────────────────────────────

  it("logout calls clearToken", async () => {
    // Pin: clearToken always called (no API call needed).
    const api = createAuthApi();
    await api.logout();
    expect(mockedClearToken).toHaveBeenCalledTimes(1);
  });

  it("logout returns success ApiResponse without backend call", async () => {
    // Pin: logout is client-side only (no POST to /auth/logout).
    // Pin so a refactor that adds a network call doesn't silently
    // delay logout UX.
    const api = createAuthApi();
    const result = await api.logout();
    expect(result.success).toBe(true);
    expect(result.message).toBe("Logged out successfully");
    expect(mockedRaw.POST).not.toHaveBeenCalled();
  });

  // ─── register ───────────────────────────────────────────────────────

  it("register POSTs to /api/v1/auth/register", async () => {
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: {} },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.register({
      username: "bob",
      email: "bob@x.com",
      password: "p",
      full_name: "Bob",
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/auth/register", {
      body: { username: "bob", email: "bob@x.com", password: "p", full_name: "Bob" },
    });
  });

  it("register does NOT call setToken (registration is separate from login)", async () => {
    // Pin: register endpoint doesn't auto-login. Pin so a
    // refactor doesn't silently bypass the login confirmation
    // flow.
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: { access_token: "should-not-be-set" } },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.register({ username: "a", email: "a@b.com", password: "p", full_name: "A" });
    expect(mockedSetToken).not.toHaveBeenCalled();
  });

  // ─── getCurrentUser ─────────────────────────────────────────────────

  it("getCurrentUser GETs /api/v1/auth/me", async () => {
    mockedRaw.GET.mockResolvedValueOnce({
      data: { success: true, message: "", data: { id: "1", name: "x" } },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.getCurrentUser();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  // ─── refreshToken ───────────────────────────────────────────────────

  it("refreshToken POSTs to /api/v1/auth/refresh", async () => {
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: { access_token: "fresh", token_type: "bearer" } },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.refreshToken();
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/auth/refresh", {});
  });

  it("refreshToken updates setToken on success", async () => {
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: { access_token: "rolled-token" } },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.refreshToken();
    expect(mockedSetToken).toHaveBeenCalledWith("rolled-token");
  });

  // ─── mockSSOLogin ───────────────────────────────────────────────────

  it("mockSSOLogin POSTs nycu_id to /api/v1/auth/mock-sso/login", async () => {
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: { access_token: "mock-tok", user: {} } },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.mockSSOLogin("310460031");
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/auth/mock-sso/login", {
      body: { nycu_id: "310460031" },
    });
  });

  it("mockSSOLogin sets token on success", async () => {
    // Pin: mock SSO mirrors real login token-write behaviour.
    mockedRaw.POST.mockResolvedValueOnce({
      data: { success: true, message: "", data: { access_token: "mock-tok-123", user: {} } },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.mockSSOLogin("x");
    expect(mockedSetToken).toHaveBeenCalledWith("mock-tok-123");
  });

  // ─── getMockUsers ───────────────────────────────────────────────────

  it("getMockUsers GETs /api/v1/auth/mock-sso/users", async () => {
    mockedRaw.GET.mockResolvedValueOnce({
      data: { success: true, message: "", data: [] },
      response: { status: 200, ok: true },
    });
    const api = createAuthApi();
    await api.getMockUsers();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/auth/mock-sso/users");
  });
});
