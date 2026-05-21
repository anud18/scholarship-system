/**
 * Payment Rosters API Module
 *
 * 造冊管理相關 API
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

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
  };
}
