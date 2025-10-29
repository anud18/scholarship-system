/**
 * Whitelist Management API Module (OpenAPI-typed)
 *
 * Handles scholarship whitelist operations:
 * - Enable/disable whitelist feature for scholarships
 * - View whitelist entries with pagination and search
 * - Batch add/remove students
 * - Import/export whitelist data via Excel
 * - Download template for bulk import
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import { createFileUploadFormData, type MultipartFormData } from '../form-data-helpers';
import type { ApiResponse, WhitelistResponse } from '../../api.legacy';

export function createWhitelistApi() {
  return {
    /**
     * Toggle scholarship whitelist feature
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    toggleScholarshipWhitelist: async (
      scholarshipId: number,
      enabled: boolean
    ): Promise<ApiResponse<{ success: boolean }>> => {
      const response = await typedClient.raw.PATCH('/api/v1/scholarships/{id}/whitelist', {
        params: { path: { id: scholarshipId } },
        body: { enabled },
      });
      return toApiResponse<{ success: boolean }>(response);
    },

    /**
     * Get whitelist entries for a configuration
     * Type-safe: Path and query parameters validated against OpenAPI
     */
    getConfigurationWhitelist: async (
      configurationId: number,
      params?: {
        page?: number;
        size?: number;
        search?: string;
      }
    ): Promise<ApiResponse<WhitelistResponse[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/{id}/whitelist', {
        params: {
          path: { id: configurationId },
          ...(params && { query: params }),
        } as any,
      });
      return toApiResponse<WhitelistResponse[]>(response);
    },

    /**
     * Batch add students to whitelist
     * Type-safe: Path parameter validated, body type correctly defined
     * Note: OpenAPI schema incorrectly shows students as Record<string, never>[]
     * but actual backend accepts { nycu_id: string; sub_type: string }[]
     */
    batchAddWhitelist: async (
      configurationId: number,
      request: { students: Array<{ nycu_id: string; sub_type: string }> }
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_items: Array<{
          nycu_id: string;
          reason: string;
        }>;
      }>
    > => {
      const response = await typedClient.raw.POST('/api/v1/scholarship-configurations/{id}/whitelist/batch', {
        params: { path: { id: configurationId } },
        body: request as any, // OpenAPI schema bug: shows Record<string, never>[] instead of proper student type
      });
      return toApiResponse<{
        success_count: number;
        failed_items: Array<{ nycu_id: string; reason: string; }>;
      }>(response);
    },

    /**
     * Batch remove students from whitelist
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    batchRemoveWhitelist: async (
      configurationId: number,
      request: {
        nycu_ids: string[];
        sub_type?: string;
      }
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_items: Array<{
          id: number;
          reason: string;
        }>;
      }>
    > => {
      const response = await typedClient.raw.DELETE('/api/v1/scholarship-configurations/{id}/whitelist/batch', {
        params: { path: { id: configurationId } },
        body: request,
      });
      return toApiResponse<{
        success_count: number;
        failed_items: Array<{ id: number; reason: string; }>;
      }>(response);
    },

    /**
     * Import whitelist from Excel
     * Type-safe: Path parameter and FormData properly typed
     */
    importWhitelistExcel: async (
      configurationId: number,
      file: File
    ): Promise<
      ApiResponse<{
        success_count: number;
        failed_items: Array<{
          row: number;
          nycu_id: string;
          reason: string;
        }>;
      }>
    > => {
      const formData = createFileUploadFormData({ file });

      const response = await typedClient.raw.POST('/api/v1/scholarship-configurations/{id}/whitelist/import', {
        params: { path: { id: configurationId } },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<{
        success_count: number;
        failed_items: Array<{ row: number; nycu_id: string; reason: string; }>;
      }>(response);
    },

    /**
     * Export whitelist to Excel
     * Type-safe: Returns Blob for file download
     */
    exportWhitelistExcel: async (
      configurationId: number
    ): Promise<Blob> => {
      const token = typedClient.getToken();
      const baseURL = typeof window !== "undefined" ? "" : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/scholarship-configurations/${configurationId}/whitelist/export`,
        {
          method: "GET",
          headers: {
            ...(token && { Authorization: `Bearer ${token}` }),
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "匯出白名單失敗");
      }

      return response.blob();
    },

    /**
     * Download whitelist import template
     * Type-safe: Returns Blob for file download
     */
    downloadTemplate: async (configurationId: number): Promise<Blob> => {
      const token = typedClient.getToken();
      const baseURL = typeof window !== "undefined" ? "" : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/scholarship-configurations/${configurationId}/whitelist/template`,
        {
          method: "GET",
          headers: {
            ...(token && { Authorization: `Bearer ${token}` }),
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "下載範本失敗");
      }

      return response.blob();
    },
  };
}
