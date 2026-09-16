import React from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { SWRConfig } from "swr";

import { useSupplementaryImportEnabled } from "../use-supplementary-import-enabled";
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

describe("useSupplementaryImportEnabled", () => {
  let getEnabled: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    getEnabled = jest.spyOn(apiClient.college, "getSupplementaryImportEnabled");
  });

  afterEach(() => {
    getEnabled.mockRestore();
  });

  it("reports enabled when admin opened it on some configuration", async () => {
    getEnabled.mockResolvedValue({
      success: true,
      message: "ok",
      data: { enabled: true },
    });

    const { result } = renderHook(() => useSupplementaryImportEnabled(), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.isSupplementaryImportEnabled).toBe(true);
  });

  it("reports disabled when no configuration opened it", async () => {
    getEnabled.mockResolvedValue({
      success: true,
      message: "ok",
      data: { enabled: false },
    });

    const { result } = renderHook(() => useSupplementaryImportEnabled(), {
      wrapper,
    });

    // `false` is a real answer, not the in-flight placeholder.
    await waitFor(() => expect(result.current.isLoaded).toBe(true));
    expect(result.current.isSupplementaryImportEnabled).toBe(false);
  });

  it("starts hidden so the tab never flashes", () => {
    getEnabled.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useSupplementaryImportEnabled(), {
      wrapper,
    });

    expect(result.current.isLoaded).toBe(false);
    expect(result.current.isSupplementaryImportEnabled).toBe(false);
  });

  it("stays hidden when the lookup fails, matching the server default", async () => {
    getEnabled.mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() => useSupplementaryImportEnabled(), {
      wrapper,
    });

    await waitFor(() => expect(result.current.error).toBeTruthy());
    // The flag is off unless admin opted in, so a failed lookup must not
    // surface a tab the admin may have deliberately closed.
    expect(result.current.isSupplementaryImportEnabled).toBe(false);
    expect(result.current.isLoaded).toBe(false);
  });

  it("does not fetch while disabled", () => {
    const { result } = renderHook(() => useSupplementaryImportEnabled(false), {
      wrapper,
    });

    expect(getEnabled).not.toHaveBeenCalled();
    expect(result.current.isSupplementaryImportEnabled).toBe(false);
  });
});
