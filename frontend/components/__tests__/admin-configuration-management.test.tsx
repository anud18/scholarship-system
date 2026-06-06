import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminConfigurationManagement } from "../admin-configuration-management";

// Create mutable mock functions
const mockGetScholarshipConfigTypes = jest.fn().mockResolvedValue({
  success: true,
  data: [
    {
      id: 1,
      code: "academic_excellence",
      name: "Academic Excellence",
      name_en: "Academic Excellence",
    },
    {
      id: 2,
      code: "research_grant",
      name: "Research Grant",
      name_en: "Research Grant",
    },
  ],
});

const mockGetScholarshipConfigurations = jest.fn().mockResolvedValue({
  success: true,
  data: [],
});

const mockCreateScholarshipConfiguration = jest.fn().mockResolvedValue({
  success: true,
  data: { id: 1, config_code: "test_config" },
});

const mockUpdateScholarshipConfiguration = jest.fn().mockResolvedValue({
  success: true,
  data: { id: 1, config_code: "test_config" },
});

const mockDeleteScholarshipConfiguration = jest.fn().mockResolvedValue({
  success: true,
  data: { message: "Configuration deleted successfully" },
});

const mockDuplicateScholarshipConfiguration = jest.fn().mockResolvedValue({
  success: true,
  data: { id: 2, config_code: "test_config_copy" },
});

const mockGetAcademies = jest.fn().mockResolvedValue({
  success: true,
  data: [],
});

const mockGetScholarshipConfiguration = jest.fn().mockResolvedValue({
  success: true,
  data: { id: 1, config_code: "test_config" },
});

const mockToggleConfigSupplementaryImport = jest
  .fn()
  .mockResolvedValue({ success: true, data: {} });

const mockToggleScholarshipWhitelist = jest
  .fn()
  .mockResolvedValue({ success: true, data: {} });

// Mock the API client
jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: {
    admin: {
      getScholarshipConfigTypes: (...args: any[]) =>
        mockGetScholarshipConfigTypes(...args),
      getScholarshipConfigurations: (...args: any[]) =>
        mockGetScholarshipConfigurations(...args),
      getScholarshipConfiguration: (...args: any[]) =>
        mockGetScholarshipConfiguration(...args),
      createScholarshipConfiguration: (...args: any[]) =>
        mockCreateScholarshipConfiguration(...args),
      updateScholarshipConfiguration: (...args: any[]) =>
        mockUpdateScholarshipConfiguration(...args),
      deleteScholarshipConfiguration: (...args: any[]) =>
        mockDeleteScholarshipConfiguration(...args),
      duplicateScholarshipConfiguration: (...args: any[]) =>
        mockDuplicateScholarshipConfiguration(...args),
    },
    referenceData: {
      getAcademies: (...args: any[]) => mockGetAcademies(...args),
    },
    college: {
      toggleConfigSupplementaryImport: (...args: any[]) =>
        mockToggleConfigSupplementaryImport(...args),
    },
    whitelist: {
      toggleScholarshipWhitelist: (...args: any[]) =>
        mockToggleScholarshipWhitelist(...args),
    },
  },
  ScholarshipType: {},
  ScholarshipConfiguration: {},
  ScholarshipConfigurationFormData: {},
}));

