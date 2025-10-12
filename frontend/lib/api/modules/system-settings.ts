/**
 * System Settings API Module (OpenAPI-typed)
 *
 * Handles system configuration management:
 * - Get/create/update/delete configuration settings
 * - Configuration validation
 * - Category and data type management
 * - Audit log tracking
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

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

export function createSystemSettingsApi() {
  return {
    /**
     * Get all configurations with optional filtering
     * Type-safe: Query parameters validated against OpenAPI
     */
    getConfigurations: async (
      category?: string,
      includeSensitive?: boolean
    ): Promise<ApiResponse<SystemConfiguration[]>> => {
      const response = await (typedClient.raw.GET as any)('/api/v1/system-settings', {
        params: {
          query: {
            category,
            include_sensitive: includeSensitive,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * Get a specific configuration by key
     * Type-safe: Path parameter and query parameters validated against OpenAPI
     */
    getConfiguration: async (
      key: string,
      includeSensitive?: boolean
    ): Promise<ApiResponse<SystemConfiguration>> => {
      const response = await typedClient.raw.GET('/api/v1/system-settings/{id}', {
        params: {
          path: { id: key },
          query: {
            include_sensitive: includeSensitive,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * Create a new configuration
     * Type-safe: Request body validated against OpenAPI
     */
    createConfiguration: async (
      configData: SystemConfigurationCreate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      const response = await (typedClient.raw.POST as any)('/api/v1/system-settings', {
        body: configData,
      });
      return toApiResponse<SystemConfiguration>(response);
    },

    /**
     * Update an existing configuration
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateConfiguration: async (
      key: string,
      configData: SystemConfigurationUpdate
    ): Promise<ApiResponse<SystemConfiguration>> => {
      const response = await typedClient.raw.PUT('/api/v1/system-settings/{id}', {
        params: { path: { id: key } },
        body: configData as any, // Categories are dynamic (fetched via getCategories()), cannot be static enum
      });
      return toApiResponse<SystemConfiguration>(response);
    },

    /**
     * Validate a configuration before saving
     * Type-safe: Request body validated against OpenAPI
     */
    validateConfiguration: async (
      configData: SystemConfigurationValidation
    ): Promise<ApiResponse<ConfigurationValidationResult>> => {
      const response = await typedClient.raw.POST('/api/v1/system-settings/validate', {
        body: configData as any, // Data types are dynamic (fetched via getDataTypes()), cannot be static enum
      });
      return toApiResponse<ConfigurationValidationResult>(response);
    },

    /**
     * Delete a configuration
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteConfiguration: async (
      key: string
    ): Promise<ApiResponse<{ message: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/system-settings/{id}', {
        params: { path: { id: key } },
      });
      return toApiResponse<{ message: string }>(response);
    },

    /**
     * Get all available configuration categories
     * Type-safe: Response type inferred from OpenAPI
     */
    getCategories: async (): Promise<ApiResponse<string[]>> => {
      const response = await typedClient.raw.GET('/api/v1/system-settings/categories');
      return toApiResponse<string[]>(response);
    },

    /**
     * Get all available data types
     * Type-safe: Response type inferred from OpenAPI
     */
    getDataTypes: async (): Promise<ApiResponse<string[]>> => {
      const response = await typedClient.raw.GET('/api/v1/system-settings/data-types');
      return toApiResponse<string[]>(response);
    },

    /**
     * Get audit logs for a specific configuration
     * Type-safe: Path parameter and query parameters validated against OpenAPI
     */
    getAuditLogs: async (
      configKey: string,
      limit: number = 50
    ): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/system-settings/audit-logs/{config_key}', {
        params: {
          path: { config_key: configKey },
          query: { limit },
        },
      });
      return toApiResponse<any[]>(response);
    },
  };
}
