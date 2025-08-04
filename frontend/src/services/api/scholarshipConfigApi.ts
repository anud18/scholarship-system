import { ApiResponse } from '@/lib/api';

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

export interface ScholarshipConfiguration {
  id: number;
  config_name: string;
  config_code: string;
  scholarship_type_id: number;
  application_period: 'semester' | 'academic_year';
  has_quota_limit: boolean;
  has_college_quota: boolean;
  quota_management_mode: 'none' | 'simple' | 'college_based' | 'interview_based';
  total_quota?: number;
  description?: string;
  is_active: boolean;
  effective_from?: string;
  effective_until?: string;
  config_data?: Record<string, any>;
  scholarship_type?: {
    code: string;
    category: string;
    name: string;
    name_en: string;
  };
}

export interface ScholarshipType {
  id: number;
  code: string;
  category: string;
  name: string;
  name_en: string;
  configurations: ScholarshipConfiguration[];
}

export const scholarshipConfigApi = {
  /**
   * Get all scholarship configurations with optional filtering
   */
  getConfigurations: async (params?: {
    scholarship_type_id?: number;
    category?: string;
    is_active?: boolean;
  }): Promise<ApiResponse<ScholarshipConfiguration[]>> => {
    const queryParams = new URLSearchParams();
    if (params?.scholarship_type_id) {
      queryParams.append('scholarship_type_id', params.scholarship_type_id.toString());
    }
    if (params?.category) {
      queryParams.append('category', params.category);
    }
    if (params?.is_active !== undefined) {
      queryParams.append('is_active', params.is_active.toString());
    }
    
    const queryString = queryParams.toString();
    const url = `/api/v1/scholarship-configurations/${queryString ? `?${queryString}` : ''}`;
    return apiCall(url);
  },

  /**
   * Get scholarship types with their configurations
   */
  getScholarshipTypesWithConfigs: async (): Promise<ApiResponse<ScholarshipType[]>> => {
    return apiCall('/api/v1/scholarship-configurations/types-with-configs');
  },

  /**
   * Get a single configuration by ID
   */
  getConfiguration: async (id: number): Promise<ApiResponse<ScholarshipConfiguration>> => {
    return apiCall(`/api/v1/scholarship-configurations/${id}`);
  },

  /**
   * Get quota status for a specific configuration
   */
  getQuotaStatus: async (id: number, semester?: string): Promise<ApiResponse<any>> => {
    const params = new URLSearchParams();
    if (semester) params.append('semester', semester);
    const queryString = params.toString();
    const url = `/api/v1/scholarship-configurations/${id}/quota-status${queryString ? `?${queryString}` : ''}`;
    return apiCall(url);
  },

  /**
   * Create a new configuration (admin only)
   */
  createConfiguration: async (config: Partial<ScholarshipConfiguration>): Promise<ApiResponse<ScholarshipConfiguration>> => {
    return apiCall('/api/v1/scholarship-configurations/', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  /**
   * Update an existing configuration (admin only)
   */
  updateConfiguration: async (id: number, config: Partial<ScholarshipConfiguration>): Promise<ApiResponse<ScholarshipConfiguration>> => {
    return apiCall(`/api/v1/scholarship-configurations/${id}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  },

  /**
   * Delete a configuration (admin only, soft delete)
   */
  deleteConfiguration: async (id: number): Promise<ApiResponse<void>> => {
    return apiCall(`/api/v1/scholarship-configurations/${id}`, {
      method: 'DELETE',
    });
  },

  /**
   * Clone a configuration (admin only)
   */
  cloneConfiguration: async (id: number, newName: string): Promise<ApiResponse<ScholarshipConfiguration>> => {
    return apiCall(`/api/v1/scholarship-configurations/${id}/clone`, {
      method: 'POST',
      body: JSON.stringify({ config_name: newName }),
    });
  },

  /**
   * Validate a configuration (admin only)
   */
  validateConfiguration: async (config: Partial<ScholarshipConfiguration>): Promise<ApiResponse<{ is_valid: boolean; errors: string[] }>> => {
    return apiCall('/api/v1/scholarship-configurations/validate', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  /**
   * Export qualified applicants list for whitelist-based scholarships
   */
  exportQualifiedApplicants: async (configId: number, semester?: string, format: 'csv' | 'excel' = 'csv'): Promise<any> => {
    const params = new URLSearchParams();
    params.append('format', format);
    if (semester) params.append('semester', semester);
    
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    
    const response = await fetch(`${API_BASE}/api/v1/scholarship-configurations/${configId}/export-qualified?${params.toString()}`, {
      headers: {
        ...(token && { 'Authorization': `Bearer ${token}` }),
      },
    });
    
    if (!response.ok) {
      throw new Error(`Export failed: ${response.statusText}`);
    }
    
    if (format === 'csv') {
      return { data: await response.text() };
    } else {
      return response.blob();
    }
  }
};