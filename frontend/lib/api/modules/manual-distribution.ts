/**
 * Manual Distribution API Module
 *
 * Provides endpoints for admin to manually allocate scholarships to students.
 * Replaces the automated quota/matrix distribution with a UI-driven workflow.
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";

export interface DistributionStudent {
  ranking_item_id: number;
  application_id: number;
  rank_position: number;
  applied_sub_types: string[];
  allocated_sub_type: string | null;
  allocation_year: number | null;
  status: string;
  college_code: string;
  college_name: string;
  department_name: string;
  grade: string;
  student_name: string;
  nationality: string;
  enrollment_date: string;
  student_id: string;
  application_identity: string;
}

export interface CollegeQuota {
  total: number;
  allocated: number;
  remaining: number;
}

export interface YearQuota {
  total: number;
  allocated: number;
  remaining: number;
  by_college: Record<string, CollegeQuota>;
}

export interface SubTypeQuotaStatus {
  display_name: string;
  /** Multi-year quota data: year string → quota info */
  by_year: Record<string, YearQuota>;
}

export type QuotaStatus = Record<string, SubTypeQuotaStatus>;

/** A flattened (sub_type × year) column descriptor for the distribution table */
export interface SubTypeYearCol {
  sub_type: string;
  year: number;
  display_name: string; // e.g., "114年 國科會博士生獎學金"
  total: number;
  remaining: number; // based on DB-confirmed allocations
  key: string; // composite key: "nstc:114"
}

export interface AllocationItem {
  ranking_item_id: number;
  sub_type_code: string | null;
  allocation_year: number | null;
}

export interface AllocateRequest {
  scholarship_type_id: number;
  academic_year: number;
  semester: string;
  allocations: AllocationItem[];
}

export interface FinalizeRequest {
  scholarship_type_id: number;
  academic_year: number;
  semester: string;
}

export interface AllocateResult {
  updated_count: number;
}

export interface FinalizeResult {
  approved_count: number;
  rejected_count: number;
  total: number;
}

export interface DistributionHistoryRecord {
  id: number;
  operation_type: string;
  change_summary: string | null;
  total_allocated: number | null;
  created_at: string | null;
  created_by: number | null;
}

export interface RestoreRequest {
  history_id: number;
}

export interface RestoreResult {
  restored_count: number;
}

export interface RosterSummary {
  id: number;
  roster_code: string;
  sub_type: string;
  allocation_year: number;
  project_number: string | null;
  period_label: string;
  status: string;
  qualified_count: number;
  disqualified_count: number;
  total_amount: string;
}

export interface GenerateRostersRequest {
  scholarship_type_id: number;
  academic_year: number;
  semester: string;
  student_verification_enabled?: boolean;
  force_regenerate?: boolean;
}

export interface GenerateRostersResult {
  rosters_created: number;
  rosters: RosterSummary[];
}

export interface DistributionSummaryStudent {
  ranking_item_id: number;
  application_id: number;
  student_name: string;
  student_id: string;
  college_code: string;
  college_name: string;
  department_name: string;
  rank_position: number;
}

export interface DistributionSummaryGroup {
  sub_type: string;
  allocation_year: number;
  count: number;
  students: DistributionSummaryStudent[];
}

export interface DistributionSummaryResult {
  groups: DistributionSummaryGroup[];
  total_allocated: number;
}

export interface AvailableCombinations {
  scholarship_types: Array<{
    id: number;
    code: string;
    name: string;
    name_en?: string;
  }>;
  academic_years: number[];
  semesters: string[];
}

export function createManualDistributionApi() {
  return {
    /**
     * Get all active scholarship types and configurations for admin distribution.
     */
    getAvailableCombinations: async (): Promise<
      ApiResponse<AvailableCombinations>
    > => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/available-combinations" as any,
        {}
      );
      return toApiResponse(response) as ApiResponse<AvailableCombinations>;
    },

    /**
     * Get ranked students with allocation status for manual distribution.
     */
    getStudents: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string,
      college_code?: string
    ): Promise<ApiResponse<DistributionStudent[]>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/students" as any,
        {
          params: {
            query: {
              scholarship_type_id,
              academic_year,
              semester,
              ...(college_code ? { college_code } : {}),
            } as any,
          },
        }
      );
      return toApiResponse(response) as ApiResponse<DistributionStudent[]>;
    },

    /**
     * Get real-time quota status per sub-type per college.
     */
    getQuotaStatus: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string
    ): Promise<ApiResponse<QuotaStatus>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/quota-status" as any,
        {
          params: {
            query: { scholarship_type_id, academic_year, semester } as any,
          },
        }
      );
      return toApiResponse(response) as ApiResponse<QuotaStatus>;
    },

    /**
     * Save manual allocation selections.
     */
    allocate: async (
      request: AllocateRequest
    ): Promise<ApiResponse<AllocateResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/allocate" as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<AllocateResult>;
    },

    /**
     * Finalize distribution - lock and update application statuses.
     */
    finalize: async (
      request: FinalizeRequest
    ): Promise<ApiResponse<FinalizeResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/finalize" as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<FinalizeResult>;
    },

    /**
     * Get allocation history for a scholarship/year/semester combination.
     */
    getHistory: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string
    ): Promise<ApiResponse<DistributionHistoryRecord[]>> => {
      const response = await typedClient.raw.GET(
        `/api/v1/manual-distribution/${scholarship_type_id}/history` as any,
        {
          params: {
            query: { academic_year, semester } as any,
          },
        }
      );
      return toApiResponse(response) as ApiResponse<
        DistributionHistoryRecord[]
      >;
    },

    /**
     * Restore allocations from a specific history record.
     */
    restoreFromHistory: async (
      scholarship_type_id: number,
      request: RestoreRequest
    ): Promise<ApiResponse<RestoreResult>> => {
      const response = await typedClient.raw.POST(
        `/api/v1/manual-distribution/${scholarship_type_id}/restore` as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<RestoreResult>;
    },

    /**
     * Get distribution summary: all allocated students grouped by sub_type × allocation_year.
     */
    getDistributionSummary: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string
    ): Promise<ApiResponse<DistributionSummaryResult>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/distribution-summary" as any,
        {
          params: {
            query: { scholarship_type_id, academic_year, semester } as any,
          },
        }
      );
      return toApiResponse(response) as ApiResponse<DistributionSummaryResult>;
    },

    /**
     * Generate payment rosters from a finalized+distributed ranking.
     * Creates one roster per (allocation_year, sub_type) combination.
     */
    generateRostersFromDistribution: async (
      request: GenerateRostersRequest
    ): Promise<ApiResponse<GenerateRostersResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/generate-rosters-from-distribution" as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<GenerateRostersResult>;
    },
  };
}
