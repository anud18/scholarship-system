"use client"

import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { InfoIcon, Loader2, Settings } from "lucide-react"
import { apiClient } from "@/lib/api"
import { toast } from "sonner"

interface ScheduleData {
  id: number
  schedule_name: string
  description?: string
  roster_cycle: string
  cron_expression: string
  auto_lock: boolean
  student_verification_enabled: boolean
  notification_enabled: boolean
  notification_emails?: string[]
  status: string
}

interface ScheduleSettingDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  schedule: ScheduleData
  onUpdated?: () => void
}

export function ScheduleSettingDialog({
  open,
  onOpenChange,
  schedule,
  onUpdated,
}: ScheduleSettingDialogProps) {
  const [formData, setFormData] = useState<Partial<ScheduleData>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (schedule) {
      setFormData({
        schedule_name: schedule.schedule_name,
        description: schedule.description,
        roster_cycle: schedule.roster_cycle,
        cron_expression: schedule.cron_expression,
        auto_lock: schedule.auto_lock,
        student_verification_enabled: schedule.student_verification_enabled,
        notification_enabled: schedule.notification_enabled,
        notification_emails: schedule.notification_emails || [],
      })
    }
  }, [schedule])

  const handleSave = async () => {
    setSaving(true)
    try {
      const updateData = {
        schedule_name: formData.schedule_name,
        description: formData.description || null,
        roster_cycle: formData.roster_cycle,
        cron_expression: formData.cron_expression,
        auto_lock: formData.auto_lock || false,
        student_verification_enabled: formData.student_verification_enabled || false,
        notification_enabled: formData.notification_enabled || false,
        notification_emails: formData.notification_emails || [],
      }

      const response = await apiClient.request(`/roster-schedules/${schedule.id}`, {
        method: "PUT",
        body: JSON.stringify(updateData),
        headers: {
          "Content-Type": "application/json",
        },
      })

      if (response.success) {
        toast.success("排程設定已更新")
        onOpenChange(false)
        onUpdated?.()
      } else {
        throw new Error(response.message || "更新失敗")
      }
    } catch (error: any) {
      console.error("Failed to update schedule:", error)
      toast.error(`儲存失敗: ${error.message || "無法更新排程設定"}`)
    } finally {
      setSaving(false)
    }
  }

  const rosterCycleOptions = [
    { value: "monthly", label: "每月" },
    { value: "semi_yearly", label: "半年度" },
    { value: "yearly", label: "年度" },
  ]

  const cronPresets = [
    { label: "每月1號午夜 (0 0 1 * *)", value: "0 0 1 * *" },
    { label: "每月15號午夜 (0 0 15 * *)", value: "0 0 15 * *" },
    { label: "每週一上午9點 (0 9 * * 1)", value: "0 9 * * 1" },
    { label: "每天午夜 (0 0 * * *)", value: "0 0 * * *" },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            排程設定
          </DialogTitle>
          <DialogDescription>
            編輯造冊排程的設定，包括執行時間、週期和通知選項
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Basic Info */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="schedule-name">排程名稱 *</Label>
              <Input
                id="schedule-name"
                value={formData.schedule_name || ""}
                onChange={(e) =>
                  setFormData({ ...formData, schedule_name: e.target.value })
                }
                placeholder="輸入排程名稱"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">說明</Label>
              <Textarea
                id="description"
                value={formData.description || ""}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                placeholder="輸入排程說明（選填）"
                rows={3}
              />
            </div>
          </div>

          {/* Schedule Settings */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold">排程設定</h3>

            <div className="space-y-2">
              <Label htmlFor="roster-cycle">造冊週期 *</Label>
              <Select
                value={formData.roster_cycle}
                onValueChange={(value) =>
                  setFormData({ ...formData, roster_cycle: value })
                }
              >
                <SelectTrigger id="roster-cycle">
                  <SelectValue placeholder="選擇造冊週期" />
                </SelectTrigger>
                <SelectContent>
                  {rosterCycleOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="cron-expression">Cron 表達式 *</Label>
              <Input
                id="cron-expression"
                value={formData.cron_expression || ""}
                onChange={(e) =>
                  setFormData({ ...formData, cron_expression: e.target.value })
                }
                placeholder="0 0 1 * *"
                className="font-mono"
              />
              <div className="text-xs text-muted-foreground space-y-1">
                <p>常用範例:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  {cronPresets.map((preset) => (
                    <li key={preset.value}>
                      <button
                        type="button"
                        className="text-primary hover:underline"
                        onClick={() =>
                          setFormData({ ...formData, cron_expression: preset.value })
                        }
                      >
                        {preset.label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>

          {/* Options */}
          <div className="space-y-4">
            <h3 className="text-sm font-semibold">選項</h3>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="auto-lock"
                checked={formData.auto_lock || false}
                onCheckedChange={(checked) =>
                  setFormData({ ...formData, auto_lock: checked as boolean })
                }
              />
              <Label htmlFor="auto-lock" className="font-normal cursor-pointer">
                自動鎖定產生的造冊
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="student-verification"
                checked={formData.student_verification_enabled || false}
                onCheckedChange={(checked) =>
                  setFormData({
                    ...formData,
                    student_verification_enabled: checked as boolean,
                  })
                }
              />
              <Label
                htmlFor="student-verification"
                className="font-normal cursor-pointer"
              >
                啟用學籍驗證
              </Label>
            </div>

            <div className="flex items-center space-x-2">
              <Checkbox
                id="notification"
                checked={formData.notification_enabled || false}
                onCheckedChange={(checked) =>
                  setFormData({
                    ...formData,
                    notification_enabled: checked as boolean,
                  })
                }
              />
              <Label htmlFor="notification" className="font-normal cursor-pointer">
                發送通知
              </Label>
            </div>
          </div>

          {/* Notification Settings */}
          {formData.notification_enabled && (
            <div className="space-y-4">
              <h3 className="text-sm font-semibold">通知設定</h3>

              <div className="space-y-2">
                <Label htmlFor="notification-emails">通知信箱</Label>
                <Textarea
                  id="notification-emails"
                  value={formData.notification_emails?.join(", ") || ""}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      notification_emails: e.target.value
                        .split(",")
                        .map((email) => email.trim())
                        .filter(Boolean),
                    })
                  }
                  placeholder="email1@example.com, email2@example.com"
                  rows={2}
                />
                <p className="text-xs text-muted-foreground">
                  多個信箱請用逗號分隔
                </p>
              </div>
            </div>
          )}

          {/* Info Alert */}
          <Alert>
            <InfoIcon className="h-4 w-4" />
            <AlertDescription className="text-sm">
              修改 Cron 表達式或造冊週期後，系統將自動重新計算下次執行時間。
              請確認設定正確後再儲存。
            </AlertDescription>
          </Alert>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            取消
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                儲存中...
              </>
            ) : (
              "儲存設定"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
