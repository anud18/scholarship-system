import { render, screen, waitFor } from "@testing-library/react";
import { ScholarshipTimeline } from "../scholarship-timeline";
import { apiClient } from "@/lib/api";

// Mock useAuth: the REAL useScholarshipPermissions hook (used un-mocked below)
// reads the current user from it.
//
// NOTE: do NOT jest.mock("@/hooks/use-scholarship-permissions") here — the
// stale root-level manual mock (__mocks__/@/hooks/use-scholarship-permissions.ts)
// shadows factory mocks for that specifier, which is why this suite's API
// mocking silently never worked. Instead we drive the real hook through the
// api layer (PR #911 pattern): spy on apiClient.admin.getMyScholarships for
// permissions and apiClient.scholarships.getAll for timeline data.
const mockUseAuth = jest.fn();
jest.mock("@/hooks/use-auth", () => ({
  useAuth: () => mockUseAuth(),
}));

// SemesterSelector fetches reference data through apiClient on mount;
// stub it out so timeline tests only exercise the timeline itself.
jest.mock("@/components/semester-selector", () => ({
  __esModule: true,
  default: () => <div data-testid="semester-selector" />,
}));

// Silence component/hook debug logging
jest.mock("@/lib/utils/logger", () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

describe("ScholarshipTimeline Component", () => {
  const mockUser = {
    id: "1",
    name: "Test User",
    email: "test@example.com",
    role: "admin" as const,
  };

  const mockScholarships = [
    {
      id: 1,
      code: "ACADEMIC_EXCELLENCE",
      name: "學業優秀獎學金",
      name_en: "Academic Excellence Scholarship",
      academic_year: 113,
      semester: "first",
      application_start_date: "2024-09-01T00:00:00Z",
      application_end_date: "2024-09-30T23:59:59Z",
      professor_review_start: "2024-10-01T00:00:00Z",
      professor_review_end: "2024-10-15T23:59:59Z",
      college_review_start: "2024-10-16T00:00:00Z",
      college_review_end: "2024-10-31T23:59:59Z",
    },
    {
      id: 2,
      code: "NEED_BASED",
      name: "清寒獎學金",
      name_en: "Need-Based Scholarship",
      academic_year: 113,
      semester: "first",
      application_start_date: "2024-09-01T00:00:00Z",
      application_end_date: "2024-09-30T23:59:59Z",
    },
  ];

  let getAllSpy: jest.SpyInstance;
  let getMyScholarshipsSpy: jest.SpyInstance;

  beforeEach(() => {
    getAllSpy = jest.spyOn(apiClient.scholarships, "getAll").mockResolvedValue({
      success: true,
      // The component only reads the snake_case fields it maps; cast keeps
      // the fixture minimal instead of building full ScholarshipType rows.
      data: mockScholarships as never,
      message: "Success",
    });
    // Real useScholarshipPermissions loads the allowed-scholarship list from
    // this endpoint for admin/college users; default to "no permissions".
    getMyScholarshipsSpy = jest
      .spyOn(apiClient.admin, "getMyScholarships")
      .mockResolvedValue({ success: true, message: "Success", data: [] });

    // Default mock for useAuth
    mockUseAuth.mockReturnValue({
      user: mockUser,
      isAuthenticated: true,
    });
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("should show all scholarships for super admin", async () => {
    const superAdminUser = { ...mockUser, role: "super_admin" as const };
    mockUseAuth.mockReturnValue({
      user: superAdminUser,
      isAuthenticated: true,
    });

    render(<ScholarshipTimeline user={superAdminUser} />);

    await waitFor(() => {
      expect(screen.getByText("獎學金時間軸")).toBeInTheDocument();
    });

    // Active-tab scholarship appears in both the tab trigger and the tab
    // content, so assert presence with getAllByText.
    await waitFor(() => {
      expect(
        screen.getAllByText("學業優秀獎學金").length
      ).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("清寒獎學金").length).toBeGreaterThanOrEqual(
        1
      );
    });
    expect(getAllSpy).toHaveBeenCalled();
  });

  it("should filter scholarships based on admin permissions", async () => {
    // Admin only has permission for scholarship id 1
    getMyScholarshipsSpy.mockResolvedValue({
      success: true,
      message: "Success",
      data: [
        {
          id: 1,
          code: "ACADEMIC_EXCELLENCE",
          name: "學業優秀獎學金",
          name_en: "Academic Excellence Scholarship",
        },
      ],
    });

    render(<ScholarshipTimeline user={mockUser} />);

    await waitFor(() => {
      expect(screen.getByText("獎學金時間軸")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getAllByText("學業優秀獎學金").length
      ).toBeGreaterThanOrEqual(1);
      expect(screen.queryByText("清寒獎學金")).not.toBeInTheDocument();
    });
  });

  it("should show no permissions message for admin with no permissions", async () => {
    render(<ScholarshipTimeline user={mockUser} />);

    await waitFor(() => {
      expect(screen.getByText("您沒有獎學金權限")).toBeInTheDocument();
      expect(
        screen.getByText("您目前沒有被分配任何獎學金權限，請聯繫管理員")
      ).toBeInTheDocument();
    });
  });

  it("should not render for student role", () => {
    const studentUser = { ...mockUser, role: "student" as const };
    mockUseAuth.mockReturnValue({ user: studentUser, isAuthenticated: true });

    const { container } = render(<ScholarshipTimeline user={studentUser} />);
    expect(container.firstChild).toBeNull();
    expect(getAllSpy).not.toHaveBeenCalled();
  });

  it("should show loading state while data is loading", () => {
    // Keep both the permissions fetch and the timeline fetch pending
    getMyScholarshipsSpy.mockImplementation(() => new Promise(() => {}));
    getAllSpy.mockImplementation(() => new Promise(() => {}));

    render(<ScholarshipTimeline user={mockUser} />);

    expect(screen.getByText("載入獎學金時間軸中...")).toBeInTheDocument();
  });

  it("should handle API errors gracefully", async () => {
    getAllSpy.mockRejectedValue(new Error("API Error"));

    render(<ScholarshipTimeline user={mockUser} />);

    await waitFor(() => {
      expect(screen.getByText("載入獎學金時間軸失敗")).toBeInTheDocument();
      expect(screen.getByText("重試")).toBeInTheDocument();
    });
  });
});
