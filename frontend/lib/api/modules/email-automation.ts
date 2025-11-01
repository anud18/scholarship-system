/**
 * Email Automation API Module (OpenAPI-typed)
 *
 * Manages automated email rules and triggers:
 * - Create/update/delete email automation rules
 * - Toggle rule activation
 * - Get available trigger events
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

export function createEmailAutomationApi() {
  return {
    /**
     * Get all email automation rules with optional filtering
     * Type-safe: Query parameters validated against OpenAPI
     */
    getRules: async (params?: {
      is_active?: boolean;
      trigger_event?: string;
    }): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/email-automation', {
        params: {
          query: {
            is_active: params?.is_active,
            trigger_event: params?.trigger_event,
          },
        },
      });
      return toApiResponse<any[]>(response);
    },

    /**
     * Create a new email automation rule
     * Type-safe: Request body validated against OpenAPI
     */
    createRule: async (ruleData: any): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/email-automation', {
        body: ruleData,
      });
      return toApiResponse(response);
    },

    /**
     * Update an existing email automation rule
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateRule: async (
      ruleId: number,
      ruleData: any
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PUT('/api/v1/email-automation/{rule_id}', {
        params: { path: { rule_id: ruleId } },
        body: ruleData,
      });
      return toApiResponse(response);
    },

    /**
     * Delete an email automation rule
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteRule: async (ruleId: number): Promise<ApiResponse<void>> => {
      const response = await typedClient.raw.DELETE('/api/v1/email-automation/{rule_id}', {
        params: { path: { rule_id: ruleId } },
      });
      return toApiResponse<void>(response);
    },

    /**
     * Toggle an email automation rule on/off
     * Type-safe: Path parameter validated against OpenAPI
     */
    toggleRule: async (ruleId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PATCH('/api/v1/email-automation/{rule_id}/toggle', {
        params: { path: { rule_id: ruleId } },
      });
      return toApiResponse(response);
    },

    /**
     * Get available trigger events for automation rules
     * Type-safe: Response type inferred from OpenAPI
     */
    getTriggerEvents: async (): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/email-automation/trigger-events');
      return toApiResponse<any[]>(response);
    },
  };
}