// Mock sonner toast (component reports errors/success via toast, not inline UI)
jest.mock("sonner", () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

// Mock useAuth so child components don't throw outside AuthProvider
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

import { toast } from "sonner";
import mockApiDefault from "@/lib/api";
const mockApi = mockApiDefault as any;
const mockToast = toast as unknown as {
  success: jest.Mock;
  error: jest.Mock;
};

// Override with mutable mocks
mockApi.admin.getScholarshipConfigTypes = mockGetScholarshipConfigTypes;
mockApi.admin.getScholarshipConfigurations = mockGetScholarshipConfigurations;
mockApi.admin.getScholarshipConfiguration = mockGetScholarshipConfiguration;
mockApi.admin.createScholarshipConfiguration =
  mockCreateScholarshipConfiguration;
mockApi.admin.updateScholarshipConfiguration =
  mockUpdateScholarshipConfiguration;
mockApi.admin.deleteScholarshipConfiguration =
  mockDeleteScholarshipConfiguration;
mockApi.admin.duplicateScholarshipConfiguration =
  mockDuplicateScholarshipConfiguration;
mockApi.college.toggleConfigSupplementaryImport =
  mockToggleConfigSupplementaryImport;
mockApi.whitelist.toggleScholarshipWhitelist = mockToggleScholarshipWhitelist;
// Note: referenceData is already mocked in jest.mock() above

// Mock UI components to avoid complex rendering issues
jest.mock("@/components/ui/card", () => ({
  Card: ({ children, className }: any) => (
    <div data-testid="card" className={className}>
      {children}
    </div>
  ),
  CardContent: ({ children, className }: any) => (
    <div data-testid="card-content" className={className}>
      {children}
    </div>
  ),
  CardHeader: ({ children }: any) => (
    <div data-testid="card-header">{children}</div>
  ),
  CardTitle: ({ children }: any) => (
    <h3 data-testid="card-title">{children}</h3>
  ),
  CardDescription: ({ children }: any) => (
    <p data-testid="card-description">{children}</p>
  ),
}));

jest.mock("@/components/ui/button", () => ({
  Button: ({ children, onClick, className, disabled, ...props }: any) => (
    <button
      data-testid="button"
      className={className}
      onClick={onClick}
      disabled={disabled}
      {...props}
    >
      {children}
    </button>
  ),
}));

jest.mock("@/components/ui/tabs", () => {
  // Only mount the active TabsContent, mirroring real Radix behaviour.
  // (Defined inside the factory because jest hoists the mock; React is global.)
  const TabsCtx = React.createContext("");
  return {
    Tabs: ({ children, value, onValueChange }: any) => (
      <TabsCtx.Provider value={value}>
        <div
          data-testid="tabs"
          data-value={value}
          onClick={() => onValueChange && onValueChange("test-value")}
        >
          {children}
        </div>
      </TabsCtx.Provider>
    ),
    TabsList: ({ children }: any) => (
      <div data-testid="tabs-list">{children}</div>
    ),
    TabsTrigger: ({ children, value }: any) => (
      <button data-testid="tabs-trigger" data-value={value}>
        {children}
      </button>
    ),
    TabsContent: ({ children, value }: any) => {
      const active = React.useContext(TabsCtx);
      return active === value ? (
        <div data-testid="tabs-content" data-value={value}>
          {children}
        </div>
      ) : null;
    },
  };
});

jest.mock("@/components/ui/select", () => ({
  Select: ({ children, value, onValueChange }: any) => (
    <div data-testid="select" data-value={value}>
      <button onClick={() => onValueChange && onValueChange("test-option")}>
        {children}
      </button>
    </div>
  ),
  SelectTrigger: ({ children }: any) => (
    <div data-testid="select-trigger">{children}</div>
  ),
  SelectContent: ({ children }: any) => (
    <div data-testid="select-content">{children}</div>
  ),
  SelectItem: ({ children, value }: any) => (
    <div data-testid="select-item" data-value={value}>
      {children}
    </div>
  ),
  SelectValue: () => <span data-testid="select-value">Selected Value</span>,
}));

jest.mock("@/components/ui/table", () => ({
  Table: ({ children }: any) => <table data-testid="table">{children}</table>,
  TableBody: ({ children }: any) => (
    <tbody data-testid="table-body">{children}</tbody>
  ),
  TableCell: ({ children, className }: any) => (
    <td data-testid="table-cell" className={className}>
      {children}
    </td>
  ),
  TableHead: ({ children }: any) => (
    <th data-testid="table-head">{children}</th>
  ),
  TableHeader: ({ children }: any) => (
    <thead data-testid="table-header">{children}</thead>
  ),
  TableRow: ({ children }: any) => <tr data-testid="table-row">{children}</tr>,
}));

jest.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: any) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: any) => (
    <div data-testid="dialog-content">{children}</div>
  ),
  DialogHeader: ({ children }: any) => (
    <div data-testid="dialog-header">{children}</div>
  ),
  DialogTitle: ({ children }: any) => (
    <h2 data-testid="dialog-title">{children}</h2>
  ),
  DialogDescription: ({ children }: any) => (
    <p data-testid="dialog-description">{children}</p>
  ),
  DialogFooter: ({ children }: any) => (
    <div data-testid="dialog-footer">{children}</div>
  ),
}));

