/**
 * Email Automation API Module
 *
 * Manages automated email rules and triggers:
 * - Create/update/delete email automation rules
 * - Toggle rule activation
 * - Get available trigger events
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

export function createEmailAutomationApi(client: ApiClient) {
  return {
    /**
     * Get all email automation rules with optional filtering
     */
    getRules: async (params?: {
      is_active?: boolean;
      trigger_event?: string;
    }): Promise<ApiResponse<any[]>> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return client.request(`/email-automation${query ? `?${query}` : ""}`);
    },

    /**
     * Create a new email automation rule
     */
    createRule: async (ruleData: any): Promise<ApiResponse<any>> => {
      return client.request("/email-automation", {
        method: "POST",
        body: JSON.stringify(ruleData),
      });
    },

    /**
     * Update an existing email automation rule
     */
    updateRule: async (
      ruleId: number,
      ruleData: any
    ): Promise<ApiResponse<any>> => {
      return client.request(`/email-automation/${ruleId}`, {
        method: "PUT",
        body: JSON.stringify(ruleData),
      });
    },

    /**
     * Delete an email automation rule
     */
    deleteRule: async (ruleId: number): Promise<ApiResponse<void>> => {
      return client.request(`/email-automation/${ruleId}`, {
        method: "DELETE",
      });
    },

    /**
     * Toggle an email automation rule on/off
     */
    toggleRule: async (ruleId: number): Promise<ApiResponse<any>> => {
      return client.request(`/email-automation/${ruleId}/toggle`, {
        method: "PATCH",
      });
    },

    /**
     * Get available trigger events for automation rules
     */
    getTriggerEvents: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/email-automation/trigger-events");
    },
  };
}
