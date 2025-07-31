"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Checkbox } from "@/components/ui/checkbox"
import { 
  FileText, 
  Users, 
  Clock, 
  Timer, 
  Search, 
  Filter, 
  Eye, 
  CheckCircle, 
  XCircle, 
  AlertCircle,
  GraduationCap,
  Star,
  TrendingUp,
  RefreshCw
} from "lucide-react"
import { useScholarshipSpecificApplications } from "@/hooks/use-admin"
import { ApplicationDetailDialog } from "@/components/application-detail-dialog"
import { AdminScholarshipManagementInterface } from "@/components/admin-scholarship-management-interface"
import { Locale } from "@/lib/validators"
import { apiClient } from "@/lib/api"

// Use the Application type from the API
import { Application } from "@/lib/api"
import { User } from "@/types/user"
import { useScholarshipPermissions } from "@/hooks/use-scholarship-permissions"

interface AdminScholarshipDashboardProps {
  user: User
}

// Dashboard-specific Application interface for the data we actually receive
interface DashboardApplication {
  id: number
  student_name?: string
  student_no?: string
  status: string
  status_name?: string
  submitted_at?: string
  days_waiting?: number
  scholarship_subtype_list?: string[]
  user?: {
    email: string
  }
  // Additional fields that might be present
  app_id?: string
  student_id?: string
  scholarship_type?: string
  scholarship_type_id?: number
  created_at?: string
  updated_at?: string
  gpa?: number
  class_ranking_percent?: number
  dept_ranking_percent?: number
  personal_statement?: string
  form_data?: Record<string, any>
  submitted_form_data?: {
    fields?: Record<string, any>
    documents?: Array<{
      file_id?: string | number
      id?: string | number
      filename?: string
      original_filename?: string
      file_path?: string
      file_type?: string
      document_type?: string
      mime_type?: string
      file_size?: number
      download_url?: string
      upload_time?: string
      document_id?: string
    }>
  }
  agree_terms?: boolean
  professor_id?: number
  reviewer_id?: number
  final_approver_id?: number
  review_score?: number
  review_comments?: string
  rejection_reason?: string
  reviewed_at?: string
  approved_at?: string
  academic_year?: string
  semester?: string
  meta_data?: any
  // API response structure
  student_data?: {
    id: number
    stdNo: string
    stdCode: string
    pid: string
    cname: string
    ename: string
    sex: string
    birthDate: string
    contacts: {
      cellphone: string
      email: string
      zipCode: string
      address: string
    }
    academic: {
      degree: number
      identity: number
      studyingStatus: number
      schoolIdentity: number
      termCount: number
      depId: number
      academyId: number
      enrollTypeCode: number
      enrollYear: number
      enrollTerm: number
      highestSchoolName: string
      nationality: number
    }
  }
}

// Data transformation function to map API response to expected format
const transformApplicationData = (app: any): DashboardApplication => {
  console.log('Transforming application data:', app)
  
  // Ensure submitted_form_data has the correct structure for file preview
  let submittedFormData = app.submitted_form_data
  if (submittedFormData && submittedFormData.documents) {
    // Transform documents to include necessary file properties for preview
    submittedFormData = {
      ...submittedFormData,
      documents: submittedFormData.documents.map((doc: any) => ({
        ...doc,
        // Map API response fields to expected format for ApplicationDetailDialog
        id: doc.file_id || doc.id || doc.document_id, // Use document_id as fallback
        file_id: doc.file_id || doc.id || doc.document_id,
        filename: doc.filename || doc.original_filename,
        original_filename: doc.original_filename,
        file_path: doc.file_path,
        file_type: doc.document_type || doc.file_type,
        mime_type: doc.mime_type,
        file_size: doc.file_size,
        download_url: doc.download_url,
        upload_time: doc.upload_time,
        // Keep original fields for compatibility
        document_id: doc.document_id,
        document_type: doc.document_type
      }))
    }
  }
  
  const transformed = {
    id: app.id,
    app_id: app.app_id,
    student_id: app.student_id,
    scholarship_type: app.scholarship_type,
    scholarship_type_id: app.scholarship_type_id,
    scholarship_subtype_list: app.scholarship_subtype_list || [],
    status: app.status,
    status_name: app.status_name,
    submitted_at: app.submitted_at,
    days_waiting: app.days_waiting,
    created_at: app.created_at,
    updated_at: app.updated_at,
    form_data: app.submitted_form_data || app.form_data,
    submitted_form_data: submittedFormData, // Use the enhanced version
    student_data: app.student_data,
    // Map student information from nested structure
    student_name: app.student_name || app.student_data?.cname || '未知',
    student_no: app.student_no || app.student_data?.stdNo || 'N/A',
    user: app.user || {
      email: app.student_data?.contacts?.email || 'N/A'
    },
    // Additional fields that might be needed by ApplicationDetailDialog
    gpa: app.gpa,
    class_ranking_percent: app.class_ranking_percent,
    dept_ranking_percent: app.dept_ranking_percent,
    personal_statement: app.personal_statement,
    agree_terms: app.agree_terms,
    professor_id: app.professor_id,
    reviewer_id: app.reviewer_id,
    final_approver_id: app.final_approver_id,
    review_score: app.review_score,
    review_comments: app.review_comments,
    rejection_reason: app.rejection_reason,
    reviewed_at: app.reviewed_at,
    approved_at: app.approved_at,
    academic_year: app.academic_year,
    semester: app.semester,
    meta_data: app.meta_data
  }
  
  console.log('Transformed result:', transformed)
  console.log('Documents in transformed data:', transformed.submitted_form_data?.documents)
  return transformed
}

