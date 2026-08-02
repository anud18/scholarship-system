"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api";
import type { StudentHistoryVisibility } from "@/lib/api/modules/student-history";

const VISIBILITY_KEY = "/student-history/visibility";

/**
 * Closed until proven open: while the request is in flight (or if it fails) no
 * gated entry point renders, so a 領獎紀錄 tab/card can never flash into view
 * for an audience the admin has shut out.
 */
const CLOSED: StudentHistoryVisibility = {
  student_enabled: false,
  college_enabled: false,
};

/**
 * Reads the admin switches controlling who may use 領獎紀錄查詢. The SWR key is
 * shared, so the college tab list, the student card and the admin toggle panel
 * all ride on a single request.
 */
export function useStudentHistoryVisibility(isEnabled: boolean = true) {
  const { data, error, isLoading, mutate } = useSWR<StudentHistoryVisibility>(
    isEnabled ? VISIBILITY_KEY : null,
    async () => {
      const response = await apiClient.studentHistory.getVisibility();
      if (!response.success || !response.data) {
        throw new Error(response.message || "無法取得領獎紀錄查詢開放設定");
      }
      return response.data;
    },
    { revalidateOnFocus: false },
  );

  return {
    visibility: data ?? CLOSED,
    /** True only once a real answer has arrived. */
    isLoaded: !!data,
    isLoading,
    error,
    mutate,
  };
}

export const studentHistoryVisibilityKeys = {
  visibility: VISIBILITY_KEY,
};
