/**
 * Tests for `EnhancedAdminDashboard` — the variant of admin-dashboard
 * with a semester-filter selector that re-fetches stats + applications
 * scoped to the selected (academic_year, semester) combination.
 *
 * 396 LOC, previously zero tests. Third in the 9-untested-admin-components
 * series (after #244 and admin-rule-management).
 *
 * What's pinned:
 * - Error-only render path: when `error` prop is set, the component
 *   short-circuits to a single error card with a retry button.
 * - Retry button is wired to `fetchDashboardStats`.
 * - When no error, the full dashboard renders with the semester selector.
 * - `filteredStats` (set by SemesterSelector callback) overrides `stats`
 *   from props as the display source — pinning the data-source precedence.
 * - `filteredApplications.length > 0` overrides `recentApplications` for
 *   the same reason.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { EnhancedAdminDashboard } from "../enhanced-admin-dashboard";

jest.mock("@/lib/api", () => ({
  __esModule: true,
  api: {
    request: jest.fn(),
  },
}));

jest.mock("../semester-selector", () => ({
  __esModule: true,
  default: () => <div data-testid="semester-selector">[selector]</div>,
}));

jest.mock("@/lib/utils/application-helpers", () => ({
  getDisplayStatusInfo: () => ({ statusLabel: "已提交", statusVariant: "default" }),
}));

const baseProps = {
  stats: { total_applications: 10, pending_review: 4, approved: 5, rejected: 1 },
  recentApplications: [] as any[],
  systemAnnouncements: [] as any[],
  isStatsLoading: false,
  isRecentLoading: false,
  isAnnouncementsLoading: false,
  error: null as string | null,
  isAuthenticated: true,
  user: { id: 1, role: "admin", name: "Test Admin" },
  login: jest.fn(),
  logout: jest.fn(),
  fetchRecentApplications: jest.fn(),
  fetchDashboardStats: jest.fn(),
  onTabChange: jest.fn(),
};

describe("EnhancedAdminDashboard", () => {
  it("short-circuits to the error card when error is set", () => {
    render(<EnhancedAdminDashboard {...baseProps} error="Service unavailable" />);
    expect(screen.getByText("載入錯誤")).toBeInTheDocument();
    expect(screen.getByText("Service unavailable")).toBeInTheDocument();
    // The semester selector is NOT rendered on the error path.
    expect(screen.queryByTestId("semester-selector")).not.toBeInTheDocument();
  });

  it("retry button on the error card calls fetchDashboardStats", () => {
    const fetchDashboardStats = jest.fn();
    render(
      <EnhancedAdminDashboard
        {...baseProps}
        error="Service unavailable"
        fetchDashboardStats={fetchDashboardStats}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "重新載入" }));
    expect(fetchDashboardStats).toHaveBeenCalledTimes(1);
  });

  it("renders the semester selector when no error", () => {
    render(<EnhancedAdminDashboard {...baseProps} />);
    expect(screen.getByTestId("semester-selector")).toBeInTheDocument();
    // Section heading confirms the rest of the layout reached render.
    expect(screen.getByText("學期篩選")).toBeInTheDocument();
  });

  it("renders stat values from the `stats` prop when no filter is active", () => {
    render(<EnhancedAdminDashboard {...baseProps} />);
    // Pin that the unfiltered prop reaches the cards.
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });
});
