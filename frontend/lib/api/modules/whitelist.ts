/**
 * Whitelist Management API Module
 *
 * Handles scholarship whitelist operations:
 * - Enable/disable whitelist feature for scholarships
 * - View whitelist entries with pagination and search
 * - Batch add/remove students
 * - Import/export whitelist data via Excel
 * - Download template for bulk import
 */

import type { ApiClient } from '../client';
import type { ApiResponse, WhitelistResponse } from '../../api';

export function createWhitelistApi(client: ApiClient) {
  return {
    /**
     * Toggle scholarship whitelist feature
     */
    toggleScholarshipWhitelist: async (
      scholarshipId: number,
      enabled: boolean
    ): Promise<ApiResponse<{ success: boolean }>> => {
      return client.request(`/scholarships/${scholarshipId}/whitelist`, {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      });
    },

    /**
     * Get whitelist entries for a configuration
     */
    getConfigurationWhitelist: async (
      configurationId: number,
      params?: {
        page?: number;
        size?: number;
        search?: string;
      }
    ): Promise<ApiResponse<WhitelistResponse[]>> => {
      const queryParams = new URLSearchParams();
      if (params?.page) queryParams.append("page", params.page.toString());
      if (params?.size) queryParams.append("size", params.size.toString());
      if (params?.search) queryParams.append("search", params.search);

      const queryString = queryParams.toString();
      const url = `/scholarship-configurations/${configurationId}/whitelist${
        queryString ? `?${queryString}` : ""
      }`;

      return client.request(url);
    },

    /**
     * Batch add students to whitelist
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
      return client.request(
        `/scholarship-configurations/${configurationId}/whitelist/batch`,
        {
          method: "POST",
          body: JSON.stringify(request),
        }
      );
    },

    /**
     * Batch remove students from whitelist
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
      return client.request(
        `/scholarship-configurations/${configurationId}/whitelist/batch`,
        {
          method: "DELETE",
          body: JSON.stringify(request),
        }
      );
    },

    /**
     * Import whitelist from Excel
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
      const formData = new FormData();
      formData.append("file", file);

      return client.request(
        `/scholarship-configurations/${configurationId}/whitelist/import`,
        {
          method: "POST",
          body: formData,
          headers: {
            // Let browser set Content-Type with boundary for FormData
          },
        }
      );
    },

    /**
     * Export whitelist to Excel
     */
    exportWhitelistExcel: async (
      configurationId: number
    ): Promise<Blob> => {
      const token = client.getToken();
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
     */
    downloadTemplate: async (configurationId: number): Promise<Blob> => {
      const token = client.getToken();
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
