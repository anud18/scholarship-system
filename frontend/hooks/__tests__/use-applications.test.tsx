import React from "react";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useApplications } from "../use-applications";
import { useAuth } from "../use-auth";
import { apiClient } from "@/lib/api";

// Mock the useAuth hook
jest.mock("../use-auth");
const mockUseAuth = useAuth as jest.MockedFunction<typeof useAuth>;

// Silence hook error logging
jest.mock("@/lib/utils/logger", () => ({
  logger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
  },
}));

// PR #911 pattern: spy on the REAL @/lib/api module object — module-factory
// mocks were never picked up by the hook (internal call sites hold direct
// references), which is why the mount effect appeared to "not trigger".
let hasTokenSpy: jest.SpyInstance;
let getMyApplicationsSpy: jest.SpyInstance;
let createApplicationSpy: jest.SpyInstance;
let submitApplicationSpy: jest.SpyInstance;
let withdrawApplicationSpy: jest.SpyInstance;
let updateApplicationSpy: jest.SpyInstance;
let uploadDocumentSpy: jest.SpyInstance;
let saveApplicationDraftSpy: jest.SpyInstance;
let deleteApplicationSpy: jest.SpyInstance;

const ok = (data: unknown) => ({ success: true, message: "", data });

// Test wrapper that provides auth context
const wrapper = ({ children }: { children: React.ReactNode }) => {
  return <div>{children}</div>;
};

