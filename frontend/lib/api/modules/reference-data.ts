/**
 * Reference Data API Module (OpenAPI-typed)
 *
 * Provides access to system reference data:
 * - Academies/colleges
 * - Departments
 * - Degrees, identities, enrollment types
 * - Scholarship periods
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

type Academy = {
  id: number;
  code: string;
  name: string;
};

type Department = {
  id: number;
  code: string;
  name: string;
  academy_code: string | null;
};

type ReferenceDataAll = {
  academies: Array<{ id: number; code: string; name: string }>;
  departments: Array<{ id: number; code: string; name: string }>;
  degrees: Array<{ id: number; name: string }>;
  identities: Array<{ id: number; name: string }>;
  studying_statuses: Array<{ id: number; name: string }>;
  school_identities: Array<{ id: number; name: string }>;
  enroll_types: Array<{
    degree_id: number;
    code: string;
    name: string;
    name_en?: string;
    degree_name?: string;
  }>;
};

type ScholarshipPeriod = {
  value: string;
  academic_year: number;
  semester: string | null;
  label: string;
  label_en: string;
  is_current: boolean;
  cycle: string;
  sort_order: number;
};

type ScholarshipPeriodsResponse = {
  periods: ScholarshipPeriod[];
  cycle: string;
  scholarship_name: string | null;
  current_period: string;
  total_periods: number;
};

export function createReferenceDataApi() {
  return {
    /**
     * Get all academies/colleges
     * Type-safe: Response type inferred from OpenAPI
     */
    getAcademies: async (): Promise<ApiResponse<Academy[]>> => {
      const response = await typedClient.raw.GET('/api/v1/reference-data/academies');
      return toApiResponse(response);
    },

    /**
     * Get all departments
     * Type-safe: Response type inferred from OpenAPI
     */
    getDepartments: async (): Promise<ApiResponse<Department[]>> => {
      const response = await typedClient.raw.GET('/api/v1/reference-data/departments');
      return toApiResponse(response);
    },

    /**
     * Get all reference data in one request
     * Type-safe: Response type inferred from OpenAPI
     */
    getAll: async (): Promise<ApiResponse<ReferenceDataAll>> => {
      const response = await typedClient.raw.GET('/api/v1/reference-data/all');
      return toApiResponse(response);
    },

    /**
     * Get scholarship periods based on application cycle
     * Type-safe: Query parameters validated against OpenAPI
     */
    getScholarshipPeriods: async (params?: {
      scholarship_id?: number;
      scholarship_code?: string;
      application_cycle?: string;
    }): Promise<ApiResponse<ScholarshipPeriodsResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/reference-data/scholarship-periods', {
        params: {
          query: {
            scholarship_id: params?.scholarship_id,
            scholarship_code: params?.scholarship_code,
            application_cycle: params?.application_cycle,
          },
        },
      });
      return toApiResponse(response);
    },
  };
}
