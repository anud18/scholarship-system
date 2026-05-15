/**
 * Email Management API Module (OpenAPI-typed)
 *
 * Handles email history, scheduling, and test mode:
 * - Email history and tracking
 * - Scheduled email management
 * - Email approval workflows
 * - Test mode configuration
 * - Audit logging
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

type EmailHistoryParams = {
  skip?: number;
  limit?: number;
  email_category?: string;
  status?: string;
  scholarship_type_id?: number;
  recipient_email?: string;
  date_from?: string;
  date_to?: string;
};

type ScheduledEmailParams = {
  skip?: number;
  limit?: number;
  status?: string;
  scholarship_type_id?: number;
  requires_approval?: boolean;
  email_category?: string;
  scheduled_from?: string;
  scheduled_to?: string;
};

type PaginatedEmailResponse = {
  // intentionally `any[]` — same paginated response wraps several distinct
  // row shapes (EmailHistoryItem, ScheduledEmailItem, audit-log row, …) that
  // are declared per-consumer. Narrowing here breaks `setEmailHistory(items)`
  // / `setScheduledEmails(items)` / `setAuditLogs(items)` at every caller.
  // See PR #674 commit-history for the reverted attempt.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  items: any[];
  total: number;
  skip: number;
  limit: number;
};

type ProcessDueEmailsResult = {
  processed: number;
  sent: number;
  failed: number;
  skipped: number;
};

type TestModeStatus = {
  enabled: boolean;
  redirect_emails: string[];
  expires_at: string | null;
  enabled_by?: number;
  enabled_at?: string;
};

type TestModeEnableParams = {
  redirect_emails: string | string[];
  duration_hours?: number;
};

type TestModeAuditLog = {
  id: number;
  event_type: string;
  timestamp: string;
  user_id: number | null;
  // Test-mode audit captures the test-mode config snapshot before and after
  // a toggle / mutation. The shape is the live TestModeStatus dict plus
  // historical fields (redirect_count, etc.), which is what
  // email-test-mode-panel renders. Narrow to dictionary access; consumers
  // already type the field as `Record<string, unknown> | null`.
  config_before: Record<string, unknown> | null;
  config_after: Record<string, unknown> | null;
  original_recipient: string | null;
  actual_recipient: string | null;
  email_subject: string | null;
  session_id: string | null;
  ip_address: string | null;
};

type SimpleTestEmailParams = {
  recipient_email: string;
  subject: string;
  body: string;
};


/**
 * React Email template (file-based, mirrors react-email-template-viewer.tsx).
 */
export interface ReactEmailTemplate {
  name: string;
  display_name: string;
  description: string;
  category: string;
  file_path: string;
  variables: Array<{
    name: string;
    description: string;
    type: string;
    default_value?: string;
  }>;
  last_modified: string;
  file_size: number;
}

/**
 * Source code payload returned by getReactEmailTemplateSource.
 */
export interface ReactEmailTemplateSource {
  source: string;
  [key: string]: unknown;
}

/**
 * Database-backed email template (text-template-editor consumer).
 */
export interface EmailTemplate {
  id: number;
  template_key: string;
  template_name: string;
  subject_template: string;
  body_template: string;
  category: string;
  variables: string[];
  is_active: boolean;
  description?: string;
}

export type EmailTemplateUpdatePayload = Partial<Omit<EmailTemplate, "id">>;

