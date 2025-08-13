"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Search, Eye, CheckCircle, AlertCircle, Clock, X } from "lucide-react"
import apiClient, { Application, ApiResponse } from "@/lib/api"
import { User } from "@/types/user"

interface ProfessorReviewComponentProps {
  user: User
}

interface SubTypeOption {
  value: string
  label: string
  label_en: string
  is_default: boolean
}

interface ReviewItem {
  sub_type_code: string
  is_recommended: boolean
  comments?: string
}

interface ReviewData {
  recommendation?: string
  items: ReviewItem[]
}

export function ProfessorReviewComponent({ user }: ProfessorReviewComponentProps) {
  const [applications, setApplications] = useState<Application[]>([])
  const [filteredApplications, setFilteredApplications] = useState<Application[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState<string>("pending")
  
  // Review form states
  const [subTypes, setSubTypes] = useState<SubTypeOption[]>([])
  const [reviewData, setReviewData] = useState<ReviewData>({
    recommendation: "",
    items: []
  })
  const [existingReview, setExistingReview] = useState<any>(null)
  const [reviewModalOpen, setReviewModalOpen] = useState(false)

  // Load applications
  const fetchApplications = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiClient.professor.getApplications(statusFilter)
      if (response.success && response.data) {
        setApplications(response.data)
        setFilteredApplications(response.data)
      } else {
        setError(response.message || "Failed to load applications")
        setApplications([])
        setFilteredApplications([])
      }
    } catch (e: any) {
      setError(e.message || "Failed to load applications")
      setApplications([])
      setFilteredApplications([])
    } finally {
      setLoading(false)
    }
  }

  // Load applications on mount and when filter changes
  useEffect(() => {
    fetchApplications()
  }, [statusFilter])

  // Search filtering
  useEffect(() => {
    if (!searchQuery) {
      setFilteredApplications(applications)
    } else {
      const filtered = applications.filter(app =>
        (app.student_name?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
        (app.student_no?.toLowerCase() || '').includes(searchQuery.toLowerCase()) ||
        (app.scholarship_name?.toLowerCase() || '').includes(searchQuery.toLowerCase())
      )
      setFilteredApplications(filtered)
    }
  }, [searchQuery, applications])

  // Get status badge variant
  const getStatusVariant = (status: string) => {
    switch (status) {
      case 'pending_recommendation':
        return 'destructive'
      case 'recommended':
        return 'default'
      case 'submitted':
        return 'secondary'
      default:
        return 'outline'
    }
  }

  // Get status display text
  const getStatusText = (status: string) => {
    switch (status) {
      case 'pending_recommendation':
        return '待推薦'
      case 'recommended':
        return '已推薦'
      case 'submitted':
        return '已提交'
      default:
        return status
    }
  }

  // Open review modal
  const openReviewModal = async (application: Application) => {
    setSelectedApplication(application)
    setLoading(true)
    setError(null)
    
    try {
      // Get available sub-types
      const subTypesResponse = await apiClient.professor.getSubTypes(application.id)
      if (subTypesResponse.success && subTypesResponse.data) {
        setSubTypes(subTypesResponse.data)
      }

      // Get existing review if any
      try {
        const reviewResponse = await apiClient.professor.getReview(application.id)
        if (reviewResponse.success && reviewResponse.data) {
          setExistingReview(reviewResponse.data)
          setReviewData({
            recommendation: reviewResponse.data.recommendation || "",
            items: reviewResponse.data.items || []
          })
        } else {
          // No existing review, initialize with sub-types
          setExistingReview(null)
          const initialItems = subTypesResponse.data?.map(subType => ({
            sub_type_code: subType.value,
            is_recommended: false,
            comments: ""
          })) || []
          setReviewData({
            recommendation: "",
            items: initialItems
          })
        }
      } catch (e) {
        // No existing review, create initial form
        setExistingReview(null)
        const initialItems = subTypesResponse.data?.map(subType => ({
          sub_type_code: subType.value,
          is_recommended: false,
          comments: ""
        })) || []
        setReviewData({
          recommendation: "",
          items: initialItems
        })
      }

      setReviewModalOpen(true)
    } catch (e: any) {
      setError(e.message || "Failed to load review data")
    } finally {
      setLoading(false)
    }
  }

  // Submit or update review
  const submitReview = async () => {
    if (!selectedApplication) return

    setLoading(true)
    setError(null)
    setSuccess(null)

    try {
      let response: ApiResponse<any>
      
      if (existingReview) {
        // Update existing review
        response = await apiClient.professor.updateReview(
          selectedApplication.id,
          existingReview.id,
          reviewData
        )
      } else {
        // Submit new review
        response = await apiClient.professor.submitReview(
          selectedApplication.id,
          reviewData
        )
      }

      if (response.success) {
        setSuccess("推薦意見已成功提交")
        setReviewModalOpen(false)
        setSelectedApplication(null)
        setReviewData({ recommendation: "", items: [] })
        setExistingReview(null)
        // Refresh applications list
        fetchApplications()
      } else {
        setError(response.message || "Failed to submit review")
      }
    } catch (e: any) {
      setError(e.message || "Failed to submit review")
    } finally {
      setLoading(false)
    }
  }

  // Update review item
  const updateReviewItem = (subTypeCode: string, field: string, value: any) => {
    setReviewData(prev => ({
      ...prev,
      items: prev.items.map(item =>
        item.sub_type_code === subTypeCode
          ? { ...item, [field]: value }
          : item
      )
    }))
  }

  // Get sub-type label
  const getSubTypeLabel = (subTypeCode: string) => {
    const subType = subTypes.find(st => st.value === subTypeCode)
    return subType?.label || subTypeCode
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">獎學金申請審查</h2>
          <p className="text-muted-foreground">審查學生獎學金申請並提供推薦意見</p>
        </div>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 text-red-700">
              <AlertCircle className="h-4 w-4" />
              <span>{error}</span>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => setError(null)}
                className="ml-auto"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {success && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 text-green-700">
              <CheckCircle className="h-4 w-4" />
              <span>{success}</span>
              <Button 
                variant="ghost" 
                size="sm" 
                onClick={() => setSuccess(null)}
                className="ml-auto"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search and Filter Controls */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input 
            placeholder="搜尋學生姓名、學號或獎學金..." 
            className="pl-8"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="狀態篩選" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">待審查</SelectItem>
            <SelectItem value="completed">已完成</SelectItem>
            <SelectItem value="all">全部</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Applications Table */}
      <Card>
        <CardHeader>
          <CardTitle>獎學金申請列表</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 text-center">
              <Clock className="h-8 w-8 animate-spin mx-auto mb-2" />
              <p>載入中...</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>學生資訊</TableHead>
                  <TableHead>獎學金類型</TableHead>
                  <TableHead>申請金額</TableHead>
                  <TableHead>提交日期</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredApplications.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                      {searchQuery ? "沒有符合搜尋條件的申請" : "目前沒有需要審查的申請"}
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredApplications.map((app) => (
                    <TableRow key={app.id}>
                      <TableCell>
                        <div>
                          <p className="font-medium">{app.student_name || "未知學生"}</p>
                          <p className="text-sm text-muted-foreground">{app.student_no}</p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div>
                          <p>{app.scholarship_name}</p>
                          {app.is_renewal && (
                            <Badge variant="outline" className="text-xs mt-1">續領</Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {app.amount ? `$${app.amount.toLocaleString()}` : "未設定"}
                      </TableCell>
                      <TableCell>
                        {app.submitted_at ? new Date(app.submitted_at).toLocaleDateString() : "未提交"}
                      </TableCell>
                      <TableCell>
                        <Badge variant={getStatusVariant(app.status)}>
                          {getStatusText(app.status)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openReviewModal(app)}
                          disabled={loading}
                        >
                          <Eye className="h-4 w-4 mr-1" />
                          審查
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Review Modal */}
      <Dialog open={reviewModalOpen} onOpenChange={setReviewModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              審查申請 - {selectedApplication?.student_name}
            </DialogTitle>
            <DialogDescription>
              請審查此獎學金申請並針對各子類型提供推薦意見
            </DialogDescription>
          </DialogHeader>

          {selectedApplication && (
            <div className="space-y-6">
              {/* Application Info */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">申請資訊</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm font-medium">學生姓名</label>
                      <p>{selectedApplication.student_name}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">學號</label>
                      <p>{selectedApplication.student_no}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">獎學金類型</label>
                      <p>{selectedApplication.scholarship_name}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">申請金額</label>
                      <p>{selectedApplication.amount ? `$${selectedApplication.amount.toLocaleString()}` : "未設定"}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Sub-type Reviews */}
              {subTypes.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">子類型推薦</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {subTypes.map((subType) => {
                      const reviewItem = reviewData.items.find(item => item.sub_type_code === subType.value)
                      return (
                        <div key={subType.value} className="border rounded-lg p-4 space-y-3">
                          <div className="flex items-center space-x-3">
                            <Checkbox
                              id={`recommend-${subType.value}`}
                              checked={reviewItem?.is_recommended || false}
                              onCheckedChange={(checked) => 
                                updateReviewItem(subType.value, 'is_recommended', checked)
                              }
                            />
                            <label 
                              htmlFor={`recommend-${subType.value}`}
                              className="font-medium cursor-pointer"
                            >
                              推薦 {subType.label}
                            </label>
                          </div>
                          <div>
                            <label className="text-sm font-medium">備註意見</label>
                            <Textarea
                              placeholder={`針對${subType.label}的具體意見...`}
                              value={reviewItem?.comments || ""}
                              onChange={(e) => 
                                updateReviewItem(subType.value, 'comments', e.target.value)
                              }
                              className="mt-1"
                            />
                          </div>
                        </div>
                      )
                    })}
                  </CardContent>
                </Card>
              )}

              {/* Overall Recommendation */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">整體推薦意見</CardTitle>
                </CardHeader>
                <CardContent>
                  <Textarea
                    placeholder="請提供對此申請的整體推薦意見..."
                    value={reviewData.recommendation || ""}
                    onChange={(e) => setReviewData(prev => ({ 
                      ...prev, 
                      recommendation: e.target.value 
                    }))}
                    rows={4}
                  />
                </CardContent>
              </Card>

              {/* Actions */}
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => setReviewModalOpen(false)}
                  disabled={loading}
                >
                  取消
                </Button>
                <Button
                  onClick={submitReview}
                  disabled={loading}
                >
                  {loading ? "提交中..." : existingReview ? "更新推薦" : "提交推薦"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}