"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Loader2, RefreshCw } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import api from "@/lib/api";
import { logger } from "@/lib/utils/logger";
import { getTermDataStatus } from "@/lib/utils/student-data-helpers";

const TERM_STATUS_SUCCESS = "success";

const TERM_STATUS_LABELS: Record<string, { zh: string; en: string }> = {
  success: { zh: "完整", en: "Complete" },
  partial: { zh: "部分（僅取得上學期資料）", en: "Partial (first term only)" },
  error: { zh: "取得失敗", en: "Failed" },
  not_requested: { zh: "未查詢", en: "Not requested" },
};

interface SisTermResyncCardProps {
  applicationId: number;
  studentData?: Record<string, unknown> | null;
  locale: "zh" | "en";
  /** Called after the snapshot was updated, so the parent reloads the application */
  onResynced: () => void;
}

/**
 * Admin card showing whether the application's SIS term data (系所、年級 …) was
 * captured, with a 重新同步 action when it was not (SIS failed at draft creation).
 */
export function SisTermResyncCard({
  applicationId,
  studentData,
  locale,
  onResynced,
}: SisTermResyncCardProps) {
  const [isResyncing, setIsResyncing] = useState(false);
  const isZh = locale === "zh";
  const status = getTermDataStatus(studentData);
  const isComplete = status === TERM_STATUS_SUCCESS;
  const statusLabel = status
    ? TERM_STATUS_LABELS[status]?.[locale] ?? status
    : isZh ? "未知" : "Unknown";

  const handleResync = async () => {
    setIsResyncing(true);
    try {
      const response = await api.admin.resyncSisTermData(applicationId);
      if (!response.success) {
        toast.error(isZh ? "重新同步失敗" : "Resync failed", {
          description: response.message,
        });
        return;
      }
      if (response.data?.updated) {
        toast.success(isZh ? "已重新同步學籍學期資料" : "SIS term data resynced");
        onResynced();
      } else if (response.data?.new_status === TERM_STATUS_SUCCESS) {
        // Another request completed it meanwhile — reload to show it
        toast.info(isZh ? "學期資料已完整" : "Term data already complete", {
          description: response.message,
        });
        onResynced();
      } else {
        toast.warning(isZh ? "未取得學期資料，未變更" : "No term data received; nothing changed", {
          description: response.message,
        });
      }
    } catch (error) {
      logger.error("SIS term resync error", { error });
      toast.error(isZh ? "重新同步失敗" : "Resync failed", {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setIsResyncing(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <RefreshCw className="h-5 w-5" />
          {isZh ? "學籍學期資料" : "SIS Term Data"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">{isZh ? "狀態" : "Status"}</span>
              <Badge variant={isComplete ? "default" : "destructive"}>{statusLabel}</Badge>
            </div>
            <p className="text-sm text-muted-foreground mt-1">
              {isComplete
                ? isZh
                  ? "已取得學期資料（系所、年級等）。"
                  : "Term data (department, grade …) is available."
                : isZh
                  ? "申請時未能取得學期資料，系所、年級等欄位在匯出時會是空白。可向學籍系統重新取得。"
                  : "Term data was not captured at application time, so department / grade export blank. Fetch it again from SIS."}
            </p>
          </div>
          {!isComplete && (
            <Button onClick={handleResync} disabled={isResyncing} size="sm">
              {isResyncing ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4 mr-2" />
              )}
              {isZh ? "重新同步" : "Resync"}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
