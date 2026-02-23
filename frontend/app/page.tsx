"use client";

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { UserRole } from "@/lib/enums";
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
  FileSpreadsheet,
  Upload,
} from "lucide-react";
import { EnhancedStudentPortal } from "@/components/enhanced-student-portal";
import { AdminScholarshipDashboard } from "@/components/admin-scholarship-dashboard";
import { AdminManagementShell } from "@/components/admin/AdminManagementShell";
import { ProfessorReviewComponent } from "@/components/professor-review-component";
import { CollegeDashboard } from "@/components/college/CollegeManagementShell";
import { AdminDashboard } from "@/components/admin-dashboard";
import { RosterManagementDashboard } from "@/components/roster-management-dashboard";
import { BatchImportPanel } from "@/components/batch-import-panel";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";
import { useLanguagePreference } from "@/hooks/use-language-preference";
import { getTranslation } from "@/lib/i18n";
import { useAuth } from "@/hooks/use-auth";
import { DevLoginPage } from "@/components/dev-login-page";
import { SSOLoginPage } from "@/components/sso-login-page";
import { useAdminDashboard } from "@/hooks/use-admin";
import { apiClient } from "@/lib/api";
import { User } from "@/types/user";
import { decodeJWT } from "@/lib/utils/jwt";

export default function ScholarshipManagementSystem() {
  const [activeTab, setActiveTab] = useState("main");
  const [editingApplicationId, setEditingApplicationId] = useState<number | null>(null);

  // Debug activeTab changes
  useEffect(() => {
    // console.log(" Active tab changed to:", activeTab);
    console.log(
      "🌐 Current URL after tab change:",
      typeof window !== "undefined" ? window.location.href : "SSR"
    );
  }, [activeTab]);

  // Check if this is an SSO callback request
  useEffect(() => {
    if (typeof window !== "undefined") {
      const path = window.location.pathname;
      const searchParams = new URLSearchParams(window.location.search);

    // console.log(" Checking current path:", path);
      console.log(
        "🔍 URL search params:",
        Object.fromEntries(searchParams.entries())
      );

      if (path === "/auth/sso-callback") {
    // console.log(" Detected SSO callback request in main page!");
        const token = searchParams.get("token");

        if (token) {
    // console.log(" Processing SSO callback with token in main page...");
          handleSSOCallbackInMainPage(token);
        } else {
          console.error("❌ No token found in SSO callback URL");
        }
      }
    }
  }, []);

  const handleSSOCallbackInMainPage = async (token: string) => {
    try {
    // console.log(" Decoding JWT token using utility module...");

      // Decode JWT using utility module (eliminates inline script for CSP compliance)
      const tokenData = decodeJWT(token);
    // console.log(" Decoded token data in main page:", tokenData);

      // Validate and cast role to UserRole enum
      const validRoles: Array<UserRole> = [
        UserRole.STUDENT,
        UserRole.PROFESSOR,
        UserRole.COLLEGE,
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
      ];
      const userRole = validRoles.includes(tokenData.role as UserRole)
        ? (tokenData.role as UserRole)
        : UserRole.STUDENT; // Fallback to student if invalid

      // Create user object from token data
      const userData = {
        id: tokenData.sub,
        nycu_id: tokenData.nycu_id,
        role: userRole,
        name: tokenData.nycu_id,
        email: `${tokenData.nycu_id}@nycu.edu.tw`,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

    // console.log(" Constructed user data in main page:", userData);
    // console.log(" Calling login() from main page...");

      login(token, userData);

    // console.log(" Login completed in main page, redirecting...");

      // Redirect based on user role
      let redirectPath = "/";

      if (userData.role === "admin" || userData.role === "super_admin") {
        redirectPath = "/#dashboard";
      } else {
        redirectPath = "/#main";
      }

      console.log("🚀 Redirecting to:", redirectPath);

      setTimeout(() => {
        window.location.href = redirectPath;
      }, 1000);
    } catch (error) {
      console.error("💥 SSO callback processing failed in main page:", error);
    }
  };

  // 使用認證 hook
  const {
    user,
    isAuthenticated,
    isLoading: authLoading,
    error: authError,
    login,
    logout,
  } = useAuth();

  // 使用語言偏好 Hook
  const { locale, changeLocale, isLanguageSwitchEnabled } =
    useLanguagePreference(user?.role || "student", "zh");

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
    fetchDashboardStats,
  } = useAdminDashboard();

  // 調試信息
  useEffect(() => {
    // console.log("🏠 ScholarshipManagementSystem mounted");
    // console.log(" User:", user);
    // console.log(" Is Authenticated:", isAuthenticated);
    // console.log("⏳ Auth Loading:", authLoading);
    console.log("❌ Auth Error:", authError);
    // console.log("📄 Recent Applications:", recentApplications);
    // console.log("🚨 Error:", error);

    // 檢查 localStorage 中的認證信息
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("auth_token");
      const userJson = localStorage.getItem("user");
      console.log("LocalStorage token exists:", !!token);
      console.log("LocalStorage user exists:", !!userJson);
      try {
        console.log("API client has token:", !!(apiClient as any).token);
      } catch (e) {
        console.log("Could not access apiClient token");
      }

      if (token) {
        console.log("Token preview:", token.substring(0, 20) + "...");
      }
    }
  }, [
    user,
    isAuthenticated,
    authLoading,
    authError,
    recentApplications,
    error,
  ]);

  // Handle hash-based navigation
  useEffect(() => {
    // console.log("🔗 Hash-based navigation effect triggered");
    if (typeof window !== "undefined") {
      const fullHash = window.location.hash;
      const hash = fullHash.replace("#", "");
      // console.log("🌐 Current URL:", window.location.href);
      // console.log("🔗 Full hash:", fullHash);
      // console.log("🏷️ Processed hash:", hash);

      const validHashes = ["dashboard", "main", "admin"];
    // console.log(" Valid hashes:", validHashes);

      if (hash && validHashes.includes(hash)) {
    // console.log(" Hash is valid, setting active tab to:", hash);
        setActiveTab(hash);
    // console.log(" Active tab updated from hash navigation");
      } else if (hash) {
        console.log("❌ Hash is invalid:", hash);
      } else {
        // console.log("📝 No hash found in URL");
      }
    } else {
      console.log("❌ Window is not defined (SSR)");
    }
  }, []);

  // Set initial active tab based on user role
  useEffect(() => {
    // console.log(" Setting active tab based on user role...");
    if (user) {
    // console.log(" User role detected:", user.role);
      // Set each role to their first available tab (index 0)
      if (user.role === "student") {
        // console.log('🎒 Student role - setting tab to "scholarship-list"');
        setActiveTab("scholarship-list");
      } else if (user.role === "professor") {
        // console.log('🎓 Professor role - setting tab to "main"');
        setActiveTab("main");
      } else if (user.role === "college") {
        // console.log('🏫 College role - setting tab to "main"');
        setActiveTab("main");
      } else if (user.role === "admin") {
        // console.log('👑 Admin role - setting tab to "dashboard"');
        setActiveTab("dashboard");
      } else if (user.role === "super_admin") {
        // console.log('👑 Super Admin role - setting tab to "dashboard"');
        setActiveTab("dashboard");
      }
    // console.log(" Active tab set based on user role");
    } else {
      console.log("❌ No user found, cannot set active tab");
    }
  }, [user]);

  const t = (key: string) => getTranslation(locale, key);

  // Handle editing application from "My Applications" tab
  const handleStartEditingApplication = (applicationId: number) => {
    setEditingApplicationId(applicationId);
    setActiveTab("new-application");
  };

  // Clear editing state when application is submitted or cancelled
  const handleClearEditingState = () => {
    setEditingApplicationId(null);
  };

  // Show loading screen while checking authentication
  if (authLoading) {
    // console.log("⏳ Showing loading screen - authLoading is true");
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-nycu-navy-600">載入中...</p>
        </div>
      </div>
    );
  }

  // Show login interface if not authenticated
  if (!isAuthenticated) {
    // console.log("🚫 User not authenticated, showing login page");
    // console.log("🌍 NODE_ENV:", process.env.NODE_ENV);
    // Development mode: use DevLoginPage
    if (process.env.NODE_ENV === "development") {
      // console.log("🛠️ Development mode - showing DevLoginPage");
      return <DevLoginPage />;
    }

    // Production mode: use SSO login
    // console.log("🏭 Production mode - showing SSOLoginPage");
    return <SSOLoginPage />;
  }

  // 根據角色決定顯示的標籤頁
  const getTabsList = () => {
    if (!user) return null;

    if (user.role === "student") {
      return (
        <TabsList className="grid w-full grid-cols-3 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="scholarship-list"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Award className="h-4 w-4" />
            {locale === "zh" ? "獎學金列表" : "Scholarship List"}
          </TabsTrigger>
          <TabsTrigger
            value="new-application"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <FileText className="h-4 w-4" />
            {locale === "zh" ? "學生申請" : "New Application"}
          </TabsTrigger>
          <TabsTrigger
            value="applications"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <BookOpen className="h-4 w-4" />
            {locale === "zh" ? "我的申請" : "My Applications"}
          </TabsTrigger>
        </TabsList>
      );
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
      );
    }

    if (user.role === "college") {
      return (
        <TabsList className="grid w-full grid-cols-2 bg-nycu-blue-50 border border-nycu-blue-200">
          <TabsTrigger
            value="main"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <GraduationCap className="h-4 w-4" />
            審核管理
          </TabsTrigger>
          <TabsTrigger
            value="batch-import"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Upload className="h-4 w-4" />
            批次匯入
          </TabsTrigger>
        </TabsList>
      );
    }

    if (user.role === "super_admin") {
      return (
        <TabsList className="grid w-full grid-cols-6 bg-nycu-blue-50 border border-nycu-blue-200">
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
            value="distribution"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Award className="h-4 w-4" />
            獎學金分發
          </TabsTrigger>
          <TabsTrigger
            value="batch-import"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Upload className="h-4 w-4" />
            批次匯入
          </TabsTrigger>
          <TabsTrigger
            value="roster"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <FileSpreadsheet className="h-4 w-4" />
            造冊管理
          </TabsTrigger>
          <TabsTrigger
            value="admin"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Cog className="h-4 w-4" />
            系統管理
          </TabsTrigger>
        </TabsList>
      );
    }

    if (user.role === "admin") {
      return (
        <TabsList className="grid w-full grid-cols-6 bg-nycu-blue-50 border border-nycu-blue-200">
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
            value="distribution"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Award className="h-4 w-4" />
            獎學金分發
          </TabsTrigger>
          <TabsTrigger
            value="batch-import"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Upload className="h-4 w-4" />
            批次匯入
          </TabsTrigger>
          <TabsTrigger
            value="roster"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <FileSpreadsheet className="h-4 w-4" />
            造冊管理
          </TabsTrigger>
          <TabsTrigger
            value="admin"
            className="flex items-center gap-2 data-[state=active]:bg-white data-[state=active]:text-nycu-blue-700"
          >
            <Cog className="h-4 w-4" />
            系統管理
          </TabsTrigger>
        </TabsList>
      );
    }

    return null;
  };

  if (!user) {
    console.log(
      "❌ User is null after authentication checks, showing loading..."
    );
    return <div>Loading...</div>;
  }

    // console.log(" Rendering main scholarship system interface");
    // console.log(" Final user state:", {
    //   id: user.id,
    //   email: user.email,
    //   role: user.role,
    //   name: user.name,
    // });
    // console.log(" Current active tab:", activeTab);
    // console.log(" Authentication state:", { isAuthenticated, authLoading });

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
                {user.role === "student"
                  ? t("system.title")
                  : "獎學金申請與簽核系統"}
              </h1>
              <p className="text-lg text-nycu-navy-600 mt-1">
                {user.role === "student"
                  ? t("system.subtitle")
                  : "NYCU Admissions Scholarship System"}
              </p>
              <p className="text-sm text-nycu-blue-600 font-medium mt-1">
                國立陽明交通大學教務處 | NYCU Office of Academic Affairs
              </p>
            </div>
          </div>
        </div>

        <Tabs
          value={activeTab}
          onValueChange={setActiveTab}
          className="space-y-6"
        >
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

          {/* 學生角色的三個 tabs */}
          {user.role === "student" && (
            <>
              <TabsContent value="scholarship-list" className="space-y-4">
                <EnhancedStudentPortal
                  user={
                    {
                      ...user,
                      studentType: "undergraduate",
                    } as User & { studentType: "undergraduate" }
                  }
                  locale={locale}
                  initialTab="scholarship-list"
                  onApplicationSubmitted={() => setActiveTab("applications")}
                  editingApplicationId={editingApplicationId}
                  onStartEditing={handleStartEditingApplication}
                  onClearEditing={handleClearEditingState}
                />
              </TabsContent>

              <TabsContent value="new-application" className="space-y-4">
                <EnhancedStudentPortal
                  user={
                    {
                      ...user,
                      studentType: "undergraduate",
                    } as User & { studentType: "undergraduate" }
                  }
                  locale={locale}
                  initialTab="new-application"
                  onApplicationSubmitted={() => {
                    setActiveTab("applications");
                    handleClearEditingState();
                  }}
                  editingApplicationId={editingApplicationId}
                  onStartEditing={handleStartEditingApplication}
                  onClearEditing={handleClearEditingState}
                />
              </TabsContent>

              <TabsContent value="applications" className="space-y-4">
                <EnhancedStudentPortal
                  user={
                    {
                      ...user,
                      studentType: "undergraduate",
                    } as User & { studentType: "undergraduate" }
                  }
                  locale={locale}
                  initialTab="applications"
                  editingApplicationId={editingApplicationId}
                  onStartEditing={handleStartEditingApplication}
                  onClearEditing={handleClearEditingState}
                />
              </TabsContent>
            </>
          )}

          {/* 主要功能頁面 */}
          <TabsContent value="main" className="space-y-4">
            {user.role === "professor" && (
              <>
                <ProfessorReviewComponent user={user} />
              </>
            )}
            {user.role === "college" && (
              <>
                <CollegeDashboard user={user} locale={locale} />
              </>
            )}
            {(user.role === "admin" || user.role === "super_admin") && (
              <>
                <AdminScholarshipDashboard user={user} />
              </>
            )}
          </TabsContent>

          {/* 獎學金分發 - 只有 admin 和 super_admin 可見 */}
          {(user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="distribution" className="space-y-4">
              <CollegeDashboard user={user} locale={locale} />
            </TabsContent>
          )}

          {/* 批次匯入 - college 和 super_admin 角色可見 */}
          {(user.role === "college" || user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="batch-import" className="space-y-4">
              <BatchImportPanel locale={locale} />
            </TabsContent>
          )}

          {/* 造冊管理 - 只有 admin 和 super_admin 可見 */}
          {(user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="roster" className="space-y-4">
              <RosterManagementDashboard />
            </TabsContent>
          )}

          {/* 系統管理 - 只有 admin 和 super_admin 可見 */}
          {(user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="admin" className="space-y-4">
              <AdminManagementShell user={user} />
            </TabsContent>
          )}
        </Tabs>
      </main>

      <Footer locale={locale} />
    </div>
  );
}
