"use client"

import React, { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { toast } from "@/components/ui/use-toast"
import { Calendar } from "lucide-react"

interface RosterSchedule {
  id: number
  schedule_name: string
  description?: string
  scholarship_configuration_id: number
  roster_cycle: string
  cron_expression?: string
  status: string
}

interface ScholarshipConfiguration {
  id: number
  config_name: string
  scholarship_type_name: string
}

interface EditScheduleDialogProps {
  schedule: RosterSchedule
  open: boolean
  onOpenChange: (open: boolean) => void
  onScheduleUpdated: () => void
}

export function EditScheduleDialog({
  schedule,
  open,
  onOpenChange,
  onScheduleUpdated,
}: EditScheduleDialogProps) {
  const [loading, setLoading] = useState(false)
  const [scholarshipConfigs, setScholarshipConfigs] = useState<ScholarshipConfiguration[]>([])
  const [formData, setFormData] = useState({
    schedule_name: "",
    description: "",
    scholarship_configuration_id: "",
    roster_cycle: "",
    cron_expression: "",
  })

  useEffect(() => {
    if (open && schedule) {
      setFormData({
        schedule_name: schedule.schedule_name,
        description: schedule.description || "",
        scholarship_configuration_id: schedule.scholarship_configuration_id.toString(),
        roster_cycle: schedule.roster_cycle,
        cron_expression: schedule.cron_expression || "",
      })
      fetchScholarshipConfigurations()
    }
  }, [open, schedule])

  const fetchScholarshipConfigurations = async () => {
    try {
      const response = await fetch("/api/v1/scholarship-configurations")
      const data = await response.json()
      setScholarshipConfigs(data.configurations || [])
    } catch (error) {
      console.error("獲取獎學金設定失敗:", error)
      toast({
        title: "錯誤",
        description: "無法載入獎學金設定",
        variant: "destructive",
      })
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.schedule_name.trim()) {
      toast({
        title: "錯誤",
        description: "請輸入排程名稱",
        variant: "destructive",
      })
      return
    }

    if (!formData.scholarship_configuration_id) {
      toast({
        title: "錯誤",
        description: "請選擇獎學金設定",
        variant: "destructive",
      })
      return
    }

    if (!formData.roster_cycle) {
      toast({
        title: "錯誤",
        description: "請選擇造冊週期",
        variant: "destructive",
      })
      return
    }

    try {
      setLoading(true)

      const submitData = {
        ...formData,
        scholarship_configuration_id: parseInt(formData.scholarship_configuration_id),
      }

      const response = await fetch(`/api/v1/roster-schedules/${schedule.id}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(submitData),
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.message || "更新排程失敗")
      }

      toast({
        title: "成功",
        description: "排程已更新",
      })

      onScheduleUpdated()
    } catch (error) {
      console.error("更新排程失敗:", error)
      toast({
        title: "錯誤",
        description: error instanceof Error ? error.message : "無法更新排程",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const getCronPresets = () => {
    return [
      { label: "每月1號 00:00", value: "0 0 1 * *" },
      { label: "每月15號 00:00", value: "0 0 15 * *" },
      { label: "每週一 09:00", value: "0 9 * * 1" },
      { label: "每天 02:00", value: "0 2 * * *" },
      { label: "每年1月1號 00:00", value: "0 0 1 1 *" },
      { label: "每年7月1號 00:00", value: "0 0 1 7 *" },
    ]
  }

  const handleCronPresetSelect = (cronExpression: string) => {
    handleInputChange("cron_expression", cronExpression)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Calendar className="w-5 h-5" />
            <span>編輯排程</span>
          </DialogTitle>
          <DialogDescription>
            修改排程設定，更新後將會重新註冊到排程器中。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="edit_schedule_name">排程名稱 *</Label>
              <Input
                id="edit_schedule_name"
                placeholder="例如：月度造冊排程"
                value={formData.schedule_name}
                onChange={(e) => handleInputChange("schedule_name", e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit_roster_cycle">造冊週期 *</Label>
              <Select
                value={formData.roster_cycle}
                onValueChange={(value) => handleInputChange("roster_cycle", value)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="選擇造冊週期" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monthly">月度</SelectItem>
                  <SelectItem value="half_yearly">半年度</SelectItem>
                  <SelectItem value="yearly">年度</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit_scholarship_configuration_id">獎學金設定 *</Label>
            <Select
              value={formData.scholarship_configuration_id}
              onValueChange={(value) => handleInputChange("scholarship_configuration_id", value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="選擇獎學金設定" />
              </SelectTrigger>
              <SelectContent>
                {scholarshipConfigs.map((config) => (
                  <SelectItem key={config.id} value={config.id.toString()}>
                    {config.config_name} ({config.scholarship_type_name})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit_description">說明</Label>
            <Textarea
              id="edit_description"
              placeholder="排程說明（選填）"
              value={formData.description}
              onChange={(e) => handleInputChange("description", e.target.value)}
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit_cron_expression">Cron 表達式</Label>
            <Input
              id="edit_cron_expression"
              placeholder="例如：0 0 1 * * (每月1號午夜執行)"
              value={formData.cron_expression}
              onChange={(e) => handleInputChange("cron_expression", e.target.value)}
            />
            <div className="text-sm text-gray-600">
              <p className="mb-2">常用設定：</p>
              <div className="grid grid-cols-2 gap-1">
                {getCronPresets().map((preset, index) => (
                  <button
                    key={index}
                    type="button"
                    className="text-left text-xs p-1 hover:bg-gray-100 rounded"
                    onClick={() => handleCronPresetSelect(preset.value)}
                  >
                    <span className="font-mono text-blue-600">{preset.value}</span>
                    <br />
                    <span className="text-gray-500">{preset.label}</span>
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs text-gray-500">
                格式：秒 分 時 日 月 星期（留空則使用預設週期排程）
              </p>
            </div>
          </div>

          <div className="bg-yellow-50 border border-yellow-200 rounded-md p-3">
            <div className="flex items-start space-x-2">
              <div className="w-5 h-5 text-yellow-600 mt-0.5">⚠️</div>
              <div className="text-sm">
                <p className="font-medium text-yellow-800">注意事項：</p>
                <ul className="mt-1 text-yellow-700 space-y-1">
                  <li>• 修改 Cron 表達式後，新的排程時間將立即生效</li>
                  <li>• 如果排程正在執行中，建議先暫停後再進行修改</li>
                  <li>• 造冊週期變更可能影響資料統計結果</li>
                </ul>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "更新中..." : "更新排程"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
