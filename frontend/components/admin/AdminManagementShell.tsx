"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AdminManagementProvider, useAdminManagement } from "@/contexts/admin-management-context";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import apiClient, { type ScholarshipPermission } from "@/lib/api";

// Lazy load heavy components
const DashboardPanel = dynamic(() => import("./dashboard/DashboardPanel").then(mod => ({ default: mod.DashboardPanel })), {
  loading: () => <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div></div>
});

const EmailPanel = dynamic(() => import("./email/EmailPanel").then(mod => ({ default: mod.EmailPanel })), {
  loading: () => <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div></div>
});

const HistoryPanel = dynamic(() => import("./history/HistoryPanel").then(mod => ({ default: mod.HistoryPanel })), {
  loading: () => <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div></div>
});

const AnnouncementsPanel = dynamic(() => import("./announcements/AnnouncementsPanel").then(mod => ({ default: mod.AnnouncementsPanel })), {
  loading: () => <div className="flex items-center justify-center py-8"><div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div></div>
});

// Import lighter components directly
import { UserManagementPanel } from "./users/UserManagementPanel";
import { QuotaPanel } from "./quota/QuotaPanel";
import { ConfigurationsPanel } from "./configurations/ConfigurationsPanel";
import { RulesPanel } from "./rules/RulesPanel";
import { WorkflowsPanel } from "./workflows/WorkflowsPanel";
import { SettingsPanel } from "./settings/SettingsPanel";

interface User {
  id: string;
  nycu_id: string;
  name: string;
  email: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
}

interface AdminManagementShellProps {
  user: User;
}

function AdminManagementContent({ user }: AdminManagementShellProps) {
  const { activeTab, setActiveTab } = useAdminManagement();
  const [hasQuotaPermission, setHasQuotaPermission] = useState(false);

  // Check quota permissions
  useEffect(() => {
    const checkQuotaPermission = async () => {
      if (user.role === "super_admin") {
        setHasQuotaPermission(true);
        return;
      }

      try {
        const response = await apiClient.admin.getCurrentUserScholarshipPermissions();
        if (response.success && response.data) {
          const permissions = response.data as ScholarshipPermission[];
          const hasQuota = permissions.some(
            (p: any) => p.can_manage_quota
          );
          setHasQuotaPermission(hasQuota);
        }
      } catch (error) {
        console.error("Failed to check quota permissions:", error);
      }
    };

    checkQuotaPermission();
  }, [user.role]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">系統管理</h2>
          <p className="text-muted-foreground">
            管理系統設定、工作流程與使用者權限
          </p>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList
          className={`grid w-full ${hasQuotaPermission ? "grid-cols-10" : "grid-cols-9"}`}
        >
          <TabsTrigger value="dashboard">系統概覽</TabsTrigger>
          <TabsTrigger value="users">使用者權限</TabsTrigger>
          {hasQuotaPermission && (
            <TabsTrigger value="quota">名額管理</TabsTrigger>
          )}
          <TabsTrigger value="configurations">獎學金配置</TabsTrigger>
          <TabsTrigger value="rules">審核規則</TabsTrigger>
          <TabsTrigger value="workflows">工作流程</TabsTrigger>
          <TabsTrigger value="email">郵件管理</TabsTrigger>
          <TabsTrigger value="history">歷史申請</TabsTrigger>
          <TabsTrigger value="announcements">系統公告</TabsTrigger>
          <TabsTrigger value="settings">系統設定</TabsTrigger>
        </TabsList>

        <TabsContent value="dashboard" className="space-y-4">
          <DashboardPanel />
        </TabsContent>

        <TabsContent value="users" className="space-y-4">
          <UserManagementPanel />
        </TabsContent>

        {hasQuotaPermission && (
          <TabsContent value="quota" className="space-y-4">
            <QuotaPanel />
          </TabsContent>
        )}

        <TabsContent value="configurations" className="space-y-4">
          <ConfigurationsPanel />
        </TabsContent>

        <TabsContent value="rules" className="space-y-4">
          <RulesPanel />
        </TabsContent>

        <TabsContent value="workflows" className="space-y-4">
          <WorkflowsPanel />
        </TabsContent>

        <TabsContent value="email" className="space-y-4">
          <EmailPanel user={user} />
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <HistoryPanel user={user} />
        </TabsContent>

        <TabsContent value="announcements" className="space-y-4">
          <AnnouncementsPanel user={user} />
        </TabsContent>

        <TabsContent value="settings" className="space-y-4">
          <SettingsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

export function AdminManagementShell({ user }: AdminManagementShellProps) {
  return (
    <AdminManagementProvider userRole={user.role}>
      <AdminManagementContent user={user} />
    </AdminManagementProvider>
  );
}
