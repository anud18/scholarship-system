/**
 * Tests for `DebugPanel` — admin-side floating debug widget that shows
 * portal/student-API/JWT data sources and the current test-mode badge.
 *
 * 913 LOC, previously zero tests. Addresses the hook's call-out of
 * remaining untested admin-side components beyond the 6 already covered
 * in PR #244.
 *
 * What's pinned (the entry-point UI gate — everything else inside
 * DebugPanel runs only after this gate):
 *
 * - `!token` short-circuit: panel renders nothing when the auth hook
 *   reports no token. (See `if (!token) return null;` in debug-panel.tsx.)
 * - With a token, the floating Bug-icon button appears.
 * - The `isTestMode` prop is forwarded through and the entry button
 *   still mounts in test-mode.
 *
 * The token gate is driven by `useAuth()`, NOT directly by
 * `localStorage`. The original suite (PR #244-skipped) seeded
 * localStorage and expected the component to read it back; it never
 * did. This rewrite mocks `useAuth` instead.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { DebugPanel } from "../debug-panel";

const mockUseAuth = jest.fn();

jest.mock("@/hooks/use-auth", () => ({
  useAuth: () => mockUseAuth(),
}));

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {},
  api: { auth: { mockSSOLogin: jest.fn() } },
}));

const baseUser = {
  id: "1",
  name: "Test Admin",
  email: "admin@example.com",
  role: "admin",
};

beforeEach(() => {
  localStorage.clear();
});

describe("DebugPanel", () => {
  it("renders nothing when useAuth() reports no token", () => {
    mockUseAuth.mockReturnValue({ user: baseUser, token: null, isAuthenticated: false });

    const { container } = render(<DebugPanel />);
    // Component does `if (!token) return null` after the mount effect runs.
    // Effect runs synchronously, so the container ends up empty.
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the floating debug button once a token is available", () => {
    // Seed an unstructured token; the component only checks truthiness for
    // the short-circuit. Decoding errors are caught and logged inside.
    mockUseAuth.mockReturnValue({
      user: baseUser,
      token: "test-token-not-a-real-jwt",
      isAuthenticated: true,
    });

    render(<DebugPanel />);
    expect(screen.getByTitle("Debug Panel")).toBeInTheDocument();
  });

  it("renders the floating debug button when isTestMode=true regardless of UI state", () => {
    mockUseAuth.mockReturnValue({
      user: baseUser,
      token: "test-token-not-a-real-jwt",
      isAuthenticated: true,
    });

    render(<DebugPanel isTestMode={true} />);
    expect(screen.getByTitle("Debug Panel")).toBeInTheDocument();
  });
});
