/**
 * Scholarships API Module
 *
 * Handles scholarship-related operations including:
 * - Fetching eligible scholarships
 * - Getting scholarship details
 * - Managing combined PhD scholarships
 */

import type { ApiClient } from '../client';
import type { ApiResponse, ScholarshipType } from '../../api';

export function createScholarshipsApi(client: ApiClient) {
  return {
    /**
     * Get scholarships eligible for current user
     */
    getEligible: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      return client.request("/scholarships/eligible");
    },

    /**
     * Get scholarship by ID
     */
    getById: async (id: number): Promise<ApiResponse<ScholarshipType>> => {
      return client.request(`/scholarships/${id}`);
    },

    /**
     * Get all scholarships
     */
    getAll: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/scholarships");
    },

    /**
     * Get combined scholarships
     */
    getCombined: async (): Promise<ApiResponse<ScholarshipType[]>> => {
      return client.request("/scholarships/combined/list");
    },

    /**
     * Create combined PhD scholarship with sub-scholarships
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
      return client.request("/scholarships/combined/phd", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
  };
}
