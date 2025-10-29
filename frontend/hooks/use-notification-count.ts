"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api";

const UNREAD_COUNT_KEY = "/notifications/unread-count";

export function useNotificationCount(isEnabled: boolean) {
  return useSWR<number>(
    isEnabled ? UNREAD_COUNT_KEY : null,
    async () => {
      const response = await apiClient.notifications.getUnreadCount();
      if (!response.success) {
        throw new Error(response.message || "Failed to fetch unread notifications");
      }
      return response.data ?? 0;
    },
    {
      revalidateOnFocus: true,
    }
  );
}

export const notificationKeys = {
  unreadCount: UNREAD_COUNT_KEY,
};
