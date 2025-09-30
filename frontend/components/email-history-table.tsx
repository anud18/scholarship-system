"use client"

import { useState, useEffect } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { RefreshCw, Mail, Eye } from "lucide-react"
import apiClient from "@/lib/api"

interface EmailHistoryTableProps {
  className?: string
}

interface EmailHistoryItem {
  id: number
  recipient_email: string
  cc_emails?: string
  bcc_emails?: string
  subject: string
  body: string
  sent_at: string
  email_category?: string
  status: string
  email_size_bytes?: number
  application_app_id?: string
  scholarship_type_name?: string
  sent_by_username?: string
  template_description?: string
}

interface EmailHistoryFilters {
  email_category: string
  status: string
  scholarship_type_id: string
  recipient_email: string
  date_from: string
  date_to: string
}

export function EmailHistoryTable({ className }: EmailHistoryTableProps) {
  const [emailHistory, setEmailHistory] = useState<EmailHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedEmail, setSelectedEmail] = useState<EmailHistoryItem | null>(null)
  const [pagination, setPagination] = useState({
    skip: 0,
    limit: 50,
    total: 0
  })
  const [filters, setFilters] = useState<EmailHistoryFilters>({
    email_category: 'all',
    status: 'all',
    scholarship_type_id: 'all',
    recipient_email: '',
    date_from: '',
    date_to: ''
  })

  const loadEmailHistory = async () => {
    setLoading(true)
    try {
      // Convert date filters to ISO datetime format
      const processedFilters = { ...filters }
      if (processedFilters.date_from) {
        processedFilters.date_from = `${processedFilters.date_from}T00:00:00Z`
      }
      if (processedFilters.date_to) {
        processedFilters.date_to = `${processedFilters.date_to}T23:59:59Z`
      }

      const params = {
        skip: pagination.skip,
        limit: pagination.limit,
        ...Object.fromEntries(Object.entries(processedFilters).filter(([_, v]) => v !== '' && v !== 'all'))
      }

      const response = await apiClient.emailManagement.getEmailHistory(params)
      if (response.success && response.data) {
        const { items, total } = response.data
        setEmailHistory(items)
        setPagination(prev => ({
          ...prev,
          total
        }))
      }
    } catch (error) {
      console.error("Failed to load email history:", error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadEmailHistory()
  }, [pagination.skip, filters])

  const getEmailCategoryLabel = (category?: string) => {
    const categoryLabels: Record<string, string> = {
      'APPLICATION_WHITELIST': '申請通知－白名單',
      'APPLICATION_STUDENT': '申請通知－申請者',
      'RECOMMENDATION_PROFESSOR': '推薦通知－指導教授',
      'REVIEW_COLLEGE': '審核通知－學院',
      'SUPPLEMENT_STUDENT': '補件通知－申請者',
      'RESULT_PROFESSOR': '結果通知－指導教授',
      'RESULT_COLLEGE': '結果通知－學院',
      'RESULT_STUDENT': '結果通知－申請者',
      'ROSTER_STUDENT': '造冊通知－申請者',
      'SYSTEM': '系統通知',
      'OTHER': '其他'
    }
    return categoryLabels[category || ''] || '未分類'
  }

  const getStatusLabel = (status: string) => {
    const statusLabels: Record<string, string> = {
      'SENT': '已發送',
      'FAILED': '發送失敗',
      'BOUNCED': '退信',
      'PENDING': '待發送'
    }
    return statusLabels[status] || status
  }

  const getStatusVariant = (status: string): "default" | "secondary" | "destructive" | "outline" => {
    switch (status) {
      case 'SENT': return 'default'
      case 'FAILED': return 'destructive'
      case 'BOUNCED': return 'secondary'
      default: return 'outline'
    }
  }

  const getCategoryVariant = (category?: string): "default" | "secondary" | "destructive" | "outline" => {
    if (!category) return 'default'
    if (category.includes('APPLICATION')) return 'default'
    if (category.includes('RECOMMENDATION')) return 'secondary'
    if (category.includes('REVIEW')) return 'outline'
    if (category.includes('RESULT')) return 'destructive'
    return 'default'
  }

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-nycu-navy-800">郵件歷史記錄</h3>
        <Button
          onClick={loadEmailHistory}
          variant="outline"
          size="sm"
          disabled={loading}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          重新載入
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4">
            <div>
              <Label className="text-sm font-medium">郵件類別</Label>
              <Select
                value={filters.email_category}
                onValueChange={(value) =>
                  setFilters(prev => ({ ...prev, email_category: value }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="APPLICATION_WHITELIST">申請通知－白名單</SelectItem>
                  <SelectItem value="APPLICATION_STUDENT">申請通知－申請者</SelectItem>
                  <SelectItem value="RECOMMENDATION_PROFESSOR">推薦通知－指導教授</SelectItem>
                  <SelectItem value="REVIEW_COLLEGE">審核通知－學院</SelectItem>
                  <SelectItem value="SUPPLEMENT_STUDENT">補件通知－申請者</SelectItem>
                  <SelectItem value="RESULT_PROFESSOR">結果通知－指導教授</SelectItem>
                  <SelectItem value="RESULT_COLLEGE">結果通知－學院</SelectItem>
                  <SelectItem value="RESULT_STUDENT">結果通知－申請者</SelectItem>
                  <SelectItem value="ROSTER_STUDENT">造冊通知－申請者</SelectItem>
                  <SelectItem value="SYSTEM">系統通知</SelectItem>
                  <SelectItem value="OTHER">其他</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm font-medium">狀態</Label>
              <Select
                value={filters.status}
                onValueChange={(value) =>
                  setFilters(prev => ({ ...prev, status: value }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="SENT">已發送</SelectItem>
                  <SelectItem value="FAILED">發送失敗</SelectItem>
                  <SelectItem value="BOUNCED">退信</SelectItem>
                  <SelectItem value="PENDING">待發送</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm font-medium">收件者</Label>
              <Input
                placeholder="搜尋收件者信箱"
                value={filters.recipient_email}
                onChange={(e) =>
                  setFilters(prev => ({ ...prev, recipient_email: e.target.value }))
                }
                className="h-8"
              />
            </div>
            <div>
              <Label className="text-sm font-medium">開始日期</Label>
              <Input
                type="date"
                value={filters.date_from}
                onChange={(e) =>
                  setFilters(prev => ({ ...prev, date_from: e.target.value }))
                }
                className="h-8"
              />
            </div>
            <div>
              <Label className="text-sm font-medium">結束日期</Label>
              <Input
                type="date"
                value={filters.date_to}
                onChange={(e) =>
                  setFilters(prev => ({ ...prev, date_to: e.target.value }))
                }
                className="h-8"
              />
            </div>
            <div className="flex items-end">
              <Button
                onClick={() => setFilters({
                  email_category: 'all',
                  status: 'all',
                  scholarship_type_id: 'all',
                  recipient_email: '',
                  date_from: '',
                  date_to: ''
                })}
                variant="outline"
                size="sm"
                className="h-8"
              >
                清除篩選
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Email History Table */}
      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                <span className="text-nycu-navy-600">載入中...</span>
              </div>
            </div>
          ) : emailHistory.length > 0 ? (
            <div className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>發送時間</TableHead>
                    <TableHead>收件者</TableHead>
                    <TableHead>主旨</TableHead>
                    <TableHead>類別</TableHead>
                    <TableHead>狀態</TableHead>
                    <TableHead>大小</TableHead>
                    <TableHead>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {emailHistory.map((email) => (
                    <TableRow key={email.id}>
                      <TableCell>
                        {new Date(email.sent_at).toLocaleString('zh-TW')}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {email.recipient_email}
                      </TableCell>
                      <TableCell className="max-w-[300px] truncate">
                        {email.subject}
                      </TableCell>
                      <TableCell>
                        <Badge variant={getCategoryVariant(email.email_category)}>
                          {getEmailCategoryLabel(email.email_category)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant={getStatusVariant(email.status)}>
                          {getStatusLabel(email.status)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {email.email_size_bytes ?
                          `${(email.email_size_bytes / 1024).toFixed(1)} KB` :
                          '-'
                        }
                      </TableCell>
                      <TableCell>
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setSelectedEmail(email)}
                            >
                              <Eye className="h-4 w-4 mr-1" />
                              查看內容
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
                            <DialogHeader>
                              <DialogTitle>郵件內容</DialogTitle>
                              <DialogDescription>
                                查看已發送郵件的詳細內容
                              </DialogDescription>
                            </DialogHeader>
                            {selectedEmail && (
                              <div className="space-y-6">
                                <div className="grid grid-cols-2 gap-6">
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">收件者</Label>
                                    <p className="text-sm text-gray-900">{selectedEmail.recipient_email}</p>
                                  </div>
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">發送時間</Label>
                                    <p className="text-sm text-gray-900">{new Date(selectedEmail.sent_at).toLocaleString('zh-TW')}</p>
                                  </div>
                                  {selectedEmail.cc_emails && (
                                    <div className="space-y-2">
                                      <Label className="text-sm font-medium text-gray-700">副本收件者 (CC)</Label>
                                      <p className="text-sm text-gray-900">{selectedEmail.cc_emails}</p>
                                    </div>
                                  )}
                                  {selectedEmail.bcc_emails && (
                                    <div className="space-y-2">
                                      <Label className="text-sm font-medium text-gray-700">密件副本 (BCC)</Label>
                                      <p className="text-sm text-gray-900">{selectedEmail.bcc_emails}</p>
                                    </div>
                                  )}
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">郵件類別</Label>
                                    <div>
                                      <Badge variant={getCategoryVariant(selectedEmail.email_category)}>
                                        {getEmailCategoryLabel(selectedEmail.email_category)}
                                      </Badge>
                                    </div>
                                  </div>
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">狀態</Label>
                                    <div>
                                      <Badge variant={getStatusVariant(selectedEmail.status)}>
                                        {getStatusLabel(selectedEmail.status)}
                                      </Badge>
                                    </div>
                                  </div>
                                </div>
                                <div className="space-y-3">
                                  <Label className="text-sm font-medium text-gray-700">主旨</Label>
                                  <p className="text-sm font-medium bg-gray-50 p-3 rounded-md border">{selectedEmail.subject}</p>
                                </div>
                                <div className="space-y-3">
                                  <Label className="text-sm font-medium text-gray-700">郵件內容</Label>
                                  <div className="bg-gray-50 p-4 rounded-md border max-h-96 overflow-y-auto">
                                    <pre className="whitespace-pre-wrap text-sm leading-relaxed text-gray-900">{selectedEmail.body}</pre>
                                  </div>
                                </div>
                              </div>
                            )}
                          </DialogContent>
                        </Dialog>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-500">
                  顯示 {pagination.skip + 1} - {Math.min(pagination.skip + pagination.limit, pagination.total)}
                  共 {pagination.total} 筆
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.skip === 0}
                    onClick={() => setPagination(prev => ({
                      ...prev,
                      skip: Math.max(0, prev.skip - prev.limit)
                    }))}
                  >
                    上一頁
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.skip + pagination.limit >= pagination.total}
                    onClick={() => setPagination(prev => ({
                      ...prev,
                      skip: prev.skip + prev.limit
                    }))}
                  >
                    下一頁
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              <Mail className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">尚無郵件歷史記錄</p>
              <p className="text-sm mt-2">系統發送的郵件會顯示在這裡</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
