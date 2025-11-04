/**
 * Payment Rosters API Module
 *
 * 造冊管理相關 API
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

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
    }): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.POST('/api/v1/payment-rosters/generate', {
        body: {
          ...data,
          student_verification_enabled: data.student_verification_enabled ?? true,
          auto_export_excel: data.auto_export_excel ?? true,
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
    ): Promise<ApiResponse<any>> => {
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
    getRoster: async (rosterId: number): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.GET('/api/v1/payment-rosters/{roster_id}', {
        params: { path: { roster_id: rosterId } },
      });
      return toApiResponse(response);
    },
  };
}
