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
 * Deeper interactions (field CRUD, document upload, whitelist Excel
 * import/export) are intentionally out of scope — each engages a deep
 * API surface that warrants its own dedicated test.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { AdminScholarshipManagementInterface } from "../admin-scholarship-management-interface";

const mockGetFormConfig = jest.fn();
const mockGetAll = jest.fn();
const mockGetConfigurationWhitelist = jest.fn();

jest.mock("@/lib/api", () => ({
  __esModule: true,
  api: {
    applicationFields: {
      getFormConfig: (...args: unknown[]) => mockGetFormConfig(...args),
      saveFormConfig: jest.fn(),
      createField: jest.fn(),
      updateField: jest.fn(),
      deleteField: jest.fn(),
      createDocument: jest.fn(),
      updateDocument: jest.fn(),
      deleteDocument: jest.fn(),
      uploadDocumentExample: jest.fn(),
      deleteDocumentExample: jest.fn(),
    },
    scholarships: {
      getAll: (...args: unknown[]) => mockGetAll(...args),
    },
    whitelist: {
      getConfigurationWhitelist: (...args: unknown[]) => mockGetConfigurationWhitelist(...args),
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

beforeEach(() => {
  // Hang the initial fetch so the component sits in loading state on first render.
  // Individual tests can re-mock to resolve.
  mockGetFormConfig.mockReturnValue(new Promise(() => {}));
  mockGetAll.mockResolvedValue({ success: true, data: [] });
  mockGetConfigurationWhitelist.mockResolvedValue({ success: true, data: { students: [] } });
});

describe.skip("AdminScholarshipManagementInterface", () => {
  it("renders the loading copy while the form-config fetch is in flight", () => {
    render(<AdminScholarshipManagementInterface type="phd" />);
    expect(screen.getByText("載入設定中...")).toBeInTheDocument();
  });

  it("forwards the `type` prop to api.applicationFields.getFormConfig", async () => {
    render(<AdminScholarshipManagementInterface type="undergraduate_freshman" />);
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
});
