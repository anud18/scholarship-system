/**
 * Student Scholarship History API Module
 *
 * - Batch lookup by 學號 for admin/college (academic info + paid-roster
 *   payment records; rosters in COMPLETED or LOCKED state). College users are
 *   server-scoped to their own college and receive a projected payload
 *   without admin-only fields.
 * - Student self-service 總領月份數 (months total only).
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";

export interface AcademicBasicInfo {
  std_cname: string | null;
  std_ename: string | null;
  std_degree: string | null;
  std_studingstatus: string | null;
  std_academyno: string | null;
  std_aca_cname: string | null;
  std_depname: string | null;
  std_depno: string | null;
  com_email: string | null;
}

export interface AcademicInfo {
  available: boolean;
  error: string | null;
  basic_info: AcademicBasicInfo | null;
}

export interface PaymentRecord {
  roster_id: number;
  roster_code: string;
  period_label: string;
  academic_year: number;
  roster_cycle: "monthly" | "semi_yearly" | "yearly";
  scholarship_name: string;
  scholarship_amount: string; // Decimal serialized as string
  scholarship_subtype: string | null;
  scholarship_type_id: number | null;
  allocation_year: number | null;
  locked_at: string | null;
  // G25 (#987): post-payment revocation/suspension context — null for
  // legacy items without a linked application.
  quota_allocation_status: string | null;
  revoked_at: string | null;
  revoke_reason: string | null;
  suspended_at: string | null;
  suspend_reason: string | null;
}

export interface HistorySummary {
  total_records: number;
  total_amount: string;
  scholarship_type_count: number;
  snapshot_name: string | null;
  /**
   * 總領月份數 — 匯入 + 系統 summed across every scholarship type. Per-type
   * caps (the 36-month PhD limit) apply to the individual entries in
   * `received_months`, not to this total.
   */
  total_received_months: number;
}

/**
 * 已領月份數 for one scholarship type: `total_months = imported_months +
 * system_months`. The imported half is a lifetime baseline from 國科會's file;
 * the system half is counted from this student's own payment records. The two
 * never cover the same month.
 *
 * The `raw_row` / `file_name` / `imported_at` fields are present only when an
 * import exists, and back the「檔案明細」expander.
 */
export interface ReceivedMonthsBreakdown {
  scholarship_type_id: number | null;
  scholarship_name: string;
  total_months: number;
  imported_months: number;
  system_months: number;
  award_start_month: string | null;
  award_current_month: string | null;
  raw_row: Record<string, string> | null;
  file_name: string | null;
  imported_at: string | null;
}

export interface StudentScholarshipHistoryData {
  student_number: string;
  academic_info: AcademicInfo;
  summary: HistorySummary;
  payment_records: PaymentRecord[];
  received_months: ReceivedMonthsBreakdown[];
}

/**
 * One entry of POST /student-history/batch. Per-student failures (查無資料,
 * out-of-college scope) arrive here with success=false — the HTTP call itself
 * still succeeds.
 */
export interface StudentHistoryBatchResult {
  student_number: string;
  success: boolean;
  error: string | null;
  data: StudentScholarshipHistoryData | null;
}

export interface StudentHistoryBatchData {
  results: StudentHistoryBatchResult[];
}

/** Student self-service payload — 總月數 only, no amounts or payment details. */
export interface MyReceivedMonthsData {
  student_number: string;
  total_received_months: number;
}

/**
 * The two admin switches deciding who 領獎紀錄查詢 is open to. Readable by any
 * authenticated user so the student card and the college tab can hide
 * themselves instead of rendering an entry point that 403s.
 */
export interface StudentHistoryVisibility {
  student_enabled: boolean;
  college_enabled: boolean;
}

/** Admin toggle payload — omit a field to leave that audience untouched. */
export interface StudentHistoryVisibilityUpdate {
  student_enabled?: boolean;
  college_enabled?: boolean;
}

export function createStudentHistoryApi() {
  return {
    async getBatch(
      studentNumbers: string[],
    ): Promise<ApiResponse<StudentHistoryBatchData>> {
      const response = await typedClient.raw.POST(
        "/api/v1/student-history/batch",
        {
          body: { student_numbers: studentNumbers },
        },
      );
      return toApiResponse<StudentHistoryBatchData>(response);
    },

    async getMyMonths(): Promise<ApiResponse<MyReceivedMonthsData>> {
      const response = await typedClient.raw.GET(
        "/api/v1/student-history/me/months",
        {},
      );
      return toApiResponse<MyReceivedMonthsData>(response);
    },

    async getVisibility(): Promise<ApiResponse<StudentHistoryVisibility>> {
      const response = await typedClient.raw.GET(
        "/api/v1/student-history/visibility",
        {},
      );
      return toApiResponse<StudentHistoryVisibility>(response);
    },

    async updateVisibility(
      update: StudentHistoryVisibilityUpdate,
    ): Promise<ApiResponse<StudentHistoryVisibility>> {
      const response = await typedClient.raw.PUT(
        "/api/v1/student-history/visibility",
        { body: update },
      );
      return toApiResponse<StudentHistoryVisibility>(response);
    },
  };
}
