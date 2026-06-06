/**
 * Tests for `BatchImportPanel` — admin UI for batch importing application
 * data via Excel upload.
 *
 * 937 LOC, previously zero tests. Addresses the hook's call-out of
 * remaining untested admin-side components beyond the 6 large admin
 * components covered in PR #244.
 *
 * What's pinned:
 * - Component mounts and triggers initial data fetches
 *   (getMyScholarships, getHistory).
 * - The "批次匯入申請資料" / "Batch Import Applications" upload section
 *   renders when there's no uploadedBatch (initial state).
 * - Locale prop controls Chinese vs English copy on the upload section.
 *
 * Heavier interactions (Excel upload, preview, confirm, delete) are
 * scope-creep — they engage a deep API surface and file-handling layer
 * that warrant their own dedicated test surfaces.
 */
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { BatchImportPanel } from "../batch-import-panel";
import { apiClient } from "@/lib/api";

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

// NOTE: We do NOT jest.mock("@/lib/api"). The component imports the REAL
// `apiClient` singleton, whose `admin` / `referenceData` / `batchImport`
// namespaces are stable lazy getters. Under this repo's native-ESM jest
// setup, a factory mock of "@/lib/api" does not intercept the component's
// import (the spies saw 0 calls). Spying directly on the real singleton's
// namespace objects works because they are the same objects the component
// reaches at runtime.

beforeEach(() => {
  jest
    .spyOn(apiClient.admin, "getMyScholarships")
    .mockResolvedValue({ success: true, data: [] } as any);
  jest
    .spyOn(apiClient.referenceData, "getScholarshipPeriods")
    .mockResolvedValue({ success: true, data: [] } as any);
  jest
    .spyOn(apiClient.batchImport, "getHistory")
    .mockResolvedValue({ success: true, data: { items: [] } } as any);
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("BatchImportPanel", () => {
  it("renders the Chinese upload section heading in default (zh) locale", async () => {
    render(<BatchImportPanel />);
    expect(await screen.findByText("批次匯入申請資料")).toBeInTheDocument();
  });

  it("renders the English upload section heading when locale='en'", async () => {
    render(<BatchImportPanel locale="en" />);
    expect(
      await screen.findByText("Batch Import Applications")
    ).toBeInTheDocument();
  });

  it("triggers getMyScholarships and getHistory on mount", async () => {
    render(<BatchImportPanel />);
    await waitFor(() => {
      expect(apiClient.admin.getMyScholarships).toHaveBeenCalled();
      expect(apiClient.batchImport.getHistory).toHaveBeenCalled();
    });
  });
});
