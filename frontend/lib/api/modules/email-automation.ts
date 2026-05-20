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

/**
 * Shape of an email automation rule as returned by GET /api/v1/email-automation.
 * Matches the canonical response of email_automation.py.
 */
export interface EmailAutomationRule {
  id: number;
  name: string;
  description?: string;
  trigger_event: string;
  template_key: string;
  delay_hours: number;
  condition_query?: string;
  is_active: boolean;
  created_by_user_id?: number;
  created_at: string;
  updated_at: string;
}

/**
 * Shape of an entry returned by GET /api/v1/email-automation/trigger-events.
 */
export interface EmailAutomationTriggerEvent {
  value: string;
  label: string;
  description: string;
}

/**
 * Request body for creating or updating an email automation rule.
 * The backend POST/PUT bodies are validated by Pydantic and remain
 * permissive via openapi-fetch (Record<string, never> generated body
 * schema); a flexible object is the only practical shape here.
 */
export type EmailAutomationRulePayload = Partial<Omit<EmailAutomationRule, "id" | "created_at" | "updated_at" | "created_by_user_id">> & {
  name: string;
  trigger_event: string;
  template_key: string;
};

export function createEmailAutomationApi() {
  return {
    /**
     * Get all email automation rules with optional filtering
     * Type-safe: Query parameters validated against OpenAPI
     */
    getRules: async (params?: {
      is_active?: boolean;
      trigger_event?: string;
    }): Promise<ApiResponse<EmailAutomationRule[]>> => {
      const response = await typedClient.raw.GET('/api/v1/email-automation', {
        params: {
          query: {
            is_active: params?.is_active,
            trigger_event: params?.trigger_event,
          },
        },
      });
      return toApiResponse<EmailAutomationRule[]>(response);
    },

    /**
     * Create a new email automation rule
     * Type-safe: Request body validated against OpenAPI
     */
    createRule: async (ruleData: EmailAutomationRulePayload): Promise<ApiResponse<EmailAutomationRule>> => {
      const response = await typedClient.raw.POST('/api/v1/email-automation', {
        body: ruleData as never,
      });
      return toApiResponse<EmailAutomationRule>(response);
    },

    /**
     * Update an existing email automation rule
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateRule: async (
      ruleId: number,
      ruleData: EmailAutomationRulePayload
    ): Promise<ApiResponse<EmailAutomationRule>> => {
      const response = await typedClient.raw.PUT('/api/v1/email-automation/{rule_id}', {
        params: { path: { rule_id: ruleId } },
        body: ruleData as never,
      });
      return toApiResponse<EmailAutomationRule>(response);
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
    toggleRule: async (ruleId: number): Promise<ApiResponse<EmailAutomationRule>> => {
      const response = await typedClient.raw.PATCH('/api/v1/email-automation/{rule_id}/toggle', {
        params: { path: { rule_id: ruleId } },
      });
      return toApiResponse<EmailAutomationRule>(response);
    },

    /**
     * Get available trigger events for automation rules
     * Type-safe: Response type inferred from OpenAPI
     */
    getTriggerEvents: async (): Promise<ApiResponse<EmailAutomationTriggerEvent[]>> => {
      const response = await typedClient.raw.GET('/api/v1/email-automation/trigger-events');
      return toApiResponse<EmailAutomationTriggerEvent[]>(response);
    },
  };
}