export function AdminScholarshipDashboard({ user }: AdminScholarshipDashboardProps) {
  // 使用 hook 獲取真實資料
  const { 
    applicationsByType, 
    scholarshipTypes,
    scholarshipStats,
    isLoading, 
    error, 
    refetch,
    updateApplicationStatus 
  } = useScholarshipSpecificApplications()

  // Get user's scholarship permissions for debugging
  const { permissions, isLoading: permissionsLoading, error: permissionsError } = useScholarshipPermissions()

  // Locale state for internationalization (管理員頁面固定使用中文)
  const [locale] = useState<Locale>("zh")
  
  // State for sub-type translations from backend
  const [subTypeTranslations, setSubTypeTranslations] = useState<Record<string, string>>({})
  const [translationsLoading, setTranslationsLoading] = useState(false)

  // Debug logging
  console.log('ScholarshipSpecificDashboard render:', {
    scholarshipTypes,
    scholarshipStats,
    applicationsByType,
    isLoading,
    error
  })

  const [selectedApplication, setSelectedApplication] = useState<DashboardApplication | null>(null)
  const [activeTab, setActiveTab] = useState("")
  const [selectedSubTypes, setSelectedSubTypes] = useState<string[]>([]) // 多選子類型
  const [tabLoading, setTabLoading] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [showApplicationDetail, setShowApplicationDetail] = useState(false)
  const [selectedApplicationForDetail, setSelectedApplicationForDetail] = useState<DashboardApplication | null>(null)

  // 動態獲取各類型申請資料
  const getApplicationsByType = (type: string) => {
    const rawApplications = applicationsByType[type] || []
    const transformedApplications = rawApplications.map(transformApplicationData)
    
    // Debug logging
    if (transformedApplications.length > 0) {
      console.log(`Transformed applications for ${type}:`, transformedApplications[0])
    }
    
    return transformedApplications
  }
  
  // 獲取當前選擇的獎學金類型的子類型（從後端獲取）
  const getCurrentScholarshipSubTypes = () => {
    if (!activeTab || !scholarshipStats[activeTab]) return []
    return scholarshipStats[activeTab].sub_types || []
  }
  
  // 當獎學金類型載入後，自動選擇第一個類型
  useEffect(() => {
    if (scholarshipTypes.length > 0 && !activeTab) {
      setActiveTab(scholarshipTypes[0])
    }
  }, [scholarshipTypes, activeTab])
  
  // 當獎學金類型改變時，重置子類型選擇
  useEffect(() => {
    setSelectedSubTypes([])
  }, [activeTab])

  // 載入子類型翻譯
  useEffect(() => {
    const loadSubTypeTranslations = async () => {
      if (Object.keys(subTypeTranslations).length > 0) return // 已經載入過
      
      setTranslationsLoading(true)
      try {
        const response = await apiClient.admin.getSubTypeTranslations()
        if (response.success && response.data) {
          // 使用中文翻譯
          setSubTypeTranslations(response.data.zh || {})
        }
      } catch (error) {
        console.error('Failed to load sub-type translations:', error)
      } finally {
        setTranslationsLoading(false)
      }
    }

    loadSubTypeTranslations()
  }, [subTypeTranslations])

  // 搜尋和篩選邏輯
  const filterApplications = (applications: DashboardApplication[]) => {
    let filtered = applications

    // 狀態篩選
    if (statusFilter !== "all") {
      filtered = filtered.filter(app => app.status === statusFilter)
    }

    // 搜尋篩選
    if (searchTerm) {
      const term = searchTerm.toLowerCase()
      filtered = filtered.filter(app => 
        app.student_name?.toLowerCase().includes(term) ||
        app.student_no?.toLowerCase().includes(term) ||
        app.user?.email.toLowerCase().includes(term) ||
        app.student_data?.cname?.toLowerCase().includes(term) ||
        app.student_data?.stdNo?.toLowerCase().includes(term) ||
        app.student_data?.contacts?.email?.toLowerCase().includes(term)
      )
    }

    return filtered
  }

  // 獲取獎學金顯示名稱（從後端資料）
  const getScholarshipDisplayName = (code: string) => {
    if (scholarshipStats[code]) {
      return locale === "zh" ? scholarshipStats[code].name : (scholarshipStats[code].name_en || scholarshipStats[code].name)
    }
    return code
  }

  // 獲取子類型顯示名稱（從後端獲取）
  const getSubTypeDisplayName = (subType: string) => {
    // 使用後端翻譯
    if (subTypeTranslations[subType]) {
      return subTypeTranslations[subType]
    }
    
    // 如果沒有翻譯，顯示原始代碼
    return subType
  }

  // 處理申請狀態更新
  const handleStatusUpdate = async (applicationId: number, newStatus: string) => {
    try {
      await updateApplicationStatus(applicationId, newStatus)
      // 重新載入數據
      refetch()
    } catch (error) {
      console.error('Failed to update application status:', error)
      alert('更新申請狀態失敗')
    }
  }

  // 渲染統計卡片
  const renderStatsCards = (applications: DashboardApplication[]) => {
    const totalApplications = applications.length
    const pendingApplications = applications.filter(app => 
      ['submitted', 'under_review'].includes(app.status)
    ).length
    const approvedApplications = applications.filter(app => 
      app.status === 'approved'
    ).length
    const rejectedApplications = applications.filter(app => 
      app.status === 'rejected'
    ).length

    return (
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總申請數</CardTitle>
            <GraduationCap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalApplications}</div>
            <p className="text-xs text-muted-foreground">累計申請案件</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">待審核</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{pendingApplications}</div>
            <p className="text-xs text-muted-foreground">等待處理案件</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">已核准</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{approvedApplications}</div>
            <p className="text-xs text-muted-foreground">核准案件</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">已拒絕</CardTitle>
            <XCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{rejectedApplications}</div>
            <p className="text-xs text-muted-foreground">拒絕案件</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  // 渲染申請列表
  const renderApplicationsTable = (applications: DashboardApplication[], showSubTypes: boolean = false) => {
    const filteredApplications = filterApplications(applications)

    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            申請案件列表
          </CardTitle>
          <CardDescription>
            共 {filteredApplications.length} 件申請案件
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* 搜尋和篩選 */}
          <div className="flex gap-4 mb-4">
            <div className="flex-1">
              <Label>搜尋申請人</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  placeholder="搜尋姓名、學號或信箱"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div>
              <Label>狀態篩選</Label>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                <option value="all">全部狀態</option>
                <option value="submitted">已提交</option>
                <option value="under_review">審核中</option>
                <option value="approved">已核准</option>
                <option value="rejected">已拒絕</option>
              </select>
            </div>
          </div>

          {/* 申請列表表格 */}
          {filteredApplications.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>申請人</TableHead>
                  <TableHead>學號</TableHead>
                  {showSubTypes && <TableHead>子項目</TableHead>}
                  <TableHead>狀態</TableHead>
                  <TableHead>提交時間</TableHead>
                  <TableHead>等待天數</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredApplications.map((app) => (
                  <TableRow key={app.id}>
                    <TableCell>
                      <div className="font-medium">{app.student_name || '未知'}</div>
                      <div className="text-sm text-gray-500">{app.user?.email || 'N/A'}</div>
                    </TableCell>
                    <TableCell>{app.student_no || 'N/A'}</TableCell>
                    {showSubTypes && (
                      <TableCell>
                        {app.scholarship_subtype_list && app.scholarship_subtype_list.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {app.scholarship_subtype_list.map((subType: string) => (
                              <Badge key={subType} variant="outline" className="text-xs">
                                {getSubTypeDisplayName(subType)}
                              </Badge>
                            ))}
                          </div>
                        ) : (
                          <span className="text-sm text-gray-500">一般</span>
                        )}
                      </TableCell>
                    )}
                    <TableCell>
                      <Badge
                        variant={
                          app.status === 'approved' ? 'default' :
                          app.status === 'rejected' ? 'destructive' :
                          app.status === 'submitted' ? 'secondary' :
                          'outline'
                        }
                      >
                        {app.status_name || app.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {app.submitted_at 
                        ? new Date(app.submitted_at).toLocaleDateString('zh-TW')
                        : 'N/A'
                      }
                    </TableCell>
                    <TableCell>
                      {app.days_waiting !== undefined 
                        ? `${app.days_waiting}天`
                        : 'N/A'
                      }
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSelectedApplicationForDetail(app)
                            setShowApplicationDetail(true)
                          }}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        {app.status === 'submitted' && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleStatusUpdate(app.id, 'approved')}
                              className="hover:bg-green-50 hover:border-green-300 hover:text-green-600"
                            >
                              <CheckCircle className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleStatusUpdate(app.id, 'rejected')}
                              className="hover:bg-red-50 hover:border-red-300 hover:text-red-600"
                            >
                              <XCircle className="h-4 w-4" />
                            </Button>
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-center py-8 text-gray-500">
              <FileText className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">尚無申請案件</p>
              <p className="text-sm mt-2">目前沒有符合條件的申請案件</p>
            </div>
          )}
        </CardContent>
      </Card>
    )
  }

  // 處理子類型選擇
  const handleSubTypeToggle = (subType: string) => {
    setSelectedSubTypes(prev => {
      if (prev.includes(subType)) {
        return prev.filter(type => type !== subType)
      } else {
        return [...prev, subType]
      }
    })
  }

  // 過濾申請數據根據選擇的子類型
  const filterApplicationsBySubTypes = (applications: DashboardApplication[]) => {
    if (selectedSubTypes.length === 0) {
      return applications // 如果沒有選擇子類型，顯示全部
    }
    
    // 這裡需要根據實際的申請數據結構來過濾
    // 暫時返回全部，實際實現時需要根據 scholarship_subtype_list 來過濾
    return applications.filter(app => {
      // 如果申請有子類型信息，檢查是否匹配
      if (app.scholarship_subtype_list && Array.isArray(app.scholarship_subtype_list)) {
        return app.scholarship_subtype_list.some((subType: string) => selectedSubTypes.includes(subType))
      }
      return true // 如果沒有子類型信息，暫時顯示
    })
  }

  // 渲染子類型多選標籤頁
  const renderSubTypeTabs = (applications: DashboardApplication[]) => {
    const subTypes = getCurrentScholarshipSubTypes()
    
    if (subTypes.length === 0) {
      // 沒有子類型的獎學金，直接顯示統計卡片和申請列表
      return (
        <div className="space-y-6">
          {renderStatsCards(applications)}
          {renderApplicationsTable(applications, false)}
        </div>
      )
    }

    // 過濾掉 "general" 類型，只顯示其他子類型
    const filteredSubTypes = subTypes.filter((subType: string) => subType !== "general")
    
    // 如果沒有其他子類型，直接顯示申請列表
    if (filteredSubTypes.length === 0) {
      // 只有 "general" 類型的獎學金，顯示統計卡片和申請列表
      return (
        <div className="space-y-6">
          {renderStatsCards(applications)}
          {renderApplicationsTable(applications, false)}
        </div>
      )
    }

    // 過濾申請數據
    const filteredApplications = filterApplicationsBySubTypes(applications)

    return (
      <div className="space-y-6">
        {/* 子類型選擇器卡片 */}
        <Card className="border-2 border-dashed border-gray-200 hover:border-gray-300 transition-colors">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg font-semibold">
              <Filter className="h-5 w-5 text-blue-600" />
              選擇子類型篩選
            </CardTitle>
            <CardDescription className="text-sm text-gray-600">
              勾選您想要查看的子類型，可多選。未選擇任何項目時將顯示全部申請。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* 子類型選項 */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {filteredSubTypes.map((subType: string) => (
                <div
                  key={subType}
                  className={`flex items-center space-x-3 p-3 rounded-lg border transition-all cursor-pointer hover:bg-gray-50 ${
                    selectedSubTypes.includes(subType)
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 bg-white'
                  }`}
                  onClick={() => handleSubTypeToggle(subType)}
                >
                  <Checkbox
                    checked={selectedSubTypes.includes(subType)}
                    onCheckedChange={() => handleSubTypeToggle(subType)}
                    className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
                  />
                  <div className="flex-1">
                    <Label className="text-sm font-medium cursor-pointer">
                      {getSubTypeDisplayName(subType)}
                    </Label>
                    <p className="text-xs text-gray-500 mt-1">
                      子類型代碼: {subType}
                    </p>
                  </div>
                  {selectedSubTypes.includes(subType) && (
                    <Badge variant="secondary" className="bg-blue-100 text-blue-800">
                      已選
                    </Badge>
                  )}
                </div>
              ))}
            </div>

            {/* 操作按鈕 */}
            <div className="flex items-center justify-between pt-4 border-t">
              <div className="text-sm text-gray-600">
                {selectedSubTypes.length > 0 ? (
                  <span className="flex items-center gap-2">
                    <CheckCircle className="h-4 w-4 text-green-600" />
                    已選擇 {selectedSubTypes.length} 個子類型: 
                    <span className="font-medium">
                      {selectedSubTypes.map(type => getSubTypeDisplayName(type)).join(', ')}
                    </span>
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 text-orange-500" />
                    未選擇任何子類型，顯示全部申請
                  </span>
                )}
              </div>
              
              {selectedSubTypes.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setSelectedSubTypes([])}
                  className="text-gray-600 hover:text-gray-800"
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  清除選擇
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 篩選結果統計 */}
        <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-200">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  篩選結果
                </h3>
                <p className="text-sm text-gray-600">
                  共找到 {filteredApplications.length} 筆申請
                  {selectedSubTypes.length > 0 && (
                    <span className="ml-2 text-blue-600">
                      (已篩選: {selectedSubTypes.map(type => getSubTypeDisplayName(type)).join(', ')})
                    </span>
                  )}
                </p>
              </div>
              <Badge variant="outline" className="text-blue-700 border-blue-300">
                {filteredApplications.length} 筆
              </Badge>
            </div>
          </CardContent>
        </Card>

        {/* 申請列表 */}
        {renderStatsCards(filteredApplications)}
        {renderApplicationsTable(filteredApplications, true)}
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="flex items-center gap-3">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-blue-600 border-t-transparent"></div>
          <span className="text-gray-600">載入獎學金資料中...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
        <h2 className="text-2xl font-bold text-red-600 mb-2">載入失敗</h2>
        <p className="text-gray-600 mb-6">{error}</p>
        <Button onClick={refetch} variant="outline">
          <RefreshCw className="h-4 w-4 mr-2" />
          重試
        </Button>
      </div>
    )
  }

  if (scholarshipTypes.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500">
        <FileText className="h-16 w-16 mx-auto mb-4 text-gray-300" />
        <p className="text-lg font-medium">尚無獎學金資料</p>
        <p className="text-sm mt-2">請先建立獎學金類型</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">獎學金申請管理</h2>
          <p className="text-muted-foreground">
            管理各類型獎學金申請案件 - {user.role === 'super_admin' ? '超級管理員' : 
            user.role === 'admin' ? '管理員' : 
            user.role === 'college' ? '學院審核人員' : 
            user.role === 'professor' ? '教授' : '未知角色'}
          </p>
        </div>
        <Button onClick={refetch} variant="outline" disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          重新整理
        </Button>
      </div>

      {/* Permission Status */}
      <Card className="bg-blue-50 border-blue-200">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="h-3 w-3 bg-blue-500 rounded-full"></div>
              <div>
                <h3 className="font-semibold text-blue-900">權限狀態</h3>
                <p className="text-sm text-blue-700">
                  {user.role === 'super_admin' 
                    ? '可管理所有獎學金類型' 
                    : user.role === 'admin' 
                    ? '可管理指定權限的獎學金類型' 
                    : user.role === 'college' 
                    ? '可管理指定權限的獎學金類型' 
                    : user.role === 'professor' 
                    ? '可查看指導學生的申請案件' 
                    : '無管理權限'}
                </p>
                {/* Debug information */}
                {process.env.NODE_ENV === 'development' && (
                  <div className="mt-2 text-xs text-blue-600">
                    <p>用戶ID: {user.id}</p>
                    <p>用戶角色: {user.role}</p>
                    <p>權限載入中: {permissionsLoading ? '是' : '否'}</p>
                    <p>權限錯誤: {permissionsError || '無'}</p>
                    <p>權限數量: {permissions.length}</p>
                    <p>獎學金類型數量: {scholarshipTypes.length}</p>
                    <p>獎學金統計數量: {Object.keys(scholarshipStats).length}</p>
                    {permissions.length > 0 && (
                      <p>權限詳情: {permissions.map(p => `${p.scholarship_name}(${p.scholarship_id})`).join(', ')}</p>
                    )}
                    {scholarshipTypes.length > 0 && (
                      <p>獎學金類型: {scholarshipTypes.join(', ')}</p>
                    )}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        try {
                          console.log('Testing permissions API...')
                          const response = await apiClient.admin.getCurrentUserScholarshipPermissions()
                          console.log('Permissions API response:', response)
                          alert(`權限 API 測試結果: ${response.success ? '成功' : '失敗'}\n權限數量: ${response.data?.length || 0}`)
                        } catch (error) {
                          console.error('Permissions API test failed:', error)
                          alert(`權限 API 測試失敗: ${error}`)
                        }
                      }}
                      className="mt-2"
                    >
                      測試權限 API
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={async () => {
                        try {
                          console.log('Testing scholarship stats API...')
                          const response = await apiClient.admin.getScholarshipStats()
                          console.log('Scholarship stats API response:', response)
                          alert(`獎學金統計 API 測試結果: ${response.success ? '成功' : '失敗'}\n獎學金數量: ${response.data ? Object.keys(response.data).length : 0}`)
                        } catch (error) {
                          console.error('Scholarship stats API test failed:', error)
                          alert(`獎學金統計 API 測試失敗: ${error}`)
                        }
                      }}
                      className="mt-2 ml-2"
                    >
                      測試獎學金統計 API
                    </Button>
                  </div>
                )}
              </div>
            </div>
            <Badge variant="outline" className="text-blue-700 border-blue-300">
              {scholarshipTypes.length} 個獎學金類型
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* 獎學金類型標籤頁 */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full" style={{ gridTemplateColumns: `repeat(${scholarshipTypes.length}, 1fr)` }}>
          {scholarshipTypes.map((type) => (
            <TabsTrigger key={type} value={type} className="text-sm">
              {getScholarshipDisplayName(type)}
            </TabsTrigger>
          ))}
        </TabsList>

        {scholarshipTypes.map((type) => (
          <TabsContent key={type} value={type} className="space-y-6">
            {renderSubTypeTabs(getApplicationsByType(type))}
          </TabsContent>
        ))}
      </Tabs>
      {/* 申請詳情 Modal */}
      <ApplicationDetailDialog
        isOpen={showApplicationDetail}
        onClose={() => {
          setShowApplicationDetail(false)
          setSelectedApplicationForDetail(null)
        }}
        application={selectedApplicationForDetail ? selectedApplicationForDetail as Application : null}
        locale={locale}
      />

      {/* 獎學金管理面板 */}
      {activeTab && (
        <div className="mt-8">
          <AdminScholarshipManagementInterface 
            type={activeTab as any} 
            className="border-t pt-6"
          />
        </div>
      )}
    </div>
  )
}
