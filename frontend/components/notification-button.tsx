"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";
import { NotificationPanel } from "@/components/notification-panel";
import { apiClient } from "@/lib/api";

interface NotificationButtonProps {
  locale: "zh" | "en";
  className?: string;
}

export function NotificationButton({
  locale = "zh",
  className = "",
}: NotificationButtonProps) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [isOpen, setIsOpen] = useState(false);

  // 獲取未讀通知數量
  const fetchUnreadCount = async () => {
    try {
      const response = await apiClient.notifications.getUnreadCount();
      if (response.success) {
        setUnreadCount(response.data || 0);
      }
    } catch (err) {
      console.error("獲取未讀通知數量錯誤:", err);
    }
  };

  // 處理通知點擊
  const handleNotificationClick = () => {
    // 點擊通知後可以執行額外邏輯
    console.log("Notification clicked");
  };

  // 處理標記已讀
  const handleMarkAsRead = () => {
    fetchUnreadCount(); // 重新獲取未讀數量
  };

  // 處理標記全部已讀
  const handleMarkAllAsRead = () => {
    setUnreadCount(0); // 立即更新UI
    fetchUnreadCount(); // 重新獲取確認
  };

  useEffect(() => {
    fetchUnreadCount();

    // 每30秒更新一次未讀數量
    const interval = setInterval(fetchUnreadCount, 30000);

    return () => clearInterval(interval);
  }, []);

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={`relative hover:bg-nycu-blue-50 ${className}`}
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <>
              {/* 橘色指示燈 - 小圓點 */}
              <span className="absolute -top-1 -right-1 h-3 w-3 bg-orange-500 rounded-full animate-pulse border-2 border-white"></span>

              {/* 數字徽章 - 如果未讀數量超過3則顯示 */}
              {unreadCount > 3 && (
                <Badge
                  variant="destructive"
                  className="absolute -top-2 -right-2 h-5 w-5 p-0 text-xs bg-orange-500 hover:bg-orange-600 border-white border-2 flex items-center justify-center"
                >
                  {unreadCount > 99 ? "99+" : unreadCount}
                </Badge>
              )}
            </>
          )}
        </Button>
      </PopoverTrigger>

      <PopoverContent
        className="w-80 p-0 mr-4"
        align="end"
        side="bottom"
        sideOffset={8}
      >
        <NotificationPanel
          locale={locale}
          onNotificationClick={handleNotificationClick}
          onMarkAsRead={handleMarkAsRead}
          onMarkAllAsRead={handleMarkAllAsRead}
        />
      </PopoverContent>
    </Popover>
  );
}
