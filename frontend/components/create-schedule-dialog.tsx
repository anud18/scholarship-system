"use client"
import { apiClient } from "@/lib/api"

import React, { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { toast } from "sonner";
import { Calendar, Plus } from "lucide-react"

interface ScholarshipConfiguration {
  id: number
  config_name: string
  scholarship_type_name: string
}

interface CreateScheduleDialogProps {
  onScheduleCreated: () => void
  preselectedConfigId?: number
  hideConfigSelector?: boolean
  customTrigger?: React.ReactNode
}

export function CreateScheduleDialog({
  onScheduleCreated,
  preselectedConfigId,
  hideConfigSelector = false,
  customTrigger
}: CreateScheduleDialogProps) {
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [scholarshipConfigs, setScholarshipConfigs] = useState<ScholarshipConfiguration[]>([])
  const [formData, setFormData] = useState({
    description: "",
    scholarship_configuration_id: "",
    roster_cycle: "",
    cron_expression: "",
  })

  useEffect(() => {
    if (open) {
      fetchScholarshipConfigurations()

      // Pre-select config if provided
      if (preselectedConfigId) {
        setFormData(prev => ({
          ...prev,
          scholarship_configuration_id: preselectedConfigId.toString()
        }))
      }
    }
  }, [open, preselectedConfigId])

  const fetchScholarshipConfigurations = async () => {
    try {
      const response = await apiClient.request("/scholarship-configurations/configurations")
      // apiClient already extracts response.data, so response.data is the actual array
      const configs = Array.isArray(response.data) ? response.data : (response.data?.data || [])
      setScholarshipConfigs(configs)
    } catch (error) {
      console.error("獲取獎學金設定失敗:", error)
      toast.error("無法載入獎學金設定")
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.scholarship_configuration_id) {
      toast.error("請選擇獎學金設定")
      return
    }

    if (!formData.roster_cycle) {
      toast.error("請選擇造冊週期")
      return
    }

    try {
      setLoading(true)

      const submitData = {
        ...formData,
        scholarship_configuration_id: parseInt(formData.scholarship_configuration_id),
      }

      await apiClient.request("/roster-schedules", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(submitData),
      })

      toast.success("排程已建立")

      // Reset form
      setFormData({
        description: "",
        scholarship_configuration_id: "",
        roster_cycle: "",
        cron_expression: "",
      })

      setOpen(false)
      onScheduleCreated()
    } catch (error) {
      console.error("建立排程失敗:", error)
      toast.error(error instanceof Error ? error.message : "無法建立排程")
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
    <Dialog open={open} onOpenChange={setOpen} modal={true}>
      <DialogTrigger asChild>
        {customTrigger || (
          <Button>
            <Plus className="w-4 h-4 mr-2" />
            建立排程
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle className="flex items-center space-x-2">
            <Calendar className="w-5 h-5" />
            <span>建立新排程</span>
          </DialogTitle>
          <DialogDescription>
            建立新的造冊排程，系統將會根據設定的時間自動產生造冊檔案。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="roster_cycle">造冊週期 *</Label>
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

          {!hideConfigSelector && (
            <div className="space-y-2">
              <Label htmlFor="scholarship_configuration_id">獎學金設定 *</Label>
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
          )}

          <div className="space-y-2">
            <Label htmlFor="description">說明</Label>
            <Textarea
              id="description"
              placeholder="排程說明（選填）"
              value={formData.description}
              onChange={(e) => handleInputChange("description", e.target.value)}
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="cron_expression">Cron 表達式</Label>
            <Input
              id="cron_expression"
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

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={loading}
            >
              取消
            </Button>
            <Button type="submit" disabled={loading}>
              {loading ? "建立中..." : "建立排程"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
