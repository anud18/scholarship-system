"use client"

import { useState, useEffect } from "react"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { ProgressTimeline } from "@/components/progress-timeline"
import { FilePreviewDialog } from "@/components/file-preview-dialog"
import { FileText, Eye, Loader2 } from "lucide-react"
import { Locale } from "@/lib/validators"
import { Application } from "@/lib/api"
import api from "@/lib/api"
import { ApplicationFormDataDisplay } from "@/components/application-form-data-display"
import { 
  getApplicationTimeline, 
  getStatusColor, 
  getStatusName, 
  getDocumentLabel, 
  fetchApplicationFiles,
  ApplicationStatus,
  formatFieldName
} from "@/lib/utils/application-helpers"

interface ApplicationDetailDialogProps {
  isOpen: boolean
  onClose: () => void
  application: Application | null
  locale: Locale
}

export function ApplicationDetailDialog({ 
  isOpen, 
  onClose, 
  application, 
  locale 
}: ApplicationDetailDialogProps) {
  const [applicationFiles, setApplicationFiles] = useState<any[]>([])
  const [isLoadingFiles, setIsLoadingFiles] = useState(false)
  const [previewFile, setPreviewFile] = useState<{ url: string; filename: string; type: string; downloadUrl?: string } | null>(null)
  const [isPreviewDialogOpen, setIsPreviewDialogOpen] = useState(false)
  const [documentLabels, setDocumentLabels] = useState<{[key: string]: { zh?: string, en?: string }}>({})
  const [isLoadingLabels, setIsLoadingLabels] = useState(false)
  const [fieldLabels, setFieldLabels] = useState<{[key: string]: { zh?: string, en?: string }}>({})
  const [applicationFields, setApplicationFields] = useState<string[]>([])
  const [isLoadingFields, setIsLoadingFields] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 獲取欄位標籤（優先使用動態標籤，後備使用靜態標籤）
  const getFieldLabel = (fieldName: string, locale: Locale, fieldLabels?: {[key: string]: { zh?: string, en?: string }}) => {
    if (fieldLabels && fieldLabels[fieldName]) {
      return locale === "zh" ? fieldLabels[fieldName].zh : (fieldLabels[fieldName].en || fieldLabels[fieldName].zh || fieldName)
    }
    return formatFieldName(fieldName, locale)
  }

  // 載入申請文件
  useEffect(() => {
    if (isOpen && application) {
      loadApplicationFiles()
      loadFormConfig()
    }
  }, [isOpen, application])

  // 載入表單配置（包含文件標籤和欄位標籤）
  const loadFormConfig = async () => {
    if (!application) return
    
    setIsLoadingLabels(true)
    setIsLoadingFields(true)
    setError(null)
    try {
      // 根據 scholarship_type_id 從後端獲取對應的 scholarship_type
      let scholarshipType = application.scholarship_type
      
      if (!scholarshipType && application.scholarship_type_id) {
        try {
          // 從後端獲取獎學金類型信息
          const scholarshipResponse = await api.scholarships.getById(application.scholarship_type_id)
          if (scholarshipResponse.success && scholarshipResponse.data) {
            scholarshipType = scholarshipResponse.data.code
          } else {
            const errorMsg = `無法獲取獎學金類型信息: ${scholarshipResponse.message}`
            console.error(errorMsg)
            setError(errorMsg)
            setDocumentLabels({})
            setFieldLabels({})
            setApplicationFields([])
            setIsLoadingLabels(false)
            setIsLoadingFields(false)
            return
          }
        } catch (error) {
          const errorMsg = `獲取獎學金類型時發生錯誤: ${error instanceof Error ? error.message : '未知錯誤'}`
          console.error(errorMsg)
          setError(errorMsg)
          setDocumentLabels({})
          setFieldLabels({})
          setApplicationFields([])
          setIsLoadingLabels(false)
          setIsLoadingFields(false)
          return
        }
      }
      
      if (!scholarshipType) {
        const errorMsg = '無法確定獎學金類型'
        console.error(errorMsg)
        setError(errorMsg)
        setDocumentLabels({})
        setFieldLabels({})
        setApplicationFields([])
        setIsLoadingLabels(false)
        setIsLoadingFields(false)
        return
      }
      
      const response = await api.applicationFields.getFormConfig(scholarshipType)
      if (response.success && response.data) {
        // 處理文件標籤
        if (response.data.documents) {
          const labels: {[key: string]: { zh?: string, en?: string }} = {}
          response.data.documents.forEach(doc => {
            labels[doc.document_name] = {
              zh: doc.document_name,
              en: doc.document_name_en || doc.document_name
            }
          })
          setDocumentLabels(labels)
        }
        
        // 處理欄位標籤
        if (response.data.fields) {
          const fieldLabels: {[key: string]: { zh?: string, en?: string }} = {}
          const fieldNames: string[] = []
          
          response.data.fields.forEach(field => {
            fieldLabels[field.field_name] = {
              zh: field.field_label,
              en: field.field_label_en || field.field_label
            }
            fieldNames.push(field.field_name)
          })
          
          setFieldLabels(fieldLabels)
          setApplicationFields(fieldNames)
        }
      } else {
        const errorMsg = `無法載入表單配置: ${response.message}`
        console.error(errorMsg)
        setError(errorMsg)
        setDocumentLabels({})
        setFieldLabels({})
        setApplicationFields([])
      }
    } catch (error) {
      const errorMsg = `載入表單配置時發生錯誤: ${error instanceof Error ? error.message : '未知錯誤'}`
      console.error(errorMsg)
      setError(errorMsg)
      setDocumentLabels({})
      setFieldLabels({})
      setApplicationFields([])
    } finally {
      setIsLoadingLabels(false)
      setIsLoadingFields(false)
    }
  }

  // 載入申請文件 - 現在直接從 submitted_form_data.documents 中獲取
  const loadApplicationFiles = async () => {
    if (!application) return
    
    setIsLoadingFiles(true)
    try {
      // 直接從 application.submitted_form_data.documents 中獲取文件
      if (application.submitted_form_data?.documents) {
        // 將 documents 轉換為 ApplicationFile 格式以保持向後兼容
        const files = application.submitted_form_data.documents.map((doc: any) => ({
          id: doc.file_id,
          filename: doc.filename,
          original_filename: doc.original_filename,
          file_size: doc.file_size,
          mime_type: doc.mime_type,
          file_type: doc.document_type,
          file_path: doc.file_path,
          download_url: doc.download_url,
          is_verified: doc.is_verified,
          uploaded_at: doc.upload_time
        }))
        setApplicationFiles(files)
      } else {
        // 如果沒有 documents，嘗試使用舊的 fetchApplicationFiles 方法（向後兼容）
        const files = await fetchApplicationFiles(application.id)
        setApplicationFiles(files)
      }
    } catch (error) {
      console.error('Failed to load application files:', error)
      setApplicationFiles([])
    } finally {
      setIsLoadingFiles(false)
    }
  }

  const handleFilePreview = (file: any) => {
    const filename = file.filename || file.original_filename
    
    // 檢查是否有文件路徑
    if (!file.file_path) {
      console.error('No file path available for preview')
      return
    }
    
    // 從後端URL中提取token
    const urlParts = file.file_path.split('?')
    if (urlParts.length < 2) {
      console.error('Invalid file URL format')
      return
    }
    
    const urlParams = new URLSearchParams(urlParts[1])
    const token = urlParams.get('token')
    
    if (!token) {
      console.error('No token found in file URL')
      return
    }
    
    // 構建前端預覽URL，包含token參數
    const previewUrl = `/api/v1/preview?fileId=${file.id}&filename=${encodeURIComponent(filename)}&type=${encodeURIComponent(file.file_type)}&applicationId=${application?.id}&token=${token}`
    
    // 判斷文件類型
    let fileType = 'other'
    if (filename.toLowerCase().endsWith('.pdf')) {
      fileType = 'application/pdf'
    } else if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'].some(ext => filename.toLowerCase().endsWith(ext))) {
      fileType = 'image'
    }
    
    console.log('Opening file preview:', {
      filename,
      fileType,
      previewUrl,
      hasToken: !!token
    })
    
    // 構建下載URL
    const downloadUrl = file.download_url || file.file_path
    
    setPreviewFile({
      url: previewUrl,
      filename: filename,
      type: fileType,
      downloadUrl: downloadUrl
    })
    setIsPreviewDialogOpen(true)
  }

  // 分離動態欄位和基本欄位
  const separateFormData = (formData: Record<string, any>) => {
    const dynamicFields: Record<string, any> = {}
    const basicFields: Record<string, any> = {}
    
    // 處理後端的 submitted_form_data.fields 結構
    if (formData.submitted_form_data && formData.submitted_form_data.fields) {
      // 後端結構：{ submitted_form_data: { fields: { field_id: { value: "..." } } } }
      Object.entries(formData.submitted_form_data.fields).forEach(([fieldId, fieldData]: [string, any]) => {
        if (fieldData && typeof fieldData === 'object' && 'value' in fieldData) {
          const value = fieldData.value
          if (value && value !== '' && fieldId !== 'files' && fieldId !== 'agree_terms') {
            if (applicationFields.includes(fieldId)) {
              dynamicFields[fieldId] = value
            } else {
              basicFields[fieldId] = value
            }
          }
        }
      })
    } else if (formData.fields) {
      // 直接處理 fields 結構
      Object.entries(formData.fields).forEach(([fieldId, fieldData]: [string, any]) => {
        if (fieldData && typeof fieldData === 'object' && 'value' in fieldData) {
          const value = fieldData.value
          if (value && value !== '' && fieldId !== 'files' && fieldId !== 'agree_terms') {
            if (applicationFields.includes(fieldId)) {
              dynamicFields[fieldId] = value
            } else {
              basicFields[fieldId] = value
            }
          }
        }
      })
    } else {
      // 前端結構：{ field_name: value }
      Object.entries(formData).forEach(([key, value]) => {
        if (!value || value === '' || key === 'files' || key === 'agree_terms') {
          return
        }
        
        if (applicationFields.includes(key)) {
          dynamicFields[key] = value
        } else {
          basicFields[key] = value
        }
      })
    }
    
    return { dynamicFields, basicFields }
  }

  if (!application) return null

  const { dynamicFields, basicFields } = (() => {
    // 優先使用 submitted_form_data，如果沒有則使用 form_data
    const dataToProcess = application.submitted_form_data || application.form_data || {}
    return separateFormData(dataToProcess)
  })()

  return (
    <>
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {locale === "zh" ? "申請詳情" : "Application Details"}
            </DialogTitle>
            <DialogDescription>
              <span>
                {locale === "zh" ? "申請編號" : "Application ID"}: {application.app_id || `APP-${application.id}`}
              </span>
            </DialogDescription>
          </DialogHeader>
          
          <div className="space-y-6">
            {/* 基本資訊 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">{locale === "zh" ? "基本資訊" : "Basic Information"}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="font-medium">{locale === "zh" ? "申請者" : "Applicant"}</Label>
                    <p className="text-sm">{application.student_name || application.student_id || "N/A"}</p>
                  </div>
                  <div>
                    <Label className="font-medium">{locale === "zh" ? "學號" : "Student ID"}</Label>
                    <p className="text-sm">{application.student_no || application.student_id || "N/A"}</p>
                  </div>
                  <div>
                    <Label className="font-medium">{locale === "zh" ? "獎學金類型" : "Scholarship Type"}</Label>
                    <p className="text-sm">{application.scholarship_type}</p>
                  </div>
                  <div>
                    <Label className="font-medium">{locale === "zh" ? "申請狀態" : "Status"}</Label>
                    <Badge variant={getStatusColor(application.status as ApplicationStatus)}>
                      {getStatusName(application.status as ApplicationStatus, locale)}
                    </Badge>
                  </div>
                  <div>
                    <Label className="font-medium">{locale === "zh" ? "建立時間" : "Created At"}</Label>
                    <p className="text-sm">{new Date(application.created_at).toLocaleDateString(locale === "zh" ? "zh-TW" : "en-US")}</p>
                  </div>
                  {application.submitted_at && (
                    <div>
                      <Label className="font-medium">{locale === "zh" ? "提交時間" : "Submitted At"}</Label>
                      <p className="text-sm">{new Date(application.submitted_at).toLocaleDateString(locale === "zh" ? "zh-TW" : "en-US")}</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* 學術資訊 */}
            {(application.gpa || application.class_ranking_percent || application.dept_ranking_percent) && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">{locale === "zh" ? "學術資訊" : "Academic Information"}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-3 gap-4">
                    {application.gpa && (
                      <div>
                        <Label className="font-medium">{locale === "zh" ? "GPA" : "GPA"}</Label>
                        <p className="text-sm">{application.gpa}</p>
                      </div>
                    )}
                    {application.class_ranking_percent && (
                      <div>
                        <Label className="font-medium">{locale === "zh" ? "班級排名" : "Class Ranking"}</Label>
                        <p className="text-sm">{application.class_ranking_percent}%</p>
                      </div>
                    )}
                    {application.dept_ranking_percent && (
                      <div>
                        <Label className="font-medium">{locale === "zh" ? "系所排名" : "Department Ranking"}</Label>
                        <p className="text-sm">{application.dept_ranking_percent}%</p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 審核進度 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">{locale === "zh" ? "審核進度" : "Review Progress"}</CardTitle>
              </CardHeader>
              <CardContent>
                <ProgressTimeline steps={getApplicationTimeline(application, locale)} />
              </CardContent>
            </Card>

            {/* 動態申請欄位 - 放在上方 */}
            {Object.keys(dynamicFields).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">{locale === "zh" ? "申請欄位" : "Application Fields"}</CardTitle>
                </CardHeader>
                <CardContent>
                  {error ? (
                    <Alert variant="destructive">
                      <AlertDescription>
                        {locale === "zh" ? "載入失敗" : "Loading failed"}: {error}
                        <Button 
                          variant="outline" 
                          size="sm" 
                          className="mt-2 ml-2"
                          onClick={() => {
                            setError(null)
                            loadFormConfig()
                          }}
                        >
                          {locale === "zh" ? "重試" : "Retry"}
                        </Button>
                      </AlertDescription>
                    </Alert>
                  ) : isLoadingFields ? (
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span className="text-sm text-muted-foreground">
                        {locale === "zh" ? "載入申請欄位中..." : "Loading application fields..."}
                      </span>
                    </div>
                  ) : (
                    <ApplicationFormDataDisplay formData={application} locale={locale} fieldLabels={fieldLabels} />
                  )}
                </CardContent>
              </Card>
            )}

            {/* 申請表單欄位 */}
            {Object.keys(basicFields).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">{locale === "zh" ? "申請表單欄位" : "Application Form Fields"}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-3">
                    {Object.entries(basicFields).map(([key, value]) => {
                      return (
                        <div key={key} className="flex flex-col space-y-1 p-2 bg-slate-50 rounded-md">
                          <Label className="text-xs font-medium text-gray-600">
                            {getFieldLabel(key, locale, fieldLabels)}
                          </Label>
                          <p className="text-sm text-gray-800">
                            {typeof value === 'string' && value.length > 50 
                              ? `${value.substring(0, 50)}...` 
                              : String(value)
                            }
                          </p>
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 個人陳述 */}
            {application.personal_statement && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">{locale === "zh" ? "個人陳述" : "Personal Statement"}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm p-2 bg-muted rounded">{application.personal_statement}</p>
                </CardContent>
              </Card>
            )}

            {/* 已上傳文件 */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">{locale === "zh" ? "已上傳文件" : "Uploaded Files"}</CardTitle>
              </CardHeader>
              <CardContent>
                {isLoadingFiles ? (
                  <div className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span className="text-sm text-muted-foreground">
                      {locale === "zh" ? "載入文件中..." : "Loading files..."}
                    </span>
                  </div>
                ) : applicationFiles.length > 0 ? (
                  <div className="space-y-2">
                    {applicationFiles.map((file: any, index: number) => (
                      <div key={file.id || index} className="flex items-center justify-between p-2 bg-muted rounded-md">
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4" />
                          <div>
                            <p className="text-sm font-medium">{file.filename || file.original_filename}</p>
                            <p className="text-xs text-muted-foreground">
                              {file.file_type ? getDocumentLabel(file.file_type, locale, documentLabels[file.file_type]) : 'Other'} • 
                              {file.file_size ? ` ${Math.round(file.file_size / 1024)}KB` : ''}
                            </p>
                          </div>
                        </div>
                        {file.file_path && (
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={() => handleFilePreview(file)}
                          >
                            <Eye className="h-4 w-4 mr-1" />
                            {locale === "zh" ? "預覽" : "Preview"}
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    {locale === "zh" ? "尚未上傳任何文件" : "No files uploaded yet"}
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </DialogContent>
      </Dialog>

      {/* 文件預覽對話框 */}
      <FilePreviewDialog
        isOpen={isPreviewDialogOpen}
        onClose={() => setIsPreviewDialogOpen(false)}
        file={previewFile}
        locale={locale}
      />
    </>
  )
} 