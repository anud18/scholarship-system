/**
 * Professor Review API Module (OpenAPI-typed)
 *
 * Handles professor-level scholarship review operations:
 * - View assigned applications for review
 * - Submit and update recommendations
 * - Manage review status and sub-type selections
 * - Track review statistics
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse, PaginatedResponse } from '../types';
import type { Application } from '../types';

/**
 * Payload returned by GET /professor/applications/{id}/review and
 * POST/PUT review submission. The backend attaches a flexible
 * object (review record fields vary by scholarship type), so we
 * keep an index signature on top of the known `id` and `items`
 * properties.
 */
export interface ProfessorReviewPayload {
  id: number;
  recommendation?: string;
  items?: Array<{
    sub_type_code: string;
    recommendation: 'approve' | 'reject' | 'pending';
    comments?: string;
  }>;
  [key: string]: unknown;
}

/**
 * Body shape accepted by submitReview/updateReview.
 */
export interface ProfessorReviewBody {
  items: Array<{
    sub_type_code: string;
    recommendation: 'approve' | 'reject';
    comments?: string;
  }>;
}

export function createProfessorApi() {
  return {
    /**
     * Get applications requiring professor review
     * Includes special handling for paginated responses
     */
    getApplications: async (
      statusFilter?: string
    ): Promise<ApiResponse<Application[]>> => {
      try {
        const response = await typedClient.raw.GET('/api/v1/professor/applications', {
          params: {
            query: {
              status_filter: statusFilter,
            },
          },
        });

        const apiResponse = toApiResponse<PaginatedResponse<Application>>(response);

        if (
          apiResponse.success &&
          apiResponse.data &&
          Array.isArray(apiResponse.data.items)
        ) {
          return {
            success: true,
            message: apiResponse.message || "Applications loaded successfully",
            data: apiResponse.data.items,
          };
        }

        return {
          success: false,
          message:
            apiResponse.message ||
            "Failed to load applications - unexpected response format",
          data: [],
        };
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : null;
        return {
          success: false,
          message: message || "Failed to load applications",
          data: [],
        };
      }
    },

    /**
     * Get existing professor review for an application
     * Type-safe: Path parameter validated against OpenAPI
     */
    getReview: async (applicationId: number): Promise<ApiResponse<ProfessorReviewPayload | null>> => {
      const response = await typedClient.raw.GET('/api/v1/professor/applications/{application_id}/review', {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse<ProfessorReviewPayload | null>(response);
    },

    /**
     * Submit professor review for an application
     * Type-safe: Path parameter and request body validated against OpenAPI
     * NEW FORMAT: Uses recommendation ('approve' | 'reject') instead of is_recommended (boolean)
     */
    submitReview: async (
      applicationId: number,
      reviewData: ProfessorReviewBody
    ): Promise<ApiResponse<ProfessorReviewPayload | null>> => {
      const response = await typedClient.raw.POST('/api/v1/professor/applications/{application_id}/review', {
        params: { path: { application_id: applicationId } },
        body: reviewData,
      });
      return toApiResponse<ProfessorReviewPayload | null>(response);
    },

    /**
     * Update existing professor review
     * Type-safe: Path parameters and request body validated against OpenAPI
     * NEW FORMAT: Uses recommendation ('approve' | 'reject') instead of is_recommended (boolean)
     */
    updateReview: async (
      applicationId: number,
      reviewId: number,
      reviewData: ProfessorReviewBody
    ): Promise<ApiResponse<ProfessorReviewPayload | null>> => {
      const response = await typedClient.raw.PUT('/api/v1/professor/applications/{application_id}/review/{review_id}', {
        params: { path: { application_id: applicationId, review_id: reviewId } },
        body: reviewData,
      });
      return toApiResponse<ProfessorReviewPayload | null>(response);
    },

    /**
     * Get available sub-types for an application
     * Type-safe: Path parameter validated against OpenAPI
     */
    getSubTypes: async (
      applicationId: number
    ): Promise<
      ApiResponse<
        Array<{
          value: string;
          label: string;
          label_en: string;
          is_default: boolean;
        }>
      >
    > => {
      const response = await typedClient.raw.GET('/api/v1/professor/applications/{application_id}/sub-types', {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse(response);
    },

    /**
     * Get basic review statistics
     * Type-safe: Response type inferred from OpenAPI
     */
    getStats: async (): Promise<
      ApiResponse<{
        pending_reviews: number;
        completed_reviews: number;
        overdue_reviews: number;
      }>
    > => {
      const response = await typedClient.raw.GET('/api/v1/professor/stats');
      return toApiResponse(response);
    },
  };
}
