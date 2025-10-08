/**
 * Professor Review API Module
 *
 * Handles professor-level scholarship review operations:
 * - View assigned applications for review
 * - Submit and update recommendations
 * - Manage review status and sub-type selections
 * - Track review statistics
 */

import type { ApiClient } from '../client';
import type { ApiResponse, Application, PaginatedResponse } from '../../api';

export function createProfessorApi(client: ApiClient) {
  return {
    /**
     * Get applications requiring professor review
     * Includes special handling for paginated responses
     */
    getApplications: async (
      statusFilter?: string
    ): Promise<ApiResponse<Application[]>> => {
      try {
        const params = statusFilter ? `?status_filter=${statusFilter}` : "";
        console.log(
          "🔍 Requesting professor applications with params:",
          params
        );

        const response = await client.request<PaginatedResponse<Application>>(
          `/professor/applications${params}`
        );
        console.log("📨 Professor applications raw response:", response);

        if (
          response.success &&
          response.data &&
          Array.isArray(response.data.items)
        ) {
          console.log(
            "✅ Loaded professor applications:",
            response.data.items.length
          );
          return {
            success: true,
            message: response.message || "Applications loaded successfully",
            data: response.data.items,
          };
        }

        console.warn("⚠️ Unexpected response format:", response);
        return {
          success: false,
          message:
            response.message ||
            "Failed to load applications - unexpected response format",
          data: [],
        };
      } catch (error: any) {
        console.error("❌ Error in professor.getApplications:", error);
        return {
          success: false,
          message: error.message || "Failed to load applications",
          data: [],
        };
      }
    },

    /**
     * Get existing professor review for an application
     */
    getReview: async (applicationId: number): Promise<ApiResponse<any>> => {
      return client.request(`/professor/applications/${applicationId}/review`);
    },

    /**
     * Submit professor review for an application
     */
    submitReview: async (
      applicationId: number,
      reviewData: {
        recommendation?: string;
        items: Array<{
          sub_type_code: string;
          is_recommended: boolean;
          comments?: string;
        }>;
      }
    ): Promise<ApiResponse<any>> => {
      return client.request(`/professor/applications/${applicationId}/review`, {
        method: "POST",
        body: JSON.stringify(reviewData),
      });
    },

    /**
     * Update existing professor review
     */
    updateReview: async (
      applicationId: number,
      reviewId: number,
      reviewData: {
        recommendation?: string;
        items: Array<{
          sub_type_code: string;
          is_recommended: boolean;
          comments?: string;
        }>;
      }
    ): Promise<ApiResponse<any>> => {
      return client.request(
        `/professor/applications/${applicationId}/review/${reviewId}`,
        {
          method: "PUT",
          body: JSON.stringify(reviewData),
        }
      );
    },

    /**
     * Get available sub-types for an application
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
      return client.request(`/professor/applications/${applicationId}/sub-types`);
    },

    /**
     * Get basic review statistics
     */
    getStats: async (): Promise<
      ApiResponse<{
        pending_reviews: number;
        completed_reviews: number;
        overdue_reviews: number;
      }>
    > => {
      return client.request("/professor/stats");
    },
  };
}
