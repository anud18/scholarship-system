"use client"

import { useState, useEffect, useMemo } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Checkbox } from "@/components/ui/checkbox"
import { ProgressTimeline } from "@/components/progress-timeline"
import { FileUpload } from "@/components/file-upload"
import { DynamicApplicationForm } from "@/components/dynamic-application-form"
import { ApplicationDetailDialog } from "@/components/application-detail-dialog"
import { Edit, Eye, Trash2, Save, AlertTriangle, Info, FileText, Calendar, User as UserIcon, Loader2, Check } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { getTranslation } from "@/lib/i18n"
import { useApplications } from "@/hooks/use-applications"
import { FormValidator, Locale } from "@/lib/validators"
import api, { ScholarshipType, Application as ApiApplication, ApplicationFile, ApplicationCreate, ApplicationField, ApplicationDocument } from "@/lib/api"
import { 
  getApplicationTimeline, 
  getStatusColor, 
  getStatusName,
  ApplicationStatus 
} from "@/lib/utils/application-helpers"
import { clsx } from "@/lib/utils"
import { User } from "@/types/user"

// 使用API的Application類型
type Application = ApiApplication

interface EnhancedStudentPortalProps {
  user: User & {
    studentType: "phd" | "master" | "undergraduate" | "other"
  }
  locale: Locale
}

type BadgeVariant = "secondary" | "default" | "outline" | "destructive"

