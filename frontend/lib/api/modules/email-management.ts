/**
 * Email Management API Module
 *
 * Handles email history, scheduling, and test mode:
 * - Email history and tracking
 * - Scheduled email management
 * - Email approval workflows
 * - Test mode configuration
 * - Audit logging
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

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
  config_before: any;
  config_after: any;
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

export function createEmailManagementApi(client: ApiClient) {
  return {
    /**
     * Get email history with filters
     */
    getEmailHistory: async (
      params?: EmailHistoryParams
    ): Promise<ApiResponse<PaginatedEmailResponse>> => {
      return client.request("/email-management/history", {
        method: "GET",
        params,
      });
    },

    /**
     * Get scheduled emails with filters
     */
    getScheduledEmails: async (
      params?: ScheduledEmailParams
    ): Promise<ApiResponse<PaginatedEmailResponse>> => {
      return client.request("/email-management/scheduled", {
        method: "GET",
        params,
      });
    },

    /**
     * Get due scheduled emails (superadmin only)
     */
    getDueScheduledEmails: async (
      limit?: number
    ): Promise<ApiResponse<any[]>> => {
      const params = limit ? { limit } : {};
      return client.request("/email-management/scheduled/due", {
        method: "GET",
        params,
      });
    },

    /**
     * Approve scheduled email
     */
    approveScheduledEmail: async (
      emailId: number,
      approvalNotes?: string
    ): Promise<ApiResponse<any>> => {
      return client.request(`/email-management/scheduled/${emailId}/approve`, {
        method: "PATCH",
        body: JSON.stringify({
          approval_notes: approvalNotes,
        }),
      });
    },

    /**
     * Cancel scheduled email
     */
    cancelScheduledEmail: async (
      emailId: number
    ): Promise<ApiResponse<any>> => {
      return client.request(`/email-management/scheduled/${emailId}/cancel`, {
        method: "PATCH",
      });
    },

    /**
     * Update scheduled email
     */
    updateScheduledEmail: async (
      emailId: number,
      data: { subject: string; body: string }
    ): Promise<ApiResponse<any>> => {
      return client.request(`/email-management/scheduled/${emailId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },

    /**
     * Process due emails (superadmin only)
     */
    processDueEmails: async (
      batchSize?: number
    ): Promise<ApiResponse<ProcessDueEmailsResult>> => {
      const params = batchSize ? { batch_size: batchSize } : {};
      return client.request("/email-management/scheduled/process", {
        method: "POST",
        params,
      });
    },

    /**
     * Get email categories
     */
    getEmailCategories: async (): Promise<ApiResponse<string[]>> => {
      return client.request("/email-management/categories");
    },

    /**
     * Get email and schedule statuses
     */
    getEmailStatuses: async (): Promise<
      ApiResponse<{
        email_statuses: string[];
        schedule_statuses: string[];
      }>
    > => {
      return client.request("/email-management/statuses");
    },

    /**
     * Get test mode status
     */
    getTestModeStatus: async (): Promise<ApiResponse<TestModeStatus>> => {
      return client.request("/email-management/test-mode/status");
    },

    /**
     * Enable test mode
     */
    enableTestMode: async (
      params: TestModeEnableParams
    ): Promise<ApiResponse<TestModeStatus & { enabled_by: number; enabled_at: string }>> => {
      // Convert array to comma-separated string, or use as-is if already string
      const emailsStr = Array.isArray(params.redirect_emails)
        ? params.redirect_emails.join(",")
        : params.redirect_emails;

      const queryParams = new URLSearchParams({
        redirect_emails: emailsStr,
        duration_hours: (params.duration_hours || 24).toString(),
      });
      return client.request(
        `/email-management/test-mode/enable?${queryParams.toString()}`,
        {
          method: "POST",
        }
      );
    },

    /**
     * Disable test mode
     */
    disableTestMode: async (): Promise<
      ApiResponse<TestModeStatus & { disabled_by: number; disabled_at: string }>
    > => {
      return client.request("/email-management/test-mode/disable", {
        method: "POST",
      });
    },

    /**
     * Get test mode audit logs
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
      return client.request("/email-management/test-mode/audit", {
        method: "GET",
        params,
      });
    },

    /**
     * Send simple test email
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
      return client.request("/email-management/send-simple-test", {
        method: "POST",
        body: JSON.stringify(params),
      });
    },
  };
}
