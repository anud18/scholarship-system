/**
 * Scholarships API Module (OpenAPI-typed)
 *
 * Handles scholarship-related operations including:
 * - Fetching eligible scholarships
 * - Getting scholarship details
 * - Managing combined PhD scholarships
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse, ScholarshipType } from '../../api.legacy';

export function createScholarshipsApi() {
  return {
    /**
     * Get scholarships eligible for current user
     * Type-safe: Response array inferred from OpenAPI
     */
    getEligible: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarships/eligible');
      return toApiResponse(response);
    },

    /**
     * Get scholarship by ID
     * Type-safe: Path parameter validated against OpenAPI
     */
    getById: async (id: number): Promise<ApiResponse<ScholarshipType>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarships/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response);
    },

    /**
     * Get all scholarships
     * Type-safe: Response array inferred from OpenAPI
     */
    getAll: async (): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarships');
      return toApiResponse(response);
    },

    /**
     * Get combined scholarships
     * Type-safe: Response array inferred from OpenAPI
     */
    getCombined: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      const response = await (typedClient.raw.GET as any)('/api/v1/scholarships/combined/list', {});
      return toApiResponse<ScholarshipType[]>(response);
    },

    /**
     * Create combined PhD scholarship with sub-scholarships
     * Type-safe: Request body validated against OpenAPI
     */
    createCombinedPhd: async (data: {
      name: string;
      name_en: string;
      description: string;
      description_en: string;
      sub_scholarships: Array<{
        code: string;
        name: string;
        name_en: string;
        description: string;
        description_en: string;
        sub_type: "nstc" | "moe";
        amount: number;
        min_gpa?: number;
        max_ranking_percent?: number;
        required_documents?: string[];
        application_start_date?: string;
        application_end_date?: string;
      }>;
    }): Promise<ApiResponse<ScholarshipType>> => {
      const response = await (typedClient.raw.POST as any)('/api/v1/scholarships/combined/phd', {
        body: data,
      });
      return toApiResponse<ScholarshipType>(response);
    },
  };
}
