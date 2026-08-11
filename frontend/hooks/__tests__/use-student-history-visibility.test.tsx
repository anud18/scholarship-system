import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";

import { useStudentHistoryVisibility } from "../use-student-history-visibility";
import { apiClient } from "@/lib/api";

// Fresh cache per test, and no retries so the error branch settles fast.
const wrapper = ({ children }: { children: React.ReactNode }) => (
  <SWRConfig
    value={{
      provider: () => new Map(),
      dedupingInterval: 0,
      shouldRetryOnError: false,
    }}
  >
    {children}
  </SWRConfig>
);

describe("useStudentHistoryVisibility", () => {
  let getVisibility: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    getVisibility = jest.spyOn(apiClient.studentHistory, "getVisibility");
  });

  afterEach(() => {
    getVisibility.mockRestore();
  });

  it("reports the stored switches", async () => {
    getVisibility.mockResolvedValue({
      success: true,
      message: "ok",
      data: { student_enabled: false, college_enabled: true },
    });

    const { result } = renderHook(() => useStudentHistoryVisibility(), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.visibility).toEqual({
      student_enabled: false,
      college_enabled: true,
    });
  });

  it("starts closed so a gated entry point never flashes", () => {
    getVisibility.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useStudentHistoryVisibility(), {
      wrapper,
    });

    expect(result.current.isLoaded).toBe(false);
    expect(result.current.visibility).toEqual({
      student_enabled: false,
      college_enabled: false,
    });
  });

  it("falls back to open when the lookup fails, matching the backend default", async () => {
    getVisibility.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useStudentHistoryVisibility(), {
      wrapper,
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    // The endpoints behind the entry point enforce the same switches, so a
    // blip costs an error message rather than removing a college's tab.
    expect(result.current.visibility).toEqual({
      student_enabled: true,
      college_enabled: true,
    });
    expect(result.current.isLoaded).toBe(false);
  });

  it("makes no request when disabled", () => {
    renderHook(() => useStudentHistoryVisibility(false), { wrapper });
    expect(getVisibility).not.toHaveBeenCalled();
  });
});
