"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Calendar, CheckCircle2, Clock, AlertCircle } from "lucide-react"
import { apiClient } from "@/lib/api"
import { PeriodDetailDialog } from "./PeriodDetailDialog"

interface Period {
  label: string
  status: "completed" | "waiting"
  roster_id?: number
  roster_code?: string
  completed_at?: string
  total_amount?: number
  qualified_count?: number
  next_schedule?: string
  estimated_count?: number
}

interface CycleStatusData {
  schedule: {
    id: number
    schedule_name: string
    roster_cycle: string
    cron_expression: string
    status: string
    next_run_at: string | null
    last_run_at: string | null
  }
  roster_cycle: string
  periods: Period[]
}

interface RosterCycleTimelineProps {
  configId: number
}

export function RosterCycleTimeline({ configId }: RosterCycleTimelineProps) {
  const [data, setData] = useState<CycleStatusData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedPeriod, setSelectedPeriod] = useState<Period | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)

  useEffect(() => {
    loadCycleStatus()
  }, [configId])

  const loadCycleStatus = async () => {
    setLoading(true)
    setError(null)

    try {
      const response = await apiClient.request("/payment-rosters/cycle-status", {
        method: "GET",
        params: { config_id: configId },
      })

      if (response.success && response.data) {
        setData(response.data)
      } else {
        setError("無法載入造冊週期資料")
      }
    } catch (err) {
      console.error("Failed to load cycle status:", err)
      setError("載入造冊週期時發生錯誤")
    } finally {
      setLoading(false)
    }
  }

  const handlePeriodClick = (period: Period) => {
    setSelectedPeriod(period)
    setDialogOpen(true)
  }

  const getCycleName = (cycle: string) => {
    const names: Record<string, string> = {
      monthly: "每月",
      semi_yearly: "半年度",
      yearly: "年度",
    }
    return names[cycle] || cycle
  }

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

  if (loading) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4 text-muted-foreground">載入造冊週期中...</p>
        </CardContent>
      </Card>
    )
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
          <p className="text-muted-foreground">{error || "無造冊週期資料"}</p>
        </CardContent>
      </Card>
    )
  }

  const completedCount = data.periods.filter((p) => p.status === "completed").length
  const waitingCount = data.periods.filter((p) => p.status === "waiting").length

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>預計分發週期</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">
                造冊週期: {getCycleName(data.roster_cycle)} • 已完成 {completedCount} / 總計{" "}
                {data.periods.length} 期
              </p>
            </div>
            <div className="flex items-center gap-4 text-sm">
              {data.schedule.next_run_at && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Clock className="h-4 w-4" />
                  <span>下次執行: {formatDate(data.schedule.next_run_at)}</span>
                </div>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
            {data.periods.map((period) => (
              <Card
                key={period.label}
                className={`cursor-pointer transition-all hover:shadow-md ${
                  period.status === "completed"
                    ? "bg-green-50 border-green-200"
                    : "bg-gray-50 border-gray-200"
                }`}
                onClick={() => handlePeriodClick(period)}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="text-sm font-semibold">{period.label}</div>
                    {period.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                    ) : (
                      <Clock className="h-4 w-4 text-gray-400" />
                    )}
                  </div>

                  {period.status === "completed" ? (
                    <div className="space-y-1">
                      <Badge variant="default" className="text-xs">
                        已完成
                      </Badge>
                      <div className="text-xs text-muted-foreground">
                        {period.qualified_count || 0} 人
                      </div>
                      {period.total_amount !== undefined && (
                        <div className="text-xs font-medium">
                          {formatCurrency(period.total_amount)}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Badge variant="secondary" className="text-xs">
                        等待造冊
                      </Badge>
                      {period.next_schedule && (
                        <div className="text-xs text-muted-foreground">
                          {formatDate(period.next_schedule)}
                        </div>
                      )}
                      {period.estimated_count !== undefined && period.estimated_count > 0 && (
                        <div className="text-xs text-muted-foreground">
                          預計 {period.estimated_count} 人
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          {data.periods.length === 0 && (
            <div className="text-center py-12 text-muted-foreground">
              <Calendar className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
              <p>目前沒有造冊週期資料</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Period Detail Dialog */}
      {selectedPeriod && (
        <PeriodDetailDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          period={selectedPeriod}
          configId={configId}
          onRosterGenerated={loadCycleStatus}
        />
      )}
    </>
  )
}
