'use client'

import React, { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { useToast } from "@/hooks/use-toast"
import api, { type UserResponse } from '@/lib/api'
import {
  validateAdvisorInfo,
  validateBankInfo,
  validateAdvisorEmail,
  sanitizeAdvisorInfo,
  sanitizeBankInfo
} from '@/lib/validations/user-profile'
import {
  User,
  Building2,
  Phone,
  Mail,
  MapPin,
  Upload,
  Save,
  Eye,
  EyeOff,
  Calendar,
  AlertCircle,
  CheckCircle,
  Camera,
  X,
  History,
  School,
  CreditCard
} from 'lucide-react'
import { FileUpload } from "@/components/file-upload"
import { FilePreviewDialog } from "@/components/file-preview-dialog"
import { useLanguagePreference } from "@/hooks/use-language-preference"
import { getTranslation } from "@/lib/i18n"

interface UserProfile {
  id: number
  user_id: number
  bank_code?: string
  account_number?: string
  bank_document_photo_url?: string
  advisor_name?: string
  advisor_email?: string
  advisor_nycu_id?: string
  preferred_language: string
  has_complete_bank_info: boolean
  has_advisor_info: boolean
  profile_completion_percentage: number
  created_at: string
  updated_at: string
}

interface CompleteUserProfile {
  user_info: UserResponse
  profile: UserProfile | null
  student_info?: any
}

interface ProfileHistory {
  id: number
  field_name: string
  old_value?: string
  new_value?: string
  change_reason?: string
  changed_at: string
}

export default function UserProfileManagement() {
  const [profile, setProfile] = useState<CompleteUserProfile | null>(null)
  const [editingProfile, setEditingProfile] = useState<Partial<UserProfile>>({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploadingBankDoc, setUploadingBankDoc] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState<ProfileHistory[]>([])
  const [activeTab, setActiveTab] = useState('overview')
  const [bankDocumentFiles, setBankDocumentFiles] = useState<File[]>([])
  const [previewFile, setPreviewFile] = useState<{
    url: string
    filename: string
    type: string
    downloadUrl?: string
  } | null>(null)
  const [showPreview, setShowPreview] = useState(false)

  // Validation states
  const [advisorErrors, setAdvisorErrors] = useState<string[]>([])
  const [bankErrors, setBankErrors] = useState<string[]>([])
  const [emailValidationError, setEmailValidationError] = useState<string>('')

  const { toast } = useToast()

  // Language preference and translation
  const { locale } = useLanguagePreference("student")
  const t = (key: string) => getTranslation(locale, key)

  useEffect(() => {
    loadProfile()
  }, [])

  const loadProfile = async () => {
    try {
      const response = await api.userProfiles.getMyProfile()
      console.log('Profile response:', response) // 調試用

      if (response.success && response.data) {
        setProfile(response.data)
        if (response.data.profile) {
          setEditingProfile(response.data.profile)
        } else {
          // 沒有個人資料時初始化空的編輯資料
          setEditingProfile({
            preferred_language: 'zh-TW'
          })
        }
      } else {
        // 如果 API 返回失敗，顯示錯誤但不阻止頁面渲染
        console.warn('Profile API returned error:', response.message)
        toast({
          title: t("profile_management.update_success"),
          description: response.message || t("profile_management.profile_may_not_exist"),
          variant: "default"
        })

        // 設置基本的用戶資料結構，即使沒有完整的個人資料
        setProfile({
          user_info: {
            id: 0,
            nycu_id: "",
            name: "",
            email: "",
            role: 'student',
            created_at: new Date().toISOString(),
            user_type: "student",
            status: "",
            dept_code: "",
            dept_name: "",
            last_login_at: ""
          },
          profile: null,
          student_info: null
        })
        setEditingProfile({
          preferred_language: 'zh-TW'
        })
      }
    } catch (error: any) {
      console.error('Load profile error:', error)

      // 網絡錯誤或其他嚴重錯誤
      if (error.name === 'TypeError' && error.message.includes('fetch')) {
        toast({
          title: t("profile_management.connection_error"),
          description: t("profile_management.connection_error_desc"),
          variant: "destructive"
        })
      } else {
        toast({
          title: t("profile_management.load_error"),
          description: error.message || t("profile_management.load_profile_error"),
          variant: "destructive"
        })
      }

      // 即使發生錯誤也設置基本結構
      setProfile({
        user_info: {
          id: 0,
          nycu_id: "",
          name: "",
          email: "",
          role: 'student',
          created_at: new Date().toISOString(),
          user_type: "student",
          status: "",
          dept_code: "",
          dept_name: "",
          last_login_at: ""
        },
        profile: null,
        student_info: null
      })
      setEditingProfile({
        preferred_language: 'zh-TW'
      })
    } finally {
      setLoading(false)
    }
  }

  // Validation functions
  const validateAdvisorData = () => {
    const advisorData = {
      advisor_name: editingProfile.advisor_name,
      advisor_email: editingProfile.advisor_email,
      advisor_nycu_id: editingProfile.advisor_nycu_id
    }

    const validation = validateAdvisorInfo(advisorData)
    setAdvisorErrors(validation.errors)
    return validation.isValid
  }

  const validateBankData = () => {
    const bankData = {
      bank_code: editingProfile.bank_code,
      account_number: editingProfile.account_number
    }

    const validation = validateBankInfo(bankData)
    setBankErrors(validation.errors)
    return validation.isValid
  }

  // Real-time email validation
  const handleAdvisorEmailChange = (email: string) => {
    setEditingProfile({
      ...editingProfile,
      advisor_email: email
    })

    // Clear previous errors
    setEmailValidationError('')
    if (advisorErrors.length > 0) {
      setAdvisorErrors([])
    }

    // Only validate if user has entered something
    if (email.trim() !== '') {
      const validation = validateAdvisorEmail(email)
      if (!validation.isValid) {
        setEmailValidationError(validation.errors[0] || '')
      }
    }
  }

  const handleSave = async (section: string) => {
    if (!editingProfile) return

    // Validate data before saving
    let isValid = true
    if (section === 'advisor') {
      isValid = validateAdvisorData()
    } else if (section === 'bank') {
      isValid = validateBankData()
    }

    if (!isValid) {
      toast({
        title: t("profile_management.validation_failed"),
        description: t("profile_management.validation_failed_desc"),
        variant: "destructive"
      })
      return
    }

    setSaving(true)
    try {
      let endpoint = '/user-profiles/me'
      let data: any = {}

      switch (section) {
        case 'bank':
          endpoint = '/user-profiles/me/bank-info'
          const bankData = sanitizeBankInfo({
            bank_code: editingProfile.bank_code,
            account_number: editingProfile.account_number
          })
          data = {
            ...bankData,
            change_reason: "Bank account information updated by user"
          }
          break
        case 'advisor':
          endpoint = '/user-profiles/me/advisor-info'
          const advisorData = sanitizeAdvisorInfo({
            advisor_name: editingProfile.advisor_name,
            advisor_email: editingProfile.advisor_email,
            advisor_nycu_id: editingProfile.advisor_nycu_id
          })
          data = {
            ...advisorData,
            change_reason: "Advisor information updated by user"
          }
          break
        default:
          data = editingProfile
      }

      let response
      switch (section) {
        case 'bank':
          response = await api.userProfiles.updateBankInfo(data)
          break
        case 'advisor':
          response = await api.userProfiles.updateAdvisorInfo(data)
          break
        default:
          response = await api.userProfiles.updateProfile(editingProfile)
      }

      if (!response.success) {
        throw new Error(response.message || 'Update failed')
      }

      toast({
        title: t("profile_management.update_success"),
        description: t("profile_management.profile_updated"),
      })

      await loadProfile()
    } catch (error: any) {
      toast({
        title: t("profile_management.update_failed"),
        description: error.response?.data?.detail || t("profile_management.update_profile_error"),
        variant: "destructive"
      })
    } finally {
      setSaving(false)
    }
  }

  const handleBankDocumentFilesChange = (files: File[]) => {
    setBankDocumentFiles(files)
  }

  const handleBankDocumentUpload = async () => {
    if (bankDocumentFiles.length === 0) {
      toast({
        title: t("profile_management.select_file"),
        description: t("profile_management.select_file_desc"),
        variant: "destructive"
      })
      return
    }

    const file = bankDocumentFiles[0] // 只處理第一個文件，因為銀行文件通常只要一個

    if (file.size > 10 * 1024 * 1024) {
      toast({
        title: t("profile_management.file_too_large"),
        description: t("profile_management.file_size_error"),
        variant: "destructive"
      })
      return
    }

    setUploadingBankDoc(true)
    try {
      const response = await api.userProfiles.uploadBankDocumentFile(file)

      if (!response.success) {
        throw new Error(response.message || 'Upload failed')
      }

      toast({
        title: t("profile_management.update_success"),
        description: t("profile_management.document_uploaded_success"),
      })

      // 清空已選擇的文件
      setBankDocumentFiles([])
      await loadProfile()
    } catch (error: any) {
      toast({
        title: t("profile_management.upload_failed"),
        description: error.response?.data?.detail || t("profile_management.upload_error"),
        variant: "destructive"
      })
    } finally {
      setUploadingBankDoc(false)
    }
  }

  const handleDeleteBankDocument = async () => {
    try {
      const response = await api.userProfiles.deleteBankDocument()

      if (response.success) {
        toast({
          title: t("profile_management.update_success"),
          description: t("profile_management.document_deleted"),
        })
        await loadProfile()
      } else {
        throw new Error(response.message || 'Delete failed')
      }
    } catch (error: any) {
      toast({
        title: t("profile_management.delete_failed"),
        description: error.message || t("profile_management.delete_error"),
        variant: "destructive"
      })
    }
  }

  const handlePreviewBankDocument = () => {
    if (!profile?.profile?.bank_document_photo_url) return

    // 從銀行文件 URL 提取檔名和 token
    const documentUrl = profile.profile.bank_document_photo_url
    const filename = documentUrl.split('/').pop()?.split('?')[0] || 'bank_document'

    // 從 URL 中提取 token（如果有的話）
    let token = ''
    const urlParts = documentUrl.split('?')
    if (urlParts.length > 1) {
      const urlParams = new URLSearchParams(urlParts[1])
      token = urlParams.get('token') || ''
    }

    // 如果 URL 中沒有 token，嘗試從存儲中獲取
    if (!token) {
      token = localStorage.getItem('auth_token') ||
              localStorage.getItem('token') ||
              sessionStorage.getItem('auth_token') ||
              sessionStorage.getItem('token') ||
              'eyJhbGciOiJIUzI' // 預設 token
    }

    // 對於個人資料的銀行文件，使用檔名作為 fileId
    const fileId = filename
    const fileType = encodeURIComponent('bank_document')
    // 對於個人資料，使用用戶 ID 作為標識符，而不是 applicationId
    const userId = profile.user_info.id || 0

    // 建立預覽 URL，使用前端路由而不是完整的外部 URL
    const previewUrl = `/api/v1/preview?fileId=${fileId}&filename=${encodeURIComponent(filename)}&type=${fileType}&userId=${userId}&token=${token}`

    console.log('Preview URL:', previewUrl) // 用於調試

    // 判斷文件類型
    let fileType_display = 'other'
    if (filename.toLowerCase().endsWith('.pdf')) {
      fileType_display = 'application/pdf'
    } else if (['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'].some(ext => filename.toLowerCase().endsWith(ext))) {
      fileType_display = 'image'
    }

    // 設定預覽文件資訊
    setPreviewFile({
      url: previewUrl,
      filename: filename,
      type: fileType_display,
      downloadUrl: documentUrl // 使用原始的文件 URL 作為下載連結
    })

    setShowPreview(true)
  }

  const handleClosePreview = () => {
    setShowPreview(false)
    setPreviewFile(null)
  }

  const loadHistory = async () => {
    try {
      const response = await api.userProfiles.getHistory()

      if (response.success && response.data) {
        setHistory(response.data)
        setShowHistory(true)
      } else {
        throw new Error(response.message || 'Failed to load history')
      }
    } catch (error: any) {
      toast({
        title: t("profile_management.load_error"),
        description: error.message || t("profile_management.load_history_error"),
        variant: "destructive"
      })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg">{t("profile_management.loading")}</div>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="container mx-auto p-6">
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {t("profile_management.loading_profile")}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const completionPercentage = profile.profile?.profile_completion_percentage || 0

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">{t("profile_management.title")}</h1>
          <p className="text-gray-600 mt-2">{t("profile_management.subtitle")}</p>
        </div>
        <Button
          variant="outline"
          onClick={loadHistory}
          className="flex items-center gap-2"
        >
          <History className="w-4 h-4" />
          {t("profile_management.history")}
        </Button>
      </div>

      {/* Profile Completion Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5" />
            {t("profile_management.completion")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>{t("profile_management.completion")}</span>
              <span>{completionPercentage}%</span>
            </div>
            <Progress value={completionPercentage} className="h-2" />
            <div className="text-sm text-gray-500">
              {completionPercentage < 100 && t("profile_management.completion_description")}
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">{t("profile_management.tabs.overview")}</TabsTrigger>
          <TabsTrigger value="basic">{t("profile_management.tabs.basic")}</TabsTrigger>
          <TabsTrigger value="bank">{t("profile_management.tabs.bank")}</TabsTrigger>
          <TabsTrigger value="advisor">{t("profile_management.tabs.advisor")}</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid md:grid-cols-2 gap-6">
            {/* Basic Info Summary */}
            <Card>
              <CardHeader>
                <CardTitle>{t("profile_management.basic_info")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <User className="w-4 h-4 text-gray-500" />
                  <div>
                    <div className="font-medium">{profile.user_info.name || t("profile_management.not_set")}</div>
                    <div className="text-sm text-gray-500">{profile.user_info.nycu_id || t("profile_management.not_set")}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-gray-500" />
                  <div className="text-sm">{profile.user_info.dept_name || t("profile_management.not_set")}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={profile.user_info.role === 'student' ? 'default' : 'secondary'}>
                    {profile.user_info.role === 'student' ? t("profile_management.student") : t("profile_management.staff")}
                  </Badge>
                  <Badge variant="outline">
                    {profile.user_info.status || t("profile_management.not_set")}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* Contact Summary */}
            <Card>
              <CardHeader>
                <CardTitle>{t("profile_management.contact_info")}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4 text-gray-500" />
                  <div className="text-sm">{profile.user_info.email}</div>
                </div>
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    {t("profile_management.contact_notice")}
                  </AlertDescription>
                </Alert>
              </CardContent>
            </Card>
          </div>

          {/* Status Cards */}
          <div className="grid md:grid-cols-2 gap-4">
            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CreditCard className="w-5 h-5 text-blue-500" />
                    <span>{t("profile_management.bank_info")}</span>
                  </div>
                  {profile.profile?.has_complete_bank_info ? (
                    <Badge variant="default">{t("profile_management.completed")}</Badge>
                  ) : (
                    <Badge variant="destructive">{t("profile_management.incomplete")}</Badge>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <School className="w-5 h-5 text-green-500" />
                    <span>{t("profile_management.advisor_info")}</span>
                  </div>
                  {profile.profile?.has_advisor_info ? (
                    <Badge variant="default">{t("profile_management.completed")}</Badge>
                  ) : (
                    <Badge variant="destructive">{t("profile_management.incomplete")}</Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Basic Info Tab */}
        <TabsContent value="basic" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>{t("profile_management.basic_readonly_title")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {t("profile_management.basic_readonly_notice")}
                </AlertDescription>
              </Alert>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>{t("profile_management.name")}</Label>
                  <Input value={profile.user_info.name} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.id_number")}</Label>
                  <Input value={profile.user_info.nycu_id} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.email")}</Label>
                  <Input value={profile.user_info.email} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.user_type")}</Label>
                  <Input value={profile.user_info.user_type} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.status")}</Label>
                  <Input value={profile.user_info.status} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.dept_code")}</Label>
                  <Input value={profile.user_info.dept_code || ''} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.dept_name")}</Label>
                  <Input value={profile.user_info.dept_name || ''} disabled />
                </div>
                <div className="space-y-2">
                  <Label>{t("profile_management.system_role")}</Label>
                  <Input value={profile.user_info.role} disabled />
                </div>
              </div>

              {/* Student specific info */}
              {profile.student_info && (
                <div className="mt-6">
                  <Separator />
                  <h3 className="text-lg font-semibold mt-4 mb-4">{t("profile_management.student_records")}</h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>{t("profile_management.degree")}</Label>
                      <Input value={profile.student_info.student?.std_degree || ''} disabled />
                    </div>
                    <div className="space-y-2">
                      <Label>{t("profile_management.enrollment_status")}</Label>
                      <Input value={profile.student_info.student?.std_studingstatus || ''} disabled />
                    </div>
                    <div className="space-y-2">
                      <Label>{t("profile_management.enrollment_year")}</Label>
                      <Input value={profile.student_info.student?.std_enrollyear || ''} disabled />
                    </div>
                    <div className="space-y-2">
                      <Label>{t("profile_management.semester_count")}</Label>
                      <Input value={profile.student_info.student?.std_termcount || ''} disabled />
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Bank Info Tab */}
        <TabsContent value="bank" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CreditCard className="w-5 h-5" />
                {t("profile_management.bank_account_info")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Bank validation errors display */}
              {bankErrors.length > 0 && (
                <Alert variant="destructive" className="mb-4">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    <div className="space-y-1">
                      {bankErrors.map((error, index) => (
                        <div key={index}>{error}</div>
                      ))}
                    </div>
                  </AlertDescription>
                </Alert>
              )}

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="bank_code">{t("profile_management.bank_code")}</Label>
                  <Input
                    id="bank_code"
                    placeholder={t("profile_management.bank_code_placeholder")}
                    value={editingProfile.bank_code || ''}
                    onChange={(e) => {
                      setEditingProfile({
                        ...editingProfile,
                        bank_code: e.target.value
                      })
                      // Clear bank errors when user starts typing
                      if (bankErrors.length > 0) {
                        setBankErrors([])
                      }
                    }}
                    className={bankErrors.some(error => error.toLowerCase().includes('bank') || error.includes('銀行代碼')) ? 'border-red-500' : ''}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="account_number">{t("profile_management.account_number")}</Label>
                  <Input
                    id="account_number"
                    placeholder={t("profile_management.account_number_placeholder")}
                    value={editingProfile.account_number || ''}
                    onChange={(e) => {
                      setEditingProfile({
                        ...editingProfile,
                        account_number: e.target.value
                      })
                      // Clear bank errors when user starts typing
                      if (bankErrors.length > 0) {
                        setBankErrors([])
                      }
                    }}
                    className={bankErrors.some(error => error.toLowerCase().includes('account') || error.includes('帳戶號碼')) ? 'border-red-500' : ''}
                  />
                </div>
              </div>

              {/* Bank Document Upload */}
              <div className="space-y-4">
                <div className="space-y-4">
                  <Label>{t("profile_management.bank_document")}</Label>

                  {/* Display current uploaded document */}
                  {profile.profile?.bank_document_photo_url && (
                    <div className="mb-4 p-4 border rounded-lg bg-green-50 border-green-200">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CheckCircle className="w-5 h-5 text-green-600" />
                          <div>
                            <span className="text-sm font-medium text-green-800">{t("profile_management.document_uploaded")}</span>
                            <p className="text-xs text-green-600">{t("profile_management.document_preview_notice")}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={handlePreviewBankDocument}
                          >
                            <Eye className="w-4 h-4 mr-1" />
                            {t("profile_management.preview")}
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={handleDeleteBankDocument}
                          >
                            <X className="w-4 h-4 mr-1" />
                            {t("profile_management.delete")}
                          </Button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* File Upload Component */}
                  <div className="space-y-4">
                    <FileUpload
                      onFilesChange={handleBankDocumentFilesChange}
                      acceptedTypes={[".jpg", ".jpeg", ".png", ".webp", ".pdf"]}
                      maxSize={10 * 1024 * 1024} // 10MB
                      maxFiles={1}
                      initialFiles={bankDocumentFiles}
                      fileType="bank_document"
                      locale="zh"
                    />

                    {/* Upload Button - only show when files are selected */}
                    {bankDocumentFiles.length > 0 && (
                      <Button
                        onClick={handleBankDocumentUpload}
                        disabled={uploadingBankDoc}
                        className="w-full"
                      >
                        {uploadingBankDoc ? (
                          <>
                            <Upload className="w-4 h-4 mr-2 animate-pulse" />
                            {t("profile_management.uploading")}
                          </>
                        ) : (
                          <>
                            <Upload className="w-4 h-4 mr-2" />
                            {t("profile_management.upload_bank_document")}
                          </>
                        )}
                      </Button>
                    )}
                  </div>

                  <div className="text-xs text-muted-foreground">
                    <p>{t("profile_management.file_formats")}</p>
                    <p>{t("profile_management.file_size_limit")}</p>
                    <p>{t("profile_management.upload_suggestion")}</p>
                  </div>
                </div>
              </div>

              <Button
                onClick={() => handleSave('bank')}
                disabled={saving}
                className="w-full"
              >
                {saving ? t("profile_management.saving") : (
                  <>
                    <Save className="w-4 h-4 mr-2" />
                    {t("profile_management.save_bank_info")}
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Advisor Info Tab */}
        <TabsContent value="advisor" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <School className="w-5 h-5" />
                {t("profile_management.advisor_info")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Advisor validation errors display */}
              {advisorErrors.length > 0 && (
                <Alert variant="destructive" className="mb-4">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    <div className="space-y-1">
                      {advisorErrors.map((error, index) => (
                        <div key={index}>{error}</div>
                      ))}
                    </div>
                  </AlertDescription>
                </Alert>
              )}

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="advisor_name">{t("profile_management.advisor_name")}</Label>
                  <Input
                    id="advisor_name"
                    placeholder={t("profile_management.advisor_name_placeholder")}
                    value={editingProfile.advisor_name || ''}
                    onChange={(e) => {
                      setEditingProfile({
                        ...editingProfile,
                        advisor_name: e.target.value
                      })
                      // Clear advisor errors when user starts typing
                      if (advisorErrors.length > 0) {
                        setAdvisorErrors([])
                      }
                    }}
                    className={advisorErrors.some(error => error.toLowerCase().includes('name') || error.includes('姓名')) ? 'border-red-500' : ''}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor_email">{t("profile_management.advisor_email")}</Label>
                  <Input
                    id="advisor_email"
                    type="email"
                    placeholder="professor@nycu.edu.tw"
                    value={editingProfile.advisor_email || ''}
                    onChange={(e) => handleAdvisorEmailChange(e.target.value)}
                    className={emailValidationError || advisorErrors.some(error => error.includes('Email')) ? 'border-red-500' : ''}
                  />
                  {emailValidationError && (
                    <div className="text-sm text-red-600 flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      {emailValidationError}
                    </div>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor_nycu_id">{t("profile_management.advisor_id")}</Label>
                  <Input
                    id="advisor_nycu_id"
                    placeholder={t("profile_management.advisor_id_placeholder")}
                    value={editingProfile.advisor_nycu_id || ''}
                    onChange={(e) => {
                      setEditingProfile({
                        ...editingProfile,
                        advisor_nycu_id: e.target.value
                      })
                      // Clear advisor errors when user starts typing
                      if (advisorErrors.length > 0) {
                        setAdvisorErrors([])
                      }
                    }}
                    className={advisorErrors.some(error => error.toLowerCase().includes('id') || error.includes('學校工號')) ? 'border-red-500' : ''}
                  />
                </div>
              </div>

              <Button
                onClick={() => handleSave('advisor')}
                disabled={saving}
                className="w-full"
              >
                {saving ? t("profile_management.saving") : (
                  <>
                    <Save className="w-4 h-4 mr-2" />
                    {t("profile_management.save_advisor_info")}
                  </>
                )}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

      </Tabs>

      {/* History Modal */}
      {showHistory && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <Card className="w-full max-w-4xl max-h-[80vh] overflow-hidden">
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle>{t("profile_management.profile_history")}</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowHistory(false)}
              >
                <X className="w-4 h-4" />
              </Button>
            </CardHeader>
            <CardContent className="overflow-y-auto">
              {history.length > 0 ? (
                <div className="space-y-4">
                  {history.map((entry) => (
                    <div key={entry.id} className="border-l-4 border-blue-200 pl-4 py-2">
                      <div className="flex justify-between items-start">
                        <div>
                          <div className="font-medium">{entry.field_name}</div>
                          <div className="text-sm text-gray-600">
                            {entry.old_value && (
                              <span>{t("profile_management.old_value")}: {entry.old_value} → </span>
                            )}
                            {t("profile_management.new_value")}: {entry.new_value}
                          </div>
                          {entry.change_reason && (
                            <div className="text-sm text-gray-500">
                              {t("profile_management.reason")}: {entry.change_reason}
                            </div>
                          )}
                        </div>
                        <div className="text-sm text-gray-400">
                          {new Date(entry.changed_at).toLocaleString('zh-TW')}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-500 py-8">
                  {t("profile_management.no_history")}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* File Preview Dialog */}
      <FilePreviewDialog
        isOpen={showPreview}
        onClose={handleClosePreview}
        file={previewFile}
        locale="zh"
      />
    </div>
  )
}
