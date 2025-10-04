"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { api } from "@/lib/api";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface TestModeStatus {
  enabled: boolean;
  redirect_emails: string[];
  expires_at: string | null;
}

export function EmailTestModeBanner() {
  const [status, setStatus] = useState<TestModeStatus | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStatus();
    // Check status every 30 seconds
    const interval = setInterval(loadStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadStatus = async () => {
    try {
      const response = await api.emailManagement.getTestModeStatus();
      if (response.success && response.data) {
        setStatus(response.data);
        // Reset dismissed state when test mode is toggled
        if (!response.data.enabled) {
          setDismissed(false);
        }
      }
    } catch (error) {
      console.error("Failed to load test mode status:", error);
    } finally {
      setLoading(false);
    }
  };

  const formatExpiryTime = (expiresAt: string | null) => {
    if (!expiresAt) return null;
    const expiry = new Date(expiresAt);
    const now = new Date();
    const diffMs = expiry.getTime() - now.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMinutes = Math.floor((diffMs % (1000 * 60 * 60)) / (1000 * 60));

    if (diffMs < 0) return "已過期";
    if (diffHours > 0) return `${diffHours} 小時 ${diffMinutes} 分鐘`;
    return `${diffMinutes} 分鐘`;
  };

  // Don't render if loading, not enabled, or dismissed
  if (loading || !status?.enabled || dismissed) {
    return null;
  }

  return (
    <Alert
      variant="warning"
      className="relative border-yellow-500 bg-yellow-50 dark:bg-yellow-950 mb-4 rounded-lg"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 mt-0.5 flex-shrink-0 text-yellow-600 dark:text-yellow-400" />
        <div className="flex-1 space-y-1">
          <div className="font-semibold text-yellow-900 dark:text-yellow-100">
            ⚠️ 郵件測試模式啟用中
          </div>
          <AlertDescription className="text-yellow-800 dark:text-yellow-200">
            <p className="mb-1">
              所有系統郵件將重定向至 {status.redirect_emails.length} 個測試信箱:
              <strong className="ml-1">{status.redirect_emails.join(", ")}</strong>
            </p>
            {status.expires_at && (
              <p className="text-sm">
                自動過期時間: {formatExpiryTime(status.expires_at)} ({new Date(status.expires_at).toLocaleString("zh-TW")})
              </p>
            )}
            <p className="text-sm mt-2 font-medium">
              ⚠️ 學生、教授和學院將不會收到實際郵件通知
            </p>
          </AlertDescription>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setDismissed(true)}
          className="flex-shrink-0 text-yellow-900 hover:text-yellow-700 hover:bg-yellow-100 dark:text-yellow-100 dark:hover:text-yellow-300 dark:hover:bg-yellow-900"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </Alert>
  );
}
