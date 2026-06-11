/**
 * Audit Logs API module (#976 / G14)
 *
 * System-wide audit-log viewer for admins — the read side of audit_logs.
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

export interface AuditLogEntry {
  id: number;
  created_at: string | null;
  user_id: number | null;
  actor_name: string | null;
  actor_nycu_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  resource_name: string | null;
  description: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  status: string | null;
  ip_address: string | null;
  meta_data: Record<string, unknown> | null;
}

export interface AuditLogFilters {
  page?: number;
  size?: number;
  resource_type?: string;
  resource_id?: string;
  action?: string;
  user_id?: number;
  date_from?: string;
  date_to?: string;
  search?: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export function createAuditLogsApi() {
  return {
    list: async (filters?: AuditLogFilters): Promise<ApiResponse<AuditLogPage>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/audit-logs', {
        params: {
          query: {
            page: filters?.page,
            size: filters?.size,
            resource_type: filters?.resource_type,
            resource_id: filters?.resource_id,
            action: filters?.action,
            user_id: filters?.user_id,
            date_from: filters?.date_from,
            date_to: filters?.date_to,
            search: filters?.search,
          },
        },
      });
      return toApiResponse(response) as ApiResponse<AuditLogPage>;
    },
  };
}
