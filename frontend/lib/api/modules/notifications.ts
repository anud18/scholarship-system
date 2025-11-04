/**
 * Notifications API Module (OpenAPI-typed)
 *
 * Handles notification operations including:
 * - Fetching user notifications
 * - Managing read/unread status
 * - System announcements
 * - Admin notification management
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

type NotificationResponse = {
  id: number;
  user_id?: string;
  title: string;
  title_en?: string;
  message: string;
  message_en?: string;
  notification_type: string;
  priority?: string | number;
  related_resource_type?: string;
  related_resource_id?: number;
  action_url?: string;
  is_read: boolean;
  is_dismissed: boolean;
  scheduled_at?: string;
  expires_at?: string;
  read_at?: string;
  created_at: string;
  metadata?: Record<string, any>;
};

type AnnouncementCreate = {
  title: string;
  message: string;
  notification_type?: string;
  target_roles?: string[];
  metadata?: any;
};

export function createNotificationsApi() {
  return {
    /**
     * Get notifications with optional filters
     * Type-safe: Query parameters validated against OpenAPI
     */
    getNotifications: async (
      skip?: number,
      limit?: number,
      unreadOnly?: boolean,
      notificationType?: string
    ): Promise<ApiResponse<NotificationResponse[]>> => {
      const response = await typedClient.raw.GET('/api/v1/notifications', {
        params: {
          query: {
            skip,
            limit,
            unread_only: unreadOnly,
            notification_type: notificationType,
          },
        },
      });
      return toApiResponse<NotificationResponse[]>(response);
    },

    /**
     * Get unread notification count
     * Type-safe: Response type inferred from OpenAPI
     */
    getUnreadCount: async (): Promise<ApiResponse<number>> => {
      const response = await typedClient.raw.GET('/api/v1/notifications/unread-count');
      return toApiResponse<number>(response);
    },

    /**
     * Mark notification as read
     * Type-safe: Path parameter validated against OpenAPI
     */
    markAsRead: async (
      notificationId: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      const response = await typedClient.raw.PATCH('/api/v1/notifications/{notification_id}/read', {
        params: { path: { notification_id: notificationId } },
      });
      return toApiResponse<NotificationResponse>(response);
    },

    /**
     * Mark all notifications as read
     * Type-safe: Response type inferred from OpenAPI
     */
    markAllAsRead: async (): Promise<
      ApiResponse<{ updated_count: number }>
    > => {
      const response = await typedClient.raw.PATCH('/api/v1/notifications/mark-all-read');
      return toApiResponse<{ updated_count: number }>(response);
    },

    /**
     * Dismiss notification
     * Type-safe: Path parameter validated against OpenAPI
     */
    dismiss: async (
      notificationId: number
    ): Promise<ApiResponse<{ notification_id: number }>> => {
      const response = await typedClient.raw.PATCH('/api/v1/notifications/{notification_id}/dismiss', {
        params: { path: { notification_id: notificationId } },
      });
      return toApiResponse<{ notification_id: number }>(response);
    },

    /**
     * Get notification detail
     * Type-safe: Path parameter validated against OpenAPI
     */
    getNotificationDetail: async (
      notificationId: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/notifications/{notification_id}', {
        params: { path: { notification_id: notificationId } },
      });
      return toApiResponse<NotificationResponse>(response);
    },

    /**
     * Create system announcement (admin only)
     * Type-safe: Request body validated against OpenAPI
     */
    createSystemAnnouncement: async (
      announcementData: AnnouncementCreate
    ): Promise<ApiResponse<NotificationResponse>> => {
      const response = await typedClient.raw.POST('/api/v1/notifications/admin/create-system-announcement', {
        body: announcementData as any, // Frontend AnnouncementCreate type includes priority field not in schema
      });
      return toApiResponse<NotificationResponse>(response);
    },

    /**
     * Create test notifications (admin only)
     * Type-safe: Response type inferred from OpenAPI
     */
    createTestNotifications: async (): Promise<
      ApiResponse<{ created_count: number; notification_ids: number[] }>
    > => {
      const response = await typedClient.raw.POST('/api/v1/notifications/admin/create-test-notifications');
      return toApiResponse<{ created_count: number; notification_ids: number[] }>(response);
    },
  };
}
