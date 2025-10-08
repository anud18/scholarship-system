/**
 * College Management API Module
 *
 * Handles college-level scholarship review and ranking operations:
 * - Application review for college administrators
 * - Ranking list management and ordering
 * - Distribution execution and finalization
 * - Quota status tracking
 * - College statistics and analytics
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

export function createCollegeApi(client: ApiClient) {
  return {
    /**
     * Get applications for college review
     */
    getApplicationsForReview: async (
      params?: string
    ): Promise<ApiResponse<any[]>> => {
      return client.request(`/college/applications${params ? `?${params}` : ""}`);
    },

    /**
     * Get rankings list with optional filters
     */
    getRankings: async (
      academicYear?: number,
      semester?: string
    ): Promise<ApiResponse<any[]>> => {
      const params = new URLSearchParams();
      if (academicYear) params.append("academic_year", academicYear.toString());
      if (semester) params.append("semester", semester);
      return client.request(
        `/college/rankings${params.toString() ? `?${params.toString()}` : ""}`
      );
    },

    /**
     * Get ranking details by ID
     */
    getRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      return client.request(`/college/rankings/${rankingId}`);
    },

    /**
     * Create new ranking
     */
    createRanking: async (data: {
      scholarship_type_id: number;
      sub_type_code: string;
      academic_year: number;
      semester?: string;
      ranking_name?: string;
    }): Promise<ApiResponse<any>> => {
      return client.request("/college/rankings", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },

    /**
     * Update ranking order
     */
    updateRankingOrder: async (
      rankingId: number,
      newOrder: Array<{ item_id: number; position: number }>
    ): Promise<ApiResponse<any>> => {
      return client.request(`/college/rankings/${rankingId}/order`, {
        method: "PUT",
        body: JSON.stringify(newOrder),
      });
    },

    /**
     * Execute distribution based on ranking
     */
    executeDistribution: async (
      rankingId: number,
      distributionRules?: any
    ): Promise<ApiResponse<any>> => {
      return client.request(`/college/rankings/${rankingId}/distribute`, {
        method: "POST",
        body: JSON.stringify({ distribution_rules: distributionRules }),
      });
    },

    /**
     * Finalize ranking (lock and approve)
     */
    finalizeRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      return client.request(`/college/rankings/${rankingId}/finalize`, {
        method: "POST",
      });
    },

    /**
     * Get quota status for specific scholarship type and period
     */
    getQuotaStatus: async (
      scholarshipTypeId: number,
      academicYear: number,
      semester?: string
    ): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams({
        scholarship_type_id: scholarshipTypeId.toString(),
        academic_year: academicYear.toString(),
      });
      if (semester) params.append("semester", semester);
      return client.request(`/college/quota-status?${params.toString()}`);
    },

    /**
     * Get college review statistics
     */
    getStatistics: async (
      academicYear?: number,
      semester?: string
    ): Promise<ApiResponse<any>> => {
      const params = new URLSearchParams();
      if (academicYear) params.append("academic_year", academicYear.toString());
      if (semester) params.append("semester", semester);
      return client.request(
        `/college/statistics${params.toString() ? `?${params.toString()}` : ""}`
      );
    },

    /**
     * Get available combinations of scholarship types, years, and semesters
     */
    getAvailableCombinations: async (): Promise<
      ApiResponse<{
        scholarship_types: Array<{
          code: string;
          name: string;
          name_en?: string;
        }>;
        academic_years: number[];
        semesters: string[];
      }>
    > => {
      return client.request("/college/available-combinations");
    },
  };
}
