"use client"

import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Calendar, Clock, Repeat } from "lucide-react"

interface ConfigInfoCardProps {
  config: {
    id: number
    config_name: string
    academic_year: number
    semester?: string
    amount?: number
  }
  schedule?: {
    id: number
    schedule_name: string
    roster_cycle: string
    status: string
    next_run_at?: string
    last_run_at?: string
  } | null
}

export function ConfigInfoCard({ config, schedule }: ConfigInfoCardProps) {
  const formatDate = (dateStr: string | null | undefined) => {
    if (!dateStr) return "-"
    try {
      const date = new Date(dateStr)
      return date.toLocaleString("zh-TW", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    } catch {
      return dateStr
    }
  }

  const getCycleName = (cycle: string) => {
    const names: Record<string, string> = {
      monthly: "每月",
      semi_yearly: "半年度",
      yearly: "年度",
    }
    return names[cycle] || cycle
  }

  const getSemesterName = (semester?: string) => {
    if (!semester) return "整學年"
    const names: Record<string, string> = {
      first: "上學期",
      second: "下學期",
    }
    return names[semester] || semester
  }

  const getStatusBadgeVariant = (status: string) => {
    const variants: Record<string, "default" | "secondary" | "destructive"> = {
      active: "default",
      paused: "secondary",
      disabled: "destructive",
      error: "destructive",
    }
    return variants[status] || "secondary"
  }

  const getStatusName = (status: string) => {
    const names: Record<string, string> = {
      active: "執行中",
      paused: "已暫停",
      disabled: "已停用",
      error: "錯誤",
    }
    return names[status] || status
  }

  return (
    <Card>
      <CardContent className="p-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {/* 獎學金名稱 */}
          <div className="space-y-1">
            <Label className="text-sm text-muted-foreground">獎學金名稱</Label>
            <p className="font-semibold text-lg">{config.config_name}</p>
          </div>

          {/* 學年度/學期 */}
          <div className="space-y-1">
            <Label className="text-sm text-muted-foreground flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              學年度 / 學期
            </Label>
            <p className="font-medium">
              {config.academic_year} 學年度
              <span className="text-muted-foreground mx-2">/</span>
              {getSemesterName(config.semester)}
            </p>
          </div>

          {/* 造冊週期 */}
          <div className="space-y-1">
            <Label className="text-sm text-muted-foreground flex items-center gap-1">
              <Repeat className="h-3 w-3" />
              造冊週期
            </Label>
            {schedule ? (
              <p className="font-medium">{getCycleName(schedule.roster_cycle)}</p>
            ) : (
              <p className="text-muted-foreground text-sm">未設定排程</p>
            )}
          </div>

          {/* 排程狀態 */}
          <div className="space-y-1">
            <Label className="text-sm text-muted-foreground">排程狀態</Label>
            {schedule ? (
              <div className="flex items-center gap-2">
                <Badge variant={getStatusBadgeVariant(schedule.status)}>
                  {getStatusName(schedule.status)}
                </Badge>
              </div>
            ) : (
              <Badge variant="secondary">未建立</Badge>
            )}
          </div>
        </div>

        {/* 排程執行時間資訊 */}
        {schedule && (
          <div className="mt-4 pt-4 border-t grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
            {schedule.last_run_at && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span>上次執行: {formatDate(schedule.last_run_at)}</span>
              </div>
            )}
            {schedule.next_run_at && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Clock className="h-4 w-4" />
                <span>下次執行: {formatDate(schedule.next_run_at)}</span>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
