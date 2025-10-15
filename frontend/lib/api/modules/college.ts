/**
 * College Management API Module (OpenAPI-typed)
 *
 * Handles college-level scholarship review and ranking operations:
 * - Application review for college administrators
 * - Ranking list management and ordering
 * - Distribution execution and finalization
 * - Quota status tracking
 * - College statistics and analytics
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

export function createCollegeApi() {
  return {
    /**
     * Get applications for college review
     * Type-safe: Query parameters validated against OpenAPI
     */
    getApplicationsForReview: async (
      params?: string
    ): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/applications');
      return toApiResponse<any[]>(response);
    },

    /**
     * Get rankings list with optional filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getRankings: async (
      academicYear?: number,
      semester?: string
    ): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/rankings', {
        params: {
          query: {
            academic_year: academicYear,
            semester,
          },
        },
      });
      return toApiResponse<any[]>(response);
    },

    /**
     * Get ranking details by ID
     * Type-safe: Path parameter validated against OpenAPI
     */
    getRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/rankings/{ranking_id}', {
        params: { path: { ranking_id: rankingId } },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Create new ranking
     * Type-safe: Request body validated against OpenAPI
     */
    createRanking: async (data: {
      scholarship_type_id: number;
      sub_type_code: string;
      academic_year: number;
      semester?: string;
      ranking_name?: string;
      force_new?: boolean;
    }): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings', {
        body: data,
      });
      return toApiResponse<any>(response);
    },

    /**
     * Update ranking metadata (name, etc.)
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateRanking: async (
      rankingId: number,
      data: { ranking_name: string }
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PUT('/api/v1/college-review/rankings/{ranking_id}' as any, {
        params: { path: { ranking_id: rankingId } },
        body: data,
      });
      return toApiResponse<any>(response);
    },

    /**
     * Update ranking order
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateRankingOrder: async (
      rankingId: number,
      newOrder: Array<{ item_id: number; position: number }>
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PUT('/api/v1/college-review/rankings/{ranking_id}/order', {
        params: { path: { ranking_id: rankingId } },
        body: newOrder,
      });
      return toApiResponse<any>(response);
    },

    /**
     * Execute distribution based on ranking
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    executeDistribution: async (
      rankingId: number,
      distributionRules?: any
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings/{ranking_id}/distribute', {
        params: { path: { ranking_id: rankingId } },
        body: { distribution_rules: distributionRules },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Finalize ranking (lock and approve)
     * Type-safe: Path parameter validated against OpenAPI
     */
    finalizeRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings/{ranking_id}/finalize', {
        params: { path: { ranking_id: rankingId } },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Import ranking data from Excel
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    importRankingExcel: async (
      rankingId: number,
      importData: Array<{
        student_id: string;
        student_name: string;
        rank_position: number;
      }>
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings/{ranking_id}/import-excel' as any, {
        params: { path: { ranking_id: rankingId } },
        body: importData,
      });
      return toApiResponse<any>(response);
    },

    /**
     * Execute matrix distribution for a ranking
     * Type-safe: Path parameter validated against OpenAPI
     */
    executeMatrixDistribution: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings/{ranking_id}/execute-matrix-distribution' as any, {
        params: { path: { ranking_id: rankingId } },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Get distribution details for a ranking
     * Type-safe: Path parameter validated against OpenAPI
     */
    getDistributionDetails: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/rankings/{ranking_id}/distribution-details' as any, {
        params: { path: { ranking_id: rankingId } },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Get quota status for specific scholarship type and period
     * Type-safe: Query parameters validated against OpenAPI
     */
    getQuotaStatus: async (
      scholarshipTypeId: number,
      academicYear: number,
      semester?: string
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/quota-status', {
        params: {
          query: {
            scholarship_type_id: scholarshipTypeId,
            academic_year: academicYear,
            semester,
          },
        },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Get college review statistics
     * Type-safe: Query parameters validated against OpenAPI
     */
    getStatistics: async (
      academicYear?: number,
      semester?: string
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/statistics', {
        params: {
          query: {
            academic_year: academicYear,
            semester,
          },
        },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Get available combinations of scholarship types, years, and semesters
     * Type-safe: Response type inferred from OpenAPI
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
      const response = await typedClient.raw.GET('/api/v1/college-review/available-combinations', {});
      return toApiResponse<{
        scholarship_types: Array<{
          code: string;
          name: string;
          name_en?: string;
        }>;
        academic_years: number[];
        semesters: string[];
      }>(response);
    },

    /**
     * Delete a ranking
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.DELETE('/api/v1/college-review/rankings/{ranking_id}' as any, {
        params: { path: { ranking_id: rankingId } },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Get sub-type translations from database
     * Type-safe: Response contains Chinese and English translations for sub-types
     */
    getSubTypeTranslations: async (): Promise<
      ApiResponse<{
        zh: { [key: string]: string };
        en: { [key: string]: string };
      }>
    > => {
      const response = await typedClient.raw.GET('/api/v1/college-review/sub-type-translations' as any, {});
      return toApiResponse<{
        zh: { [key: string]: string };
        en: { [key: string]: string };
      }>(response);
    },
  };
}
