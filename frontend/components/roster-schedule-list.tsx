"use client"

import React, { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog"
import { toast } from "@/components/ui/use-toast"
import { Search, MoreHorizontal, Play, Pause, Square, Trash2, Edit, Calendar, FileText } from "lucide-react"
import { EditScheduleDialog } from "./edit-schedule-dialog"
import { formatDateTime, getStatusBadgeVariant } from "@/lib/utils"
import { apiClient } from "@/lib/api"

interface RosterSchedule {
  id: number
  schedule_name: string
  description?: string
  scholarship_configuration_id: number
  roster_cycle: string
  cron_expression?: string
  status: string
  last_run_at?: string
  next_run_at?: string
  last_run_result?: string
  total_runs?: number
  successful_runs?: number
  failed_runs?: number
  created_at: string
  scheduler_info?: {
    next_run_time?: string
    trigger?: string
    pending?: boolean
  }
}

interface RosterScheduleListProps {
  onScheduleChange: () => void
}

export function RosterScheduleList({ onScheduleChange }: RosterScheduleListProps) {
  const [schedules, setSchedules] = useState<RosterSchedule[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [pagination, setPagination] = useState({ skip: 0, limit: 20, total: 0 })
  const [selectedSchedule, setSelectedSchedule] = useState<RosterSchedule | null>(null)
  const [editDialogOpen, setEditDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [actionLoading, setActionLoading] = useState<{ [key: number]: boolean }>({})

  useEffect(() => {
    fetchSchedules()
  }, [search, statusFilter, pagination.skip, pagination.limit])

  const fetchSchedules = async () => {
    try {
      setLoading(true)
      const params: any = {
        skip: pagination.skip,
        limit: pagination.limit,
      }

      if (search) params.search = search
      if (statusFilter !== "all") params.status = statusFilter

      const response = await apiClient.request("/roster-schedules/", { params })
      const data = response.data || response

      if (data.items) {
        setSchedules(data.items)
        setPagination(prev => ({ ...prev, total: data.total }))
      }
    } catch (error) {
      console.error("獲取排程列表失敗:", error)
      toast({
        title: "錯誤",
        description: "無法載入排程列表",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }

  const handleStatusUpdate = async (scheduleId: number, newStatus: string) => {
    try {
      setActionLoading(prev => ({ ...prev, [scheduleId]: true }))

      await apiClient.request(`/roster-schedules/${scheduleId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: newStatus }),
      })

      toast({
        title: "成功",
        description: `排程狀態已更新為 ${getStatusLabel(newStatus)}`,
      })

      fetchSchedules()
      onScheduleChange()
    } catch (error) {
      console.error("狀態更新失敗:", error)
      toast({
        title: "錯誤",
        description: "無法更新排程狀態",
        variant: "destructive",
      })
    } finally {
      setActionLoading(prev => ({ ...prev, [scheduleId]: false }))
    }
  }

  const handleExecuteNow = async (scheduleId: number) => {
    try {
      setActionLoading(prev => ({ ...prev, [scheduleId]: true }))

      await apiClient.request(`/roster-schedules/${scheduleId}/execute`, {
        method: "POST",
      })

      toast({
        title: "成功",
        description: "排程已觸發執行",
      })

      fetchSchedules()
      onScheduleChange()
    } catch (error) {
      console.error("執行排程失敗:", error)
      toast({
        title: "錯誤",
        description: "無法執行排程",
        variant: "destructive",
      })
    } finally {
      setActionLoading(prev => ({ ...prev, [scheduleId]: false }))
    }
  }

  const handleDelete = async () => {
    if (!selectedSchedule) return

    try {
      await apiClient.request(`/roster-schedules/${selectedSchedule.id}`, {
        method: "DELETE",
      })

      toast({
        title: "成功",
        description: "排程已刪除",
      })

      fetchSchedules()
      onScheduleChange()
      setDeleteDialogOpen(false)
      setSelectedSchedule(null)
    } catch (error) {
      console.error("刪除排程失敗:", error)
      toast({
        title: "錯誤",
        description: "無法刪除排程",
        variant: "destructive",
      })
    }
  }

  const getStatusLabel = (status: string) => {
    const labels: { [key: string]: string } = {
      active: "啟用中",
      paused: "暫停",
      disabled: "停用",
      error: "錯誤"
    }
    return labels[status] || status
  }

  const getCycleLabel = (cycle: string) => {
    const labels: { [key: string]: string } = {
      monthly: "月度",
      half_yearly: "半年度",
      yearly: "年度"
    }
    return labels[cycle] || cycle
  }

  const handlePageChange = (newSkip: number) => {
    setPagination(prev => ({ ...prev, skip: newSkip }))
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-center">
          <CardTitle>排程管理</CardTitle>
          <div className="flex space-x-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
              <Input
                placeholder="搜尋排程名稱或說明..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10 w-64"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-32">
                <SelectValue placeholder="狀態篩選" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部狀態</SelectItem>
                <SelectItem value="active">啟用中</SelectItem>
                <SelectItem value="paused">暫停</SelectItem>
                <SelectItem value="disabled">停用</SelectItem>
                <SelectItem value="error">錯誤</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>排程名稱</TableHead>
                <TableHead>造冊週期</TableHead>
                <TableHead>Cron 表達式</TableHead>
                <TableHead>狀態</TableHead>
                <TableHead>上次執行</TableHead>
                <TableHead>下次執行</TableHead>
                <TableHead>執行統計</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8">
                    載入中...
                  </TableCell>
                </TableRow>
              ) : schedules.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-gray-500">
                    沒有找到排程
                  </TableCell>
                </TableRow>
              ) : (
                schedules.map((schedule) => (
                  <TableRow key={schedule.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{schedule.schedule_name}</div>
                        {schedule.description && (
                          <div className="text-sm text-gray-500 mt-1">
                            {schedule.description}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {getCycleLabel(schedule.roster_cycle)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <code className="text-sm bg-gray-100 px-2 py-1 rounded">
                        {schedule.cron_expression || "無"}
                      </code>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStatusBadgeVariant(schedule.status)}>
                        {getStatusLabel(schedule.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        {schedule.last_run_at ? (
                          <>
                            <div>{formatDateTime(schedule.last_run_at)}</div>
                            {schedule.last_run_result && (
                              <Badge
                                variant={schedule.last_run_result === "success" ? "default" : "destructive"}
                                className="mt-1 text-xs"
                              >
                                {schedule.last_run_result === "success" ? "成功" : "失敗"}
                              </Badge>
                            )}
                          </>
                        ) : (
                          <span className="text-gray-400">尚未執行</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        {schedule.scheduler_info?.next_run_time ? (
                          formatDateTime(schedule.scheduler_info.next_run_time)
                        ) : (
                          <span className="text-gray-400">未排程</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm space-y-1">
                        <div>總計: {schedule.total_runs || 0}</div>
                        <div className="flex space-x-2">
                          <span className="text-green-600">
                            成功: {schedule.successful_runs || 0}
                          </span>
                          <span className="text-red-600">
                            失敗: {schedule.failed_runs || 0}
                          </span>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            className="h-8 w-8 p-0"
                            disabled={actionLoading[schedule.id]}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => {
                              setSelectedSchedule(schedule)
                              setEditDialogOpen(true)
                            }}
                          >
                            <Edit className="mr-2 h-4 w-4" />
                            編輯排程
                          </DropdownMenuItem>

                          <DropdownMenuItem
                            onClick={() => handleExecuteNow(schedule.id)}
                            disabled={schedule.status !== "active"}
                          >
                            <Play className="mr-2 h-4 w-4" />
                            立即執行
                          </DropdownMenuItem>

                          <DropdownMenuSeparator />

                          {schedule.status === "active" && (
                            <DropdownMenuItem
                              onClick={() => handleStatusUpdate(schedule.id, "paused")}
                            >
                              <Pause className="mr-2 h-4 w-4" />
                              暫停排程
                            </DropdownMenuItem>
                          )}

                          {schedule.status === "paused" && (
                            <DropdownMenuItem
                              onClick={() => handleStatusUpdate(schedule.id, "active")}
                            >
                              <Play className="mr-2 h-4 w-4" />
                              恢復排程
                            </DropdownMenuItem>
                          )}

                          {schedule.status !== "disabled" && (
                            <DropdownMenuItem
                              onClick={() => handleStatusUpdate(schedule.id, "disabled")}
                            >
                              <Square className="mr-2 h-4 w-4" />
                              停用排程
                            </DropdownMenuItem>
                          )}

                          <DropdownMenuSeparator />

                          <DropdownMenuItem
                            className="text-red-600"
                            onClick={() => {
                              setSelectedSchedule(schedule)
                              setDeleteDialogOpen(true)
                            }}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            刪除排程
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        {pagination.total > pagination.limit && (
          <div className="flex items-center justify-between space-x-2 py-4">
            <div className="text-sm text-gray-500">
              顯示 {pagination.skip + 1} 至 {Math.min(pagination.skip + pagination.limit, pagination.total)} 筆，
              共 {pagination.total} 筆
            </div>
            <div className="flex space-x-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handlePageChange(Math.max(0, pagination.skip - pagination.limit))}
                disabled={pagination.skip === 0}
              >
                上一頁
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handlePageChange(pagination.skip + pagination.limit)}
                disabled={pagination.skip + pagination.limit >= pagination.total}
              >
                下一頁
              </Button>
            </div>
          </div>
        )}
      </CardContent>

      {/* Edit Dialog */}
      {selectedSchedule && (
        <EditScheduleDialog
          schedule={selectedSchedule}
          open={editDialogOpen}
          onOpenChange={setEditDialogOpen}
          onScheduleUpdated={() => {
            fetchSchedules()
            onScheduleChange()
            setEditDialogOpen(false)
            setSelectedSchedule(null)
          }}
        />
      )}

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確認刪除</AlertDialogTitle>
            <AlertDialogDescription>
              確定要刪除排程「{selectedSchedule?.schedule_name}」嗎？
              此操作無法復原，且會從排程器中移除該排程。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-red-600 hover:bg-red-700">
              確認刪除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