export function createEmailManagementApi() {
  return {
    /**
     * Get email history with filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getEmailHistory: async (
      params?: EmailHistoryParams
    ): Promise<ApiResponse<PaginatedEmailResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/email-management/history', {
        params: { query: params as any },
      });
      return toApiResponse<PaginatedEmailResponse>(response);
    },

    /**
     * Get scheduled emails with filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getScheduledEmails: async (
      params?: ScheduledEmailParams
    ): Promise<ApiResponse<PaginatedEmailResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/email-management/scheduled', {
        params: { query: params as any },
      });
      return toApiResponse<PaginatedEmailResponse>(response);
    },

    /**
     * Get due scheduled emails (superadmin only)
     * Type-safe: Query parameters validated against OpenAPI
     */
    getDueScheduledEmails: async (
      limit?: number
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET('/api/v1/email-management/scheduled/due', {
        params: { query: { limit } },
      });
      return toApiResponse(response);
    },

    /**
     * Approve scheduled email
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    approveScheduledEmail: async (
      emailId: number,
      approvalNotes?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PATCH('/api/v1/email-management/scheduled/{email_id}/approve', {
        params: { path: { email_id: emailId } },
        body: {
          approval_notes: approvalNotes,
        },
      });
      return toApiResponse(response);
    },

    /**
     * Cancel scheduled email
     * Type-safe: Path parameter validated against OpenAPI
     */
    cancelScheduledEmail: async (
      emailId: number
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PATCH('/api/v1/email-management/scheduled/{email_id}/cancel', {
        params: { path: { email_id: emailId } },
      });
      return toApiResponse(response);
    },

    /**
     * Update scheduled email
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateScheduledEmail: async (
      emailId: number,
      data: { subject: string; body: string }
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PATCH('/api/v1/email-management/scheduled/{email_id}', {
        params: { path: { email_id: emailId } },
        body: data,
      });
      return toApiResponse(response);
    },

    /**
     * Process due emails (superadmin only)
     * Type-safe: Query parameters validated against OpenAPI
     */
    processDueEmails: async (
      batchSize?: number
    ): Promise<ApiResponse<ProcessDueEmailsResult>> => {
      const response = await typedClient.raw.POST('/api/v1/email-management/scheduled/process', {
        params: { query: { batch_size: batchSize } },
      });
      return toApiResponse(response);
    },

    /**
     * Get email categories
     * Type-safe: Response type inferred from OpenAPI
     */
    getEmailCategories: async (): Promise<ApiResponse<string[]>> => {
      const response = await typedClient.raw.GET('/api/v1/email-management/categories');
      return toApiResponse(response);
    },

    /**
     * Get email and schedule statuses
     * Type-safe: Response type inferred from OpenAPI
     */
    getEmailStatuses: async (): Promise<
      ApiResponse<{
        email_statuses: string[];
        schedule_statuses: string[];
      }>
    > => {
      const response = await typedClient.raw.GET('/api/v1/email-management/statuses');
      return toApiResponse(response);
    },

    /**
     * Get test mode status
     * Type-safe: Response type inferred from OpenAPI
     */
    getTestModeStatus: async (): Promise<ApiResponse<TestModeStatus>> => {
      const response = await typedClient.raw.GET('/api/v1/email-management/test-mode/status');
      return toApiResponse(response);
    },

    /**
     * Enable test mode
     * Type-safe: Query parameters validated against OpenAPI
     */
    enableTestMode: async (
      params: TestModeEnableParams
    ): Promise<ApiResponse<TestModeStatus & { enabled_by: number; enabled_at: string }>> => {
      // Convert array to comma-separated string, or use as-is if already string
      const emailsStr = Array.isArray(params.redirect_emails)
        ? params.redirect_emails.join(",")
        : params.redirect_emails;

      const response = await typedClient.raw.POST('/api/v1/email-management/test-mode/enable', {
        params: {
          query: {
            redirect_emails: emailsStr,
            duration_hours: params.duration_hours || 24,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * Disable test mode
     * Type-safe: Response type inferred from OpenAPI
     */
    disableTestMode: async (): Promise<
      ApiResponse<TestModeStatus & { disabled_by: number; disabled_at: string }>
    > => {
      const response = await typedClient.raw.POST('/api/v1/email-management/test-mode/disable');
      return toApiResponse(response);
    },

    /**
     * Get test mode audit logs
     * Type-safe: Query parameters validated against OpenAPI
     */
    getTestModeAuditLogs: async (params?: {
      limit?: number;
      event_type?: string;
    }): Promise<
      ApiResponse<{
        items: TestModeAuditLog[];
        total: number;
      }>
    > => {
      const response = await typedClient.raw.GET('/api/v1/email-management/test-mode/audit', {
        params: { query: params },
      });
      return toApiResponse(response);
    },

    /**
     * Send simple test email
     * Type-safe: Request body validated against OpenAPI
     */
    sendSimpleTestEmail: async (
      params: SimpleTestEmailParams
    ): Promise<
      ApiResponse<{
        success: boolean;
        message: string;
        email_id: number | null;
        error?: string;
      }>
    > => {
      const response = await typedClient.raw.POST('/api/v1/email-management/send-simple-test', {
        body: params,
      });
      return toApiResponse(response);
    },

    /**
     * Get all React Email templates
     * NOTE: Using base client until OpenAPI schema is regenerated
     */
    getReactEmailTemplates: async (): Promise<ApiResponse<ReactEmailTemplate[]>> => {
      const { ApiClient } = await import('../client');
      const client = new ApiClient();
      return client.request('/email-management/react-email-templates', {
        method: 'GET',
      });
    },

    /**
     * Get specific React Email template
     * NOTE: Using base client until OpenAPI schema is regenerated
     */
    getReactEmailTemplate: async (templateName: string): Promise<ApiResponse<ReactEmailTemplate>> => {
      const { ApiClient } = await import('../client');
      const client = new ApiClient();
      return client.request(`/email-management/react-email-templates/${templateName}`, {
        method: 'GET',
      });
    },

    /**
     * Get React Email template source code
     * NOTE: Using base client until OpenAPI schema is regenerated
     */
    getReactEmailTemplateSource: async (templateName: string): Promise<ApiResponse<ReactEmailTemplateSource>> => {
      const { ApiClient } = await import('../client');
      const client = new ApiClient();
      return client.request(`/email-management/react-email-templates/${templateName}/source`, {
        method: 'GET',
      });
    },

    /**
     * Get all email templates (database templates)
     * NOTE: Using base client until OpenAPI schema is regenerated
     */
    getEmailTemplates: async (): Promise<ApiResponse<EmailTemplate[]>> => {
      const { ApiClient } = await import('../client');
      const client = new ApiClient();
      return client.request('/email-management/templates', {
        method: 'GET',
      });
    },

    /**
     * Update email template (database template)
     * NOTE: Using base client until OpenAPI schema is regenerated
     */
    updateEmailTemplate: async (templateId: number, data: EmailTemplateUpdatePayload): Promise<ApiResponse<EmailTemplate>> => {
      const { ApiClient } = await import('../client');
      const client = new ApiClient();
      return client.request(`/email-management/templates/${templateId}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      });
    },
  };
}
