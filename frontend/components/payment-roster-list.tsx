"use client"
import { apiClient } from "@/lib/api"

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
import { Search, MoreHorizontal, Download, Eye, RefreshCw, Trash2, FileSpreadsheet } from "lucide-react"
import { formatDateTime, getStatusBadgeVariant } from "@/lib/utils"

interface PaymentRoster {
  id: number
  roster_name: string
  scholarship_configuration_id: number
  scholarship_config_name?: string
  roster_period: string
  status: string
  total_amount: number
  student_count: number
  created_at: string
  file_path?: string
  file_size?: number
  generated_by?: string
  metadata?: {
    export_format?: string
    template_used?: string
    total_records?: number
  }
}

interface PaymentRosterListProps {
  onRosterChange: () => void
}

export function PaymentRosterList({ onRosterChange }: PaymentRosterListProps) {
  const [rosters, setRosters] = useState<PaymentRoster[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [pagination, setPagination] = useState({ skip: 0, limit: 20, total: 0 })
  const [selectedRoster, setSelectedRoster] = useState<PaymentRoster | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [actionLoading, setActionLoading] = useState<{ [key: number]: boolean }>({})

  useEffect(() => {
    fetchRosters()
  }, [search, statusFilter, pagination.skip, pagination.limit])

  const fetchRosters = async () => {
    try {
      setLoading(true)
      const params = new URLSearchParams({
        skip: pagination.skip.toString(),
        limit: pagination.limit.toString(),
      })

      if (search) params.set("search", search)
      if (statusFilter !== "all") params.set("status", statusFilter)

      const response = await apiClient.request("/payment-rosters", { params: Object.fromEntries(params) })
      const data = response.data || response

      if (data.items) {
        setRosters(data.items)
        setPagination(prev => ({ ...prev, total: data.total }))
      }
    } catch (error) {
      console.error("獲取造冊列表失敗:", error)
      toast({
        title: "錯誤",
        description: "無法載入造冊列表",
        variant: "destructive",
      })
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = async (rosterId: number) => {
    try {
      setActionLoading(prev => ({ ...prev, [rosterId]: true }))

      const response = await apiClient.request(`/payment-rosters/${rosterId}/download`)
      const data = response.data || response

      // For file downloads, the API should return download_url
      if (data.download_url) {
        window.open(data.download_url, '_blank')
      } else {
        throw new Error("無法取得下載連結")
      }

      toast({
        title: "成功",
        description: "造冊檔案已下載",
      })
    } catch (error) {
      console.error("下載造冊失敗:", error)
      toast({
        title: "錯誤",
        description: "無法下載造冊檔案",
        variant: "destructive",
      })
    } finally {
      setActionLoading(prev => ({ ...prev, [rosterId]: false }))
    }
  }

  const handleRegenerateRoster = async (rosterId: number) => {
    try {
      setActionLoading(prev => ({ ...prev, [rosterId]: true }))

      await apiClient.request(`/payment-rosters/${rosterId}/regenerate`, {
        method: "POST",
      })

      toast({
        title: "成功",
        description: "造冊已重新產生",
      })

      fetchRosters()
      onRosterChange()
    } catch (error) {
      console.error("重新產生造冊失敗:", error)
      toast({
        title: "錯誤",
        description: "無法重新產生造冊",
        variant: "destructive",
      })
    } finally {
      setActionLoading(prev => ({ ...prev, [rosterId]: false }))
    }
  }

  const handleDelete = async () => {
    if (!selectedRoster) return

    try {
      await apiClient.request(`/payment-rosters/${selectedRoster.id}`, {
        method: "DELETE",
      })

      toast({
        title: "成功",
        description: "造冊已刪除",
      })

      fetchRosters()
      onRosterChange()
      setDeleteDialogOpen(false)
      setSelectedRoster(null)
    } catch (error) {
      console.error("刪除造冊失敗:", error)
      toast({
        title: "錯誤",
        description: "無法刪除造冊",
        variant: "destructive",
      })
    }
  }

  const getStatusLabel = (status: string) => {
    const labels: { [key: string]: string } = {
      pending: "處理中",
      completed: "已完成",
      failed: "失敗",
      cancelled: "已取消"
    }
    return labels[status] || status
  }

  const getPeriodLabel = (period: string) => {
    const labels: { [key: string]: string } = {
      monthly: "月度",
      half_yearly: "半年度",
      yearly: "年度"
    }
    return labels[period] || period
  }

  const formatFileSize = (size?: number) => {
    if (!size) return "未知"
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatAmount = (amount: number) => {
    return new Intl.NumberFormat('zh-TW', {
      style: 'currency',
      currency: 'TWD',
    }).format(amount)
  }

  const handlePageChange = (newSkip: number) => {
    setPagination(prev => ({ ...prev, skip: newSkip }))
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-between items-center">
          <CardTitle>造冊管理</CardTitle>
          <div className="flex space-x-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
              <Input
                placeholder="搜尋造冊名稱..."
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
                <SelectItem value="pending">處理中</SelectItem>
                <SelectItem value="completed">已完成</SelectItem>
                <SelectItem value="failed">失敗</SelectItem>
                <SelectItem value="cancelled">已取消</SelectItem>
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
                <TableHead>造冊名稱</TableHead>
                <TableHead>造冊週期</TableHead>
                <TableHead>狀態</TableHead>
                <TableHead>金額統計</TableHead>
                <TableHead>學生人數</TableHead>
                <TableHead>檔案資訊</TableHead>
                <TableHead>建立時間</TableHead>
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
              ) : rosters.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="text-center py-8 text-gray-500">
                    沒有找到造冊記錄
                  </TableCell>
                </TableRow>
              ) : (
                rosters.map((roster) => (
                  <TableRow key={roster.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{roster.roster_name}</div>
                        {roster.scholarship_config_name && (
                          <div className="text-sm text-gray-500 mt-1">
                            {roster.scholarship_config_name}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {getPeriodLabel(roster.roster_period)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={getStatusBadgeVariant(roster.status)}>
                        {getStatusLabel(roster.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        <div className="font-medium text-green-600">
                          {formatAmount(roster.total_amount)}
                        </div>
                        {roster.metadata?.total_records && (
                          <div className="text-gray-500">
                            {roster.metadata.total_records} 筆記錄
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">
                        {roster.student_count} 人
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm space-y-1">
                        {roster.file_path ? (
                          <>
                            <div className="flex items-center space-x-1">
                              <FileSpreadsheet className="w-3 h-3 text-green-600" />
                              <span className="text-green-600">已產生</span>
                            </div>
                            <div className="text-gray-500">
                              {formatFileSize(roster.file_size)}
                            </div>
                          </>
                        ) : (
                          <span className="text-gray-400">尚未產生</span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm">
                        <div>{formatDateTime(roster.created_at)}</div>
                        {roster.generated_by && (
                          <div className="text-gray-500 mt-1">
                            by {roster.generated_by}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            className="h-8 w-8 p-0"
                            disabled={actionLoading[roster.id]}
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => {
                              // Get token from localStorage, following CLAUDE.md pattern
                              const token = localStorage.getItem("auth_token") ||
                                            localStorage.getItem("token") || "";
                              window.open(`/api/v1/preview?type=roster&rosterId=${roster.id}&token=${token}`, '_blank')
                            }}
                          >
                            <Eye className="mr-2 h-4 w-4" />
                            預覽造冊
                          </DropdownMenuItem>

                          {roster.file_path && (
                            <DropdownMenuItem
                              onClick={() => handleDownload(roster.id)}
                              disabled={actionLoading[roster.id]}
                            >
                              <Download className="mr-2 h-4 w-4" />
                              下載檔案
                            </DropdownMenuItem>
                          )}

                          <DropdownMenuItem
                            onClick={() => handleRegenerateRoster(roster.id)}
                            disabled={actionLoading[roster.id]}
                          >
                            <RefreshCw className="mr-2 h-4 w-4" />
                            重新產生
                          </DropdownMenuItem>

                          <DropdownMenuSeparator />

                          <DropdownMenuItem
                            className="text-red-600"
                            onClick={() => {
                              setSelectedRoster(roster)
                              setDeleteDialogOpen(true)
                            }}
                          >
                            <Trash2 className="mr-2 h-4 w-4" />
                            刪除造冊
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

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確認刪除</AlertDialogTitle>
            <AlertDialogDescription>
              確定要刪除造冊「{selectedRoster?.roster_name}」嗎？
              此操作無法復原，包括相關的檔案也會被刪除。
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
