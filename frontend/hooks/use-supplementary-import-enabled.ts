"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api";

const ENABLED_KEY = "/college-review/supplementary-import/enabled";

/**
 * Whether admin has opened 補充匯入 on at least one active scholarship
 * configuration this college may operate. The college 補充匯入 tab exists only
 * while this is true.
 *
 * Fails closed: the flag defaults to off server-side and the tab exists only
 * after a deliberate admin opt-in, so while loading and on a failed lookup the
 * tab stays hidden rather than flashing in against the admin's decision.
 *
 * Focus revalidation is inherited from the global SWR config so an admin
 * toggle reaches an already-open college session on the next focus.
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
    }
  );

  return {
    isSupplementaryImportEnabled: data ?? false,
    /** True only once a real answer has arrived. */
    isLoaded: data !== undefined,
    isLoading,
    error,
    mutate,
  };
}
