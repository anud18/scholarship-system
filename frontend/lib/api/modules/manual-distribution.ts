/**
 * Manual Distribution API Module
 *
 * Provides endpoints for admin to manually allocate scholarships to students.
 * Replaces the automated quota/matrix distribution with a UI-driven workflow.
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

export interface DistributionStudent {
  ranking_item_id: number;
  application_id: number;
  rank_position: number;
  applied_sub_types: string[];
  allocated_sub_type: string | null;
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

export interface SubTypeQuotaStatus {
  display_name: string;
  total: number;
  allocated: number;
  remaining: number;
  by_college: Record<string, CollegeQuota>;
}

export type QuotaStatus = Record<string, SubTypeQuotaStatus>;

export interface AllocationItem {
  ranking_item_id: number;
  sub_type_code: string | null;
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

export interface AvailableCombinations {
  scholarship_types: Array<{ id: number; code: string; name: string; name_en?: string }>;
  academic_years: number[];
  semesters: string[];
}

export function createManualDistributionApi() {
  return {
    /**
     * Get all active scholarship types and configurations for admin distribution.
     */
    getAvailableCombinations: async (): Promise<ApiResponse<AvailableCombinations>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/manual-distribution/available-combinations' as any,
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
        '/api/v1/manual-distribution/students' as any,
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
        '/api/v1/manual-distribution/quota-status' as any,
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
    allocate: async (request: AllocateRequest): Promise<ApiResponse<AllocateResult>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/manual-distribution/allocate' as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<AllocateResult>;
    },

    /**
     * Finalize distribution - lock and update application statuses.
     */
    finalize: async (request: FinalizeRequest): Promise<ApiResponse<FinalizeResult>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/manual-distribution/finalize' as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<FinalizeResult>;
    },
  };
}
