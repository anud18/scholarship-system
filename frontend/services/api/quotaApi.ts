/**
 * API client for quota management
 */

import { ApiResponse } from '@/lib/api'
import {
  MatrixQuotaData,
  ScholarshipQuotaOverview,
  UpdateMatrixQuotaRequest,
  UpdateQuotaResponse,
  CollegeConfig,
  SubTypeConfig,
  AvailablePeriod
} from '@/types/quota'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/**
 * Helper function to make authenticated API calls
 */
const apiCall = async <T = any>(
  url: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> => {
  // Get auth token from localStorage if available
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null

  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers,
    },
    ...options,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `API call failed: ${response.statusText}`)
  }

  return response.json()
}

export const quotaApi = {
  /**
   * Get available semesters/academic years
   */
  getAvailableSemesters: async (quotaManagementMode?: string): Promise<ApiResponse<AvailablePeriod[]>> => {
    const params = quotaManagementMode ? `?quota_management_mode=${quotaManagementMode}` : ''
    return apiCall<AvailablePeriod[]>(`/api/v1/scholarship-configurations/available-semesters${params}`)
  },

  /**
   * Get quota overview for all scholarship types
   */
  getQuotaOverview: async (period: string): Promise<ApiResponse<ScholarshipQuotaOverview[]>> => {
    return apiCall<ScholarshipQuotaOverview[]>(
      `/api/v1/scholarship-configurations/overview/${period}`
    )
  },

  /**
   * Get matrix quota status for PhD scholarships
   */
  getMatrixQuotaStatus: async (period: string): Promise<ApiResponse<MatrixQuotaData>> => {
    return apiCall<MatrixQuotaData>(
      `/api/v1/scholarship-configurations/matrix-quota-status/${period}`
    )
  },

  /**
   * Update a specific matrix quota
   */
  updateMatrixQuota: async (
    request: UpdateMatrixQuotaRequest
  ): Promise<ApiResponse<UpdateQuotaResponse>> => {
    return apiCall<UpdateQuotaResponse>('/api/v1/scholarship-configurations/matrix-quota', {
      method: 'PUT',
      body: JSON.stringify(request),
    })
  },

  /**
   * Get college configurations
   */
  getCollegeConfigs: async (): Promise<ApiResponse<CollegeConfig[]>> => {
    return apiCall<CollegeConfig[]>('/api/v1/scholarship-configurations/colleges')
  },

  /**
   * Get scholarship type configurations
   */
  getScholarshipTypeConfigs: async (): Promise<ApiResponse<any[]>> => {
    return apiCall<any[]>('/api/v1/scholarship-configurations/scholarship-types')
  },

  /**
   * Batch update multiple matrix quotas
   */
  batchUpdateMatrixQuotas: async (
    updates: UpdateMatrixQuotaRequest[]
  ): Promise<ApiResponse<UpdateQuotaResponse[]>> => {
    // Process updates sequentially to avoid conflicts
    const results: UpdateQuotaResponse[] = []
    const errors: string[] = []

    for (const update of updates) {
      try {
        const response = await quotaApi.updateMatrixQuota(update)
        if (response.success && response.data) {
          results.push(response.data)
        } else {
          errors.push(`Failed to update ${update.sub_type}-${update.college}: ${response.message}`)
        }
      } catch (error) {
        errors.push(`Error updating ${update.sub_type}-${update.college}: ${error}`)
      }
    }

    return {
      success: errors.length === 0,
      message: errors.length > 0
        ? `Batch update completed with ${errors.length} errors`
        : 'All quotas updated successfully',
      data: results,
      errors: errors.length > 0 ? errors : undefined
    }
  },

  /**
   * Export quota data as CSV
   */
  exportQuotaData: async (
    academicYear: string,
    format: 'csv' | 'excel' = 'csv'
  ): Promise<Blob> => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
    const params = new URLSearchParams({
      academic_year: academicYear,
      format
    })

    const response = await fetch(
      `${API_BASE}/api/v1/scholarship-configurations/export-quota?${params}`,
      {
        headers: {
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
      }
    )

    if (!response.ok) {
      throw new Error(`Export failed: ${response.statusText}`)
    }

    return response.blob()
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
      limit: limit.toString()
    })
    return apiCall<any[]>(`/api/v1/scholarship-configurations/quota-history?${params}`)
  },

  /**
   * Validate quota changes before applying
   */
  validateQuotaChange: async (
    request: UpdateMatrixQuotaRequest
  ): Promise<ApiResponse<{ valid: boolean; warnings: string[] }>> => {
    return apiCall<{ valid: boolean; warnings: string[] }>(
      '/api/v1/scholarship-configurations/validate-quota',
      {
        method: 'POST',
        body: JSON.stringify(request),
      }
    )
  }
}

// Export helper functions for quota calculations
export function calculateTotalQuota(quotaData: MatrixQuotaData): number {
  let total = 0
  Object.values(quotaData.phd_quotas).forEach(colleges => {
    Object.values(colleges).forEach(cell => {
      total += cell.total_quota
    })
  })
  return total
}

export function calculateUsagePercentage(used: number, total: number): number {
  if (total === 0) return 0
  return Math.round((used / total) * 100)
}

export function getQuotaStatusColor(percentage: number): string {
  if (percentage >= 95) return 'red'
  if (percentage >= 80) return 'orange'
  if (percentage >= 50) return 'yellow'
  return 'green'
}
