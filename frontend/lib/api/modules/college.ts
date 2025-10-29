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
import type { components as SchemaComponents } from '../generated/schema';

type CreateRankingRequest =
  SchemaComponents['schemas']['Body_create_ranking_api_v1_college_review_rankings_post'];
type CreateRankingInput = Omit<CreateRankingRequest, 'force_new'> & { force_new?: boolean };

export function createCollegeApi() {
  return {
    /**
     * Get applications for college review
     * Type-safe: Query parameters validated against OpenAPI
     */
    getApplicationsForReview: async (
      queryString?: string
    ): Promise<ApiResponse<any[]>> => {
      // Parse query string into params object
      const queryParams: {
        academic_year?: number;
        semester?: string;
        scholarship_type?: string;
      } = {};

      if (queryString) {
        const params = new URLSearchParams(queryString);

        if (params.has('academic_year')) {
          const yearStr = params.get('academic_year');
          if (yearStr) {
            queryParams.academic_year = parseInt(yearStr);
          }
        }
        if (params.has('semester')) {
          const semesterVal = params.get('semester');
          if (semesterVal) {
            queryParams.semester = semesterVal;
          }
        }
        if (params.has('scholarship_type')) {
          const typeVal = params.get('scholarship_type');
          if (typeVal) {
            queryParams.scholarship_type = typeVal;
          }
        }
      }

      const response = await typedClient.raw.GET('/api/v1/college-review/applications', {
        params: { query: queryParams }
      });
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
    createRanking: async (data: CreateRankingInput): Promise<ApiResponse<any>> => {
      const payload: CreateRankingRequest = {
        ...data,
        force_new: data.force_new ?? false,
      };
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings', {
        body: payload,
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
     * Unfinalize ranking (unlock to allow editing)
     * Type-safe: Path parameter validated against OpenAPI
     */
    unfinalizeRanking: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/rankings/{ranking_id}/unfinalize' as any, {
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
     * Get roster status for a ranking
     * 查詢排名的造冊狀態和進展
     * Type-safe: Path parameter validated against OpenAPI
     */
    getRankingRosterStatus: async (rankingId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/rankings/{ranking_id}/roster-status' as any, {
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
     * NOTE: Statistics endpoint was removed from backend
     * TODO: Reimplement using ApplicationReview + ApplicationReviewItem
     * See backend/app/api/v1/endpoints/college_review/utilities.py
     */

    /**
     * Get available combinations of scholarship types, years, and semesters
     * Type-safe: Response type inferred from OpenAPI
     */
    getAvailableCombinations: async (): Promise<
      ApiResponse<{
        scholarship_types: Array<{
          id: number;
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
          id: number;
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
     * Create or update college review for an application
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    reviewApplication: async (
      applicationId: number,
      reviewData: {
        recommendation: 'approve' | 'reject' | 'conditional';
        review_comments?: string;
        academic_score?: number;
        professor_review_score?: number;
        college_criteria_score?: number;
        special_circumstances_score?: number;
        decision_reason?: string;
        is_priority?: boolean;
        needs_special_attention?: boolean;
      }
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/applications/{application_id}/review' as any, {
        params: { path: { application_id: applicationId } },
        body: reviewData,
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

    /**
     * Get the college that the current college user has management permission for
     * Type-safe: Response contains college information from Academy table
     */
    getManagedCollege: async (): Promise<
      ApiResponse<{
        code: string;
        name: string;
        name_en: string;
        scholarship_count: number;
      } | null>
    > => {
      const response = await typedClient.raw.GET('/api/v1/college-review/managed-college' as any, {});
      return toApiResponse<{
        code: string;
        name: string;
        name_en: string;
        scholarship_count: number;
      } | null>(response);
    },

    /**
     * Get student preview information for college review
     * Type-safe: Path and query parameters validated against OpenAPI
     */
    getStudentPreview: async (
      studentId: string,
      academicYear?: number
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/students/{student_id}/preview', {
        params: {
          path: { student_id: studentId },
          query: { academic_year: academicYear },
        },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Get available sub-types for an application (unified review system)
     * Uses multi-role review API endpoint
     * Type-safe: Path parameter validated against OpenAPI
     */
    getSubTypes: async (applicationId: number): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/reviews/applications/{application_id}/sub-types' as any, {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse<any[]>(response);
    },

    /**
     * Get existing review for an application (unified review system)
     * Uses multi-role review API endpoint
     * Type-safe: Path parameter validated against OpenAPI
     */
    getReview: async (applicationId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/reviews/applications/{application_id}/review' as any, {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse<any>(response);
    },

    /**
     * Submit review for an application (unified review system with sub-type items)
     * Uses multi-role review API endpoint
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    submitReview: async (
      applicationId: number,
      reviewData: {
        items: Array<{
          sub_type_code: string;
          recommendation: 'approve' | 'reject';
          comments?: string;
        }>;
      }
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/reviews/applications/{application_id}/review' as any, {
        params: { path: { application_id: applicationId } },
        body: reviewData,
      });
      return toApiResponse<any>(response);
    },
  };
}
