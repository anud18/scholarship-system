"use client";

import React, { useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ReactEmailTemplateViewer } from "./react-email-template-viewer";
import { TextTemplateEditor } from "./text-template-editor";
import { Mail, FileText, Code } from "lucide-react";

interface EmailTemplateManagementProps {
  locale?: "zh" | "en";
}

export function EmailTemplateManagement({ locale = "zh" }: EmailTemplateManagementProps) {
  const [activeTab, setActiveTab] = useState<string>("react-email");

  const translations = {
    zh: {
      title: "郵件模板管理",
      description: "管理系統郵件模板，包括 React Email 模板和文字模板",
      reactEmailTab: "React Email 模板",
      textTemplateTab: "文字模板",
      reactEmailDesc: "現代化郵件模板，使用 React 技術構建",
      textTemplateDesc: "資料庫儲存的簡單文字模板，可直接編輯",
    },
    en: {
      title: "Email Template Management",
      description: "Manage system email templates, including React Email templates and text templates",
      reactEmailTab: "React Email Templates",
      textTemplateTab: "Text Templates",
      reactEmailDesc: "Modern email templates built with React technology",
      textTemplateDesc: "Simple text templates stored in database, directly editable",
    },
  };

  const t = translations[locale];

  return (
    <div className="container mx-auto py-8 px-4">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Mail className="h-8 w-8 text-nycu-blue-600" />
            <div>
              <CardTitle className="text-2xl">{t.title}</CardTitle>
              <CardDescription>{t.description}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2 mb-6">
              <TabsTrigger value="react-email" className="flex items-center gap-2">
                <Code className="h-4 w-4" />
                {t.reactEmailTab}
              </TabsTrigger>
              <TabsTrigger value="text-template" className="flex items-center gap-2">
                <FileText className="h-4 w-4" />
                {t.textTemplateTab}
              </TabsTrigger>
            </TabsList>

            <TabsContent value="react-email" className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-4">
                <p className="text-sm text-blue-900">{t.reactEmailDesc}</p>
              </div>
              <ReactEmailTemplateViewer />
            </TabsContent>

            <TabsContent value="text-template" className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
                <p className="text-sm text-green-900">{t.textTemplateDesc}</p>
              </div>
              <TextTemplateEditor />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
