/**
 * Tests for `AdminScholarshipManagementInterface` — per-scholarship-type
 * admin UI for managing application form fields, document requirements,
 * whitelist, and terms.
 *
 * 1746 LOC, previously zero tests. Fifth in the 9-untested-admin-components
 * series.
 *
 * What's pinned:
 * - Loading state copy renders while initial config fetch is in flight.
 * - The `type` prop drives the form-config fetch (we assert the correct
 *   scholarship code reaches the API call).
 *
 * - Editing a 固定文件（系統預設）item saves. Those arrive from the form config
 *   with `id: 0` because they are built in code rather than stored, so the
 *   save has to create a row (carrying `fixed_key`) instead of PUTting id 0,
 *   which 404s.
 *
 * Deeper interactions (field CRUD, document upload, whitelist Excel
 * import/export) are intentionally out of scope — each engages a deep
 * API surface that warrants its own dedicated test.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AdminScholarshipManagementInterface } from "../admin-scholarship-management-interface";

const mockGetFormConfig = jest.fn();
const mockGetAll = jest.fn();
const mockGetConfigurationWhitelist = jest.fn();
const mockCreateDocument = jest.fn();
const mockUpdateDocument = jest.fn();

jest.mock("../../lib/api", () => ({
  __esModule: true,
  api: {
    applicationFields: {
      getFormConfig: (...args: unknown[]) => mockGetFormConfig(...args),
      saveFormConfig: jest.fn(),
      createField: jest.fn(),
      updateField: jest.fn(),
      deleteField: jest.fn(),
      createDocument: (...args: unknown[]) => mockCreateDocument(...args),
      updateDocument: (...args: unknown[]) => mockUpdateDocument(...args),
      deleteDocument: jest.fn(),
      uploadDocumentExample: jest.fn(),
      deleteDocumentExample: jest.fn(),
    },
    scholarships: {
      getAll: (...args: unknown[]) => mockGetAll(...args),
    },
    whitelist: {
      getConfigurationWhitelist: (...args: unknown[]) =>
        mockGetConfigurationWhitelist(...args),
      batchAddWhitelist: jest.fn(),
      batchRemoveWhitelist: jest.fn(),
      importWhitelistExcel: jest.fn(),
      exportWhitelistExcel: jest.fn(),
      downloadTemplate: jest.fn(),
    },
  },
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

beforeEach(() => {
  // Hang the initial fetch so the component sits in loading state on first render.
  // Individual tests can re-mock to resolve.
  mockGetFormConfig.mockReturnValue(new Promise(() => {}));
  mockGetAll.mockResolvedValue({ success: true, data: [] });
  mockGetConfigurationWhitelist.mockResolvedValue({
    success: true,
    data: { students: [] },
  });
  mockCreateDocument.mockReset();
  mockUpdateDocument.mockReset();
});

const FIXED_DOCUMENT = {
  id: 0,
  scholarship_type: "phd",
  document_name: "存摺封面",
  description: "請上傳存摺封面",
  is_required: true,
  display_in_list: true,
  requires_upload: true,
  accepted_file_types: ["PDF", "JPG"],
  max_file_size: "10MB",
  max_file_count: 1,
  display_order: 1,
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  is_fixed: true,
  fixed_key: "bank_statement",
};

describe("AdminScholarshipManagementInterface", () => {
  it("renders the loading copy while the form-config fetch is in flight", () => {
    render(<AdminScholarshipManagementInterface type="phd" />);
    expect(screen.getByText("載入設定中...")).toBeInTheDocument();
  });

  it("forwards the `type` prop to api.applicationFields.getFormConfig", async () => {
    render(
      <AdminScholarshipManagementInterface type="undergraduate_freshman" />
    );
    await waitFor(() => {
      expect(mockGetFormConfig).toHaveBeenCalled();
    });
    // The first positional arg is the scholarship type code.
    const callArgs = mockGetFormConfig.mock.calls[0];
    expect(callArgs[0]).toBe("undergraduate_freshman");
  });

  it("forwards a different `type` prop correctly (direct_phd)", async () => {
    render(<AdminScholarshipManagementInterface type="direct_phd" />);
    await waitFor(() => {
      expect(mockGetFormConfig).toHaveBeenCalled();
    });
    expect(mockGetFormConfig.mock.calls[0][0]).toBe("direct_phd");
  });

  it("saves an edit to a 固定文件 item by creating a row, not PUTting id 0", async () => {
    mockGetFormConfig.mockResolvedValue({
      success: true,
      data: { scholarship_type: "phd", fields: [], documents: [FIXED_DOCUMENT] },
    });
    mockCreateDocument.mockResolvedValue({
      success: true,
      data: { ...FIXED_DOCUMENT, id: 12, document_name: "存摺封面（含戶名）" },
    });

    const user = userEvent.setup();
    render(<AdminScholarshipManagementInterface type="phd" />);

    await user.click(await screen.findByRole("tab", { name: /文件要求/ }));
    const fixedRow = (await screen.findByText("存摺封面")).closest("tr");
    expect(fixedRow).not.toBeNull();

    // 編輯 is the row's only action — a built-in item has no delete button.
    // (The 啟用/停用 switch is a button too, so exclude it.)
    const actions = Array.from(
      fixedRow!.querySelectorAll("button:not([role='switch'])")
    );
    expect(actions).toHaveLength(1);
    await user.click(actions[0]);

    const nameInput = await screen.findByDisplayValue("存摺封面");
    await user.clear(nameInput);
    await user.type(nameInput, "存摺封面（含戶名）");
    await user.click(screen.getByRole("button", { name: /更新文件/ }));

    await waitFor(() => {
      expect(mockCreateDocument).toHaveBeenCalled();
    });
    expect(mockUpdateDocument).not.toHaveBeenCalled();

    const payload = mockCreateDocument.mock.calls[0][0];
    expect(payload.fixed_key).toBe("bank_statement");
    expect(payload.document_name).toBe("存摺封面（含戶名）");
    expect(payload.scholarship_type).toBe("phd");
  });
});