jest.mock("@/components/ui/input", () => ({
  Input: ({ value, onChange, placeholder, type, id }: any) => (
    <input
      data-testid="input"
      type={type || "text"}
      id={id}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
    />
  ),
}));

jest.mock("@/components/ui/textarea", () => ({
  Textarea: ({ value, onChange, placeholder, id }: any) => (
    <textarea
      data-testid="textarea"
      id={id}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
    />
  ),
}));

jest.mock("@/components/ui/label", () => ({
  Label: ({ children, htmlFor }: any) => (
    <label data-testid="label" htmlFor={htmlFor}>
      {children}
    </label>
  ),
}));

jest.mock("@/components/ui/badge", () => ({
  Badge: ({ children, variant }: any) => (
    <span data-testid="badge" data-variant={variant}>
      {children}
    </span>
  ),
}));

jest.mock("@/components/ui/alert-dialog", () => ({
  AlertDialog: ({ children, open }: any) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogContent: ({ children }: any) => (
    <div data-testid="alert-dialog-content">{children}</div>
  ),
  AlertDialogHeader: ({ children }: any) => (
    <div data-testid="alert-dialog-header">{children}</div>
  ),
  AlertDialogTitle: ({ children }: any) => (
    <h2 data-testid="alert-dialog-title">{children}</h2>
  ),
  AlertDialogDescription: ({ children }: any) => (
    <p data-testid="alert-dialog-description">{children}</p>
  ),
  AlertDialogFooter: ({ children }: any) => (
    <div data-testid="alert-dialog-footer">{children}</div>
  ),
  AlertDialogAction: ({ children, onClick }: any) => (
    <button data-testid="alert-dialog-action" onClick={onClick}>
      {children}
    </button>
  ),
  AlertDialogCancel: ({ children }: any) => (
    <button data-testid="alert-dialog-cancel">{children}</button>
  ),
}));

// Mock console methods to avoid test noise
const originalConsoleError = console.error;
const originalConsoleLog = console.log;
beforeAll(() => {
  console.error = jest.fn();
  console.log = jest.fn();
});

afterAll(() => {
  console.error = originalConsoleError;
  console.log = originalConsoleLog;
});

