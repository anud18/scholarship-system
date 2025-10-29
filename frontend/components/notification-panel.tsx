"use client";

import { useState, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Bell,
  AlertCircle,
  Info,
  AlertTriangle,
  CheckCircle,
  Clock,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { format } from "date-fns";
import { zhCN, enUS } from "date-fns/locale";
import { apiClient } from "@/lib/api";
import { useNotifications } from "@/contexts/notification-context";

interface NotificationData {
  id: number;
  title: string;
  title_en?: string;
  message: string;
  message_en?: string;
  notification_type: "info" | "warning" | "error" | "success" | "reminder";
  priority: "low" | "normal" | "high" | "urgent";
  related_resource_type?: string;
  related_resource_id?: number;
  action_url?: string;
  is_read: boolean;
  is_dismissed: boolean;
  scheduled_at?: string;
  expires_at?: string;
  read_at?: string;
  created_at: string;
  metadata?: any;
}

interface NotificationPanelProps {
  locale: "zh" | "en";
  onNotificationClick?: (notification: NotificationData) => void;
}

export function NotificationPanel({
  locale = "zh",
  onNotificationClick,
}: NotificationPanelProps) {
  const [notifications, setNotifications] = useState<NotificationData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedNotifications, setExpandedNotifications] = useState<
    Set<number>
  >(new Set());

  const { unreadCount, markAsRead, markAllAsRead } = useNotifications();

  // 獲取通知列表
  const fetchNotifications = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await apiClient.notifications.getNotifications(0, 50);
      if (response.success) {
        const notifications = (response.data || []).map(n => ({
          ...n,
          notification_type: n.notification_type as
            | "info"
            | "warning"
            | "error"
            | "success"
            | "reminder",
          priority: n.priority as "low" | "normal" | "high" | "urgent",
        }));
        setNotifications(notifications);
      } else {
        throw new Error(response.message || "獲取通知失敗");
      }
    } catch (err) {
      console.error("獲取通知錯誤:", err);
      setError(err instanceof Error ? err.message : "獲取通知失敗");
    } finally {
      setIsLoading(false);
    }
  };

  // 標記通知為已讀
  const handleMarkAsRead = async (notificationId: number) => {
    try {
      // 更新本地狀態
      setNotifications(prev =>
        prev.map(n =>
          n.id === notificationId
            ? { ...n, is_read: true, read_at: new Date().toISOString() }
            : n
        )
      );

      // 透過 context 標記已讀 (會自動更新 unreadCount)
      await markAsRead(notificationId);
    } catch (err) {
      console.error("標記已讀失敗:", err);
    }
  };

  // 標記所有通知為已讀
  const handleMarkAllAsRead = async () => {
    try {
      // 更新本地狀態
      setNotifications(prev =>
        prev.map(n => ({
          ...n,
          is_read: true,
          read_at: new Date().toISOString(),
        }))
      );

      // 透過 context 標記全部已讀
      await markAllAsRead();
    } catch (err) {
      console.error("標記全部已讀失敗:", err);
    }
  };

  // 切換通知展開狀態
  const toggleNotificationExpanded = (notificationId: number) => {
    setExpandedNotifications(prev => {
      const newSet = new Set(prev);
      if (newSet.has(notificationId)) {
        newSet.delete(notificationId);
      } else {
        newSet.add(notificationId);
      }
      return newSet;
    });
  };

  // 檢查訊息是否過長需要展開功能
  const isMessageLong = (message: string) => {
    return message.length > 80; // 如果訊息超過80個字符，認為是長訊息
  };

  // 獲取通知類型圖標
  const getNotificationIcon = (type: string, priority: string) => {
    const iconClass =
      priority === "urgent"
        ? "text-red-500"
        : priority === "high"
          ? "text-orange-500"
          : "text-blue-500";

    switch (type) {
      case "error":
        return <AlertCircle className={`h-4 w-4 ${iconClass}`} />;
      case "warning":
        return <AlertTriangle className={`h-4 w-4 ${iconClass}`} />;
      case "success":
        return <CheckCircle className={`h-4 w-4 ${iconClass}`} />;
      case "reminder":
        return <Clock className={`h-4 w-4 ${iconClass}`} />;
      default:
        return <Info className={`h-4 w-4 ${iconClass}`} />;
    }
  };

  // 獲取優先級標籤
  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "urgent":
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-red-100 text-red-700">
            {locale === "zh" ? "緊急" : "Urgent"}
          </span>
        );
      case "high":
        return (
          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-orange-100 text-orange-700">
            {locale === "zh" ? "重要" : "High"}
          </span>
        );
      case "normal":
        return null;
      default:
        return null;
    }
  };

  // 格式化時間
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return format(date, "MM/dd HH:mm", {
      locale: locale === "zh" ? zhCN : enUS,
    });
  };

  // 獲取通知標題和內容
  const getNotificationText = (notification: NotificationData) => {
    const title =
      locale === "en" && notification.title_en
        ? notification.title_en
        : notification.title;
    const message =
      locale === "en" && notification.message_en
        ? notification.message_en
        : notification.message;
    return { title, message };
  };

  // 初始載入通知列表
  useEffect(() => {
    fetchNotifications();
  }, []);

  // 監聽 panel 開啟事件
  useEffect(() => {
    const handlePanelOpen = () => {
      fetchNotifications();
    };

    // 監聽通知已讀事件,更新本地狀態
    const handleNotificationRead = (event: CustomEvent) => {
      const { notificationId } = event.detail;
      setNotifications(prev =>
        prev.map(n =>
          n.id === notificationId
            ? { ...n, is_read: true, read_at: new Date().toISOString() }
            : n
        )
      );
    };

    // 監聽全部已讀事件
    const handleAllRead = () => {
      setNotifications(prev =>
        prev.map(n => ({
          ...n,
          is_read: true,
          read_at: new Date().toISOString(),
        }))
      );
    };

    window.addEventListener("notification-panel-open", handlePanelOpen);
    window.addEventListener("notification-read", handleNotificationRead as EventListener);
    window.addEventListener("notifications-all-read", handleAllRead);

    return () => {
      window.removeEventListener("notification-panel-open", handlePanelOpen);
      window.removeEventListener("notification-read", handleNotificationRead as EventListener);
      window.removeEventListener("notifications-all-read", handleAllRead);
    };
  }, []);

  if (isLoading) {
    return (
      <Card className="w-96">
        <CardHeader className="pb-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Bell className="h-4 w-4" />
              {locale === "zh" ? "通知" : "Notifications"}
            </CardTitle>
            <Skeleton className="h-4 w-8" />
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {[1, 2, 3].map(i => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-3 w-3/4" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-[420px] border shadow-lg">
      {/* Header */}
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold flex items-center gap-2">
            <Bell className="h-4 w-4" />
            {locale === "zh" ? "通知" : "Notifications"}
          </CardTitle>
          {unreadCount > 0 && (
            <Badge variant="destructive" className="rounded-full">
              {unreadCount}
            </Badge>
          )}
        </div>
      </CardHeader>

      {/* Content */}
      <CardContent className="p-0">
        {error ? (
          <div className="p-8 text-center">
            <AlertCircle className="h-10 w-10 text-red-400 mx-auto mb-3" />
            <p className="text-sm text-gray-600 mb-3">{error}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchNotifications}
            >
              {locale === "zh" ? "重試" : "Retry"}
            </Button>
          </div>
        ) : notifications.length === 0 ? (
          <div className="p-12 text-center">
            <Bell className="h-10 w-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500">
              {locale === "zh" ? "暫無通知" : "No notifications"}
            </p>
          </div>
        ) : (
          <ScrollArea className="h-[480px]">
            <div className="p-4 space-y-3">
              {notifications.map((notification) => {
                const { title, message } = getNotificationText(notification);
                const isExpanded = expandedNotifications.has(notification.id);
                const needsExpansion = isMessageLong(message);

                return (
                  <div
                    key={notification.id}
                    className={`relative rounded-lg border transition-all cursor-pointer ${
                      !notification.is_read
                        ? "bg-blue-50/50 border-blue-200 hover:bg-blue-50"
                        : "bg-white border-gray-200 hover:bg-gray-50"
                    }`}
                    onClick={() => {
                      if (!notification.is_read) {
                        handleMarkAsRead(notification.id);
                      }
                    }}
                  >
                    {/* Unread indicator */}
                    {!notification.is_read && (
                      <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500 rounded-l-lg" />
                    )}

                    <div className="p-3 pl-4">
                      <div className="flex gap-3">
                        {/* Icon */}
                        <div className="flex-shrink-0 mt-0.5">
                          {getNotificationIcon(
                            notification.notification_type,
                            notification.priority
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          {/* Title and badge */}
                          <div className="flex items-start justify-between gap-2 mb-1.5">
                            <h4 className="text-sm font-semibold text-gray-900 leading-tight">
                              {title}
                            </h4>
                            <div className="flex items-center gap-1.5 flex-shrink-0">
                              {!notification.is_read && (
                                <div className="w-2 h-2 bg-blue-500 rounded-full" />
                              )}
                              {getPriorityBadge(notification.priority)}
                            </div>
                          </div>

                          {/* Message */}
                          <p
                            className={`text-sm text-gray-600 leading-relaxed mb-2 ${
                              needsExpansion && !isExpanded ? "line-clamp-2" : ""
                            }`}
                          >
                            {message}
                          </p>

                          {/* Expand button */}
                          {needsExpansion && (
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={e => {
                                e.stopPropagation();
                                toggleNotificationExpanded(notification.id);
                              }}
                              className="h-7 px-2 -ml-2 text-xs"
                            >
                              {isExpanded ? (
                                <>
                                  <ChevronUp className="h-3 w-3 mr-1" />
                                  {locale === "zh" ? "收起" : "Collapse"}
                                </>
                              ) : (
                                <>
                                  <ChevronDown className="h-3 w-3 mr-1" />
                                  {locale === "zh" ? "展開" : "Expand"}
                                </>
                              )}
                            </Button>
                          )}

                          {/* Footer */}
                          <div className="flex items-center justify-between mt-2 pt-2 border-t">
                            <span className="text-xs text-gray-500">
                              {formatDate(notification.created_at)}
                            </span>

                            {notification.action_url && (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={e => {
                                  e.stopPropagation();
                                  if (notification.action_url) {
                                    if (!notification.is_read) {
                                      handleMarkAsRead(notification.id);
                                    }
                                    if (notification.action_url.startsWith("http")) {
                                      window.open(notification.action_url, "_blank");
                                    } else {
                                      window.location.href = notification.action_url;
                                    }
                                  }
                                }}
                                className="h-7 px-2 text-xs font-medium"
                              >
                                {locale === "zh" ? "查看" : "View"}
                                <ExternalLink className="h-3 w-3 ml-1" />
                              </Button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
