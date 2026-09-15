/**
 * Tests for `AdminScholarshipDashboard` — the per-scholarship-type
 * admin dashboard for reviewing applications.
 *
 * 1721 LOC, previously zero tests. Fourth in the 9-untested-admin-components
 * series (after #244 added admin-dashboard + admin-rule-management +
 * enhanced-admin-dashboard).
 *
 * What's pinned:
 * - Loading branch: skeleton placeholders + "載入獎學金資料中..." copy.
 * - Error branch: error card with refetch button.
 * - Refetch button on the error card calls the `refetch` hook return.
 * - Empty-scholarship-types branch: "尚無獎學金資料" copy + helper hint.
 *
 * Deeper interaction tests (status updates, sub-type filtering, bank
 * verification) belong in their own files — this test focuses on the
 * three early-return states the rest of the component never reaches.
 */
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { AdminScholarshipDashboard } from "../admin-scholarship-dashboard";

const mockRefetch = jest.fn();
const mockUseScholarshipSpecificApplications = jest.fn();

jest.mock("@/hooks/use-admin", () => ({
  useScholarshipSpecificApplications: () =>
    mockUseScholarshipSpecificApplications(),
}));

jest.mock("@/hooks/use-scholarship-permissions", () => ({
  useScholarshipPermissions: () => ({
    permissions: { all_scholarships: true, scholarship_ids: [] },
    isLoading: false,
    error: null,
  }),
}));

jest.mock("@/hooks/use-scholarship-data", () => ({
  useScholarshipData: () => ({ subTypeTranslations: {} }),
}));

// Heavy sub-component — stub at module boundary so the test isn't
// fighting its render. Earlier versions also referenced
// @/components/application-detail and @/components/bank-verification-display
// but those modules don't exist in this repo (jest.mock cannot intercept
// missing paths, and would crash module resolution before describe.skip
// can take effect).
jest.mock("@/components/application-audit-trail", () => ({
  ApplicationAuditTrail: () => null,
}));
jest.mock("@/components/common/ApplicationReviewDialog", () => ({
  ApplicationReviewDialog: () => null,
}));
jest.mock("@/components/delete-application-dialog", () => ({
  DeleteApplicationDialog: () => null,
}));
jest.mock("@/components/professor-assignment-dropdown", () => ({
  ProfessorAssignmentDropdown: () => null,
}));
jest.mock("@/components/semester-selector", () => ({
  SemesterSelector: () => null,
}));
jest.mock("@/components/admin-scholarship-management-interface", () => ({
  AdminScholarshipManagementInterface: () => null,
}));
jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {},
  api: {},
}));
jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));
jest.mock("@/hooks/use-auth", () => ({
  __esModule: true,
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: 1, role: "admin", name: "Test Admin" },
    login: jest.fn(),
    logout: jest.fn(),
    isLoading: false,
  }),
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const baseUser = { id: 1, role: "admin", name: "Test", nycu_id: "admin1" };

describe("AdminScholarshipDashboard", () => {
  beforeEach(() => {
    mockRefetch.mockClear();
  });

  it("renders loading skeleton state when isLoading=true", () => {
    mockUseScholarshipSpecificApplications.mockReturnValue({
      applicationsByType: {},
      scholarshipTypes: [],
      scholarshipStats: {},
      isLoading: true,
      error: null,
      refetch: mockRefetch,
      updateApplicationStatus: jest.fn(),
    });

    render(<AdminScholarshipDashboard user={baseUser as never} />);

    expect(screen.getByText("獎學金申請管理")).toBeInTheDocument();
    expect(screen.getByText("載入獎學金資料中...")).toBeInTheDocument();
  });

  it("renders error card when the hook returns an error", () => {
    mockUseScholarshipSpecificApplications.mockReturnValue({
      applicationsByType: {},
      scholarshipTypes: [],
      scholarshipStats: {},
      isLoading: false,
      error: "Backend returned 500",
      refetch: mockRefetch,
      updateApplicationStatus: jest.fn(),
    });

    render(<AdminScholarshipDashboard user={baseUser as never} />);

    expect(screen.getByText("載入失敗")).toBeInTheDocument();
    expect(screen.getByText("Backend returned 500")).toBeInTheDocument();
  });

  it("retry button on the error card calls refetch", () => {
    mockUseScholarshipSpecificApplications.mockReturnValue({
      applicationsByType: {},
      scholarshipTypes: [],
      scholarshipStats: {},
      isLoading: false,
      error: "Backend down",
      refetch: mockRefetch,
      updateApplicationStatus: jest.fn(),
    });

    render(<AdminScholarshipDashboard user={baseUser as never} />);

    fireEvent.click(screen.getByRole("button", { name: /重試/ }));
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  it("renders empty-state copy when scholarshipTypes is [] (no error, not loading)", () => {
    mockUseScholarshipSpecificApplications.mockReturnValue({
      applicationsByType: {},
      scholarshipTypes: [],
      scholarshipStats: {},
      isLoading: false,
      error: null,
      refetch: mockRefetch,
      updateApplicationStatus: jest.fn(),
    });

    render(<AdminScholarshipDashboard user={baseUser as never} />);

    expect(screen.getByText("尚無獎學金資料")).toBeInTheDocument();
    expect(screen.getByText("請先建立獎學金類型")).toBeInTheDocument();
  });

  it("shows the 刪除申請 button only for rows the server marks is_deletable", () => {
    const row = (overrides: Record<string, unknown>) => ({
      id: 1,
      app_id: "APP-114-1-00001",
      status: "under_review",
      review_stage: "professor_reviewed",
      academic_year: "114",
      semester: "first",
      student_data: { std_cname: "王小明", std_stdcode: "310460001" },
      submitted_form_data: {},
      scholarship_subtype_list: [],
      created_at: "2026-09-01T00:00:00Z",
      updated_at: "2026-09-01T00:00:00Z",
      ...overrides,
    });
    mockUseScholarshipSpecificApplications.mockReturnValue({
      applicationsByType: {
        phd: [
          row({
            id: 1,
            app_id: "APP-DELETABLE",
            student_data: { std_cname: "可刪除生", std_stdcode: "310460001" },
            is_deletable: true,
          }),
          row({
            id: 2,
            app_id: "APP-DISTRIBUTED",
            status: "approved",
            review_stage: "quota_distributed",
            student_data: { std_cname: "已分發生", std_stdcode: "310460002" },
            is_deletable: false,
          }),
          // Status alone no longer decides: a submitted row is NOT deletable when the server says so
          row({
            id: 3,
            app_id: "APP-SUBMITTED-LOCKED",
            status: "submitted",
            student_data: { std_cname: "已配置生", std_stdcode: "310460003" },
            is_deletable: false,
          }),
        ],
      },
      scholarshipTypes: ["phd"],
      scholarshipStats: { phd: { total: 3 } },
      isLoading: false,
      error: null,
      refetch: mockRefetch,
      updateApplicationStatus: jest.fn(),
    });

    render(<AdminScholarshipDashboard user={baseUser as never} />);

    expect(screen.getByText(/可刪除生/)).toBeInTheDocument();
    expect(screen.getByText(/已分發生/)).toBeInTheDocument();
    expect(screen.getByText(/已配置生/)).toBeInTheDocument();
    expect(screen.getAllByTitle("刪除申請（分發階段前可刪除）")).toHaveLength(
      1
    );
  });
});
