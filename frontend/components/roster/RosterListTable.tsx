"use client";

import { useState } from "react";
import { logger } from "@/lib/utils/logger";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Download,
  Eye,
  PlayCircle,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  RefreshCcw,
  Lock,
} from "lucide-react";
import { RosterDetailDialog } from "./RosterDetailDialog";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";

interface Period {
  label: string;
  status:
    | "completed"
    | "waiting"
    | "failed"
    | "processing"
    | "draft"
    | "locked";
  roster_id?: number;
  roster_code?: string;
  roster_status?: string;
  error_message?: string;
  completed_at?: string;
  total_amount?: number;
  qualified_count?: number;
  next_schedule?: string;
  period_start_date?: string;
  period_end_date?: string;
  sub_type?: string | null;
  allocation_year?: number | null;
  project_number?: string | null;
  excel_stale?: boolean;
}

interface RosterListTableProps {
  periods: Period[];
  configId: number;
  /**
   * Roster cycle from the parent schedule (monthly | semi_yearly | yearly).
   * Required — previously this was hardcoded to "monthly" when generating
   * rosters, which silently mislabelled rosters generated against
   * semi-yearly / yearly schedules. See PR #507.
   */
  rosterCycle: string;
  onRosterGenerated?: () => void;
}

export function RosterListTable({
  periods,
  configId,
  rosterCycle,
  onRosterGenerated,
}: RosterListTableProps) {
  const [selectedPeriod, setSelectedPeriod] = useState<Period | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [regenerating, setRegenerating] = useState<number | null>(null);

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-";
    try {
      const date = new Date(dateStr);
      return date.toLocaleString("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  const formatDateOnly = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-";
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  const formatPeriodRange = (startDate?: string, endDate?: string) => {
    if (!startDate || !endDate) return "-";
    return `${formatDateOnly(startDate)} - ${formatDateOnly(endDate)}`;
  };

  const handleViewRoster = (period: Period) => {
    setSelectedPeriod(period);
    setDialogOpen(true);
  };

  const handleDownload = async (period: Period) => {
    if (!period.roster_id) return;

    setDownloading(period.roster_id);
    try {
      const token = apiClient.getToken();
      const response = await fetch(
        `/api/v1/payment-rosters/${period.roster_id}/download`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error("Download failed");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute(
        "download",
        `${period.roster_code || period.label}.xlsx`
      );
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast.success("造冊檔案已下載");
    } catch (error) {
      logger.error("Failed to download roster", { error: error });
      toast.error("下載失敗: 無法下載造冊檔案");
    } finally {
      setDownloading(null);
    }
  };

  const handleGenerateNow = async (
    period: Period,
    isRegeneration: boolean = false
  ) => {
    setGenerating(period.label);
    try {
      const response = await apiClient.paymentRosters.generateRoster({
        scholarship_configuration_id: configId,
        period_label: period.label,
        roster_cycle: rosterCycle as never,
        academic_year: parseInt(period.label.split("-")[0]),
        student_verification_enabled: true,
        auto_export_excel: true,
        force_regenerate: isRegeneration,
      });

      if (response.success) {
        toast.success(`已成功產生 ${period.label} 的造冊`);
        onRosterGenerated?.();
      } else {
        throw new Error(response.message || "產生造冊失敗");
      }
    } catch (error: unknown) {
      logger.error("Failed to generate roster", { error: error });
      toast.error(`產生造冊失敗: ${(error instanceof Error ? error.message : "無法產生造冊")}`);
    } finally {
      setGenerating(null);
    }
  };

  /**
   * 重新生成一份既有造冊的名單。
   *
   * 以 roster_id 定位（不是 period_label）：矩陣分發下同一個 period_label 底下
   * 會有多份 (子類型 × 配額年度) 造冊，走 handleGenerateNow 的 config+期間鍵
   * 會打到別份造冊。
   */
  const handleRegenerate = async (period: Period) => {
    if (!period.roster_id) return;
    if (
      !window.confirm(
        `確認重新生成「${period.label}${period.sub_type ? ` · ${period.sub_type}` : ""}」的造冊名單？\n\n` +
          "系統會依當下的分發名單與學生資料重建全部明細並重新匯出 Excel；" +
          "您先前的人為排除／移除會保留。"
      )
    )
      return;

    setRegenerating(period.roster_id);
    try {
      const response = await apiClient.paymentRosters.regenerateRoster(
        period.roster_id
      );
      if (response.success) {
        toast.success(response.message || "造冊已重新生成");
        onRosterGenerated?.();
      } else {
        throw new Error(response.message || "重新生成造冊失敗");
      }
    } catch (error: unknown) {
      logger.error("Failed to regenerate roster", { error: error });
      toast.error(
        error instanceof Error ? error.message : "重新生成造冊失敗"
      );
    } finally {
      setRegenerating(null);
    }
  };

  const getRowClassName = (status: string) => {
    switch (status) {
      case "completed":
      case "locked":
        return "bg-green-50 hover:bg-green-100";
      case "failed":
        return "bg-red-50 hover:bg-red-100";
      case "processing":
        return "bg-blue-50 hover:bg-blue-100";
      case "draft":
      case "waiting":
      default:
        return "bg-gray-50 hover:bg-gray-100";
    }
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>造冊列表</CardTitle>
        </CardHeader>
        <CardContent>
          {periods.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Clock className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              <p>目前沒有造冊資料</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px] whitespace-nowrap">
                    期間
                  </TableHead>
                  <TableHead className="whitespace-nowrap">子類型</TableHead>
                  <TableHead className="whitespace-nowrap">配額年度</TableHead>
                  <TableHead className="whitespace-nowrap">造冊期間</TableHead>
                  <TableHead className="w-[120px] whitespace-nowrap">
                    狀態
                  </TableHead>
                  <TableHead className="whitespace-nowrap">
                    完成時間 / 下次排程
                  </TableHead>
                  <TableHead className="text-right whitespace-nowrap">
                    操作
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {periods.map(period => (
                  <TableRow
                    key={`${period.label}-${period.sub_type ?? ""}-${period.allocation_year ?? ""}`}
                    className={getRowClassName(period.status)}
                  >
                    {/* 期間 */}
                    <TableCell className="font-medium whitespace-nowrap">
                      {period.label}
                    </TableCell>

                    {/* 子類型 */}
                    <TableCell className="whitespace-nowrap">
                      {period.sub_type ? (
                        <span className="font-mono text-sm text-blue-700">
                          {period.sub_type}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>

                    {/* 配額年度 */}
                    <TableCell className="whitespace-nowrap">
                      {period.allocation_year ? (
                        <div>
                          <span className="font-medium">
                            {period.allocation_year}
                          </span>
                          {period.project_number && (
                            <div className="text-xs text-muted-foreground">
                              {period.project_number}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">-</span>
                      )}
                    </TableCell>

                    {/* 造冊期間 */}
                    <TableCell className="whitespace-nowrap">
                      {formatPeriodRange(
                        period.period_start_date,
                        period.period_end_date
                      )}
                    </TableCell>

                    {/* 狀態 */}
                    <TableCell className="whitespace-nowrap">
                      {/* 已鎖定要先判斷：cycle-status 把 LOCKED 與 COMPLETED 都
                          折成 status="completed"，只看 status 會讓「已鎖定」永遠
                          顯示成「已完成」——管理員就看不出為何沒有「重新生成」。 */}
                      {period.roster_status === "locked" ||
                      period.status === "locked" ? (
                        <Badge variant="default" className="bg-slate-600">
                          <Lock className="mr-1 h-3 w-3" />
                          已鎖定
                        </Badge>
                      ) : period.status === "completed" ? (
                        <Badge variant="default" className="bg-green-600">
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                          已完成
                        </Badge>
                      ) : period.status === "failed" ? (
                        <Badge variant="destructive">
                          <XCircle className="mr-1 h-3 w-3" />
                          失敗
                        </Badge>
                      ) : period.status === "processing" ? (
                        <Badge
                          variant="secondary"
                          className="bg-blue-100 text-blue-700"
                        >
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          處理中
                        </Badge>
                      ) : period.status === "draft" ? (
                        <Badge variant="secondary">
                          <Clock className="mr-1 h-3 w-3" />
                          草稿
                        </Badge>
                      ) : (
                        <Badge variant="secondary">
                          <Clock className="mr-1 h-3 w-3" />
                          等待中
                        </Badge>
                      )}
                    </TableCell>

                    {/* 完成時間 / 下次排程 */}
                    <TableCell>
                      {period.status === "completed" ||
                      period.status === "locked" ? (
                        <div className="text-sm">
                          <div>{formatDate(period.completed_at)}</div>
                          {period.qualified_count !== undefined && (
                            <div className="text-muted-foreground">
                              {period.qualified_count} 人
                            </div>
                          )}
                        </div>
                      ) : period.status === "failed" ? (
                        <div className="text-sm text-red-600">
                          <div>產生失敗</div>
                          {period.error_message && (
                            <div
                              className="text-xs line-clamp-2"
                              title={period.error_message}
                            >
                              {period.error_message}
                            </div>
                          )}
                        </div>
                      ) : period.status === "processing" ? (
                        <div className="text-sm text-blue-600">
                          正在處理中...
                        </div>
                      ) : (
                        <div className="text-sm text-muted-foreground">
                          {period.next_schedule ? (
                            <>下次排程: {formatDate(period.next_schedule)}</>
                          ) : (
                            "待排程"
                          )}
                        </div>
                      )}
                    </TableCell>

                    {/* 操作 */}
                    <TableCell className="text-right">
                      {period.status === "completed" ||
                      period.status === "locked" ? (
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleViewRoster(period)}
                          >
                            <Eye className="mr-1 h-4 w-4" />
                            查看名單
                          </Button>
                          {/* 已鎖定的造冊不可重建（後端會擋），需先解鎖。
                              必須看 roster_status：cycle-status 把 LOCKED 與
                              COMPLETED 都折成 period.status="completed"，只有
                              roster_status 帶真正的造冊狀態。 */}
                          {period.roster_status !== "locked" && period.roster_id && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleRegenerate(period)}
                              disabled={regenerating === period.roster_id}
                              title="依當下的分發名單與學生資料重建名單（不需人員有異動）"
                            >
                              {regenerating === period.roster_id ? (
                                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                              ) : (
                                <RefreshCcw className="mr-1 h-4 w-4" />
                              )}
                              {regenerating === period.roster_id
                                ? "生成中..."
                                : "重新生成"}
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="default"
                            onClick={() => handleDownload(period)}
                            disabled={downloading === period.roster_id}
                          >
                            <Download className="mr-1 h-4 w-4" />
                            {downloading === period.roster_id
                              ? "下載中..."
                              : "下載Excel"}
                          </Button>
                        </div>
                      ) : period.status === "failed" ? (
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={() => handleGenerateNow(period, true)}
                          disabled={generating === period.label}
                        >
                          <PlayCircle className="mr-1 h-4 w-4" />
                          {generating === period.label
                            ? "產生中..."
                            : "重新產生"}
                        </Button>
                      ) : period.status === "processing" ? (
                        <Button size="sm" variant="outline" disabled>
                          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                          處理中...
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleGenerateNow(period)}
                          disabled={generating === period.label}
                        >
                          <PlayCircle className="mr-1 h-4 w-4" />
                          {generating === period.label
                            ? "產生中..."
                            : "立即產生"}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Roster Detail Dialog */}
      {selectedPeriod && (
        <RosterDetailDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          period={selectedPeriod}
          configId={configId}
          onRosterChanged={onRosterGenerated}
        />
      )}
    </>
  );
}
