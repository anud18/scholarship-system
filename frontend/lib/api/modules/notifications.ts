/**
 * Notifications API Module
 *
 * Handles notification operations including:
 * - Fetching user notifications
 * - Managing read/unread status
 * - System announcements
 * - Admin notification management
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

// Import types from main api.ts for now
type NotificationResponse = {
  id: number;
  user_id: string;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  is_dismissed: boolean;
  created_at: string;
  read_at?: string;
  metadata?: any;
};

type AnnouncementCreate = {
  title: string;
  message: string;
  notification_type?: string;
  target_roles?: string[];
  metadata?: any;
};

export function createNotificationsApi(client: ApiClient) {
  return {
    /**
     * Get notifications with optional filters
     */
    getNotifications: async (
      skip?: number,
      limit?: number,
      unreadOnly?: boolean,
      notificationType?: string
    ): Promise<ApiResponse<NotificationResponse[]>> => {
      const params = new URLSearchParams();
      if (skip) params.append("skip", skip.toString());
      if (limit) params.append("limit", limit.toString());
      if (unreadOnly) params.append("unread_only", "true");
      if (notificationType)
        params.append("notification_type", notificationType);

      const queryString = params.toString();
      return client.request(
        `/notifications${queryString ? `?${queryString}` : ""}`
      );
    },

    /**
     * Get unread notification count
     */
    getUnreadCount: async (): Promise<ApiResponse<number>> => {
      return client.request("/notifications/unread-count");
    },

    /**
     * Mark notification as read
     */
    markAsRead: async (
      notificationId: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      return client.request(`/notifications/${notificationId}/read`, {
        method: "PATCH",
      });
    },

    /**
     * Mark all notifications as read
     */
    markAllAsRead: async (): Promise<
      ApiResponse<{ updated_count: number }>
    > => {
      return client.request("/notifications/mark-all-read", {
        method: "PATCH",
      });
    },

    /**
     * Dismiss notification
     */
    dismiss: async (
      notificationId: number
    ): Promise<ApiResponse<{ notification_id: number }>> => {
      return client.request(`/notifications/${notificationId}/dismiss`, {
        method: "PATCH",
      });
    },

    /**
     * Get notification detail
     */
    getNotificationDetail: async (
      notificationId: number
    ): Promise<ApiResponse<NotificationResponse>> => {
      return client.request(`/notifications/${notificationId}`);
    },

    /**
     * Create system announcement (admin only)
     */
    createSystemAnnouncement: async (
      announcementData: AnnouncementCreate
    ): Promise<ApiResponse<NotificationResponse>> => {
      return client.request("/notifications/admin/create-system-announcement", {
        method: "POST",
        body: JSON.stringify(announcementData),
      });
    },

    /**
     * Create test notifications (admin only)
     */
    createTestNotifications: async (): Promise<
      ApiResponse<{ created_count: number; notification_ids: number[] }>
    > => {
      return client.request("/notifications/admin/create-test-notifications", {
        method: "POST",
      });
    },
  };
}
