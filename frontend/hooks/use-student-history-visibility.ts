"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api";
import type { StudentHistoryVisibility } from "@/lib/api/modules/student-history";

const VISIBILITY_KEY = "/student-history/visibility";

/**
 * Closed while the request is in flight, so a 領獎紀錄 tab/card never flashes
 * into view for an audience the admin has shut out.
 */
const CLOSED: StudentHistoryVisibility = {
  student_enabled: false,
  college_enabled: false,
};

/**
 * ...but OPEN if the request itself failed. This mirrors the backend, which
 * reads an unknown setting as open, and keeps a network blip from silently
 * removing a college's tab. The entry point only leads to endpoints that
 * enforce the same switches server-side, so a wrong guess here costs an error
 * message, never access.
 */
const OPEN_ON_ERROR: StudentHistoryVisibility = {
  student_enabled: true,
  college_enabled: true,
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
    // SWR keeps the last good `data` across a failed revalidation, so the
    // error fallback only applies when nothing was ever fetched.
    visibility: data ?? (error ? OPEN_ON_ERROR : CLOSED),
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