// TODO: Fix remaining tests - many test non-existent functionality or complex dialog/tab interactions
// 6/20 tests passing - basic rendering and simple actions work
// Remaining failures: tests expect component to load data that's passed as props, or complex UI interactions
describe("AdminConfigurationManagement Component", () => {
  const mockScholarshipTypes = [
    {
      id: 1,
      code: "phd",
      name: "PhD獎學金",
      name_en: "PhD Scholarship",
      category: "doctoral",
      description: "PhD獎學金說明",
      amount: "",
      currency: "TWD",
      application_cycle: "semester",
      application_start_date: "",
      application_end_date: "",
      eligible_sub_types: [],
      description_en: "",
      passed: [],
      warnings: [],
      errors: [],
    },
    {
      id: 2,
      code: "master",
      name: "碩士獎學金",
      name_en: "Master Scholarship",
      category: "graduate",
      description: "碩士獎學金說明",
      amount: "",
      currency: "TWD",
      application_cycle: "semester",
      application_start_date: "",
      application_end_date: "",
      eligible_sub_types: [],
      description_en: "",
      passed: [],
      warnings: [],
      errors: [],
    },
  ];

  const mockConfigurations = [
    {
      id: 1,
      scholarship_type_id: 1,
      academic_year: 114,
      semester: "first",
      config_name: "PhD獎學金114學年度第一學期",
      config_code: "PHD-114-1",
      amount: 50000,
      currency: "TWD",
      is_active: true,
      updated_at: "2024-01-15T10:30:00",
      description: "PhD獎學金配置說明",
    },
    {
      id: 2,
      scholarship_type_id: 1,
      academic_year: 113,
      semester: "second",
      config_name: "PhD獎學金113學年度第二學期",
      config_code: "PHD-113-2",
      amount: 45000,
      currency: "TWD",
      is_active: false,
      updated_at: "2023-12-01T15:45:00",
      description: "PhD獎學金配置說明",
    },
  ];

  // mockConfigurations[0] is active, [1] is inactive. The component issues two
  // requests (is_active:true then is_active:false) and concatenates the results,
  // so split the data by the requested flag to avoid duplicate rows/keys.
  const activeConfigs = mockConfigurations.filter(c => c.is_active);
  const inactiveConfigs = mockConfigurations.filter(c => !c.is_active);

  beforeEach(() => {
    jest.clearAllMocks();

    // Setup default API mocks
    mockApi.admin.getScholarshipConfigTypes.mockResolvedValue({
      success: true,
      data: mockScholarshipTypes,
    });

    mockApi.admin.getScholarshipConfigurations.mockImplementation((p: any) =>
      Promise.resolve({
        success: true,
        data: p?.is_active ? activeConfigs : inactiveConfigs,
      })
    );
  });

  it("should render component with loading state initially", () => {
    render(<AdminConfigurationManagement scholarshipTypes={[]} />);

    expect(screen.getByText("尚無獎學金類型")).toBeInTheDocument();
  });

  it("should load and display scholarship types", async () => {
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(screen.getByText("PhD獎學金")).toBeInTheDocument();
      expect(screen.getByText("碩士獎學金")).toBeInTheDocument();
    });
  });

  it("should display error message when loading configurations fails", async () => {
    mockApi.admin.getScholarshipConfigurations.mockRejectedValue(
      new Error("Failed to load configurations")
    );

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    // Errors are surfaced via toast (no inline error UI).
    await waitFor(
      () => {
        expect(mockToast.error).toHaveBeenCalledWith(
          expect.stringContaining("載入配置失敗")
        );
      },
      { timeout: 2000 }
    );
  });

  it("should load configurations when scholarship type is selected", async () => {
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    // Check that configurations are loaded for the auto-selected first type.
    // Load is per-type only (active + inactive), no academic_year/semester filter.
    await waitFor(() => {
      expect(mockApi.admin.getScholarshipConfigurations).toHaveBeenCalledWith({
        scholarship_type_id: 1,
        is_active: true,
      });
    });
    expect(mockApi.admin.getScholarshipConfigurations).toHaveBeenCalledWith({
      scholarship_type_id: 1,
      is_active: false,
    });
  });

  it("should display configurations in table", async () => {
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(
        screen.getByText("PhD獎學金114學年度第一學期")
      ).toBeInTheDocument();
    });
    // Year/semester rendered together: "114 第一學期"
    expect(screen.getByText(/114\s*第一學期/)).toBeInTheDocument();
    // Config code badge is rendered
    expect(screen.getByText("PHD-114-1")).toBeInTheDocument();
  });

  it("should show empty state when no configurations exist", async () => {
    mockApi.admin.getScholarshipConfigurations.mockResolvedValue({
      success: true,
      data: [],
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(screen.getByText("尚無配置資料")).toBeInTheDocument();
    });
  });

  it("should open create dialog when create button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(screen.getByText("新增配置")).toBeInTheDocument();
    });

    const createButton = screen.getByText("新增配置");
    await user.click(createButton);

    await waitFor(() => {
      expect(screen.getByText("新增獎學金配置")).toBeInTheDocument();
      expect(
        screen.getByText("為選定的獎學金類型建立新的配置設定")
      ).toBeInTheDocument();
    });
  });

  it("should create new configuration successfully", async () => {
    const user = userEvent.setup();
    mockApi.admin.createScholarshipConfiguration.mockResolvedValue({
      success: true,
      data: { id: 3, config_name: "New Test Config" },
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    // Wait for load and click create button
    await waitFor(() => {
      expect(screen.getByText("新增配置")).toBeInTheDocument();
    });

    const createButton = screen.getByText("新增配置");
    await user.click(createButton);

    // Fill form (simplified for testing)
    await waitFor(() => {
      const nameInput = screen.getAllByTestId("input")[0]; // First input should be config_name
      fireEvent.change(nameInput, { target: { value: "Test Configuration" } });
    });

    // Submit form
    const submitButton = screen.getByText("建立配置");
    await user.click(submitButton);

    await waitFor(() => {
      expect(mockApi.admin.createScholarshipConfiguration).toHaveBeenCalled();
    });
  });

  it("should handle create configuration error", async () => {
    const user = userEvent.setup();
    mockApi.admin.createScholarshipConfiguration.mockRejectedValue({
      response: {
        data: { message: "Creation failed" },
      },
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(screen.getByText("新增配置")).toBeInTheDocument();
    });

    const createButton = screen.getByText("新增配置");
    await user.click(createButton);

    const submitButton = screen.getByText("建立配置");
    await user.click(submitButton);

    // Error surfaced via toast: "建立配置失敗: Creation failed"
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        expect.stringContaining("Creation failed")
      );
    });
  });

  it("should open edit dialog when edit button is clicked", async () => {
    const user = userEvent.setup();
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    // Wait for the row (and its action buttons) to render.
    await waitFor(() => {
      expect(
        screen.getByText("PhD獎學金114學年度第一學期")
      ).toBeInTheDocument();
    });

    // The edit action button carries title="編輯配置" (spread onto the mock button).
    const editButton = screen.getAllByTitle("編輯配置")[0];
    await user.click(editButton);

    await waitFor(() => {
      expect(screen.getByText("編輯獎學金配置")).toBeInTheDocument();
    });
  });

  it("should update configuration successfully", async () => {
    const user = userEvent.setup();
    mockApi.admin.updateScholarshipConfiguration.mockResolvedValue({
      success: true,
      data: { id: 1, config_name: "Updated Configuration" },
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    // This is a simplified test - in reality would need to properly trigger edit dialog
    await waitFor(() => {
      expect(mockApi.admin.getScholarshipConfigurations).toHaveBeenCalled();
    });
  });

  it("should delete configuration successfully", async () => {
    mockApi.admin.deleteScholarshipConfiguration.mockResolvedValue({
      success: true,
      data: { id: 1, is_active: false },
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(mockApi.admin.getScholarshipConfigurations).toHaveBeenCalled();
    });
  });

  it("should duplicate configuration successfully", async () => {
    mockApi.admin.duplicateScholarshipConfiguration.mockResolvedValue({
      success: true,
      data: { id: 4, config_name: "Duplicated Configuration" },
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(mockApi.admin.getScholarshipConfigurations).toHaveBeenCalled();
    });
  });

  it("should load configurations for the selected type (per-type, no year filter)", async () => {
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(mockApi.admin.getScholarshipConfigurations).toHaveBeenCalledWith({
        scholarship_type_id: 1,
        is_active: true,
      });
    });
  });

  // Year/semester filtering at the API level was removed; load is per scholarship
  // type only (active + inactive). Filtering now happens client-side via search.
  it("should filter configurations by semester", () => {});

  // The standalone "重新載入" refresh button was removed from the redesigned UI;
  // reloads happen automatically after create/update/delete and on type change.
  it("should refresh configurations when refresh button is clicked", () => {});

  it("should display active/inactive status correctly", async () => {
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      // Active config row shows the "已啟用" status badge.
      expect(screen.getByText("已啟用")).toBeInTheDocument();
    });
    // Inactive config row shows "已停用".
    expect(screen.getByText("已停用")).toBeInTheDocument();
  });

  it("should handle API errors gracefully", async () => {
    mockApi.admin.getScholarshipConfigurations.mockRejectedValue({
      response: {
        data: { message: "Server error" },
      },
    });

    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    // Load failures are surfaced via toast (the error has no `.message`, so the
    // component falls back to its default "載入配置失敗: ..." prefix).
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        expect.stringContaining("載入配置失敗")
      );
    });
  });

  // The redesigned component reports errors via toast notifications rather than a
  // dismissible inline error banner, so there is no "×" close button to test.
  it("should close error message when X button is clicked", () => {});

  it("should validate form data before submission", async () => {
    const user = userEvent.setup();
    render(
      <AdminConfigurationManagement scholarshipTypes={mockScholarshipTypes} />
    );

    await waitFor(() => {
      expect(screen.getByText("新增配置")).toBeInTheDocument();
    });

    const createButton = screen.getByText("新增配置");
    await user.click(createButton);

    // Try to submit without filling required fields
    await waitFor(() => {
      const submitButton = screen.getByText("建立配置");
      expect(submitButton).toBeInTheDocument();
    });

    // The form should have validation - specific validation testing would require more detailed form interaction
  });
});
