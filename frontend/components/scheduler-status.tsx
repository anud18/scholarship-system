"use client"
import { apiClient } from "@/lib/api"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { toast } from "sonner";
import { Play, Pause, Square, Clock, Activity, AlertTriangle, CheckCircle, XCircle, RefreshCw } from "lucide-react"
import { formatDateTime } from "@/lib/utils"

interface SchedulerInfo {
  scheduler_running: boolean
  scheduler_state: string
  job_count: number
  active_jobs: number
  pending_jobs: number
  executor_info: {
    class: string
    max_workers: number
    current_workers: number
  }
  jobstore_info: {
    class: string
    connected: boolean
  }
  next_run_time?: string
  uptime?: string
}

interface JobInfo {
  id: string
  name: string
  next_run_time?: string
  trigger: string
  executor: string
  misfire_grace_time?: number
  max_instances: number
  coalesce: boolean
  args: any[]
  kwargs: any
}

export function SchedulerStatus() {
  const [schedulerInfo, setSchedulerInfo] = useState<SchedulerInfo | null>(null)
  const [jobs, setJobs] = useState<JobInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)

  useEffect(() => {
    fetchSchedulerStatus()
    // 每30秒自動刷新
    const interval = setInterval(fetchSchedulerStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const fetchSchedulerStatus = async () => {
    try {
      setLoading(true)

      // Fetch scheduler status (includes jobs)
      const statusResponse = await apiClient.request("/roster-schedules/scheduler/status")
      const statusData = statusResponse.data || statusResponse

      setSchedulerInfo(statusData)
      setJobs(statusData.jobs || [])
    } catch (error) {
      console.error("獲取排程器狀態失敗:", error)
      toast.error("無法載入排程器狀態")
    } finally {
      setLoading(false)
    }
  }

  const handleSchedulerAction = async (action: 'start' | 'stop' | 'restart') => {
    try {
      setActionLoading(true)

      const response = await apiClient.request(`/roster-schedules/scheduler/${action}`, {
        method: "POST",
      })


      const actionLabels = {
        start: "啟動",
        stop: "停止",
        restart: "重啟"
      }

      toast.success(`排程器已${actionLabels[action]}`)

      // 稍等一下再刷新狀態
      setTimeout(fetchSchedulerStatus, 1000)
    } catch (error) {
      console.error(`排程器${action}操作失敗:`, error)
      toast.error(`無法${action}排程器`)
    } finally {
      setActionLoading(false)
    }
  }

  const getSchedulerStatusIcon = () => {
    if (!schedulerInfo) return <Clock className="h-4 w-4 text-gray-400" />

    if (schedulerInfo.scheduler_running) {
      return <CheckCircle className="h-4 w-4 text-green-600" />
    } else {
      return <XCircle className="h-4 w-4 text-red-600" />
    }
  }

  const getSchedulerStatusBadge = () => {
    if (!schedulerInfo) return <Badge variant="secondary">未知</Badge>

    if (schedulerInfo.scheduler_running) {
      return <Badge variant="default" className="bg-green-600">執行中</Badge>
    } else {
      return <Badge variant="destructive">已停止</Badge>
    }
  }

  const getTriggerLabel = (trigger: string) => {
    if (trigger.includes("cron")) return "Cron 排程"
    if (trigger.includes("interval")) return "間隔執行"
    if (trigger.includes("date")) return "單次執行"
    return trigger
  }

  return (
    <div className="space-y-6">
      {/* Scheduler Status Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">排程器狀態</CardTitle>
            {getSchedulerStatusIcon()}
          </CardHeader>
          <CardContent>
            <div className="flex items-center space-x-2">
              {getSchedulerStatusBadge()}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {schedulerInfo?.scheduler_state || "未知狀態"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">工作總數</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{schedulerInfo?.job_count || 0}</div>
            <p className="text-xs text-muted-foreground">已註冊的工作</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">活躍工作</CardTitle>
            <Play className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{schedulerInfo?.active_jobs || 0}</div>
            <p className="text-xs text-muted-foreground">正在執行中</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">等待工作</CardTitle>
            <Clock className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-orange-600">{schedulerInfo?.pending_jobs || 0}</div>
            <p className="text-xs text-muted-foreground">排隊等待中</p>
          </CardContent>
        </Card>
      </div>

      {/* Scheduler Controls */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <CardTitle>排程器控制</CardTitle>
            <Button
              variant="outline"
              onClick={fetchSchedulerStatus}
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              重新整理
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex space-x-2">
            <Button
              onClick={() => handleSchedulerAction('start')}
              disabled={actionLoading || schedulerInfo?.scheduler_running}
              className="bg-green-600 hover:bg-green-700"
            >
              <Play className="w-4 h-4 mr-2" />
              啟動排程器
            </Button>
            <Button
              onClick={() => handleSchedulerAction('stop')}
              disabled={actionLoading || !schedulerInfo?.scheduler_running}
              variant="destructive"
            >
              <Square className="w-4 h-4 mr-2" />
              停止排程器
            </Button>
            <Button
              onClick={() => handleSchedulerAction('restart')}
              disabled={actionLoading}
              variant="outline"
            >
              <RefreshCw className="w-4 h-4 mr-2" />
              重啟排程器
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Scheduler Details */}
      {schedulerInfo && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">執行器資訊</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">執行器類型:</span>
                <span className="text-sm font-medium">{schedulerInfo.executor_info?.class || "未知"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">最大工作者:</span>
                <span className="text-sm font-medium">{schedulerInfo.executor_info?.max_workers || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">當前工作者:</span>
                <span className="text-sm font-medium">{schedulerInfo.executor_info?.current_workers || 0}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">儲存器資訊</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">儲存器類型:</span>
                <span className="text-sm font-medium">{schedulerInfo.jobstore_info?.class || "未知"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-gray-600">連線狀態:</span>
                <Badge variant={schedulerInfo.jobstore_info?.connected ? "default" : "destructive"}>
                  {schedulerInfo.jobstore_info?.connected ? "已連線" : "未連線"}
                </Badge>
              </div>
              {schedulerInfo.next_run_time && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-600">下次執行:</span>
                  <span className="text-sm font-medium">{formatDateTime(schedulerInfo.next_run_time)}</span>
                </div>
              )}
              {schedulerInfo.uptime && (
                <div className="flex justify-between">
                  <span className="text-sm text-gray-600">運行時間:</span>
                  <span className="text-sm font-medium">{schedulerInfo.uptime}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Active Jobs Table */}
      <Card>
        <CardHeader>
          <CardTitle>活躍工作列表</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>工作ID</TableHead>
                  <TableHead>工作名稱</TableHead>
                  <TableHead>觸發器類型</TableHead>
                  <TableHead>下次執行時間</TableHead>
                  <TableHead>執行器</TableHead>
                  <TableHead>最大實例數</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8">
                      載入中...
                    </TableCell>
                  </TableRow>
                ) : jobs.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-gray-500">
                      沒有活躍的工作
                    </TableCell>
                  </TableRow>
                ) : (
                  jobs.map((job) => (
                    <TableRow key={job.id}>
                      <TableCell>
                        <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                          {job.id}
                        </code>
                      </TableCell>
                      <TableCell className="font-medium">{job.name}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {getTriggerLabel(job.trigger)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {job.next_run_time ? (
                          formatDateTime(job.next_run_time)
                        ) : (
                          <span className="text-gray-400">未排程</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary">{job.executor}</Badge>
                      </TableCell>
                      <TableCell>{job.max_instances}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
