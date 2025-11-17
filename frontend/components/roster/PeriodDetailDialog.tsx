"use client"

import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import {
  Download,
  InfoIcon,
  Calendar,
  Users,
  DollarSign,
  PlayCircle,
  Loader2,
  XCircle,
  AlertTriangle,
  CheckCircle2,
  Lock,
} from "lucide-react"
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
  estimated_count?: number
}

interface PeriodDetailDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  period: Period
  configId: number
  onRosterGenerated?: () => void
}

export function PeriodDetailDialog({
  open,
  onOpenChange,
  period,
  configId,
  onRosterGenerated,
}: PeriodDetailDialogProps) {
  const [downloading, setDownloading] = useState(false)
  const [generating, setGenerating] = useState(false)

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

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("zh-TW", {
      style: "currency",
      currency: "TWD",
      minimumFractionDigits: 0,
    }).format(amount)
  }

  const handleDownload = async () => {
    if (!period.roster_id) return

    setDownloading(true)
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
      setDownloading(false)
    }
  }

  const handleGenerateNow = async () => {
    setGenerating(true)
    try {
      // TODO: Need to get schedule_id from parent component
      // For now, we'll use the generate API directly
      const response = await apiClient.request("/payment-rosters/generate", {
        method: "POST",
        body: JSON.stringify({
          scholarship_configuration_id: configId,
          period_label: period.label,
          roster_cycle: "monthly", // TODO: Get from schedule
          academic_year: parseInt(period.label.split("-")[0]),
          student_verification_enabled: true,
          auto_export_excel: true,
        }),
        headers: {
          "Content-Type": "application/json",
        },
      })

      if (response.success) {
        toast.success(`已成功產生 ${period.label} 的造冊`)
        onOpenChange(false)
        onRosterGenerated?.()
      } else {
        throw new Error(response.message || "產生造冊失敗")
      }
    } catch (error: any) {
      console.error("Failed to generate roster:", error)
      toast.error(`產生造冊失敗: ${error.message || "無法產生造冊"}`)
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {period.status === "completed" || period.status === "locked"
              ? "造冊詳情"
              : period.status === "failed"
              ? "造冊失敗"
              : period.status === "processing"
              ? "造冊處理中"
              : "等待造冊"}{" "}
            - {period.label}
          </DialogTitle>
          <DialogDescription>
            {period.status === "completed" || period.status === "locked"
              ? "查看此期間的造冊詳細資訊"
              : period.status === "failed"
              ? "造冊產生過程中發生錯誤"
              : period.status === "processing"
              ? "系統正在處理此造冊，請稍候"
              : "此期間尚未產生造冊"}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {period.status === "completed" || period.status === "locked" ? (
            <>
              {/* Completed/Locked Roster Details */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-muted-foreground">造冊代碼</Label>
                  <p className="font-mono font-medium">{period.roster_code}</p>
                </div>

                <div className="space-y-2">
                  <Label className="text-muted-foreground">狀態</Label>
                  <div>
                    {period.status === "locked" ? (
                      <Badge variant="default" className="bg-green-600">
                        <Lock className="mr-1 h-3 w-3" />
                        已鎖定
                      </Badge>
                    ) : (
                      <Badge variant="default" className="bg-green-600">
                        <CheckCircle2 className="mr-1 h-3 w-3" />
                        已完成
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-muted-foreground">完成時間</Label>
                  <p className="text-sm">{formatDate(period.completed_at)}</p>
                </div>

                <div className="space-y-2">
                  <Label className="text-muted-foreground">學生人數</Label>
                  <div className="flex items-center gap-2">
                    <Users className="h-4 w-4 text-muted-foreground" />
                    <p className="font-medium">{period.qualified_count || 0} 人</p>
                  </div>
                </div>

                <div className="space-y-2 col-span-2">
                  <Label className="text-muted-foreground">總金額</Label>
                  <div className="flex items-center gap-2">
                    <DollarSign className="h-4 w-4 text-muted-foreground" />
                    <p className="text-lg font-bold">
                      {formatCurrency(period.total_amount || 0)}
                    </p>
                  </div>
                </div>
              </div>

              <Separator />

              <DialogFooter>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  關閉
                </Button>
                <Button onClick={handleDownload} disabled={downloading}>
                  {downloading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      下載中...
                    </>
                  ) : (
                    <>
                      <Download className="mr-2 h-4 w-4" />
                      下載 Excel
                    </>
                  )}
                </Button>
              </DialogFooter>
            </>
          ) : period.status === "failed" ? (
            <>
              {/* Failed Roster Details */}
              <Alert variant="destructive">
                <XCircle className="h-4 w-4" />
                <AlertDescription>
                  <div className="space-y-2">
                    <p className="font-semibold">造冊產生失敗</p>
                    {period.error_message && (
                      <p className="text-sm">{period.error_message}</p>
                    )}
                  </div>
                </AlertDescription>
              </Alert>

              <div className="grid grid-cols-2 gap-4">
                {period.roster_code && (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">造冊代碼</Label>
                    <p className="font-mono font-medium">{period.roster_code}</p>
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-muted-foreground">狀態</Label>
                  <div>
                    <Badge variant="destructive">
                      <XCircle className="mr-1 h-3 w-3" />
                      失敗
                    </Badge>
                  </div>
                </div>
              </div>

              <Separator />

              <DialogFooter>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  關閉
                </Button>
                <Button variant="destructive" onClick={handleGenerateNow} disabled={generating}>
                  {generating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      重新產生中...
                    </>
                  ) : (
                    <>
                      <PlayCircle className="mr-2 h-4 w-4" />
                      重新產生造冊
                    </>
                  )}
                </Button>
              </DialogFooter>
            </>
          ) : period.status === "processing" ? (
            <>
              {/* Processing Roster Details */}
              <Alert className="bg-blue-50 border-blue-200">
                <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
                <AlertDescription className="text-blue-800">
                  系統正在處理此造冊，請稍候片刻。造冊完成後會自動更新狀態。
                </AlertDescription>
              </Alert>

              <div className="grid grid-cols-2 gap-4">
                {period.roster_code && (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">造冊代碼</Label>
                    <p className="font-mono font-medium">{period.roster_code}</p>
                  </div>
                )}

                <div className="space-y-2">
                  <Label className="text-muted-foreground">狀態</Label>
                  <div>
                    <Badge variant="secondary" className="bg-blue-100 text-blue-700">
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      處理中
                    </Badge>
                  </div>
                </div>
              </div>

              <Separator />

              <DialogFooter>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  關閉
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              {/* Waiting/Draft Roster Details */}
              <Alert>
                <InfoIcon className="h-4 w-4" />
                <AlertDescription>
                  此期間尚未產生造冊。您可以等待排程自動執行，或立即手動產生造冊。
                </AlertDescription>
              </Alert>

              <div className="space-y-4">
                {period.next_schedule && (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">下次排程時間</Label>
                    <div className="flex items-center gap-2">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <p className="text-sm">{formatDate(period.next_schedule)}</p>
                    </div>
                  </div>
                )}

                {period.estimated_count !== undefined && period.estimated_count > 0 && (
                  <div className="space-y-2">
                    <Label className="text-muted-foreground">預計人數</Label>
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4 text-muted-foreground" />
                      <p className="text-sm">{period.estimated_count} 人</p>
                    </div>
                  </div>
                )}
              </div>

              <Separator />

              <DialogFooter>
                <Button variant="outline" onClick={() => onOpenChange(false)}>
                  取消
                </Button>
                <Button onClick={handleGenerateNow} disabled={generating}>
                  {generating ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      產生中...
                    </>
                  ) : (
                    <>
                      <PlayCircle className="mr-2 h-4 w-4" />
                      立即產生造冊
                    </>
                  )}
                </Button>
              </DialogFooter>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
