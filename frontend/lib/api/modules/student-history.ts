/**
 * Admin Student Scholarship History API Module
 *
 * Single-student lookup by 學號 — returns academic info + locked-roster payment records.
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
  allocation_year: number | null;
  locked_at: string | null;
}

export interface HistorySummary {
  total_records: number;
  total_amount: string;
  scholarship_type_count: number;
  snapshot_name: string | null;
}

export interface StudentScholarshipHistoryData {
  student_number: string;
  academic_info: AcademicInfo;
  summary: HistorySummary;
  payment_records: PaymentRecord[];
}

export function createStudentHistoryApi() {
  return {
    async getByNumber(
      studentNumber: string,
    ): Promise<ApiResponse<StudentScholarshipHistoryData>> {
      const response = await typedClient.raw.GET(
        "/api/v1/admin/student-history/{student_number}",
        {
          params: { path: { student_number: studentNumber } },
        },
      );
      return toApiResponse<StudentScholarshipHistoryData>(response);
    },
  };
}
