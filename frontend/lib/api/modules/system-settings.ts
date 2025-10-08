/**
 * System Settings API Module
 *
 * Handles system configuration management:
 * - Get/create/update/delete configuration settings
 * - Configuration validation
 * - Category and data type management
 * - Audit log tracking
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

// System configuration types
type SystemConfiguration = {
  key: string;
  value: any;
  data_type: string;
  category: string;
  description?: string;
  is_sensitive: boolean;
  created_at: string;
  updated_at: string;
};

type SystemConfigurationCreate = {
  key: string;
  value: any;
  data_type: string;
  category: string;
  description?: string;
  is_sensitive?: boolean;
};

type SystemConfigurationUpdate = {
  value?: any;
  data_type?: string;
  category?: string;
  description?: string;
  is_sensitive?: boolean;
};

type SystemConfigurationValidation = {
  key: string;
  value: any;
  data_type: string;
};

type ConfigurationValidationResult = {
  valid: boolean;
  errors?: string[];
  warnings?: string[];
};

export function createSystemSettingsApi(client: ApiClient) {
  return {
    /**
     * Get all configurations with optional filtering
     */
    getConfigurations: async (
      category?: string,
      includeSensitive?: boolean
    ): Promise<ApiResponse<SystemConfiguration[]>> => {
      const params = new URLSearchParams();
      if (category) params.append("category", category);
      if (includeSensitive) params.append("include_sensitive", "true");
      const queryString = params.toString();
      return client.request(
        `/system-settings${queryString ? `?${queryString}` : ""}`
      );
    },

    /**
     * Get a specific configuration by key
     */
    getConfiguration: async (
      key: string,
      includeSensitive?: boolean
    ): Promise<ApiResponse<SystemConfiguration>> => {
      const params = includeSensitive ? "?include_sensitive=true" : "";
      return client.request(
        `/system-settings/${encodeURIComponent(key)}${params}`
      );
    },

    /**
     * Create a new configuration
     */
    createConfiguration: async (
      configData: SystemConfigurationCreate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      return client.request("/system-settings", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    /**
     * Update an existing configuration
     */
    updateConfiguration: async (
      key: string,
      configData: SystemConfigurationUpdate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      return client.request(`/system-settings/${encodeURIComponent(key)}`, {
        method: "PUT",
        body: JSON.stringify(configData),
      });
    },

    /**
     * Validate a configuration before saving
     */
    validateConfiguration: async (
      configData: SystemConfigurationValidation
    ): Promise<ApiResponse<ConfigurationValidationResult>> => {
      return client.request("/system-settings/validate", {
        method: "POST",
        body: JSON.stringify(configData),
      });
    },

    /**
     * Delete a configuration
     */
    deleteConfiguration: async (
      key: string
    ): Promise<ApiResponse<{ message: string }>> => {
      return client.request(`/system-settings/${encodeURIComponent(key)}`, {
        method: "DELETE",
      });
    },

    /**
     * Get all available configuration categories
     */
    getCategories: async (): Promise<ApiResponse<string[]>> => {
      return client.request("/system-settings/categories");
    },

    /**
     * Get all available data types
     */
    getDataTypes: async (): Promise<ApiResponse<string[]>> => {
      return client.request("/system-settings/data-types");
    },

    /**
     * Get audit logs for a specific configuration
     */
    getAuditLogs: async (
      configKey: string,
      limit: number = 50
    ): Promise<ApiResponse<any[]>> => {
      return client.request(
        `/system-settings/audit-logs/${encodeURIComponent(configKey)}?limit=${limit}`
      );
    },
  };
}
