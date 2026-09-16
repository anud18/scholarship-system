"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api";

const ENABLED_KEY = "/college-review/supplementary-import/enabled";

/**
 * Whether admin has opened 補充匯入 on at least one active scholarship
 * configuration. The college 補充匯入 tab exists only while this is true.
 *
 * Hidden while the request is in flight so the tab never flashes in for a
 * college the admin has shut out, but shown if the lookup itself failed: the
 * panel behind it re-checks every period server-side (/availability and the
 * upload's 403), so a network blip costs an explanatory message, never access.
 */
export function useSupplementaryImportEnabled(isEnabled: boolean = true) {
  const { data, error, isLoading, mutate } = useSWR<boolean>(
    isEnabled ? ENABLED_KEY : null,
    async () => {
      const response = await apiClient.college.getSupplementaryImportEnabled();
      if (!response.success || !response.data) {
        throw new Error(response.message || "無法取得補充匯入開放狀態");
      }
      return response.data.enabled;
    },
    { revalidateOnFocus: false }
  );

  return {
    // SWR keeps the last good `data` across a failed revalidation, so the
    // error fallback only applies when nothing was ever fetched.
    isSupplementaryImportEnabled: data ?? (error ? true : false),
    /** True only once a real answer has arrived. */
    isLoaded: data !== undefined,
    isLoading,
    error,
    mutate,
  };
}

export const supplementaryImportEnabledKeys = {
  enabled: ENABLED_KEY,
};
