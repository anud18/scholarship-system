/**
 * Quota Management API Module
 *
 * Handles scholarship quota management including:
 * - Matrix quota status and updates
 * - College and scholarship type configurations
 * - Quota history and validation
 * - Data export functionality
 *
 * Integrated from services/api/quotaApi.ts
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

// Import types from quota types
// These types should ideally be in a shared types file
type MatrixQuotaData = {
  academic_year: string;
  quota_management_mode: string;
  phd_quotas: Record<string, Record<string, any>>;
  college_configs: any[];
  sub_type_configs: any[];
};

type ScholarshipQuotaOverview = {
  scholarship_type: string;
  scholarship_type_zh: string;
  total_quota: number;
  used_quota: number;
  remaining_quota: number;
  usage_percentage: number;
};

type UpdateMatrixQuotaRequest = {
  academic_year: string;
  sub_type: string;
  college: string;
  total_quota: number;
};

type UpdateQuotaResponse = {
  academic_year: string;
  sub_type: string;
  college: string;
  total_quota: number;
  used_quota: number;
  remaining_quota: number;
};

type CollegeConfig = {
  college_code: string;
  college_name: string;
  college_name_en: string;
};

type AvailablePeriod = {
  period: string;
  display_name: string;
  quota_management_mode: string;
};

export function createQuotaApi(client: ApiClient) {
  return {
    /**
     * Get available semesters/academic years
     */
    getAvailableSemesters: async (
      quotaManagementMode?: string
    ): Promise<ApiResponse<AvailablePeriod[]>> => {
      const params = quotaManagementMode
        ? `?quota_management_mode=${quotaManagementMode}`
        : "";
      return client.request<AvailablePeriod[]>(
        `/scholarship-configurations/available-semesters${params}`
      );
    },

    /**
     * Get quota overview for all scholarship types
     */
    getQuotaOverview: async (
      period: string
    ): Promise<ApiResponse<ScholarshipQuotaOverview[]>> => {
      return client.request<ScholarshipQuotaOverview[]>(
        `/scholarship-configurations/overview/${period}`
      );
    },

    /**
     * Get matrix quota status for PhD scholarships
     */
    getMatrixQuotaStatus: async (
      period: string
    ): Promise<ApiResponse<MatrixQuotaData>> => {
      return client.request<MatrixQuotaData>(
        `/scholarship-configurations/matrix-quota-status/${period}`
      );
    },

    /**
     * Update a specific matrix quota
     */
    updateMatrixQuota: async (
      request: UpdateMatrixQuotaRequest
    ): Promise<ApiResponse<UpdateQuotaResponse>> => {
      return client.request<UpdateQuotaResponse>(
        "/scholarship-configurations/matrix-quota",
        {
          method: "PUT",
          body: JSON.stringify(request),
        }
      );
    },

    /**
     * Get college configurations
     */
    getCollegeConfigs: async (): Promise<ApiResponse<CollegeConfig[]>> => {
      return client.request<CollegeConfig[]>(
        "/scholarship-configurations/colleges"
      );
    },

    /**
     * Get scholarship type configurations
     */
    getScholarshipTypeConfigs: async (): Promise<ApiResponse<any[]>> => {
      return client.request<any[]>(
        "/scholarship-configurations/scholarship-types"
      );
    },

    /**
     * Batch update multiple matrix quotas
     */
    batchUpdateMatrixQuotas: async (
      updates: UpdateMatrixQuotaRequest[]
    ): Promise<ApiResponse<UpdateQuotaResponse[]>> => {
      // Process updates sequentially to avoid conflicts
      const results: UpdateQuotaResponse[] = [];
      const errors: string[] = [];

      for (const update of updates) {
        try {
          const response = await client.request<UpdateQuotaResponse>(
            "/scholarship-configurations/matrix-quota",
            {
              method: "PUT",
              body: JSON.stringify(update),
            }
          );
          if (response.success && response.data) {
            results.push(response.data);
          } else {
            errors.push(
              `Failed to update ${update.sub_type}-${update.college}: ${response.message}`
            );
          }
        } catch (error) {
          errors.push(
            `Error updating ${update.sub_type}-${update.college}: ${error}`
          );
        }
      }

      return {
        success: errors.length === 0,
        message:
          errors.length > 0
            ? `Batch update completed with ${errors.length} errors`
            : "All quotas updated successfully",
        data: results,
        errors: errors.length > 0 ? errors : undefined,
      };
    },

    /**
     * Export quota data as CSV or Excel
     */
    exportQuotaData: async (
      academicYear: string,
      format: "csv" | "excel" = "csv"
    ): Promise<Blob> => {
      const token = client.getToken();
      const params = new URLSearchParams({
        academic_year: academicYear,
        format,
      });

      const baseURL = typeof window !== "undefined" ? "" : process.env.INTERNAL_API_URL || "http://localhost:8000";
      const response = await fetch(
        `${baseURL}/api/v1/scholarship-configurations/export-quota?${params}`,
        {
          headers: {
            ...(token && { Authorization: `Bearer ${token}` }),
          },
        }
      );

      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`);
      }

      return response.blob();
    },

    /**
     * Get quota history/changelog
     */
    getQuotaHistory: async (
      academicYear: string,
      limit: number = 50
    ): Promise<ApiResponse<any[]>> => {
      const params = new URLSearchParams({
        academic_year: academicYear,
        limit: limit.toString(),
      });
      return client.request<any[]>(
        `/scholarship-configurations/quota-history?${params}`
      );
    },

    /**
     * Validate quota changes before applying
     */
    validateQuotaChange: async (
      request: UpdateMatrixQuotaRequest
    ): Promise<ApiResponse<{ valid: boolean; warnings: string[] }>> => {
      return client.request<{ valid: boolean; warnings: string[] }>(
        "/scholarship-configurations/validate-quota",
        {
          method: "POST",
          body: JSON.stringify(request),
        }
      );
    },
  };
}

/**
 * Helper functions for quota calculations
 */

export function calculateTotalQuota(quotaData: MatrixQuotaData): number {
  let total = 0;
  Object.values(quotaData.phd_quotas).forEach(colleges => {
    Object.values(colleges).forEach(cell => {
      total += cell.total_quota;
    });
  });
  return total;
}

export function calculateUsagePercentage(used: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((used / total) * 100);
}

export function getQuotaStatusColor(percentage: number): string {
  if (percentage >= 95) return "red";
  if (percentage >= 80) return "orange";
  if (percentage >= 50) return "yellow";
  return "green";
}