export function EnhancedStudentPortal({ user, locale }: EnhancedStudentPortalProps) {
  const t = (key: string) => getTranslation(locale, key)
  const validator = useMemo(() => new FormValidator(locale), [locale])
  
  const [activeTab, setActiveTab] = useState("applications")
  const [editingApplication, setEditingApplication] = useState<Application | null>(null)
  const [selectedSubTypes, setSelectedSubTypes] = useState<Record<string, string[]>>({})
  

  
  // 直接從 eligibleScholarships (API) 取得名稱，找不到就顯示 code
  const getScholarshipTypeName = (scholarshipType: string): string => {
    const scholarship = eligibleScholarships.find(s => s.code === scholarshipType)
    return scholarship ? (locale === "zh" ? scholarship.name : (scholarship.name_en || scholarship.name)) : scholarshipType
  }
  
  // Debug authentication status
  useEffect(() => {
    console.log('EnhancedStudentPortal mounted with user:', user)
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null
    console.log('Current auth token exists:', !!token)
    console.log('Token preview:', token ? token.substring(0, 20) + '...' : 'No token')
  }, [user])
  
  // Use real application data from API
  const { 
    applications, 
    isLoading: applicationsLoading, 
    error: applicationsError,
    fetchApplications,
    createApplication,
    saveApplicationDraft,
    submitApplication: submitApplicationApi,
    withdrawApplication,
    uploadDocument,
    updateApplication,
    deleteApplication
  } = useApplications()

  // State for eligible scholarships
  const [eligibleScholarships, setEligibleScholarships] = useState<ScholarshipType[]>([])
  const [isLoadingScholarships, setIsLoadingScholarships] = useState(true)
  const [scholarshipsError, setScholarshipsError] = useState<string | null>(null)
  
  // State for scholarship application info (form fields and documents)
  const [scholarshipApplicationInfo, setScholarshipApplicationInfo] = useState<{
    [scholarshipType: string]: {
      fields: ApplicationField[]
      documents: ApplicationDocument[]
      isLoading: boolean
      error: string | null
    }
  }>({})

  // Fetch eligible scholarships on component mount
  useEffect(() => {
    const fetchEligibleScholarships = async () => {
      try {
        setIsLoadingScholarships(true)
        const response = await api.scholarships.getEligible()
        
        let scholarshipData: ScholarshipType[] = []
        if (response.success && response.data) {
          scholarshipData = response.data
        } else {
          setScholarshipsError(response.message || '無法獲取獎學金資料')
          setEligibleScholarships([])
          return
        }
        
        if (scholarshipData.length === 0) {
          setScholarshipsError('目前沒有符合資格的獎學金')
        } else {
          setEligibleScholarships(scholarshipData)
          setScholarshipsError(null)
          
          // 自動載入每個獎學金的申請資訊
          scholarshipData.forEach(scholarship => {
            fetchScholarshipApplicationInfo(scholarship.code)
          })
        }
      } catch (error) {
        console.error('Error fetching scholarships:', error) // Debug log
        setScholarshipsError(error instanceof Error ? error.message : '發生未知錯誤')
        setEligibleScholarships([])
      } finally {
        setIsLoadingScholarships(false)
      }
    }

    fetchEligibleScholarships()
  }, [])

  // 獲取獎學金申請資訊（表單欄位和文件要求）
  const fetchScholarshipApplicationInfo = async (scholarshipType: string) => {
    // 如果已經載入過，直接返回
    if (scholarshipApplicationInfo[scholarshipType] && !scholarshipApplicationInfo[scholarshipType].isLoading) {
      return scholarshipApplicationInfo[scholarshipType]
    }

    // 設置載入狀態
    setScholarshipApplicationInfo(prev => ({
      ...prev,
      [scholarshipType]: {
        ...prev[scholarshipType],
        isLoading: true,
        error: null
      }
    }))

    try {
      const response = await api.applicationFields.getFormConfig(scholarshipType)
      
      if (response.success && response.data) {
        setScholarshipApplicationInfo(prev => ({
          ...prev,
          [scholarshipType]: {
            fields: response.data?.fields || [],
            documents: response.data?.documents || [],
            isLoading: false,
            error: null
          }
        }))
      } else {
        setScholarshipApplicationInfo(prev => ({
          ...prev,
          [scholarshipType]: {
            fields: [],
            documents: [],
            isLoading: false,
            error: response.message || '無法獲取申請資訊'
          }
        }))
      }
    } catch (error) {
      console.error(`Failed to fetch application info for ${scholarshipType}:`, error)
      setScholarshipApplicationInfo(prev => ({
        ...prev,
        [scholarshipType]: {
          fields: [],
          documents: [],
          isLoading: false,
          error: error instanceof Error ? error.message : '獲取申請資訊時發生錯誤'
        }
      }))
    }
  }

  // Form state for new application
  const [newApplicationData, setNewApplicationData] = useState<ApplicationCreate>({
    scholarship_type: '',
    form_data: {
      fields: {},
      documents: []
    }
  })
  
  // Dynamic form state
  const [dynamicFormData, setDynamicFormData] = useState<Record<string, any>>({})
  const [dynamicFileData, setDynamicFileData] = useState<Record<string, File[]>>({})
  
  // Terms agreement state
  const [agreeTerms, setAgreeTerms] = useState(false)
  
  // File upload state (for backwards compatibility)
  const [uploadedFiles, setUploadedFiles] = useState<{ [documentType: string]: File[] }>({})
  const [selectedScholarship, setSelectedScholarship] = useState<ScholarshipType | null>(null)
  
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formProgress, setFormProgress] = useState(0)

  // Calculate form completion progress (based on dynamic form configuration)
  useEffect(() => {
    if (!newApplicationData.scholarship_type) {
      setFormProgress(0)
      return
    }

    // Get form configuration to calculate proper progress
    const calculateProgress = async () => {
      try {
        const response = await api.applicationFields.getFormConfig(newApplicationData.scholarship_type)
        if (!response.success || !response.data) {
          setFormProgress(0)
          return
        }

        const { fields, documents } = response.data
        
        // Calculate total required items
        const requiredFields = fields.filter(f => f.is_active && f.is_required)
        const requiredDocuments = documents.filter(d => d.is_active && d.is_required)
        let totalRequired = requiredFields.length + requiredDocuments.length
        
        // Add sub-type selection as a required item if applicable
        const scholarship = selectedScholarship
        if (scholarship?.eligible_sub_types && 
            scholarship.eligible_sub_types[0] !== "general" &&
            scholarship.eligible_sub_types.length > 0) {
          totalRequired += 1
        }
        
        // Add terms agreement as a required item
        totalRequired += 1
        
        if (totalRequired === 0) {
          setFormProgress(100) // No requirements means 100% complete
          return
        }

        let completedItems = 0

        // Check required fields completion
        requiredFields.forEach(field => {
          const fieldValue = dynamicFormData[field.field_name]
          if (fieldValue !== undefined && fieldValue !== null && fieldValue !== '') {
            completedItems++
          }
        })

        // Check required documents completion
        requiredDocuments.forEach(doc => {
          const docFiles = dynamicFileData[doc.document_name]
          if (docFiles && docFiles.length > 0) {
            completedItems++
          }
        })
        
        // Check sub-type selection completion
        if (scholarship?.eligible_sub_types && 
            scholarship.eligible_sub_types[0] !== "general" &&
            scholarship.eligible_sub_types.length > 0) {
          if (selectedSubTypes[newApplicationData.scholarship_type]?.length > 0) {
            completedItems++
          }
        }
        
        // Check terms agreement completion
        if (agreeTerms) {
          completedItems++
        }

        // Calculate percentage
        const progress = Math.round((completedItems / totalRequired) * 100)
        setFormProgress(progress)
      } catch (error) {
        console.error('Error calculating progress:', error)
        setFormProgress(0)
      }
    }

    calculateProgress()
  }, [newApplicationData.scholarship_type, dynamicFormData, dynamicFileData, selectedScholarship, selectedSubTypes, agreeTerms])

  // 新增狀態用於詳情對話框
  const [selectedApplicationForDetails, setSelectedApplicationForDetails] = useState<Application | null>(null)
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false)

  const handleSubmitApplication = async () => {
    if (!newApplicationData.scholarship_type) {
      alert(locale === "zh" ? "請選擇獎學金類型" : "Please select scholarship type")
      return
    }

    if (!agreeTerms) {
      alert(locale === "zh" ? "您必須同意申請條款才能提交申請" : "You must agree to the terms and conditions to submit the application")
      return
    }

    try {
      setIsSubmitting(true)
      
      // Format form fields according to backend requirements
      const formFields: Record<string, {
        field_id: string,
        field_type: string,
        value: string,
        required: boolean
      }> = {}

      // Convert dynamic form data to required format
      Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
        formFields[fieldName] = {
          field_id: fieldName,
          field_type: "text", // You might need to get this from field configuration
          value: String(value),
          required: true // This should come from field configuration
        }
      })

      // Format documents according to backend requirements - 使用整合後的文件結構
      const documents = Object.entries(dynamicFileData).map(([docType, files]) => {
        const file = files[0] // Assuming single file per document type
        return {
          document_id: docType,
          document_type: docType,
          file_path: file.name, // This should be the server path after upload
          original_filename: file.name,
          upload_time: new Date().toISOString()
        }
      })

      // Prepare the application data according to backend format
      const applicationData = {
        scholarship_type: newApplicationData.scholarship_type,
        scholarship_subtype_list: selectedSubTypes[newApplicationData.scholarship_type]?.length 
          ? selectedSubTypes[newApplicationData.scholarship_type] 
          : ["general"],
        agree_terms: agreeTerms,
        form_data: {
          fields: formFields,
          documents: documents
        }
      }
      
      if (editingApplication) {
        // 編輯模式 - 更新草稿然後提交
        console.log('Updating application with data:', applicationData)
        await updateApplication(editingApplication.id, applicationData)
        
        // 上傳新文件
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            if (!(file as any).isUploaded) {
              await uploadDocument(editingApplication.id, file, docType)
            }
          }
        }
        
        // 提交編輯後的申請
        await submitApplicationApi(editingApplication.id)
      } else {
        // 新建模式 - 先創建草稿，然後提交
        console.log('Creating application as draft with data:', applicationData)
        const createdApplication = await createApplication(applicationData, true) // 創建為草稿
        
        if (!createdApplication || !createdApplication.id) {
          throw new Error('Failed to create application')
        }
        
        // 上傳文件
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            await uploadDocument(createdApplication.id, file, docType)
          }
        }
        
        // 提交草稿
        await submitApplicationApi(createdApplication.id)
      }

      // 重置表單
      setNewApplicationData({ 
        scholarship_type: '',
        form_data: {
          fields: {},
          documents: []
        }
      })
      setDynamicFormData({})
      setDynamicFileData({})
      setUploadedFiles({})
      setSelectedScholarship(null)
      setEditingApplication(null)
      setAgreeTerms(false)
      
      // 重新載入申請列表
      await fetchApplications()
      setActiveTab("applications")
      
      alert(locale === "zh" ? "申請提交成功！" : "Application submitted successfully!")
      
    } catch (error) {
      console.error('Failed to submit application:', error)
      let errorMessage = error instanceof Error ? error.message : 'Unknown error'
      alert(locale === "zh" ? `提交失敗: ${errorMessage}` : `Failed to submit application: ${errorMessage}`)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSaveDraft = async () => {
    if (!newApplicationData.scholarship_type) {
      alert(locale === "zh" ? "請選擇獎學金類型" : "Please select scholarship type")
      return
    }

    try {
      setIsSubmitting(true)
      
      // Format form fields according to backend requirements
      const formFields: Record<string, {
        field_id: string,
        field_type: string,
        value: string,
        required: boolean
      }> = {}

      // Convert dynamic form data to required format
      Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
        formFields[fieldName] = {
          field_id: fieldName,
          field_type: "text", // You might need to get this from field configuration
          value: String(value),
          required: true // This should come from field configuration
        }
      })

      // Format documents according to backend requirements
      const documents = Object.entries(dynamicFileData).map(([docType, files]) => {
        const file = files[0] // Assuming single file per document type
        return {
          document_id: docType,
          document_type: docType,
          file_path: file.name, // This should be the server path after upload
          original_filename: file.name,
          upload_time: new Date().toISOString()
        }
      })

      // Prepare the application data according to backend format
      const applicationData = {
        scholarship_type: newApplicationData.scholarship_type,
        scholarship_subtype_list: selectedSubTypes[newApplicationData.scholarship_type]?.length 
          ? selectedSubTypes[newApplicationData.scholarship_type] 
          : ["general"],
        agree_terms: agreeTerms,
        form_data: {
          fields: formFields,
          documents: documents
        }
      }

      if (editingApplication) {
        // 編輯模式 - 更新現有申請
        console.log('Updating draft application with data:', applicationData)
        await updateApplication(editingApplication.id, applicationData)
        
        // 上傳新文件
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            if (!(file as any).isUploaded) {
              await uploadDocument(editingApplication.id, file, docType)
            }
          }
        }
        
        alert(locale === "zh" ? "草稿已更新" : "Draft updated successfully")
      } else {
        // 新建模式 - 創建新草稿
        console.log('Saving new draft with data:', applicationData)
        const application = await saveApplicationDraft(applicationData)
        
        if (application && application.id) {
          // 上傳文件
          for (const [docType, files] of Object.entries(dynamicFileData)) {
            for (const file of files) {
              if (!(file as any).isUploaded) {
                await uploadDocument(application.id, file, docType)
              }
            }
          }
          
          alert(locale === "zh" ? "草稿已保存，您可以繼續編輯" : "Draft saved successfully. You can continue editing.")
        } else {
          alert(locale === "zh" ? "儲存草稿失敗" : "Failed to save draft")
          return
        }
      }
      
      // 重新載入申請列表
      await fetchApplications()
      
      // 如果是編輯模式，保持在編輯狀態；如果是新建模式，重置表單
      if (!editingApplication) {
        // Reset form only for new applications
        setNewApplicationData({ 
          scholarship_type: "",
          form_data: {
            fields: {},
            documents: []
          }
        })
        setDynamicFormData({})
        setDynamicFileData({})
        setAgreeTerms(false)
        setSelectedSubTypes({})
      }
    } catch (error) {
      console.error('Failed to save draft:', error)
      let errorMessage = error instanceof Error ? error.message : 'Unknown error'
      alert(locale === "zh" ? `保存失敗: ${errorMessage}` : `Failed to save draft: ${errorMessage}`)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleWithdrawApplication = async (applicationId: number) => {
    try {
      await withdrawApplication(applicationId)
    } catch (error) {
      console.error('Failed to withdraw application:', error)
    }
  }

  const handleDeleteApplication = async (applicationId: number) => {
    if (!confirm(locale === "zh" ? "確定要刪除此草稿嗎？此操作無法復原。" : "Are you sure you want to delete this draft? This action cannot be undone.")) {
      return
    }

    try {
      await deleteApplication(applicationId)
      alert(locale === "zh" ? "草稿已成功刪除" : "Draft deleted successfully")
    } catch (error) {
      console.error('Failed to delete application:', error)
      alert(locale === "zh" ? "刪除草稿時發生錯誤" : "Error occurred while deleting draft")
    }
  }

  // 查看詳情處理函數
  const handleViewDetails = async (application: Application) => {
    try {
      // 從後端獲取完整的申請詳情，包括 form_data
      const response = await api.applications.getApplicationById(application.id)
      if (response.success && response.data) {
        setSelectedApplicationForDetails(response.data)
      } else {
        // 如果獲取失敗，使用原始的申請資料
        setSelectedApplicationForDetails(application)
      }
    } catch (error) {
      console.error('Failed to fetch application details:', error)
      // 如果獲取失敗，使用原始的申請資料
    setSelectedApplicationForDetails(application)
    }
    
    setIsDetailsDialogOpen(true)
  }

  // 取消編輯函數
  const handleCancelEdit = () => {
    setEditingApplication(null)
    setNewApplicationData({ 
      scholarship_type: '',
      form_data: {
        fields: {},
        documents: []
      }
    })
    setDynamicFormData({})
    setDynamicFileData({})
    setUploadedFiles({})
    setSelectedScholarship(null)
    setAgreeTerms(false)
    setSelectedSubTypes({})
    setActiveTab("applications")
  }

  // 編輯處理函數
  const handleEditApplication = async (application: Application) => {
    // 設置編輯模式
    setEditingApplication(application)
    
    // 先設置獎學金類型，這樣可以確保 selectedScholarship 正確設置
    const scholarship = eligibleScholarships.find(s => s.code === application.scholarship_type) || null
    setSelectedScholarship(scholarship)
    
    // 載入申請資料到表單
    setNewApplicationData({
      scholarship_type: application.scholarship_type,
      personal_statement: application.personal_statement || '',
      form_data: {
        fields: {},
        documents: []
      }
    })
    
    // 載入同意條款狀態
    setAgreeTerms(application.agree_terms || false)
    
    // 載入現有的表單資料
    const existingFormData: Record<string, any> = {}
    const existingFileData: Record<string, File[]> = {}
    
    // 處理 submitted_form_data 或 form_data
    const formData = application.submitted_form_data || application.form_data || {}
    
    // 處理欄位資料
    if (formData.fields) {
      // 後端格式：{ fields: { field_id: { value: "..." } } }
      Object.entries(formData.fields).forEach(([fieldId, fieldData]: [string, any]) => {
        if (fieldData && typeof fieldData === 'object' && 'value' in fieldData) {
          existingFormData[fieldId] = fieldData.value
        }
      })
    } else {
      // 前端格式：直接是欄位資料
      Object.entries(formData).forEach(([key, value]) => {
        if (key !== 'documents' && key !== 'files' && value !== undefined && value !== null && value !== '') {
          existingFormData[key] = value
        }
      })
    }
    
    // 處理文件資料
    if (formData.documents) {
      // 後端格式：{ documents: [{ document_id: "...", ... }] }
      formData.documents.forEach((doc: any) => {
        if (doc.document_id && doc.original_filename) {
          // 直接使用後端返回的文件數據，轉換為 FileUpload 組件期望的格式
          const fileData = {
            id: doc.file_id,
            filename: doc.filename || doc.original_filename,
            original_filename: doc.original_filename,
            file_size: doc.file_size,
            mime_type: doc.mime_type,
            file_type: doc.document_type,
            file_path: doc.file_path,
            download_url: doc.download_url,
            is_verified: doc.is_verified,
            uploaded_at: doc.upload_time,
                      // 添加 FileUpload 組件需要的屬性
          name: doc.original_filename,
          size: doc.file_size || 0,
          originalSize: doc.file_size || 0, // FileUpload 組件使用這個屬性
          type: doc.mime_type || 'application/octet-stream',
          // 標記為已上傳的文件
          isUploaded: true
          }
          existingFileData[doc.document_id] = [fileData as any]
        }
      })
    }
    
    // 載入子類型選擇 - 確保在設置 selectedScholarship 之後
    // 檢查獎學金是否有特殊的子類型（不是只有 general）
    const hasSpecialSubTypes = scholarship?.eligible_sub_types && 
      scholarship.eligible_sub_types.length > 0 && 
      scholarship.eligible_sub_types[0] !== "general"
    
    console.log('Debug handleEditApplication:', {
      applicationId: application.id,
      scholarshipType: application.scholarship_type,
      scholarshipSubtypeList: application.scholarship_subtype_list,
      hasSpecialSubTypes,
      eligibleSubTypes: scholarship?.eligible_sub_types
    })
    
    if (hasSpecialSubTypes) {
      // 只有當獎學金有特殊子類型時才載入子類型選擇
      if (application.scholarship_subtype_list && application.scholarship_subtype_list.length > 0) {
        console.log('Loading from scholarship_subtype_list:', application.scholarship_subtype_list)
        setSelectedSubTypes(prev => ({
          ...prev,
          [application.scholarship_type]: application.scholarship_subtype_list as string[]
        }))
      } else {
        // 如果沒有子類型列表，嘗試從表單資料中獲取
        const formData = application.submitted_form_data || application.form_data || {}
        if (formData.scholarship_subtype_list && formData.scholarship_subtype_list.length > 0) {
          console.log('Loading from form data:', formData.scholarship_subtype_list)
          setSelectedSubTypes(prev => ({
            ...prev,
            [application.scholarship_type]: formData.scholarship_subtype_list as string[]
          }))
        } else {
          // 如果都沒有，設置為空陣列
          console.log('No subtype data found, setting empty array')
          setSelectedSubTypes(prev => ({
            ...prev,
            [application.scholarship_type]: []
          }))
        }
      }
    } else {
      // 如果獎學金只有 general 類型，設置為空陣列（不顯示子類型選擇）
      console.log('Scholarship has only general type, setting empty array')
      setSelectedSubTypes(prev => ({
        ...prev,
        [application.scholarship_type]: []
      }))
    }
    
    // 設置動態表單資料
    setDynamicFormData(existingFormData)
    setDynamicFileData(existingFileData)
    
    // 切換到新增申請頁面
    setActiveTab("new-application")
  }

  // Loading state
  if (isLoadingScholarships) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">
            {locale === "zh" ? "正在載入資料..." : "Loading data..."}
          </p>
          {isLoadingScholarships && (
            <p className="text-sm text-muted-foreground mt-2">
              {locale === "zh" ? "載入獎學金資訊..." : "Loading scholarship information..."}
            </p>
          )}
        </CardContent>
      </Card>
    )
  }

  // Error state
  if (scholarshipsError) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-4" />
          <p className="text-destructive">
            {scholarshipsError}
          </p>
        </CardContent>
      </Card>
    )
  }

  // No eligible scholarships
  if (eligibleScholarships.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-orange-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">
            {locale === "zh" ? "目前沒有符合資格的獎學金" : "No Eligible Scholarships"}
          </h3>
          <p className="text-muted-foreground">
            {locale === "zh"
              ? "很抱歉，您目前沒有符合申請資格的獎學金。請稍後再試或聯繫獎學金辦公室。"
              : "Sorry, you are not currently eligible for any scholarships. Please try again later or contact the scholarship office."}
          </p>
        </CardContent>
      </Card>
    )
  }

  const renderApplicationCard = (application: Application) => (
    <Card key={application.id} className="mb-4">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{application.scholarship_type}</span>
          <Badge variant={getStatusColor(application.status as ApplicationStatus)}>
            {getStatusName(application.status as ApplicationStatus, locale)}
          </Badge>
        </CardTitle>
        <CardDescription>
          {t("applications.submitted_at")}: {application.submitted_at ? new Date(application.submitted_at).toLocaleDateString() : '-'}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ProgressTimeline steps={getApplicationTimeline(application, locale)} />
        {application.status === "draft" && (
          <div className="mt-4 flex justify-end space-x-2">
            <Button variant="outline" onClick={() => handleWithdrawApplication(application.id)}>
              {t("applications.withdraw")}
            </Button>
            <Button onClick={handleSubmitApplication}>
              {t("applications.submit")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )

  return (
    <div className="space-y-6">
      {/* Scholarship Info Cards */}
      {eligibleScholarships.map((scholarship) => {
        const applicationInfo = scholarshipApplicationInfo[scholarship.code]
        const isEligible = Array.isArray(scholarship.eligible_sub_types) && 
          scholarship.eligible_sub_types.length > 0
        
        return (
        <Card 
          key={scholarship.id} 
          className={clsx(
            "border border-gray-100",
            isEligible 
              ? "bg-white hover:border-primary/30 transition-colors" 
              : "bg-gray-50/50 border-gray-100 hover:bg-gray-50/80 transition-colors"
          )}
        >
          <CardHeader className="pb-2">
            {/* Title and Status Badge */}
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-xl">
                  {locale === "zh" ? scholarship.name : (scholarship.name_en || scholarship.name)}
                </CardTitle>
                {isEligible ? (
                  <Badge variant="outline" className="bg-emerald-50 text-emerald-600 border-emerald-100">
                    <Check className="h-3 w-3 mr-1" />
                    {locale === "zh" ? "可申請" : "Eligible"}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="bg-amber-50 text-amber-600 border-amber-100">
                    <AlertTriangle className="h-3 w-3 mr-1" />
                    {locale === "zh" ? "不符合申請資格" : "Not Eligible"}
                  </Badge>
                )}
              </div>
              <Badge variant="outline" className="text-lg px-3 py-1 bg-white">
                {scholarship.amount} {scholarship.currency}
              </Badge>
            </div>

            <CardDescription className="text-sm pb-3">
              {locale === "zh" ? scholarship.description : (scholarship.description_en || scholarship.description)}
            </CardDescription>

            {/* Eligible Programs Section */}
            {scholarship.eligible_sub_types && scholarship.eligible_sub_types.length > 0 && scholarship.eligible_sub_types[0] !== "general" && (
              <div className="mt-3 bg-indigo-50/30 rounded-lg border border-indigo-100/50 divide-y divide-indigo-100/50">
                <div className="px-3 py-2">
                  <p className="text-sm font-medium text-indigo-900">
                    {getTranslation(locale, "scholarship_sections.eligible_programs")}
                  </p>
                </div>
                <div className="px-3 py-2 flex flex-wrap gap-1.5">
                  {scholarship.eligible_sub_types.map((subType) => (
                    <Badge 
                      key={subType} 
                      variant="outline" 
                      className="bg-white text-indigo-600 border-indigo-100 shadow-sm"
                    >
                      {getTranslation(locale, `scholarship_subtypes.${subType}`)}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </CardHeader>

          <CardContent>
            <div className="grid grid-cols-2 gap-6">
              {/* Left Column - Eligibility & Period */}
              <div className="space-y-4">
                {/* 申請資格 */}
                <div className="rounded-lg border border-gray-100 overflow-hidden">
                  <div className="bg-sky-50/50 px-3 py-2 border-b border-gray-100">
                    <div className="flex items-center gap-2">
                      <Info className="h-4 w-4 text-sky-500" />
                      <p className="text-sm font-medium text-sky-700">
                        {getTranslation(locale, "scholarship_sections.eligibility")}
                      </p>
                    </div>
                  </div>
                  <div className="p-3 space-y-3">
                    {/* Basic eligibility tags */}
                    <div className="flex flex-wrap gap-1">
                      {scholarship.passed?.filter(rule => !rule.sub_type).map((rule) => (
                        <Badge 
                          key={rule.rule_id} 
                          variant="outline" 
                          className="bg-emerald-50 text-emerald-600 border-emerald-100"
                        >
                          {getTranslation(locale, `eligibility_tags.${rule.tag}`)}
                        </Badge>
                      ))}
                    </div>

                    {/* Sub-type specific rules */}
                    {["nstc", "moe_1w", "moe_2w"].map(subType => {
                      const rulesForType = scholarship.passed?.filter(rule => rule.sub_type === subType);
                      if (!rulesForType?.length) return null;
                      
                      return (
                        <div key={subType} className="pl-2 border-l-2 border-gray-200">
                          <p className="text-sm text-gray-600 mb-1">
                            {getTranslation(locale, `rule_types.${subType}`)}:
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {rulesForType.map((rule) => (
                              <Badge 
                                key={rule.rule_id} 
                                variant="outline" 
                                className="bg-emerald-50 text-emerald-600 border-emerald-100"
                              >
                                {getTranslation(locale, `eligibility_tags.${rule.tag}`)}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      );
                    })}

                    {/* Warnings */}
                    {scholarship.warnings && scholarship.warnings.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {scholarship.warnings?.map((rule) => (
                          <Badge 
                            key={rule.rule_id} 
                            variant="outline" 
                            className="bg-amber-50 text-amber-600 border-amber-100"
                          >
                            <AlertTriangle className="h-3 w-3 mr-1" />
                            {getTranslation(locale, `eligibility_tags.${rule.tag}`)}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {/* Errors */}
                    {scholarship.errors && scholarship.errors.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {scholarship.errors?.map((rule) => (
                          <Badge 
                            key={rule.rule_id} 
                            variant="outline" 
                            className="bg-rose-50 text-rose-600 border-rose-100"
                          >
                            <AlertTriangle className="h-3 w-3 mr-1" />
                            {getTranslation(locale, `eligibility_tags.${rule.tag}`)}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* 申請期間 */}
                {scholarship.application_start_date && scholarship.application_end_date && (
                  <div className="rounded-lg border border-gray-100 overflow-hidden">
                    <div className="bg-amber-50/50 px-3 py-2 border-b border-gray-100">
                      <div className="flex items-center gap-2">
                        <Calendar className="h-4 w-4 text-amber-500" />
                        <p className="text-sm font-medium text-amber-700">
                          {getTranslation(locale, "scholarship_sections.period")}
                        </p>
                      </div>
                    </div>
                    <div className="p-3">
                      <p className="text-sm text-gray-600">
                        {new Date(scholarship.application_start_date).toLocaleDateString()} - {new Date(scholarship.application_end_date).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Right Column - Application Fields & Documents */}
              <div className="space-y-4">
                {/* Loading State */}
                {applicationInfo?.isLoading && (
                  <div className="rounded-lg border border-gray-100 p-3">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
                      <p className="text-sm font-medium">{locale === "zh" ? "申請資訊" : "Application Info"}</p>
                    </div>
                    <p className="text-sm text-gray-600 mt-2">
                      {locale === "zh" ? "載入中..." : "Loading..."}
                    </p>
                  </div>
                )}

                {/* Error State */}
                {applicationInfo?.error && (
                  <div className="rounded-lg border border-rose-100 bg-rose-50/50 p-3">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-rose-500" />
                      <p className="text-sm font-medium text-rose-700">{locale === "zh" ? "載入錯誤" : "Load Error"}</p>
                    </div>
                    <p className="text-sm text-rose-600 mt-2">{applicationInfo.error}</p>
                    <Button 
                      variant="outline" 
                      size="sm" 
                      onClick={() => fetchScholarshipApplicationInfo(scholarship.code)}
                      className="mt-2"
                    >
                      {locale === "zh" ? "重試" : "Retry"}
                    </Button>
                  </div>
                )}

                {/* Application Fields */}
                {applicationInfo && !applicationInfo.isLoading && !applicationInfo.error && (
                  <div className="rounded-lg border border-gray-100 overflow-hidden">
                    <div className="bg-violet-50/50 px-3 py-2 border-b border-gray-100">
                      <div className="flex items-center gap-2">
                        <Edit className="h-4 w-4 text-violet-500" />
                        <p className="text-sm font-medium text-violet-700">
                          {getTranslation(locale, "scholarship_sections.fields")}
                        </p>
                      </div>
                    </div>
                    <div className="p-3">
                      <div className="flex flex-wrap gap-1.5">
                        {applicationInfo.fields
                          .filter(field => field.is_active)
                          .map((field) => (
                            <Badge key={field.id} variant="outline" className="text-xs bg-white text-gray-600 border-gray-200">
                              {locale === "zh" ? field.field_label : (field.field_label_en || field.field_label)}
                            </Badge>
                          ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Required Documents */}
                {applicationInfo && !applicationInfo.isLoading && !applicationInfo.error && (
                  <div className="rounded-lg border border-gray-100 overflow-hidden">
                    <div className="bg-emerald-50/50 px-3 py-2 border-b border-gray-100">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-emerald-500" />
                        <p className="text-sm font-medium text-emerald-700">
                          {getTranslation(locale, "scholarship_sections.required_docs")}
                        </p>
                      </div>
                    </div>
                    <div className="p-3">
                      <div className="flex flex-wrap gap-1.5">
                        {applicationInfo.documents
                          .filter(doc => doc.is_required && doc.is_active)
                          .map((doc) => (
                            <Badge key={doc.id} variant="outline" className="text-xs bg-white text-gray-600 border-gray-200">
                              {locale === "zh" ? doc.document_name : (doc.document_name_en || doc.document_name)}
                            </Badge>
                          ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Optional Documents */}
                {applicationInfo && !applicationInfo.isLoading && !applicationInfo.error && applicationInfo.documents.filter(doc => !doc.is_required && doc.is_active).length > 0 && (
                  <div className="rounded-lg border border-gray-100 overflow-hidden">
                    <div className="bg-sky-50/50 px-3 py-2 border-b border-gray-100">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-sky-500" />
                        <p className="text-sm font-medium text-sky-700">
                          {getTranslation(locale, "scholarship_sections.optional_docs")}
                        </p>
                      </div>
                    </div>
                    <div className="p-3">
                      <div className="flex flex-wrap gap-1.5">
                        {applicationInfo.documents
                          .filter(doc => !doc.is_required && doc.is_active)
                          .map((doc) => (
                            <Badge key={doc.id} variant="outline" className="text-xs bg-white text-gray-600 border-gray-200">
                              {locale === "zh" ? doc.document_name : (doc.document_name_en || doc.document_name)}
                            </Badge>
                          ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
        )
      })}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList>
          <TabsTrigger value="applications">{locale === "zh" ? "我的申請" : "My Applications"}</TabsTrigger>
          <TabsTrigger value="new-application">{locale === "zh" ? "新增申請" : "New Application"}</TabsTrigger>
          <TabsTrigger value="profile">{locale === "zh" ? "個人資料" : "Profile"}</TabsTrigger>
        </TabsList>

        <TabsContent value="applications" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{locale === "zh" ? "申請記錄" : "Application Records"}</CardTitle>
              <CardDescription>
                {locale === "zh"
                  ? "查看您的獎學金申請狀態與進度"
                  : "View your scholarship application status and progress"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {applicationsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin" />
                </div>
              ) : applicationsError ? (
                <div className="text-destructive text-center py-4">
                  {applicationsError}
                </div>
              ) : applications.length === 0 ? (
                <div className="text-center py-8">
                  <div className="flex flex-col items-center gap-2">
                    <FileText className="h-12 w-12 text-muted-foreground" />
                    <p className="text-lg font-medium text-muted-foreground">
                      {locale === "zh" ? "尚無申請記錄" : "No application records"}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {locale === "zh" 
                        ? "您可以點擊「新增申請」開始申請獎學金" 
                        : "Click 'New Application' to start your scholarship application"}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  {applications.map((app) => (
                    <div key={app.id} className="space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="font-medium">{getScholarshipTypeName(app.scholarship_type)}</h4>
                          <p className="text-sm text-muted-foreground">
                            {locale === "zh" ? "申請編號" : "Application ID"}: {app.app_id || `APP-${app.id}`}
                          </p>
                        </div>
                        <Badge variant={getStatusColor(app.status as ApplicationStatus)}>
                          {getStatusName(app.status as ApplicationStatus, locale)}
                        </Badge>
                      </div>

                      {/* Progress Timeline */}
                      <Card>
                        <CardHeader>
                          <CardTitle className="text-base flex items-center gap-2">
                            <Calendar className="h-4 w-4" />
                            {locale === "zh" ? "審核進度" : "Review Progress"}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <ProgressTimeline steps={getApplicationTimeline(app, locale)} orientation="horizontal" />
                        </CardContent>
                      </Card>

                      <div className="flex gap-2">
                        <Button variant="outline" size="sm" onClick={() => handleViewDetails(app)}>
                          <Eye className="h-4 w-4 mr-1" />
                          {locale === "zh" ? "查看詳情" : "View Details"}
                        </Button>
                        {app.status === "draft" && (
                          <>
                            <Button variant="outline" size="sm" onClick={() => handleEditApplication(app)}>
                              <Edit className="h-4 w-4 mr-1" />
                              {locale === "zh" ? "編輯" : "Edit"}
                            </Button>
                            <Button 
                              variant="outline" 
                              size="sm" 
                              onClick={() => handleDeleteApplication(app.id)}
                              className="text-destructive hover:text-destructive"
                            >
                              <Trash2 className="h-4 w-4 mr-1" />
                              {locale === "zh" ? "刪除草稿" : "Delete Draft"}
                            </Button>
                          </>
                        )}
                        {app.status === "submitted" && (
                          <Button variant="outline" size="sm" onClick={() => handleWithdrawApplication(app.id)}>
                            <Trash2 className="h-4 w-4 mr-1" />
                            {locale === "zh" ? "撤回申請" : "Withdraw"}
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="new-application" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {editingApplication ? (
                  <>
                    <Edit className="h-5 w-5" />
                    {locale === "zh" ? "編輯申請" : "Edit Application"}
                  </>
                ) : (
                  <>
                    <FileText className="h-5 w-5" />
                    {locale === "zh" ? `申請獎學金` : `Apply for Scholarship`}
                  </>
                )}
              </CardTitle>
              <CardDescription>
                {editingApplication ? (
                  locale === "zh" 
                    ? `正在編輯申請編號: ${editingApplication.app_id || `APP-${editingApplication.id}`}` 
                    : `Editing Application ID: ${editingApplication.app_id || `APP-${editingApplication.id}`}`
                ) : (
                  locale === "zh"
                    ? "選擇獎學金類型後，請填寫完整資料並上傳相關文件"
                    : "Please select a scholarship type, complete all information and upload required documents"
                )}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Form fields */}
              <div className="space-y-4">
                <div>
                  <Label htmlFor="scholarship_type">{locale === "zh" ? "獎學金類型" : "Scholarship Type"} *</Label>
                  <Select 
                    value={newApplicationData.scholarship_type} 
                    onValueChange={(value) => {
                      setNewApplicationData(prev => ({ ...prev, scholarship_type: value }))
                      const scholarship = eligibleScholarships.find(s => s.code === value)
                      setSelectedScholarship(scholarship || null)
                      
                      // Initialize selected sub-types if not "general"
                      if (scholarship?.eligible_sub_types && 
                          scholarship.eligible_sub_types[0] !== "general" &&
                          scholarship.eligible_sub_types.length > 0) {
                        setSelectedSubTypes(prev => ({
                          ...prev,
                          [value]: [...scholarship.eligible_sub_types]
                        }))
                      }
                      
                      // Reset dynamic form data when scholarship type changes
                      setDynamicFormData({})
                      setDynamicFileData({})
                      
                      // Clear legacy uploaded files
                      setUploadedFiles({})
                      
                      // Reset terms agreement when scholarship type changes
                      setAgreeTerms(false)
                    }}
                    disabled={editingApplication !== null}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={locale === "zh" ? "選擇獎學金類型" : "Select scholarship type"} />
                    </SelectTrigger>
                    <SelectContent>
                      {eligibleScholarships
                        .filter(scholarship => 
                          Array.isArray(scholarship.eligible_sub_types) && 
                          scholarship.eligible_sub_types.length > 0
                        )
                        .map((scholarship) => (
                          <SelectItem key={scholarship.id} value={scholarship.code}>
                            {scholarship.name}
                          </SelectItem>
                        ))}
                    </SelectContent>
                  </Select>
                  {editingApplication && (
                    <p className="text-sm text-muted-foreground mt-1">
                      {locale === "zh" ? "編輯模式下無法更改獎學金類型" : "Cannot change scholarship type in edit mode"}
                    </p>
                  )}
                </div>

                {/* Sub-type selection UI */}
                {newApplicationData.scholarship_type && selectedScholarship?.eligible_sub_types && 
                 selectedScholarship.eligible_sub_types.length > 0 && 
                 selectedScholarship.eligible_sub_types[0] !== "general" && (
                  <div className="space-y-2">
                    <Label>{locale === "zh" ? "申請欄位" : "Application Fields"} *</Label>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {(() => {
                        console.log('Debug sub-type selection:', {
                          scholarshipType: newApplicationData.scholarship_type,
                          eligibleSubTypes: selectedScholarship.eligible_sub_types,
                          selectedSubTypes: selectedSubTypes[newApplicationData.scholarship_type],
                          editingApplication: editingApplication?.id
                        })
                        return null
                      })()}
                      {selectedScholarship.eligible_sub_types.map((subType) => {
                        const isSelected = selectedSubTypes[newApplicationData.scholarship_type]?.includes(subType)
                        console.log(`Subtype ${subType} isSelected:`, isSelected)
                        return (
                          <Card
                            key={subType}
                            className={clsx(
                              "relative cursor-pointer transition-all duration-200",
                              "hover:border-primary/50",
                              isSelected && "border-primary bg-primary/5"
                            )}
                            onClick={() => {
                              setSelectedSubTypes(prev => {
                                const currentSelected = prev[newApplicationData.scholarship_type] || []
                                const newSelected = isSelected
                                  ? currentSelected.filter(t => t !== subType)
                                  : [...currentSelected, subType]
                                return {
                                  ...prev,
                                  [newApplicationData.scholarship_type]: newSelected
                                }
                              })
                            }}
                          >
                            <div className="absolute top-2 right-2 w-4 h-4 rounded-full border-2 flex items-center justify-center">
                              {isSelected && (
                                <div className="w-2 h-2 rounded-full bg-primary" />
                              )}
                            </div>
                            <CardContent className="p-4">
                              <p className="text-sm font-medium">
                                {getTranslation(locale, `scholarship_subtypes.${subType}`)}
                              </p>
                            </CardContent>
                          </Card>
                        )
                      })}
                    </div>
                    {selectedSubTypes[newApplicationData.scholarship_type]?.length === 0 && (
                      <p className="text-sm text-destructive">
                        {locale === "zh" ? "請至少選擇一個申請項目" : "Please select at least one item"}
                      </p>
                    )}
                  </div>
                )}

                {/* Dynamic Application Form */}
                {newApplicationData.scholarship_type && (
                  <DynamicApplicationForm
                    scholarshipType={newApplicationData.scholarship_type}
                    locale={locale}
                    onFieldChange={(fieldName, value) => {
                      setDynamicFormData(prev => ({ ...prev, [fieldName]: value }))
                    }}
                    onFileChange={(documentType, files) => {
                      setDynamicFileData(prev => ({ ...prev, [documentType]: files }))
                    }}
                    initialValues={dynamicFormData}
                    initialFiles={dynamicFileData}
                    selectedSubTypes={selectedSubTypes[newApplicationData.scholarship_type] || []}
                  />
                )}
              </div>

              {/* Progress indicator */}
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span>{locale === "zh" ? "完成進度" : "Progress"}</span>
                  <span>{formProgress}%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div 
                    className="bg-blue-600 h-2 rounded-full transition-all duration-300" 
                    style={{ width: `${formProgress}%` }}
                  ></div>
                </div>
              </div>

              {/* Terms Agreement */}
              <div className="flex items-center space-x-2 pt-4">
                <Checkbox
                  id="agree_terms"
                  checked={agreeTerms}
                  onCheckedChange={(checked) => setAgreeTerms(checked as boolean)}
                />
                <Label htmlFor="agree_terms" className="text-sm">
                  {locale === "zh"
                    ? `我已閱讀並同意${selectedScholarship?.name || '獎學金'}申請相關條款與規定`
                    : `I have read and agree to the terms and conditions for ${selectedScholarship?.name || 'scholarship'} application`}
                </Label>
              </div>

              {/* Action buttons */}
              <div className="flex gap-3 pt-4">
                {editingApplication && (
                  <Button 
                    variant="outline"
                    onClick={handleCancelEdit}
                    disabled={isSubmitting}
                    className="flex-1"
                  >
                    {locale === "zh" ? "取消編輯" : "Cancel Edit"}
                  </Button>
                )}
                
                <Button 
                  variant="outline"
                  onClick={handleSaveDraft}
                  disabled={isSubmitting}
                  className="flex-1"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {locale === "zh" ? "儲存中..." : "Saving..."}
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4 mr-2" />
                      {editingApplication ? (
                        locale === "zh" ? "更新草稿" : "Update Draft"
                      ) : (
                        locale === "zh" ? "儲存草稿" : "Save Draft"
                      )}
                    </>
                  )}
                </Button>
                
                <Button 
                  onClick={handleSubmitApplication}
                  disabled={isSubmitting || formProgress < 100}
                  className="flex-1 nycu-gradient text-white"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      {editingApplication ? (
                        locale === "zh" ? "更新中..." : "Updating..."
                      ) : (
                        locale === "zh" ? "提交中..." : "Submitting..."
                      )}
                    </>
                  ) : (
                    editingApplication ? (
                      locale === "zh" ? "更新申請" : "Update Application"
                    ) : (
                      locale === "zh" ? "提交申請" : "Submit Application"
                    )
                  )}
                </Button>
              </div>
              
              {formProgress < 100 && (
                <div className="text-center">
                  <p className="text-sm text-muted-foreground">
                    {locale === "zh" 
                      ? `請完成所有必填項目 (${formProgress}%)` 
                      : `Please complete all required fields (${formProgress}%)`
                    }
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="profile" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>{locale === "zh" ? "個人資料" : "Personal Information"}</CardTitle>
              <CardDescription>
                {locale === "zh"
                  ? "管理您的個人資訊與學籍資料"
                  : "Manage your personal information and academic records"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>{locale === "zh" ? "學號" : "Student ID"}</Label>
                  <Input value={user.id} disabled />
                </div>
                <div>
                  <Label>{locale === "zh" ? "姓名" : "Name"}</Label>
                  <Input value={user.name} disabled />
                </div>
                <div>
                  <Label>{locale === "zh" ? "電子郵件" : "Email"}</Label>
                  <Input value={user.email} disabled />
                </div>
                <div>
                  <Label>{locale === "zh" ? "學生類型" : "Student Type"}</Label>
                  <Input
                    value={
                      user.studentType === "undergraduate"
                        ? locale === "zh"
                          ? "學士"
                          : "Undergraduate"
                        : user.studentType === "phd"
                          ? locale === "zh"
                            ? "博士"
                            : "PhD"
                          : locale === "zh"
                            ? "錯誤"
                            : "Error"
                    }
                    disabled
                  />
                </div>
              </div>

              <div className="pt-4">
                <Button variant="outline">
                  <Edit className="h-4 w-4 mr-2" />
                  {locale === "zh" ? "更新聯絡資訊" : "Update Contact Information"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* 申請詳情對話框 */}
      <ApplicationDetailDialog
        application={selectedApplicationForDetails}
        isOpen={isDetailsDialogOpen}
        onClose={() => setIsDetailsDialogOpen(false)}
        locale={locale}
      />

    </div>
  )
}
