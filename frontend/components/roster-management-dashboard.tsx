"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { FileSpreadsheet, Settings, Play, Clock } from "lucide-react"
import { RosterScheduleList } from "./roster-schedule-list"
import { SchedulerStatus } from "./scheduler-status"
import { CompactConfigSelector } from "./roster/CompactConfigSelector"
import { CreateSchedulePrompt } from "./roster/CreateSchedulePrompt"
import { ConfigInfoCard } from "./roster/ConfigInfoCard"
import { MatrixQuotaDisplay } from "./roster/MatrixQuotaDisplay"
import { StudentRosterPreview } from "./roster/StudentRosterPreview"
import { RosterListTable } from "./roster/RosterListTable"
import { ScheduleSettingDialog } from "./roster/ScheduleSettingDialog"
import { apiClient } from "@/lib/api"

interface DashboardStats {
  totalSchedules: number
  activeSchedules: number
  totalRosters: number
  pendingRosters: number
  schedulerRunning: boolean
}

export function RosterManagementDashboard() {
  const [stats, setStats] = useState<DashboardStats>({
    totalSchedules: 0,
    activeSchedules: 0,
    totalRosters: 0,
    pendingRosters: 0,
    schedulerRunning: false
  })
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState("roster-management")
  const [selectedConfig, setSelectedConfig] = useState<any>(null)
  const [selectedSchedule, setSelectedSchedule] = useState<any>(null)
  const [cycleData, setCycleData] = useState<any>(null)
  const [loadingSchedule, setLoadingSchedule] = useState(false)
  const [loadingCycle, setLoadingCycle] = useState(false)
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false)

  useEffect(() => {
    fetchDashboardStats()
  }, [])

  const fetchDashboardStats = async () => {
    try {
      setLoading(true)

      // Fetch schedule stats
      const scheduleResponse = await apiClient.request("/roster-schedules")
      const scheduleData = scheduleResponse.data || scheduleResponse

      // Fetch roster stats
      const rosterResponse = await apiClient.request("/payment-rosters")
      const rosterData = rosterResponse.data || rosterResponse

      // Fetch scheduler status
      const schedulerResponse = await apiClient.request("/roster-schedules/scheduler/status")
      const schedulerData = schedulerResponse.data || schedulerResponse

      setStats({
        totalSchedules: scheduleData.total || 0,
        activeSchedules: scheduleData.items?.filter((s: any) => s.status === "active").length || 0,
        totalRosters: rosterData.total || 0,
        pendingRosters: rosterData.items?.filter((r: any) => r.status === "pending").length || 0,
        schedulerRunning: schedulerData.scheduler_running || false
      })
    } catch (error) {
      console.error("獲取儀表板統計失敗:", error)
    } finally {
      setLoading(false)
    }
  }

  const handleConfigSelect = async (configId: number, config: any) => {
    setSelectedConfig(config)
    setLoadingSchedule(true)
    setLoadingCycle(true)

    try {
      // Load schedule for this config
      const scheduleResponse = await apiClient.request(`/roster-schedules/by-config/${configId}`)

      if (scheduleResponse.success && scheduleResponse.data) {
        setSelectedSchedule(scheduleResponse.data)
      } else {
        setSelectedSchedule(null)
      }
    } catch (error) {
      console.error("Failed to load schedule:", error)
      setSelectedSchedule(null)
    } finally {
      setLoadingSchedule(false)
    }

    // Load cycle status
    try {
      const cycleResponse = await apiClient.request("/payment-rosters/cycle-status", {
        method: "GET",
        params: { config_id: configId },
      })

      if (cycleResponse.success && cycleResponse.data) {
        setCycleData(cycleResponse.data)
      } else {
        setCycleData(null)
      }
    } catch (error) {
      console.error("Failed to load cycle status:", error)
      setCycleData(null)
    } finally {
      setLoadingCycle(false)
    }
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">造冊管理系統</h1>
        <p className="text-gray-600 mt-1">獎學金造冊管理</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">總排程數</p>
                <p className="text-2xl font-bold">{stats.totalSchedules}</p>
              </div>
              <Settings className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">啟用排程</p>
                <p className="text-2xl font-bold text-green-600">{stats.activeSchedules}</p>
              </div>
              <Play className="h-8 w-8 text-green-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">總造冊數</p>
                <p className="text-2xl font-bold">{stats.totalRosters}</p>
              </div>
              <FileSpreadsheet className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">待處理造冊</p>
                <p className="text-2xl font-bold text-orange-600">{stats.pendingRosters}</p>
              </div>
              <Clock className="h-8 w-8 text-orange-600" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">排程器狀態</p>
                <Badge variant={stats.schedulerRunning ? "default" : "destructive"}>
                  {stats.schedulerRunning ? "執行中" : "已停止"}
                </Badge>
              </div>
              {stats.schedulerRunning ? (
                <Play className="h-8 w-8 text-green-600" />
              ) : (
                <Clock className="h-8 w-8 text-red-600" />
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="roster-management" className="flex items-center space-x-2">
            <FileSpreadsheet className="w-4 h-4" />
            <span>造冊管理</span>
          </TabsTrigger>
          <TabsTrigger value="schedules" className="flex items-center space-x-2">
            <Settings className="w-4 h-4" />
            <span>排程管理</span>
          </TabsTrigger>
          <TabsTrigger value="scheduler" className="flex items-center space-x-2">
            <Clock className="w-4 h-4" />
            <span>排程器狀態</span>
          </TabsTrigger>
        </TabsList>

        {/* 造冊管理 Tab */}
        <TabsContent value="roster-management" className="space-y-4">
          {/* Config Selector + Schedule Setting in top right */}
          <div className="flex justify-end items-center gap-4">
            <CompactConfigSelector onConfigSelect={handleConfigSelect} />

            {selectedSchedule && (
              <Button
                variant="outline"
                onClick={() => setScheduleDialogOpen(true)}
              >
                <Settings className="mr-2 h-4 w-4" />
                排程設定
              </Button>
            )}
          </div>

          {/* Content based on config selection */}
          {loadingSchedule ? (
            <Card>
              <CardContent className="p-12 text-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto"></div>
                <p className="mt-4 text-muted-foreground">載入中...</p>
              </CardContent>
            </Card>
          ) : selectedConfig ? (
            <>
              {!selectedSchedule ? (
                <CreateSchedulePrompt
                  configName={selectedConfig.config_name}
                  configId={selectedConfig.id}
                  onScheduleCreated={() => handleConfigSelect(selectedConfig.id, selectedConfig)}
                />
              ) : (
                <div className="space-y-4">
                  {/* Config Info Card */}
                  <ConfigInfoCard config={selectedConfig} schedule={selectedSchedule} />

                  {/* Matrix Quota Display (if applicable) */}
                  <MatrixQuotaDisplay
                    quotas={selectedConfig.quotas}
                    hasMatrix={selectedConfig.has_college_quota}
                  />

                  {/* Student Roster Preview */}
                  <StudentRosterPreview
                    configId={selectedConfig.id}
                    rankingId={selectedSchedule.ranking_id}
                  />

                  {/* Roster List Table */}
                  {cycleData && cycleData.periods && (
                    <RosterListTable
                      periods={cycleData.periods}
                      configId={selectedConfig.id}
                    />
                  )}
                </div>
              )}
            </>
          ) : (
            <Card>
              <CardContent className="p-12 text-center">
                <p className="text-muted-foreground">
                  請從右上角選擇獎學金配置以查看造冊資訊
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="schedules" className="space-y-4">
          <RosterScheduleList onScheduleChange={fetchDashboardStats} />
        </TabsContent>

        <TabsContent value="scheduler" className="space-y-4">
          <SchedulerStatus />
        </TabsContent>
      </Tabs>

      {/* Schedule Setting Dialog */}
      {selectedSchedule && (
        <ScheduleSettingDialog
          open={scheduleDialogOpen}
          onOpenChange={setScheduleDialogOpen}
          schedule={selectedSchedule}
          onUpdated={() => handleConfigSelect(selectedConfig.id, selectedConfig)}
        />
      )}
    </div>
  )
}
