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
import api from '@/lib/api'
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

interface UserInfo {
  id: number
  nycu_id: string
  name: string
  email: string
  user_type: string
  status: string
  dept_code: string
  dept_name: string
  role: string
  created_at: string
  last_login_at: string
}

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
  user_info: UserInfo
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
  const { toast } = useToast()

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
          title: "提示",
          description: response.message || "個人資料可能尚未建立，您可以開始填寫資料",
          variant: "default"
        })
        
        // 設置基本的用戶資料結構，即使沒有完整的個人資料
        setProfile({
          user_info: {
            id: 0,
            nycu_id: "",
            name: "",
            email: "",
            user_type: "",
            status: "",
            dept_code: "",
            dept_name: "",
            role: "",
            created_at: "",
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
          title: "連線錯誤",
          description: "無法連接到伺服器，請檢查網路連線",
          variant: "destructive"
        })
      } else {
        toast({
          title: "載入錯誤",
          description: error.message || "載入個人資料時發生錯誤",
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
          user_type: "",
          status: "",
          dept_code: "",
          dept_name: "",
          role: "",
          created_at: "",
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

  const handleSave = async (section: string) => {
    if (!editingProfile) return
    
    setSaving(true)
    try {
      let endpoint = '/user-profiles/me'
      let data: any = {}

      switch (section) {
        case 'bank':
          endpoint = '/user-profiles/me/bank-info'
          data = {
            bank_code: editingProfile.bank_code,
            account_number: editingProfile.account_number,
            change_reason: "使用者更新銀行帳戶資訊"
          }
          break
        case 'advisor':
          endpoint = '/user-profiles/me/advisor-info'
          data = {
            advisor_name: editingProfile.advisor_name,
            advisor_email: editingProfile.advisor_email,
            advisor_nycu_id: editingProfile.advisor_nycu_id,
            change_reason: "使用者更新指導教授資訊"
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
        title: "成功",
        description: "個人資料已更新",
      })
      
      await loadProfile()
    } catch (error: any) {
      toast({
        title: "更新失敗",
        description: error.response?.data?.detail || "更新個人資料時發生錯誤",
        variant: "destructive"
      })
    } finally {
      setSaving(false)
    }
  }

  const handleBankDocumentUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    if (file.size > 10 * 1024 * 1024) {
      toast({
        title: "檔案太大",
        description: "檔案大小不能超過 10MB",
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
        title: "成功",
        description: "銀行帳戶證明文件已上傳",
      })

      await loadProfile()
    } catch (error: any) {
      toast({
        title: "上傳失敗",
        description: error.response?.data?.detail || "上傳檔案時發生錯誤",
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
          title: "成功",
          description: "銀行帳戶證明文件已刪除",
        })
        await loadProfile()
      } else {
        throw new Error(response.message || 'Delete failed')
      }
    } catch (error: any) {
      toast({
        title: "刪除失敗",
        description: error.message || "刪除檔案時發生錯誤",
        variant: "destructive"
      })
    }
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
        title: "載入失敗",
        description: error.message || "載入異動紀錄時發生錯誤",
        variant: "destructive"
      })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg">載入中...</div>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="container mx-auto p-6">
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            正在載入個人資料...
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
          <h1 className="text-3xl font-bold">個人資料管理</h1>
          <p className="text-gray-600 mt-2">管理您的個人資訊與學籍資料</p>
        </div>
        <Button 
          variant="outline" 
          onClick={loadHistory}
          className="flex items-center gap-2"
        >
          <History className="w-4 h-4" />
          異動紀錄
        </Button>
      </div>

      {/* Profile Completion Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5" />
            個人資料完整度
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>完整度</span>
              <span>{completionPercentage}%</span>
            </div>
            <Progress value={completionPercentage} className="h-2" />
            <div className="text-sm text-gray-500">
              {completionPercentage < 100 && "建議完善個人資料以便更好地使用系統功能"}
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">總覽</TabsTrigger>
          <TabsTrigger value="basic">基本資料</TabsTrigger>
          <TabsTrigger value="bank">銀行帳戶</TabsTrigger>
          <TabsTrigger value="advisor">指導教授</TabsTrigger>
        </TabsList>

        {/* Overview Tab */}
        <TabsContent value="overview" className="space-y-6">
          <div className="grid md:grid-cols-2 gap-6">
            {/* Basic Info Summary */}
            <Card>
              <CardHeader>
                <CardTitle>基本資料</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <User className="w-4 h-4 text-gray-500" />
                  <div>
                    <div className="font-medium">{profile.user_info.name || '未設定'}</div>
                    <div className="text-sm text-gray-500">{profile.user_info.nycu_id || '未設定'}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Building2 className="w-4 h-4 text-gray-500" />
                  <div className="text-sm">{profile.user_info.dept_name || '未設定'}</div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant={profile.user_info.role === 'student' ? 'default' : 'secondary'}>
                    {profile.user_info.role === 'student' ? '學生' : '職員'}
                  </Badge>
                  <Badge variant="outline">
                    {profile.user_info.status || '未設定'}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            {/* Contact Summary */}
            <Card>
              <CardHeader>
                <CardTitle>聯絡資訊</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <Mail className="w-4 h-4 text-gray-500" />
                  <div className="text-sm">{profile.user_info.email}</div>
                </div>
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    聯絡資訊來自校務系統，如需修改請洽學務處。
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
                    <span>銀行帳戶</span>
                  </div>
                  {profile.profile?.has_complete_bank_info ? (
                    <Badge variant="default">已完成</Badge>
                  ) : (
                    <Badge variant="destructive">未完成</Badge>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <School className="w-5 h-5 text-green-500" />
                    <span>指導教授</span>
                  </div>
                  {profile.profile?.has_advisor_info ? (
                    <Badge variant="default">已完成</Badge>
                  ) : (
                    <Badge variant="destructive">未完成</Badge>
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
              <CardTitle>基本資料 (從 API 取得，無法修改)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Alert>
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  以下資料來自校務系統，如需修改請聯繫相關單位。
                </AlertDescription>
              </Alert>

              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>姓名</Label>
                  <Input value={profile.user_info.name} disabled />
                </div>
                <div className="space-y-2">
                  <Label>學號/員工編號</Label>
                  <Input value={profile.user_info.nycu_id} disabled />
                </div>
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input value={profile.user_info.email} disabled />
                </div>
                <div className="space-y-2">
                  <Label>身份類別</Label>
                  <Input value={profile.user_info.user_type} disabled />
                </div>
                <div className="space-y-2">
                  <Label>狀態</Label>
                  <Input value={profile.user_info.status} disabled />
                </div>
                <div className="space-y-2">
                  <Label>系所代碼</Label>
                  <Input value={profile.user_info.dept_code || ''} disabled />
                </div>
                <div className="space-y-2">
                  <Label>系所名稱</Label>
                  <Input value={profile.user_info.dept_name || ''} disabled />
                </div>
                <div className="space-y-2">
                  <Label>系統角色</Label>
                  <Input value={profile.user_info.role} disabled />
                </div>
              </div>

              {/* Student specific info */}
              {profile.student_info && (
                <div className="mt-6">
                  <Separator />
                  <h3 className="text-lg font-semibold mt-4 mb-4">學籍資料</h3>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>學位</Label>
                      <Input value={profile.student_info.student?.std_degree || ''} disabled />
                    </div>
                    <div className="space-y-2">
                      <Label>學籍狀態</Label>
                      <Input value={profile.student_info.student?.std_studingstatus || ''} disabled />
                    </div>
                    <div className="space-y-2">
                      <Label>入學年度</Label>
                      <Input value={profile.student_info.student?.std_enrollyear || ''} disabled />
                    </div>
                    <div className="space-y-2">
                      <Label>在學期數</Label>
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
                銀行帳戶資訊
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="bank_code">銀行代碼</Label>
                  <Input
                    id="bank_code"
                    placeholder="例：808"
                    value={editingProfile.bank_code || ''}
                    onChange={(e) => setEditingProfile({
                      ...editingProfile,
                      bank_code: e.target.value
                    })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="account_number">帳戶號碼</Label>
                  <Input
                    id="account_number"
                    placeholder="請輸入完整帳戶號碼"
                    value={editingProfile.account_number || ''}
                    onChange={(e) => setEditingProfile({
                      ...editingProfile,
                      account_number: e.target.value
                    })}
                  />
                </div>
              </div>

              {/* Bank Document Upload */}
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>銀行帳戶證明文件</Label>
                  <div className="flex flex-col gap-2">
                    {profile.profile?.bank_document_photo_url ? (
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-green-600">✓ 已上傳證明文件</span>
                        <Button 
                          variant="destructive" 
                          size="sm"
                          onClick={handleDeleteBankDocument}
                        >
                          <X className="w-4 h-4 mr-2" />
                          刪除文件
                        </Button>
                      </div>
                    ) : (
                      <div className="text-sm text-gray-500">尚未上傳證明文件</div>
                    )}
                    
                    <Label htmlFor="bank-doc-upload" className="cursor-pointer">
                      <Button 
                        variant="outline" 
                        disabled={uploadingBankDoc}
                        asChild
                      >
                        <span>
                          {uploadingBankDoc ? (
                            "上傳中..."
                          ) : (
                            <>
                              <Upload className="w-4 h-4 mr-2" />
                              上傳帳戶證明文件
                            </>
                          )}
                        </span>
                      </Button>
                    </Label>
                    <input
                      id="bank-doc-upload"
                      type="file"
                      accept="image/*"
                      onChange={handleBankDocumentUpload}
                      className="hidden"
                    />
                  </div>
                </div>
              </div>

              <Button
                onClick={() => handleSave('bank')}
                disabled={saving}
                className="w-full"
              >
                {saving ? "儲存中..." : (
                  <>
                    <Save className="w-4 h-4 mr-2" />
                    儲存銀行帳戶資訊
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
                指導教授資訊
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="advisor_name">指導教授姓名</Label>
                  <Input
                    id="advisor_name"
                    placeholder="例：王小明"
                    value={editingProfile.advisor_name || ''}
                    onChange={(e) => setEditingProfile({
                      ...editingProfile,
                      advisor_name: e.target.value
                    })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor_email">指導教授 Email</Label>
                  <Input
                    id="advisor_email"
                    type="email"
                    placeholder="professor@nycu.edu.tw"
                    value={editingProfile.advisor_email || ''}
                    onChange={(e) => setEditingProfile({
                      ...editingProfile,
                      advisor_email: e.target.value
                    })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="advisor_nycu_id">指導教授學校工號</Label>
                  <Input
                    id="advisor_nycu_id"
                    placeholder="例：professor123"
                    value={editingProfile.advisor_nycu_id || ''}
                    onChange={(e) => setEditingProfile({
                      ...editingProfile,
                      advisor_nycu_id: e.target.value
                    })}
                  />
                </div>
              </div>

              <Button
                onClick={() => handleSave('advisor')}
                disabled={saving}
                className="w-full"
              >
                {saving ? "儲存中..." : (
                  <>
                    <Save className="w-4 h-4 mr-2" />
                    儲存指導教授資訊
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
              <CardTitle>個人資料異動紀錄</CardTitle>
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
                              <span>舊值: {entry.old_value} → </span>
                            )}
                            新值: {entry.new_value}
                          </div>
                          {entry.change_reason && (
                            <div className="text-sm text-gray-500">
                              原因: {entry.change_reason}
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
                  尚無異動紀錄
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}