"use client";

import React, { createContext, useContext, useCallback, useEffect } from "react";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";
import { useNotificationCount } from "@/hooks/use-notification-count";

interface NotificationContextValue {
  unreadCount: number;
  refreshUnreadCount: () => Promise<void>;
  markAsRead: (notificationId: number) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  notifyPanelOpen: () => void;
}

const NotificationContext = createContext<NotificationContextValue | undefined>(undefined);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const {
    data,
    mutate,
  } = useNotificationCount(Boolean(user));

  const unreadCount = user ? data ?? 0 : 0;

  // 獲取未讀通知數量
  const refreshUnreadCount = useCallback(async () => {
    if (!user) {
      return;
    }

    try {
      await mutate();
    } catch (err) {
      console.error("獲取未讀通知數量錯誤:", err);
    }
  }, [mutate, user]);

  // 標記單個通知為已讀
  const markAsRead = useCallback(async (notificationId: number) => {
    try {
      const response = await apiClient.notifications.markAsRead(notificationId);
      if (response.success) {
        // 更新未讀數量
        mutate(prev => Math.max((prev ?? 0) - 1, 0), false);

        // 發送事件通知其他元件
        window.dispatchEvent(new CustomEvent("notification-read", {
          detail: { notificationId }
        }));
      }
    } catch (err) {
      console.error("標記已讀失敗:", err);
    }
  }, [mutate]);

  // 標記全部通知為已讀
  const markAllAsRead = useCallback(async () => {
    try {
      const response = await apiClient.notifications.markAllAsRead();
      if (response.success) {
        mutate(() => 0, false);

        // 發送事件通知其他元件
        window.dispatchEvent(new CustomEvent("notifications-all-read"));
      }
    } catch (err) {
      console.error("標記全部已讀失敗:", err);
    }
  }, [mutate]);

  // 通知 Panel 開啟
  const notifyPanelOpen = useCallback(() => {
    window.dispatchEvent(new CustomEvent("notification-panel-open"));
  }, []);

  // 當通知面板開啟時重新取得未讀數量
  useEffect(() => {
    const handlePanelOpen = () => {
      if (user) {
        void mutate();
      }
    };

    window.addEventListener("notification-panel-open", handlePanelOpen);
    return () => window.removeEventListener("notification-panel-open", handlePanelOpen);
  }, [mutate, user]);

  const value: NotificationContextValue = {
    unreadCount,
    refreshUnreadCount,
    markAsRead,
    markAllAsRead,
    notifyPanelOpen,
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (context === undefined) {
    throw new Error("useNotifications must be used within a NotificationProvider");
  }
  return context;
}
