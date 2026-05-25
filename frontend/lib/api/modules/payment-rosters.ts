/**
 * Payment Rosters API Module
 *
 * 造冊管理相關 API
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';
import type { components } from '../generated/schema';

/** Schema 型別別名：造冊建立請求 */
type RosterCreateRequest = components['schemas']['RosterCreateRequest'];

/** Schema 型別別名：造冊匯出請求 */
type RosterExportRequest = components['schemas']['RosterExportRequest'];

export interface RevokedSuspendedEntry {
  application_id: number;
  student_name: string;
  student_id_number: string;
  event_at: string;
  reason: string | null;
  item_id: number | null;
}

export interface RevokedSuspendedList {
  revoked: RevokedSuspendedEntry[];
  suspended: RevokedSuspendedEntry[];
}

export function createPaymentRostersApi() {
  return {
    /**
     * 取得可用於造冊的排名清單
     */
    getAvailableRankings: async (
      scholarshipConfigurationId: number,
      academicYear: number,
      semester?: string
    ): Promise<ApiResponse<{
      rankings: Array<{
        id: number;
        ranking_name: string;
        distribution_executed: boolean;
        distribution_date?: string;
        allocated_count: number;
        total_applications: number;
        is_finalized: boolean;
        academic_year: number;
        semester?: string;
      }>;
      scholarship_configuration_id: number;
      academic_year: number;
      semester?: string;
    }>> => {
      const response = await typedClient.raw.GET('/api/v1/payment-rosters/available-rankings', {
        params: {
          query: {
            scholarship_configuration_id: scholarshipConfigurationId,
            academic_year: academicYear,
            semester,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * 產生造冊
     */
    generateRoster: async (data: {
      scholarship_configuration_id: number;
      period_label: string;
      roster_cycle: "monthly" | "semi_yearly" | "yearly";
      academic_year: number;
      student_verification_enabled?: boolean;
      ranking_id?: number;
      auto_export_excel?: boolean;
      force_regenerate?: boolean;
    }): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/payment-rosters/generate', {
        body: {
          ...data,
          student_verification_enabled: data.student_verification_enabled ?? true,
          auto_export_excel: data.auto_export_excel ?? true,
          force_regenerate: data.force_regenerate ?? false,
        },
      });
      return toApiResponse(response);
    },

    /**
     * 取得造冊清單
     */
    getRosters: async (
      scholarshipConfigurationId?: number,
      academicYear?: number,
      status?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/payment-rosters', {
        params: {
          query: {
            scholarship_configuration_id: scholarshipConfigurationId,
            academic_year: academicYear,
            status,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * 取得造冊詳情
     */
    getRoster: async (rosterId: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/payment-rosters/{roster_id}', {
        params: { path: { roster_id: rosterId } },
      });
      return toApiResponse(response);
    },

    /**
     * 取得造冊中已撤銷/停發的學生清單
     * Lists students still embedded in a locked roster whose allocation was later revoked or suspended.
     */
    getRevokedSuspended: async (
      roster_id: number
    ): Promise<ApiResponse<RevokedSuspendedList>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/{roster_id}/revoked-suspended',
        {
          params: { path: { roster_id } },
        }
      );
      return toApiResponse(response) as ApiResponse<RevokedSuspendedList>;
    },

    /**
     * 從已鎖定造冊中移除單一項目
     * Hard-delete a single item from a LOCKED roster; sets excel_stale to true.
     */
    removeItemFromLockedRoster: async (
      roster_id: number,
      item_id: number,
      reason?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.DELETE(
        '/api/v1/payment-rosters/{roster_id}/items/{item_id}',
        {
          params: { path: { roster_id, item_id } },
          body: { reason: reason ?? null },
        }
      );
      return toApiResponse(response);
    },

    /**
     * 鎖定造冊 (admin only)
     */
    lockRoster: async (roster_id: number): Promise<ApiResponse<{ roster_code: string }>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/lock',
        { params: { path: { roster_id } } }
      );
      return toApiResponse(response) as ApiResponse<{ roster_code: string }>;
    },

    /**
     * 解鎖造冊 (admin only)
     */
    unlockRoster: async (roster_id: number): Promise<ApiResponse<{ roster_code: string }>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/unlock',
        { params: { path: { roster_id } } }
      );
      return toApiResponse(response) as ApiResponse<{ roster_code: string }>;
    },

    /**
     * 取得造冊明細項目
     * GET /api/v1/payment-rosters/{roster_id}/items
     */
    getRosterItems: async (
      roster_id: number,
      params?: {
        skip?: number;
        limit?: number;
        is_qualified?: boolean | null;
      }
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/{roster_id}/items',
        {
          params: {
            path: { roster_id },
            query: params,
          },
        }
      );
      return toApiResponse(response);
    },

    /**
     * 排除造冊明細項目 (軟刪除: 學生繳回 / 放棄)
     * POST /api/v1/payment-rosters/{roster_id}/items/{item_id}/exclude
     */
    excludeRosterItem: async (
      roster_id: number,
      item_id: number,
      reason_category: string,
      reason_note?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/items/{item_id}/exclude',
        {
          params: { path: { roster_id, item_id } },
          body: {
            reason_category,
            reason_note: reason_note ?? null,
          },
        }
      );
      return toApiResponse(response);
    },

    /**
     * 取得造冊稽核日誌
     * GET /api/v1/payment-rosters/{roster_id}/audit-logs
     */
    getAuditLogs: async (
      roster_id: number,
      params?: { skip?: number; limit?: number }
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/{roster_id}/audit-logs',
        {
          params: {
            path: { roster_id },
            query: params,
          },
        }
      );
      return toApiResponse(response);
    },

    /**
     * 取得造冊統計資訊
     * GET /api/v1/payment-rosters/{roster_id}/statistics
     */
    getStatistics: async (roster_id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/{roster_id}/statistics',
        { params: { path: { roster_id } } }
      );
      return toApiResponse(response);
    },

    /**
     * 匯出造冊至 Excel (STD_UP_MIXLISTA 格式)
     * POST /api/v1/payment-rosters/{roster_id}/export
     */
    exportRoster: async (
      roster_id: number,
      request?: Partial<RosterExportRequest>
    ): Promise<ApiResponse<unknown>> => {
      const body: RosterExportRequest = {
        template_name: request?.template_name ?? 'STD_UP_MIXLISTA',
        include_header: request?.include_header ?? true,
        include_statistics: request?.include_statistics ?? true,
        max_preview_rows: request?.max_preview_rows ?? null,
        ...request,
      };
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/export',
        {
          params: { path: { roster_id } },
          body,
        }
      );
      return toApiResponse(response);
    },

    /**
     * 下載造冊 Excel 檔案
     * GET /api/v1/payment-rosters/{roster_id}/download
     */
    downloadRoster: async (
      roster_id: number,
      use_minio?: boolean
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/{roster_id}/download',
        {
          params: {
            path: { roster_id },
            query: use_minio !== undefined ? { use_minio } : undefined,
          },
        }
      );
      return toApiResponse(response);
    },

    /**
     * 預覽造冊學生名單（包含完整驗證）
     * GET /api/v1/payment-rosters/preview-students
     */
    previewStudents: async (params: {
      config_id: number;
      ranking_id?: number | null;
      period_label?: string | null;
      academic_year?: number | null;
      student_verification_enabled?: boolean;
    }): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/preview-students',
        { params: { query: params } }
      );
      return toApiResponse(response);
    },

    /**
     * 取得造冊週期狀態
     * GET /api/v1/payment-rosters/cycle-status
     */
    getCycleStatus: async (config_id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/cycle-status',
        { params: { query: { config_id } } }
      );
      return toApiResponse(response);
    },

    /**
     * 造冊產生預演 (不實際建立造冊)
     * POST /api/v1/payment-rosters/{roster_id}/dry-run
     */
    dryRunRoster: async (
      roster_id: number,
      request: RosterCreateRequest
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/dry-run',
        {
          params: { path: { roster_id } },
          body: request,
        }
      );
      return toApiResponse(response);
    },
  };
}
