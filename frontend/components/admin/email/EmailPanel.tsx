"use client";

import { EmailAutomationManagement } from "@/components/email-automation-management";
import { EmailHistoryTable } from "@/components/email-history-table";
import { EmailTestModePanel } from "@/components/email-test-mode-panel";
import { ScheduledEmailsTable } from "@/components/scheduled-emails-table";
import { EmailTemplateManagement } from "@/components/email-template-management";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import apiClient, { EmailTemplate } from "@/lib/api";
import { Eye, FileText, Mail, Save, Users } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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

interface EmailPanelProps {
  user: User;
}

export function EmailPanel({ user }: EmailPanelProps) {
  const [emailManagementTab, setEmailManagementTab] = useState("templates");

  return (
    <Card className="academic-card border-nycu-blue-200">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
          <Mail className="h-5 w-5 text-nycu-blue-600" />
          郵件管理
        </CardTitle>
        <CardDescription>
          管理郵件模板、查看歷史記錄、管理排程郵件
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs
          value={emailManagementTab}
          onValueChange={setEmailManagementTab}
        >
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="templates">郵件模板</TabsTrigger>
            <TabsTrigger value="automation">自動化規則</TabsTrigger>
            <TabsTrigger value="history">歷史記錄</TabsTrigger>
            <TabsTrigger value="scheduled">排程郵件</TabsTrigger>
            <TabsTrigger value="test-mode">測試模式</TabsTrigger>
          </TabsList>

          {/* 郵件模板管理 */}
          <TabsContent value="templates" className="mt-6">
            <EmailTemplateManagement locale="zh" />
          </TabsContent>

          {/* 郵件自動化規則 */}
          <TabsContent value="automation" className="mt-6">
            <EmailAutomationManagement />
          </TabsContent>

          {/* 郵件歷史記錄 */}
          <TabsContent value="history" className="mt-6">
            <EmailHistoryTable />
          </TabsContent>

          {/* 排程郵件管理 */}
          <TabsContent value="scheduled" className="mt-6">
            <ScheduledEmailsTable currentUserRole={user.role} />
          </TabsContent>

          {/* 測試模式 */}
          <TabsContent value="test-mode" className="mt-6">
            <EmailTestModePanel />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
