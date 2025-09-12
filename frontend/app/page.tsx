"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import {
  BookOpen,
  Users,
  Cog,
  FileText,
  TrendingUp,
  Clock,
  CheckCircle,
  AlertCircle,
  Award,
  GraduationCap,
  Loader2,
} from "lucide-react"
import { EnhancedStudentPortal } from "@/components/enhanced-student-portal"
import { AdminScholarshipDashboard } from "@/components/admin-scholarship-dashboard"
import { AdminManagementInterface } from "@/components/admin-management-interface"
import { ProfessorReviewComponent } from "@/components/professor-review-component"
import { CollegeDashboard } from "@/components/college-dashboard"
import { AdminDashboard } from "@/components/admin-dashboard"
import { Header } from "@/components/header"
import { Footer } from "@/components/footer"
import { useLanguagePreference } from "@/hooks/use-language-preference"
import { getTranslation } from "@/lib/i18n"
import { useAuth } from "@/hooks/use-auth"
import { DevLoginPage } from "@/components/dev-login-page"
import { SSOLoginPage } from "@/components/sso-login-page"
import { useAdminDashboard } from "@/hooks/use-admin"
import { apiClient } from "@/lib/api"
import { User } from "@/types/user"

export default function ScholarshipManagementSystem() {
  const [activeTab, setActiveTab] = useState("main")
  
  // 使用認證 hook
  const { user, isAuthenticated, isLoading: authLoading, error: authError, login, logout } = useAuth()
  
  // 使用語言偏好 Hook
  const { locale, changeLocale, isLanguageSwitchEnabled } = useLanguagePreference(user?.role || "student", "zh")
  
  // 使用 admin dashboard hook
  const { 
    stats, 
    recentApplications, 
    systemAnnouncements, 
    allApplications,
    isStatsLoading, 
    isRecentLoading, 
    isAnnouncementsLoading,
    error,
    fetchRecentApplications,
    fetchDashboardStats 
  } = useAdminDashboard()

  // 調試信息
  useEffect(() => {
    console.log('🏠 ScholarshipManagementSystem mounted')
    console.log('👤 User:', user)
    console.log('🔐 Is Authenticated:', isAuthenticated)
    console.log('⏳ Auth Loading:', authLoading)
    console.log('❌ Auth Error:', authError)
    console.log('📄 Recent Applications:', recentApplications)
    console.log('🚨 Error:', error)
    
    // 檢查 localStorage 中的認證信息
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('auth_token')
      const userJson = localStorage.getItem('user')
      console.log('LocalStorage token exists:', !!token)
      console.log('LocalStorage user exists:', !!userJson)
      try {
        console.log('API client has token:', !!(apiClient as any).token)
      } catch (e) {
        console.log('Could not access apiClient token')
      }
      
      if (token) {
        console.log('Token preview:', token.substring(0, 20) + '...')
      }
    }
  }, [user, isAuthenticated, authLoading, authError, recentApplications, error])

  // Handle hash-based navigation
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash.replace('#', '')
      if (hash && ['dashboard', 'main', 'admin'].includes(hash)) {
        setActiveTab(hash)
      }
    }
  }, [])

  // Set initial active tab based on user role
  useEffect(() => {
    console.log('🎯 Setting active tab based on user role...')
    if (user) {
      console.log('👤 User role detected:', user.role)
      // Set each role to their first available tab (index 0)
      if (user.role === "student") {
        console.log('🎒 Student role - setting tab to "main"')
        setActiveTab("main")
      } else if (user.role === "professor") {
        console.log('🎓 Professor role - setting tab to "main"')
        setActiveTab("main")
      } else if (user.role === "college") {
        console.log('🏫 College role - setting tab to "main"')
        setActiveTab("main")
      } else if (user.role === "admin") {
        console.log('👑 Admin role - setting tab to "dashboard"')
        setActiveTab("dashboard")
      } else if (user.role === "super_admin") {
        console.log('👑 Super Admin role - setting tab to "dashboard"')
        setActiveTab("dashboard")
      }
      console.log('✅ Active tab set based on user role')
    } else {
      console.log('❌ No user found, cannot set active tab')
    }
  }, [user])

  const t = (key: string) => getTranslation(locale, key)

  // Show loading screen while checking authentication
  if (authLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-nycu-navy-600">載入中...</p>
        </div>
      </div>
    )
  }

  // Show login interface if not authenticated
  if (!isAuthenticated) {
    // Development mode: use DevLoginPage
    if (process.env.NODE_ENV === 'development') {
      return <DevLoginPage />
    }
    
    // Production mode: use SSO login
    return <SSOLoginPage />
  }

  // 根據角色決定顯示的標籤頁
  const getTabsList = () => {
    if (!user) return null;
    
    if (user.role === "student") {
      return (
        <TabsList className="grid w-full grid-cols-1 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="main"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <BookOpen className="h-4 w-4" />
            {t("nav.applications")}
          </TabsTrigger>
        </TabsList>
      )
    }

    if (user.role === "professor") {
      return (
        <TabsList className="grid w-full grid-cols-1 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="main"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Users className="h-4 w-4" />
            獎學金申請審查
          </TabsTrigger>
        </TabsList>
      )
    }

    if (user.role === "college") {
      return (
        <TabsList className="grid w-full grid-cols-1 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="main"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <GraduationCap className="h-4 w-4" />
            審核管理
          </TabsTrigger>
        </TabsList>
      )
    }

    if (user.role === "super_admin") {
      return (
        <TabsList className="grid w-full grid-cols-3 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="dashboard"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <TrendingUp className="h-4 w-4" />
            儀表板
          </TabsTrigger>
          <TabsTrigger
            value="main"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Users className="h-4 w-4" />
            審核管理
          </TabsTrigger>
          <TabsTrigger
            value="admin"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Cog className="h-4 w-4" />
            系統管理
          </TabsTrigger>
        </TabsList>
      )
    }

    if (user.role === "admin") {
      return (
        <TabsList className="grid w-full grid-cols-3 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="dashboard"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <TrendingUp className="h-4 w-4" />
            儀表板
          </TabsTrigger>
          <TabsTrigger
            value="main"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Users className="h-4 w-4" />
            審核管理
          </TabsTrigger>
          <TabsTrigger
            value="admin"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Cog className="h-4 w-4" />
            系統管理
          </TabsTrigger>
        </TabsList>
      )
    }

    return null
  }

  if (!user) {
    return <div>Loading...</div>
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex flex-col">
      <Header
        user={user}
        locale={locale}
        onLocaleChange={changeLocale}
        showLanguageSwitcher={isLanguageSwitchEnabled}
        onLogout={logout}
      />

      <main className="container mx-auto px-4 py-8 flex-1">
        <div className="mb-8">
          <div className="flex items-center gap-4 mb-4">
            <div className="nycu-gradient h-16 w-16 rounded-xl flex items-center justify-center nycu-shadow">
              <GraduationCap className="h-8 w-8 text-white" />
            </div>
            <div>
              <h1 className="text-4xl font-bold tracking-tight text-nycu-navy-800">
                {user.role === "student" ? t("system.title") : "獎學金申請與簽核作業管理系統"}
              </h1>
              <p className="text-lg text-nycu-navy-600 mt-1">
                {user.role === "student"
                  ? t("system.subtitle")
                  : "Scholarship Application and Approval Management System"}
              </p>
              <p className="text-sm text-nycu-blue-600 font-medium mt-1">
                國立陽明交通大學教務處 | NYCU Office of Academic Affairs
              </p>
            </div>
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          {getTabsList()}

          {/* 儀表板 - 只有 admin 和 super_admin 可見 */}
          {(user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="dashboard" className="space-y-4">
              <AdminDashboard
                stats={stats}
                recentApplications={recentApplications}
                systemAnnouncements={systemAnnouncements}
                isStatsLoading={isStatsLoading}
                isRecentLoading={isRecentLoading}
                isAnnouncementsLoading={isAnnouncementsLoading}
                error={error}
                isAuthenticated={isAuthenticated}
                user={user}
                login={login}
                logout={logout}
                fetchRecentApplications={fetchRecentApplications}
                fetchDashboardStats={fetchDashboardStats}
                onTabChange={setActiveTab}
              />
            </TabsContent>
          )}

          {/* 主要功能頁面 */}
          <TabsContent value="main" className="space-y-4">
            {user.role === "student" && <EnhancedStudentPortal user={{
              ...user,
              studentType: "undergraduate" // 默認值，實際應該從用戶數據中獲取
            } as User & { studentType: "undergraduate" }} locale={locale} />}
            {user.role === "professor" && <ProfessorReviewComponent user={user} />}
            {user.role === "college" && <CollegeDashboard user={user} locale={locale} />}
            {(user.role === "admin" || user.role === "super_admin") && <AdminScholarshipDashboard user={user} />}
          </TabsContent>

          {/* 系統管理 - 只有 admin 和 super_admin 可見 */}
          {(user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="admin" className="space-y-4">
              <AdminManagementInterface user={user} />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <Footer locale={locale} />
    </div>
  )
}
