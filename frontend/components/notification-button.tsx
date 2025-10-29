"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";
import { NotificationPanel } from "@/components/notification-panel";
import { useNotifications } from "@/contexts/notification-context";

interface NotificationButtonProps {
  locale: "zh" | "en";
  className?: string;
}

export function NotificationButton({
  locale = "zh",
  className = "",
}: NotificationButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { unreadCount, notifyPanelOpen } = useNotifications();

  // 處理 Popover 開啟
  const handleOpenChange = (open: boolean) => {
    setIsOpen(open);
    if (open) {
      // 通知 Panel 開啟,觸發載入通知列表
      notifyPanelOpen();
    }
  };

  // 處理通知點擊
  const handleNotificationClick = () => {
    console.log("Notification clicked");
  };

  return (
    <Popover open={isOpen} onOpenChange={handleOpenChange}>
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
        />
      </PopoverContent>
    </Popover>
  );
}