describe("useApplications Hook", () => {
  beforeEach(() => {
    hasTokenSpy = jest.spyOn(apiClient, "hasToken").mockReturnValue(true);
    getMyApplicationsSpy = jest
      .spyOn(apiClient.applications, "getMyApplications")
      .mockResolvedValue(ok([]) as never);
    createApplicationSpy = jest
      .spyOn(apiClient.applications, "createApplication")
      .mockResolvedValue(ok({}) as never);
    submitApplicationSpy = jest
      .spyOn(apiClient.applications, "submitApplication")
      .mockResolvedValue(ok({}) as never);
    withdrawApplicationSpy = jest
      .spyOn(apiClient.applications, "withdrawApplication")
      .mockResolvedValue(ok({}) as never);
    updateApplicationSpy = jest
      .spyOn(apiClient.applications, "updateApplication")
      .mockResolvedValue(ok({}) as never);
    uploadDocumentSpy = jest
      .spyOn(apiClient.applications, "uploadDocument")
      .mockResolvedValue(ok({}) as never);
    saveApplicationDraftSpy = jest
      .spyOn(apiClient.applications, "saveApplicationDraft")
      .mockResolvedValue(ok({}) as never);
    deleteApplicationSpy = jest
      .spyOn(apiClient.applications, "deleteApplication")
      .mockResolvedValue(ok(null) as never);

    // Default auth state
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      user: { id: "1", nycu_id: "testuser" },
      login: jest.fn(),
      logout: jest.fn(),
      updateUser: jest.fn(),
      isLoading: false,
      error: null,
    } as never);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("fetchApplications", () => {
    it("should fetch applications on mount", async () => {
      const mockApplications = [
        { id: 1, status: "draft", created_at: "2025-01-01" },
        { id: 2, status: "submitted", created_at: "2025-01-02" },
      ];

      getMyApplicationsSpy.mockResolvedValue(ok(mockApplications));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(getMyApplicationsSpy).toHaveBeenCalled();
      });

      await waitFor(() => {
        expect(result.current.applications).toEqual(mockApplications);
        expect(result.current.isLoading).toBe(false);
        expect(result.current.error).toBeNull();
      });
    });

    it("should handle array response format", async () => {
      const mockApplications = [{ id: 1, status: "draft" }];

      getMyApplicationsSpy.mockResolvedValue(mockApplications);

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.applications).toEqual(mockApplications);
      });
    });

    it("should not fetch when user is not authenticated", async () => {
      mockUseAuth.mockReturnValue({
        isAuthenticated: false,
        user: null,
        login: jest.fn(),
        logout: jest.fn(),
        updateUser: jest.fn(),
        isLoading: false,
        error: null,
      } as never);

      const { result } = renderHook(() => useApplications(), { wrapper });

      expect(getMyApplicationsSpy).not.toHaveBeenCalled();
      expect(result.current.applications).toEqual([]);
    });

    it("should not fetch when no auth token is present", async () => {
      hasTokenSpy.mockReturnValue(false);

      const { result } = renderHook(() => useApplications(), { wrapper });

      expect(getMyApplicationsSpy).not.toHaveBeenCalled();
      expect(result.current.applications).toEqual([]);
    });

    it("should handle fetch error", async () => {
      getMyApplicationsSpy.mockRejectedValue(new Error("Network error"));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.error).toBe("Network error");
        expect(result.current.isLoading).toBe(false);
      });
    });

    it("should surface API message when response has no success flag", async () => {
      getMyApplicationsSpy.mockResolvedValue({
        success: false,
        message: "Failed to fetch",
      });

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.error).toBe("Failed to fetch");
      });
    });
  });

  describe("createApplication", () => {
    it("should create application successfully", async () => {
      const newApplication = {
        id: 3,
        status: "draft",
        created_at: "2025-01-03",
      };
      const applicationData = { scholarship_type: "academic_excellence" };

      createApplicationSpy.mockResolvedValue(ok(newApplication));

      const { result } = renderHook(() => useApplications(), { wrapper });

      let createdApp: unknown;
      await act(async () => {
        createdApp = await result.current.createApplication(
          applicationData as never
        );
      });

      expect(createdApp).toEqual(newApplication);
      expect(result.current.applications).toContain(newApplication);
    });

    it("should handle create application error", async () => {
      const applicationData = { scholarship_type: "academic_excellence" };

      createApplicationSpy.mockRejectedValue(new Error("Create failed"));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await act(async () => {
        await expect(
          result.current.createApplication(applicationData as never)
        ).rejects.toThrow("Create failed");
      });

      expect(result.current.error).toBe("Create failed");
    });
  });

  describe("submitApplication", () => {
    it("should submit application successfully", async () => {
      const submittedApp = {
        id: 1,
        status: "submitted",
        submitted_at: "2025-01-01",
      };

      // Set initial applications
      getMyApplicationsSpy.mockResolvedValue(ok([{ id: 1, status: "draft" }]));
      submitApplicationSpy.mockResolvedValue(ok(submittedApp));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(1);
      });

      await act(async () => {
        await result.current.submitApplication(1);
      });

      expect(result.current.applications[0]).toEqual(submittedApp);
    });

    it("should handle submit application error", async () => {
      submitApplicationSpy.mockRejectedValue(new Error("Submit failed"));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await act(async () => {
        await expect(result.current.submitApplication(1)).rejects.toThrow(
          "Submit failed"
        );
      });

      expect(result.current.error).toBe("Submit failed");
    });
  });

  describe("withdrawApplication", () => {
    it("should withdraw application successfully", async () => {
      const withdrawnApp = { id: 1, status: "withdrawn" };

      getMyApplicationsSpy.mockResolvedValue(
        ok([{ id: 1, status: "submitted" }])
      );
      withdrawApplicationSpy.mockResolvedValue(ok(withdrawnApp));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(1);
      });

      await act(async () => {
        await result.current.withdrawApplication(1);
      });

      expect(result.current.applications[0]).toEqual(withdrawnApp);
    });
  });

  describe("updateApplication", () => {
    it("should update application successfully", async () => {
      const updatedApp = {
        id: 1,
        status: "draft",
        personal_statement: "Updated statement",
      };

      getMyApplicationsSpy.mockResolvedValue(
        ok([{ id: 1, status: "draft", personal_statement: "Original" }])
      );
      updateApplicationSpy.mockResolvedValue(ok(updatedApp));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(1);
      });

      await act(async () => {
        await result.current.updateApplication(1, {
          personal_statement: "Updated statement",
        } as never);
      });

      expect(result.current.applications[0]).toEqual(updatedApp);
    });
  });

  describe("uploadDocument", () => {
    it("should upload document and refresh applications", async () => {
      const file = new File(["content"], "test.pdf", {
        type: "application/pdf",
      });

      uploadDocumentSpy.mockResolvedValue(ok({ file_id: "file123" }));

      const { result } = renderHook(() => useApplications(), { wrapper });

      // Wait for the mount fetch so the call count below is deterministic
      await waitFor(() => {
        expect(getMyApplicationsSpy).toHaveBeenCalledTimes(1);
      });

      await act(async () => {
        const uploadResult = await result.current.uploadDocument(
          1,
          file,
          "transcript"
        );
        expect(uploadResult).toEqual({ file_id: "file123" });
      });

      expect(uploadDocumentSpy).toHaveBeenCalledWith(1, file, "transcript");
      // Should refresh applications after upload
      expect(getMyApplicationsSpy).toHaveBeenCalledTimes(2);
    });
  });

  describe("saveApplicationDraft", () => {
    it("should save draft successfully", async () => {
      const draftApp = { id: 3, status: "draft" };
      const draftData = { scholarship_type: "research" };

      saveApplicationDraftSpy.mockResolvedValue(ok(draftApp));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await act(async () => {
        const savedDraft = await result.current.saveApplicationDraft(
          draftData as never
        );
        expect(savedDraft).toEqual(draftApp);
      });

      expect(result.current.applications).toContain(draftApp);
    });
  });

  describe("deleteApplication", () => {
    it("should delete application successfully", async () => {
      getMyApplicationsSpy.mockResolvedValue(
        ok([
          { id: 1, status: "draft" },
          { id: 2, status: "draft" },
        ])
      );
      deleteApplicationSpy.mockResolvedValue(ok(null));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await waitFor(() => {
        expect(result.current.applications).toHaveLength(2);
      });

      await act(async () => {
        await result.current.deleteApplication(1);
      });

      expect(result.current.applications).toHaveLength(1);
      expect(result.current.applications[0].id).toBe(2);
    });
  });

  describe("error handling", () => {
    it("should set error state when API calls fail", async () => {
      createApplicationSpy.mockRejectedValue(new Error("API Error"));

      const { result } = renderHook(() => useApplications(), { wrapper });

      await act(async () => {
        await expect(
          result.current.createApplication({
            scholarship_type: "test",
          } as never)
        ).rejects.toThrow("API Error");
      });

      expect(result.current.error).toBe("API Error");
    });

    it("should clear error on successful operation", async () => {
      const { result } = renderHook(() => useApplications(), { wrapper });

      // First set an error
      createApplicationSpy.mockRejectedValue(new Error("First error"));

      await act(async () => {
        await expect(
          result.current.createApplication({
            scholarship_type: "test",
          } as never)
        ).rejects.toThrow("First error");
      });

      expect(result.current.error).toBe("First error");

      // Then clear it with successful operation
      createApplicationSpy.mockResolvedValue(ok({ id: 1, status: "draft" }));

      await act(async () => {
        await result.current.createApplication({
          scholarship_type: "test",
        } as never);
      });

      expect(result.current.error).toBeNull();
    });
  });
});
