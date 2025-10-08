/**
 * Reference Data API Module
 *
 * Provides access to system reference data:
 * - Academies/colleges
 * - Departments
 * - Degrees, identities, enrollment types
 * - Scholarship periods
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

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

export function createReferenceDataApi(client: ApiClient) {
  return {
    /**
     * Get all academies/colleges
     */
    getAcademies: async (): Promise<ApiResponse<Academy[]>> => {
      return client.request("/reference-data/academies");
    },

    /**
     * Get all departments
     */
    getDepartments: async (): Promise<ApiResponse<Department[]>> => {
      return client.request("/reference-data/departments");
    },

    /**
     * Get all reference data in one request
     */
    getAll: async (): Promise<ApiResponse<ReferenceDataAll>> => {
      return client.request("/reference-data/all");
    },

    /**
     * Get scholarship periods based on application cycle
     */
    getScholarshipPeriods: async (params?: {
      scholarship_id?: number;
      scholarship_code?: string;
      application_cycle?: string;
    }): Promise<ApiResponse<ScholarshipPeriodsResponse>> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return client.request(
        `/reference-data/scholarship-periods${query ? `?${query}` : ""}`
      );
    },
  };
}
