"use client"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  FileText,
  TrendingUp,
  Clock,
  CheckCircle,
  AlertCircle,
  Award,
  Loader2,
} from "lucide-react"
import { api } from "@/lib/api"
import { ScholarshipTimeline } from "@/components/scholarship-timeline"
import { useScholarshipPermissions } from "@/hooks/use-scholarship-permissions"

interface AdminDashboardProps {
  stats: any
  recentApplications: any[]
  systemAnnouncements: any[]
  isStatsLoading: boolean
  isRecentLoading: boolean
  isAnnouncementsLoading: boolean
  error: string | null
  isAuthenticated: boolean
  user: any
  login: (token: string, userData: any) => void
  logout: () => void
  fetchRecentApplications: () => void
  fetchDashboardStats: () => void
  onTabChange?: (tab: string) => void
}

export function AdminDashboard({
  stats,
  recentApplications,
  systemAnnouncements,
  isStatsLoading,
  isRecentLoading,
  isAnnouncementsLoading,
  error,
  isAuthenticated,
  user,
  login,
  logout,
  fetchRecentApplications,
  fetchDashboardStats,
  onTabChange
}: AdminDashboardProps) {
  // Get user's scholarship permissions
  const { filterScholarshipsByPermission } = useScholarshipPermissions()

  // 狀態中文化映射
  const getStatusText = (status: string) => {
    const statusMap = {
      'draft': '草稿',
      'submitted': '已提交',
      'under_review': '審核中',
      'pending_recommendation': '待推薦',
      'recommended': '已推薦',
      'approved': '已核准',
      'rejected': '已拒絕',
      'returned': '已退回',
      'withdrawn': '已撤回',
      'cancelled': '已取消'
    }
    return statusMap[status as keyof typeof statusMap] || status
  }

  // 直接使用 API 回傳的獎學金名稱
  const getScholarshipTypeName = (type: string, typeZh?: string, typeName?: string) => {
    if (typeZh) return typeZh
    if (typeName) return typeName
    return type
  }

  // 格式化日期
  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('zh-TW', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    })
  }

  return (
    <div className="space-y-6">
      {/* Welcome Banner */}
      <div className="nycu-gradient rounded-xl p-6 text-white nycu-shadow">
        <div className="flex items-center gap-4">
          <Award className="h-12 w-12 text-white/90" />
          <div>
            <h2 className="text-2xl font-bold mb-2">獎學金管理系統儀表板</h2>
            <p className="text-white/90">
              歡迎使用陽明交通大學獎學金申請與簽核作業管理系統，提升獎學金作業效率與透明度
            </p>
          </div>
        </div>
      </div>


      {/* 開發者調試工具欄 */}
      {process.env.NODE_ENV === 'development' && (
        <div className="bg-gray-100 border border-gray-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <h3 className="font-medium text-gray-800 mb-2">開發者調試信息</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-gray-600">
                <div>
                  <strong>認證狀態:</strong> {isAuthenticated ? '✅ 已認證' : '❌ 未認證'}<br/>
                  <strong>用戶:</strong> {user?.name || '未知'} ({user?.role || '未知'})<br/>
                  <strong>用戶ID:</strong> {user?.id || '未知'}
                </div>
                <div>
                  <strong>最近申請數量:</strong> {recentApplications.length}<br/>
                  <strong>載入狀態:</strong> {isRecentLoading ? '載入中...' : '完成'}<br/>
                  <strong>錯誤:</strong> {error || '無'}
                </div>
                <div>
                  <strong>Token:</strong> {typeof window !== 'undefined' && localStorage.getItem('auth_token') ? '存在' : '不存在'}<br/>
                  <strong>API端點:</strong> {api.constructor.name}<br/>
                  <strong>統計數據:</strong> {stats ? `${stats.total_applications} 總申請` : '未載入'}
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  console.log('Testing super_admin login...')
                  try {
                    const response = await api.auth.mockSSOLogin('super_admin')
                    console.log('Mock login response:', response)

                    if (response.success && response.data) {
                      const { access_token, user: userData } = response.data
                      login(access_token, userData)
                      console.log('Super admin login successful')

                      // 手動觸發數據刷新
                      setTimeout(() => {
                        fetchRecentApplications()
                        fetchDashboardStats()
                      }, 1000)
                    }
                  } catch (e) {
                    console.error('Test login failed:', e)
                  }
                }}
                className="px-3 py-1 bg-green-600 text-white text-sm rounded hover:bg-green-700"
              >
                登錄為 Super Admin
              </button>
              <button
                onClick={() => {
                  console.log('Refreshing all data...')
                  fetchRecentApplications()
                  fetchDashboardStats()
                }}
                className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
              >
                刷新數據
              </button>
              <button
                onClick={() => {
                  logout()
                }}
                className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
              >
                登出
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-red-600" />
              <div>
                <p className="text-red-700 font-medium">載入資料時發生錯誤</p>
                <p className="text-red-600 text-sm">{error}</p>
                <div className="text-xs text-red-500 mt-1">
                  <p>認證狀態: {isAuthenticated ? '已認證' : '未認證'}</p>
                  <p>用戶角色: {user?.role || '未知'}</p>
                  <p>用戶ID: {user?.id || '未知'}</p>
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={async () => {
                  console.log('Manual retry triggered')
                  fetchRecentApplications()
                }}
                className="px-3 py-1 bg-red-600 text-white text-sm rounded hover:bg-red-700"
              >
                重試
              </button>
              {/* 測試登錄按鈕 */}
              <button
                onClick={async () => {
                  try {
                    console.log('Testing super_admin login...')
                    const response = await api.auth.mockSSOLogin('super_admin')
                    console.log('Mock login response:', response)

                    if (response.success && response.data) {
                      const { access_token, user: userData } = response.data
                      login(access_token, userData)
                      console.log('Super admin login successful')
                    }
                  } catch (e) {
                    console.error('Test login failed:', e)
                  }
                }}
                className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700"
              >
                測試登錄
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <Card className="academic-card border-nycu-blue-200 hover:shadow-lg transition-all duration-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-nycu-navy-700">總申請案件</CardTitle>
            <FileText className="h-5 w-5 text-nycu-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-nycu-navy-800">
              {isStatsLoading ? (
                <Loader2 className="h-8 w-8 animate-spin" />
              ) : (
                stats?.total_applications || 0
              )}
            </div>
            <p className="text-xs text-nycu-blue-600 font-medium">總申請案件</p>
          </CardContent>
        </Card>

        <Card className="academic-card border-nycu-orange-200 hover:shadow-lg transition-all duration-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-nycu-navy-700">待審核</CardTitle>
            <Clock className="h-5 w-5 text-nycu-orange-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-nycu-navy-800">
              {isStatsLoading ? (
                <Loader2 className="h-8 w-8 animate-spin" />
              ) : (
                stats?.pending_review || 0
              )}
            </div>
            <p className="text-xs text-nycu-orange-600 font-medium">需要處理</p>
          </CardContent>
        </Card>

        <Card className="academic-card border-green-200 hover:shadow-lg transition-all duration-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-nycu-navy-700">已核准</CardTitle>
            <CheckCircle className="h-5 w-5 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-nycu-navy-800">
              {isStatsLoading ? (
                <Loader2 className="h-8 w-8 animate-spin" />
              ) : (
                stats?.approved || 0
              )}
            </div>
            <p className="text-xs text-green-600 font-medium">本月核准</p>
          </CardContent>
        </Card>

        <Card className="academic-card border-nycu-blue-200 hover:shadow-lg transition-all duration-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-nycu-navy-700">平均處理時間</CardTitle>
            <TrendingUp className="h-5 w-5 text-nycu-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-nycu-navy-800">
              {isStatsLoading ? (
                <Loader2 className="h-8 w-8 animate-spin" />
              ) : (
                stats?.avg_processing_time || "N/A"
              )}
            </div>
            <p className="text-xs text-nycu-blue-600 font-medium">處理時間</p>
          </CardContent>
        </Card>
      </div>

      {/* 獎學金時間軸 - 根據用戶權限顯示 */}
      <ScholarshipTimeline user={user} />

      <div className="grid gap-6 md:grid-cols-2">
        <Card className="academic-card border-nycu-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
              <FileText className="h-5 w-5 text-nycu-blue-600" />
              最近申請
            </CardTitle>
            <CardDescription>最新的獎學金申請狀態</CardDescription>
          </CardHeader>
          <CardContent>
            {isRecentLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-nycu-blue-600" />
                <span className="ml-2 text-nycu-navy-600">載入中...</span>
              </div>
            ) : recentApplications.length > 0 ? (
              <div className="space-y-4">
                {recentApplications.map((app) => (
                  <div key={app.id} className="flex items-center justify-between p-4 bg-nycu-blue-50 rounded-lg hover:bg-nycu-blue-100 transition-colors">
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-2">
                        <p className="font-medium text-nycu-navy-800">
                          {getScholarshipTypeName(app.scholarship_type, app.scholarship_type_zh, app.scholarship_name)}
                        </p>
                        <Badge
                          variant={
                            app.status === 'approved' ? 'default' :
                            app.status === 'rejected' ? 'destructive' :
                            'outline'
                          }
                          className={
                            app.status === 'approved' ? 'bg-green-600' :
                            app.status === 'rejected' ? 'bg-red-600' :
                            'border-nycu-orange-300 text-nycu-orange-700'
                          }
                        >
                          {getStatusText(app.status)}
                        </Badge>
                      </div>
                      <div className="flex items-center justify-between text-sm text-nycu-navy-600">
                        <span>{app.app_id || `APP-${app.id}`}</span>
                        <div className="flex gap-4">
                          {app.submitted_at && (
                            <span>提交：{formatDate(app.submitted_at)}</span>
                          )}
                          <span>創建：{formatDate(app.created_at)}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-nycu-navy-600">
                <FileText className="h-12 w-12 mx-auto mb-2 text-nycu-blue-300" />
                <p>暫無申請資料</p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="academic-card border-nycu-blue-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
              <AlertCircle className="h-5 w-5 text-nycu-orange-600" />
              系統公告
            </CardTitle>
            <CardDescription>重要通知與更新</CardDescription>
          </CardHeader>
          <CardContent>
            {isAnnouncementsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-nycu-blue-600" />
                <span className="ml-2 text-nycu-navy-600">載入中...</span>
              </div>
            ) : systemAnnouncements.length > 0 ? (
              <div className="space-y-4">
                {systemAnnouncements.map((announcement) => (
                  <div key={announcement.id} className="flex items-start space-x-3 p-3 bg-nycu-orange-50 rounded-lg">
                    <AlertCircle className={`h-5 w-5 mt-0.5 flex-shrink-0 ${
                      announcement.notification_type === 'error' ? 'text-red-600' :
                      announcement.notification_type === 'warning' ? 'text-nycu-orange-600' :
                      announcement.notification_type === 'success' ? 'text-green-600' :
                      'text-nycu-blue-600'
                    }`} />
                    <div>
                      <p className="text-sm font-medium text-nycu-navy-800">{announcement.title}</p>
                      <p className="text-xs text-nycu-navy-600">{announcement.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-nycu-navy-600">
                <AlertCircle className="h-12 w-12 mx-auto mb-2 text-nycu-blue-300" />
                <p>暫無系統公告</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
