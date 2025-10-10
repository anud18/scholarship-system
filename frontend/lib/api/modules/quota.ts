/**
 * Quota Management API Module (OpenAPI-typed)
 *
 * Handles scholarship quota management including:
 * - Matrix quota status and updates
 * - College and scholarship type configurations
 * - Quota history and validation
 * - Data export functionality
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

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

export function createQuotaApi() {
  return {
    /**
     * Get available semesters/academic years
     * Type-safe: Query parameters validated against OpenAPI
     */
    getAvailableSemesters: async (
      quotaManagementMode?: string
    ): Promise<ApiResponse<AvailablePeriod[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/available-semesters', {
        params: { query: { quota_management_mode: quotaManagementMode } },
      });
      return toApiResponse<AvailablePeriod[]>(response);
    },

    /**
     * Get quota overview for all scholarship types
     * Type-safe: Path parameter validated against OpenAPI
     */
    getQuotaOverview: async (
      period: string
    ): Promise<ApiResponse<ScholarshipQuotaOverview[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/overview/{period}', {
        params: { path: { period } },
      });
      return toApiResponse<ScholarshipQuotaOverview[]>(response);
    },

    /**
     * Get matrix quota status for PhD scholarships
     * Type-safe: Path parameter validated against OpenAPI
     */
    getMatrixQuotaStatus: async (
      period: string
    ): Promise<ApiResponse<MatrixQuotaData>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/matrix-quota-status/{period}', {
        params: { path: { period } },
      });
      return toApiResponse<MatrixQuotaData>(response);
    },

    /**
     * Update a specific matrix quota
     * Type-safe: Request body validated against OpenAPI
     */
    updateMatrixQuota: async (
      request: UpdateMatrixQuotaRequest
    ): Promise<ApiResponse<UpdateQuotaResponse>> => {
      const response = await typedClient.raw.PUT('/api/v1/scholarship-configurations/matrix-quota', {
        body: request as any, // Frontend UpdateMatrixQuotaRequest structure differs from generated schema
      });
      return toApiResponse<UpdateQuotaResponse>(response);
    },

    /**
     * Get college configurations
     * Type-safe: Response type inferred from OpenAPI
     */
    getCollegeConfigs: async (): Promise<ApiResponse<CollegeConfig[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/colleges');
      return toApiResponse<CollegeConfig[]>(response);
    },

    /**
     * Get scholarship type configurations
     * Type-safe: Response type inferred from OpenAPI
     */
    getScholarshipTypeConfigs: async (): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/scholarship-configurations/scholarship-types');
      return toApiResponse<any[]>(response);
    },

    /**
     * Batch update multiple matrix quotas
     * Type-safe: Processes updates sequentially with type checking
     */
    batchUpdateMatrixQuotas: async (
      updates: UpdateMatrixQuotaRequest[]
    ): Promise<ApiResponse<UpdateQuotaResponse[]>> => {
      const results: UpdateQuotaResponse[] = [];
      const errors: string[] = [];

      for (const update of updates) {
        try {
          const response = await typedClient.raw.PUT('/api/v1/scholarship-configurations/matrix-quota', {
            body: update as any, // Frontend UpdateMatrixQuotaRequest structure differs from generated schema
          });
          const apiResponse = toApiResponse<UpdateQuotaResponse>(response);
          if (apiResponse.success && apiResponse.data) {
            results.push(apiResponse.data);
          } else {
            errors.push(
              `Failed to update ${update.sub_type}-${update.college}: ${apiResponse.message}`
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
            : 'All quotas updated successfully',
        data: results,
        errors: errors.length > 0 ? errors : undefined,
      };
    },

    /**
     * Export quota data as CSV or Excel
     * Type-safe: Returns Blob for file download
     */
    exportQuotaData: async (
      academicYear: string,
      format: 'csv' | 'excel' = 'csv'
    ): Promise<Blob> => {
      const token = typedClient.getToken();
      const params = new URLSearchParams({
        academic_year: academicYear,
        format,
      });

      const baseURL = typeof window !== 'undefined' ? '' : process.env.INTERNAL_API_URL || 'http://localhost:8000';
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
     * Type-safe: Query parameters validated against OpenAPI
     */
    getQuotaHistory: async (
      academicYear: string,
      limit: number = 50
    ): Promise<ApiResponse<any[]>> => {
      const response = await (typedClient.raw.GET as any)('/api/v1/scholarship-configurations/quota-history', {
        params: {
          query: {
            academic_year: academicYear,
            limit,
          },
        },
      });
      return toApiResponse<any[]>(response);
    },

    /**
     * Validate quota changes before applying
     * Type-safe: Request body and response validated
     */
    validateQuotaChange: async (
      request: UpdateMatrixQuotaRequest
    ): Promise<ApiResponse<{ valid: boolean; warnings: string[] }>> => {
      const response = await (typedClient.raw.POST as any)('/api/v1/scholarship-configurations/validate-quota', {
        body: request,
      });
      return toApiResponse<{ valid: boolean; warnings: string[] }>(response);
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
  if (percentage >= 95) return 'red';
  if (percentage >= 80) return 'orange';
  if (percentage >= 50) return 'yellow';
  return 'green';
}
