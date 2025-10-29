"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Calendar, Clock, FileSpreadsheet, Settings, Play, Pause, Square, Download } from "lucide-react"
import { RosterScheduleList } from "./roster-schedule-list"
import { PaymentRosterList } from "./payment-roster-list"
import { SchedulerStatus } from "./scheduler-status"
import { CreateScheduleDialog } from "./create-schedule-dialog"
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
  const [activeTab, setActiveTab] = useState("schedules")

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

  const handleRefresh = () => {
    fetchDashboardStats()
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">造冊管理系統</h1>
          <p className="text-gray-600 mt-1">獎學金造冊排程與管理</p>
        </div>
        <div className="flex space-x-2">
          <Button variant="outline" onClick={handleRefresh}>
            <Clock className="w-4 h-4 mr-2" />
            重新整理
          </Button>
          <CreateScheduleDialog onScheduleCreated={handleRefresh} />
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總排程數</CardTitle>
            <Settings className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalSchedules}</div>
            <p className="text-xs text-muted-foreground">排程設定總數</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">啟用排程</CardTitle>
            <Play className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.activeSchedules}</div>
            <p className="text-xs text-muted-foreground">正在執行的排程</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總造冊數</CardTitle>
            <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.totalRosters}</div>
            <p className="text-xs text-muted-foreground">已產生造冊總數</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">待處理造冊</CardTitle>
            <Calendar className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">{stats.pendingRosters}</div>
            <p className="text-xs text-muted-foreground">尚未完成的造冊</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">排程器狀態</CardTitle>
            {stats.schedulerRunning ? (
              <Play className="h-4 w-4 text-green-600" />
            ) : (
              <Square className="h-4 w-4 text-red-600" />
            )}
          </CardHeader>
          <CardContent>
            <div className="flex items-center space-x-2">
              <Badge variant={stats.schedulerRunning ? "default" : "destructive"}>
                {stats.schedulerRunning ? "執行中" : "已停止"}
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              APScheduler 狀態
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="schedules" className="flex items-center space-x-2">
            <Settings className="w-4 h-4" />
            <span>排程管理</span>
          </TabsTrigger>
          <TabsTrigger value="rosters" className="flex items-center space-x-2">
            <FileSpreadsheet className="w-4 h-4" />
            <span>造冊管理</span>
          </TabsTrigger>
          <TabsTrigger value="scheduler" className="flex items-center space-x-2">
            <Clock className="w-4 h-4" />
            <span>排程器狀態</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="schedules" className="space-y-4">
          <RosterScheduleList onScheduleChange={handleRefresh} />
        </TabsContent>

        <TabsContent value="rosters" className="space-y-4">
          <PaymentRosterList onRosterChange={handleRefresh} />
        </TabsContent>

        <TabsContent value="scheduler" className="space-y-4">
          <SchedulerStatus />
        </TabsContent>
      </Tabs>
    </div>
  )
}
