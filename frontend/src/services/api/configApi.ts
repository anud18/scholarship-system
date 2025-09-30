import { ApiResponse } from '@/lib/api';
import { ScholarshipTypeConfig, SubTypeConfig } from '@/types/quota';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const apiCall = async (url: string, options: RequestInit = {}) => {
  // Get auth token from localStorage if available
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;

  const response = await fetch(`${API_BASE}${url}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token && { 'Authorization': `Bearer ${token}` }),
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API call failed: ${response.statusText}`);
  }

  return response.json();
};

export interface CollegeConfig {
  code: string;
  name: string;
  name_en?: string;
}

export interface RegionConfig {
  code: string;
  name: string;
  name_en?: string;
}

export const configApi = {
  /**
   * Get all scholarship type configurations
   */
  getScholarshipTypeConfigs: async (): Promise<ApiResponse<ScholarshipTypeConfig[]>> => {
    return apiCall('/api/v1/scholarship-configurations/test/types');
  },

  /**
   * Get all sub-type configurations
   */
  getSubTypeConfigs: async (): Promise<ApiResponse<SubTypeConfig[]>> => {
    return apiCall('/api/v1/scholarship-configurations/test/sub-types');
  },

  /**
   * Get college configurations
   */
  getCollegeConfigs: async (): Promise<ApiResponse<CollegeConfig[]>> => {
    return apiCall('/api/v1/scholarship-configurations/test/colleges');
  },

  /**
   * Get region configurations
   */
  getRegionConfigs: async (): Promise<ApiResponse<RegionConfig[]>> => {
    return apiCall('/api/v1/scholarship-configurations/test/regions');
  },

  /**
   * Get matrix quota status for PhD scholarships
   */
  getMatrixQuotaStatus: async (semester: string = '2025-1'): Promise<ApiResponse<any>> => {
    return apiCall(`/api/v1/scholarship-configurations/test/matrix-quota-status/${semester}`);
  },

  /**
   * Get regional quota status for undergraduate freshman scholarships
   */
  getRegionalQuotaStatus: async (semester: string = '2025-1'): Promise<ApiResponse<any>> => {
    return apiCall(`/api/v1/scholarship-configurations/test/regional-quota-status/${semester}`);
  },

  /**
   * Update matrix quota (admin only)
   */
  updateMatrixQuota: async (
    subType: string,
    college: string,
    newQuota: number
  ): Promise<ApiResponse<any>> => {
    return apiCall('/api/v1/scholarship-configurations/matrix-quota', {
      method: 'PUT',
      body: JSON.stringify({
        sub_type: subType,
        college: college,
        new_quota: newQuota
      }),
    });
  },

  /**
   * Update regional quota (admin only)
   */
  updateRegionalQuota: async (
    regionCode: string,
    newQuota: number
  ): Promise<ApiResponse<any>> => {
    return apiCall('/api/v1/scholarship-configurations/regional-quota', {
      method: 'PUT',
      body: JSON.stringify({
        region_code: regionCode,
        new_quota: newQuota
      }),
    });
  }
};
