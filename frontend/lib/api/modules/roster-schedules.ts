/**
 * Roster Schedules API Module
 *
 * 造冊排程管理相關 API
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';
import type { components } from '../generated/schema';

export function createRosterSchedulesApi() {
  return {
    /**
     * 列出造冊排程
     * List roster schedules with optional filtering
     */
    listSchedules: async (params?: {
      skip?: number;
      limit?: number;
      status?: string;
      scholarship_configuration_id?: number;
      search?: string;
    }): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/roster-schedules', {
        params: {
          query: {
            skip: params?.skip,
            limit: params?.limit,
            // schema uses status_filter, component passes status
            status_filter: params?.status as components['schemas']['RosterScheduleStatus'] | undefined,
            scholarship_configuration_id: params?.scholarship_configuration_id,
            search: params?.search,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * 建立新的造冊排程
     */
    createSchedule: async (
      data: components['schemas']['RosterScheduleCreate']
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/roster-schedules', {
        body: data,
      });
      return toApiResponse(response);
    },

    /**
     * 取得特定造冊排程詳情
     */
    getSchedule: async (schedule_id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/roster-schedules/{schedule_id}', {
        params: { path: { schedule_id } },
      });
      return toApiResponse(response);
    },

    /**
     * 更新造冊排程
     */
    updateSchedule: async (
      schedule_id: number,
      data: components['schemas']['RosterScheduleUpdate']
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT('/api/v1/roster-schedules/{schedule_id}', {
        params: { path: { schedule_id } },
        body: data,
      });
      return toApiResponse(response);
    },

    /**
     * 刪除造冊排程
     */
    deleteSchedule: async (schedule_id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.DELETE('/api/v1/roster-schedules/{schedule_id}', {
        params: { path: { schedule_id } },
      });
      return toApiResponse(response);
    },

    /**
     * 更新排程狀態 (active, paused, disabled)
     */
    updateScheduleStatus: async (
      schedule_id: number,
      data: components['schemas']['RosterScheduleStatusUpdate']
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PATCH('/api/v1/roster-schedules/{schedule_id}/status', {
        params: { path: { schedule_id } },
        body: data,
      });
      return toApiResponse(response);
    },

    /**
     * 立即執行排程（手動觸發）
     */
    executeSchedule: async (
      schedule_id: number,
      force_regenerate?: boolean
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST('/api/v1/roster-schedules/{schedule_id}/execute', {
        params: {
          path: { schedule_id },
          query: { force_regenerate },
        },
      });
      return toApiResponse(response);
    },

    /**
     * 依獎學金配置查詢排程
     */
    getScheduleByConfig: async (config_id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/roster-schedules/by-config/{config_id}', {
        params: { path: { config_id } },
      });
      return toApiResponse(response);
    },

    /**
     * 取得排程器狀態與所有活躍的排程任務
     */
    getSchedulerStatus: async (): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET('/api/v1/roster-schedules/scheduler/status');
      return toApiResponse(response);
    },
  };
}
