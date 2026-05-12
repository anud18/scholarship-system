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
  useScholarshipSpecificApplications: () => mockUseScholarshipSpecificApplications(),
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

// Heavy sub-components — stub at module boundary so the test isn't
// fighting their renders. Each is exercised in its own component test.
jest.mock("@/components/application-detail", () => ({
  ApplicationDetail: () => null,
}));
jest.mock("@/components/application-audit-trail", () => ({
  ApplicationAuditTrail: () => null,
}));
jest.mock("@/components/bank-verification-display", () => ({
  BankVerificationDisplay: () => null,
}));
jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {},
  api: {},
}));
jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
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
});
