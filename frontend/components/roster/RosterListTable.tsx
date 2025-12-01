"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Download, Eye, PlayCircle, Clock, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import { RosterDetailDialog } from "./RosterDetailDialog"
import { apiClient } from "@/lib/api"
import { toast } from "sonner"

interface Period {
  label: string
  status: "completed" | "waiting" | "failed" | "processing" | "draft" | "locked"
  roster_id?: number
  roster_code?: string
  roster_status?: string
  error_message?: string
  completed_at?: string
  total_amount?: number
  qualified_count?: number
  next_schedule?: string
  period_start_date?: string
  period_end_date?: string
}

interface RosterListTableProps {
  periods: Period[]
  configId: number
  onRosterGenerated?: () => void
}

export function RosterListTable({ periods, configId, onRosterGenerated }: RosterListTableProps) {
  const [selectedPeriod, setSelectedPeriod] = useState<Period | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [generating, setGenerating] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<number | null>(null)

  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-"
    try {
      const date = new Date(dateStr)
      return date.toLocaleString("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    } catch {
      return dateStr
    }
  }

  const formatDateOnly = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-"
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString("zh-TW", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      })
    } catch {
      return dateStr
    }
  }

  const formatPeriodRange = (startDate?: string, endDate?: string) => {
    if (!startDate || !endDate) return "-"
    return `${formatDateOnly(startDate)} - ${formatDateOnly(endDate)}`
  }

  const handleViewRoster = (period: Period) => {
    setSelectedPeriod(period)
    setDialogOpen(true)
  }

  const handleDownload = async (period: Period) => {
    if (!period.roster_id) return

    setDownloading(period.roster_id)
    try {
      const token = apiClient.getToken()
      const response = await fetch(
        `/api/v1/payment-rosters/${period.roster_id}/download`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      )

      if (!response.ok) {
        throw new Error("Download failed")
      }

      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = url
      link.setAttribute("download", `${period.roster_code || period.label}.xlsx`)
      document.body.appendChild(link)
      link.click()
      link.parentNode?.removeChild(link)
      window.URL.revokeObjectURL(url)

      toast.success("造冊檔案已下載")
    } catch (error) {
      console.error("Failed to download roster:", error)
      toast.error("下載失敗: 無法下載造冊檔案")
    } finally {
      setDownloading(null)
    }
  }

  const handleGenerateNow = async (period: Period, isRegeneration: boolean = false) => {
    setGenerating(period.label)
    try {
      const response = await apiClient.request("/payment-rosters/generate", {
        method: "POST",
        body: JSON.stringify({
          scholarship_configuration_id: configId,
          period_label: period.label,
          roster_cycle: "monthly", // TODO: Get from schedule
          academic_year: parseInt(period.label.split("-")[0]),
          student_verification_enabled: true,
          auto_export_excel: true,
          force_regenerate: isRegeneration,
        }),
        headers: {
          "Content-Type": "application/json",
        },
      })

      if (response.success) {
        toast.success(`已成功產生 ${period.label} 的造冊`)
        onRosterGenerated?.()
      } else {
        throw new Error(response.message || "產生造冊失敗")
      }
    } catch (error: any) {
      console.error("Failed to generate roster:", error)
      toast.error(`產生造冊失敗: ${error.message || "無法產生造冊"}`)
    } finally {
      setGenerating(null)
    }
  }

  const getRowClassName = (status: string) => {
    switch (status) {
      case "completed":
      case "locked":
        return "bg-green-50 hover:bg-green-100"
      case "failed":
        return "bg-red-50 hover:bg-red-100"
      case "processing":
        return "bg-blue-50 hover:bg-blue-100"
      case "draft":
      case "waiting":
      default:
        return "bg-gray-50 hover:bg-gray-100"
    }
  }

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
                  <TableHead className="w-[120px] whitespace-nowrap">期間</TableHead>
                  <TableHead className="whitespace-nowrap">造冊期間</TableHead>
                  <TableHead className="w-[120px] whitespace-nowrap">狀態</TableHead>
                  <TableHead className="whitespace-nowrap">完成時間 / 下次排程</TableHead>
                  <TableHead className="text-right whitespace-nowrap">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {periods.map((period) => (
                  <TableRow key={period.label} className={getRowClassName(period.status)}>
                    {/* 期間 */}
                    <TableCell className="font-medium whitespace-nowrap">{period.label}</TableCell>

                    {/* 造冊期間 */}
                    <TableCell className="whitespace-nowrap">
                      {formatPeriodRange(period.period_start_date, period.period_end_date)}
                    </TableCell>

                    {/* 狀態 */}
                    <TableCell className="whitespace-nowrap">
                      {period.status === "completed" ? (
                        <Badge variant="default" className="bg-green-600">
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                          已完成
                        </Badge>
                      ) : period.status === "locked" ? (
                        <Badge variant="default" className="bg-green-600">
                          <CheckCircle2 className="mr-1 h-3 w-3" />
                          已鎖定
                        </Badge>
                      ) : period.status === "failed" ? (
                        <Badge variant="destructive">
                          <XCircle className="mr-1 h-3 w-3" />
                          失敗
                        </Badge>
                      ) : period.status === "processing" ? (
                        <Badge variant="secondary" className="bg-blue-100 text-blue-700">
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
                      {period.status === "completed" || period.status === "locked" ? (
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
                            <div className="text-xs line-clamp-2" title={period.error_message}>
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
                      {period.status === "completed" || period.status === "locked" ? (
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleViewRoster(period)}
                          >
                            <Eye className="mr-1 h-4 w-4" />
                            查看名單
                          </Button>
                          <Button
                            size="sm"
                            variant="default"
                            onClick={() => handleDownload(period)}
                            disabled={downloading === period.roster_id}
                          >
                            <Download className="mr-1 h-4 w-4" />
                            {downloading === period.roster_id ? "下載中..." : "下載Excel"}
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
                          {generating === period.label ? "產生中..." : "重新產生"}
                        </Button>
                      ) : period.status === "processing" ? (
                        <Button
                          size="sm"
                          variant="outline"
                          disabled
                        >
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
                          {generating === period.label ? "產生中..." : "立即產生"}
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
        />
      )}
    </>
  )
}
