"use client";

import React, { createContext, useContext, useState, useCallback, useEffect } from "react";
import { apiClient } from "@/lib/api";

interface NotificationContextValue {
  unreadCount: number;
  refreshUnreadCount: () => Promise<void>;
  markAsRead: (notificationId: number) => Promise<void>;
  markAllAsRead: () => Promise<void>;
  notifyPanelOpen: () => void;
}

const NotificationContext = createContext<NotificationContextValue | undefined>(undefined);

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [unreadCount, setUnreadCount] = useState(0);

  // 獲取未讀通知數量
  const refreshUnreadCount = useCallback(async () => {
    try {
      const response = await apiClient.notifications.getUnreadCount();
      if (response.success) {
        setUnreadCount(response.data || 0);
      }
    } catch (err) {
      console.error("獲取未讀通知數量錯誤:", err);
    }
  }, []);

  // 標記單個通知為已讀
  const markAsRead = useCallback(async (notificationId: number) => {
    try {
      const response = await apiClient.notifications.markAsRead(notificationId);
      if (response.success) {
        // 更新未讀數量
        await refreshUnreadCount();

        // 發送事件通知其他元件
        window.dispatchEvent(new CustomEvent("notification-read", {
          detail: { notificationId }
        }));
      }
    } catch (err) {
      console.error("標記已讀失敗:", err);
    }
  }, [refreshUnreadCount]);

  // 標記全部通知為已讀
  const markAllAsRead = useCallback(async () => {
    try {
      const response = await apiClient.notifications.markAllAsRead();
      if (response.success) {
        setUnreadCount(0);

        // 發送事件通知其他元件
        window.dispatchEvent(new CustomEvent("notifications-all-read"));
      }
    } catch (err) {
      console.error("標記全部已讀失敗:", err);
    }
  }, []);

  // 通知 Panel 開啟
  const notifyPanelOpen = useCallback(() => {
    window.dispatchEvent(new CustomEvent("notification-panel-open"));
  }, []);

  // 初始載入時取得未讀數量
  useEffect(() => {
    refreshUnreadCount();
  }, [refreshUnreadCount]);

  // 監聽 notification panel 開啟事件，當面板開啟時刷新未讀數量
  useEffect(() => {
    const handlePanelOpen = () => {
      refreshUnreadCount();
    };

    window.addEventListener("notification-panel-open", handlePanelOpen);
    return () => window.removeEventListener("notification-panel-open", handlePanelOpen);
  }, [refreshUnreadCount]);

  // 監聽頁面焦點變化，當用戶切回視窗時刷新未讀數量
  useEffect(() => {
    const handleFocus = () => {
      refreshUnreadCount();
    };

    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refreshUnreadCount]);

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
