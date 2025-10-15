"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Eye, Mail, Code, FileText, AlertCircle, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { renderEmailTemplate } from "@/lib/email-renderer";

interface TemplateVariable {
  name: string;
  type: string;
  default_value?: string;
}

interface ReactEmailTemplate {
  name: string;
  display_name: string;
  description: string;
  category: string;
  file_path: string;
  variables: TemplateVariable[];
  last_modified: string;
  file_size: number;
}

interface PreviewDialogProps {
  template: ReactEmailTemplate | null;
  open: boolean;
  onClose: () => void;
}

function PreviewDialog({ template, open, onClose }: PreviewDialogProps) {
  const [testData, setTestData] = useState<Record<string, string>>({});
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [isSendingTest, setIsSendingTest] = useState(false);
  const [testEmail, setTestEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Initialize test data with default values
  useEffect(() => {
    if (template) {
      const initialData: Record<string, string> = {};
      template.variables.forEach((variable) => {
        initialData[variable.name] = variable.default_value || "";
      });
      setTestData(initialData);
    }
  }, [template]);

  const handleGeneratePreview = async () => {
    if (!template) return;

    setIsLoadingPreview(true);
    setError(null);

    try {
      const html = await renderEmailTemplate(template.name as any, testData);
      setPreviewHtml(html);
    } catch (err) {
      console.error("Failed to render template:", err);
      setError(err instanceof Error ? err.message : "渲染模板失敗");
    } finally {
      setIsLoadingPreview(false);
    }
  };

  const handleSendTestEmail = async () => {
    if (!template || !testEmail) {
      setError("請輸入測試郵箱地址");
      return;
    }

    setIsSendingTest(true);
    setError(null);
    setSuccess(null);

    try {
      // First render the email
      const html = await renderEmailTemplate(template.name as any, testData);

      // Then send it via the email API
      await api.emailManagement.sendSimpleTestEmail({
        recipient_email: testEmail,
        subject: `[測試] ${template.display_name}`,
        body: html,
      });

      setSuccess(`測試郵件已發送至 ${testEmail}`);
      setTimeout(() => setSuccess(null), 5000);
    } catch (err) {
      console.error("Failed to send test email:", err);
      setError(err instanceof Error ? err.message : "發送測試郵件失敗");
    } finally {
      setIsSendingTest(false);
    }
  };

  if (!template) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            預覽模板：{template.display_name}
          </DialogTitle>
          <DialogDescription>{template.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Template Info */}
          <div className="flex items-center gap-4 text-sm text-gray-600">
            <span className="flex items-center gap-1">
              <FileText className="h-4 w-4" />
              {template.file_path}
            </span>
            <Badge>{template.category}</Badge>
          </div>

          {/* Test Data Form */}
          <div className="space-y-4">
            <h4 className="font-semibold">測試資料</h4>
            <div className="grid grid-cols-2 gap-4">
              {template.variables.map((variable) => (
                <div key={variable.name}>
                  <Label htmlFor={variable.name}>
                    {variable.name}
                    <span className="text-xs text-gray-500 ml-2">({variable.type})</span>
                  </Label>
                  <Input
                    id={variable.name}
                    value={testData[variable.name] || ""}
                    onChange={(e) =>
                      setTestData((prev) => ({
                        ...prev,
                        [variable.name]: e.target.value,
                      }))
                    }
                    placeholder={variable.default_value || `輸入 ${variable.name}`}
                  />
                </div>
              ))}
            </div>

            <Button onClick={handleGeneratePreview} disabled={isLoadingPreview} className="w-full">
              {isLoadingPreview ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  渲染中...
                </>
              ) : (
                <>
                  <Eye className="mr-2 h-4 w-4" />
                  生成預覽
                </>
              )}
            </Button>
          </div>

          {/* Preview */}
          {previewHtml && (
            <div className="space-y-4">
              <h4 className="font-semibold">預覽</h4>
              <div className="border rounded-lg overflow-hidden">
                <iframe
                  srcDoc={previewHtml}
                  className="w-full h-[400px]"
                  title="Email Preview"
                  sandbox="allow-same-origin"
                />
              </div>
            </div>
          )}

          {/* Test Email */}
          <div className="space-y-4 border-t pt-4">
            <h4 className="font-semibold">發送測試郵件</h4>
            <div className="flex gap-2">
              <Input
                type="email"
                placeholder="輸入測試郵箱地址"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
              />
              <Button onClick={handleSendTestEmail} disabled={isSendingTest || !testEmail}>
                {isSendingTest ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    發送中...
                  </>
                ) : (
                  <>
                    <Mail className="mr-2 h-4 w-4" />
                    發送測試
                  </>
                )}
              </Button>
            </div>
          </div>

          {/* Messages */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert className="bg-green-50 text-green-900 border-green-200">
              <AlertDescription>{success}</AlertDescription>
            </Alert>
          )}

          {/* Source Code Info */}
          <Alert>
            <Code className="h-4 w-4" />
            <AlertDescription>
              此模板為 React Email 模板，僅供預覽。如需修改，請在本地開發環境編輯：
              <code className="ml-2 px-2 py-1 bg-gray-100 rounded text-xs">{template.file_path}</code>
            </AlertDescription>
          </Alert>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ReactEmailTemplateViewer() {
  const [templates, setTemplates] = useState<ReactEmailTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<ReactEmailTemplate | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.emailManagement.getReactEmailTemplates();
      console.log("📧 React Email Templates API response:", response);

      // Check if data is an array
      if (Array.isArray(response.data)) {
        console.log(`✅ Found ${response.data.length} React Email templates`);
        setTemplates(response.data);
      } else if (response.success && response.data) {
        console.warn("⚠️ Unexpected response data format:", response.data);
        setTemplates([]);
        setError("回應格式錯誤：無法解析模板列表");
      } else {
        console.warn("⚠️ No templates data in response:", response);
        setTemplates([]);
      }
    } catch (err) {
      console.error("❌ Failed to fetch React Email templates:", err);
      setError(err instanceof Error ? err.message : "載入模板失敗");
    } finally {
      setIsLoading(false);
    }
  };

  const handlePreviewTemplate = (template: ReactEmailTemplate) => {
    setSelectedTemplate(template);
    setPreviewOpen(true);
  };

  const handleViewSource = async (template: ReactEmailTemplate) => {
    try {
      const response = await api.emailManagement.getReactEmailTemplateSource(template.name);

      // Open source code in a new window or dialog
      const sourceWindow = window.open("", "_blank");
      if (sourceWindow && response.data) {
        sourceWindow.document.write(`
          <html>
            <head>
              <title>${template.display_name} - 源碼</title>
              <style>
                body { margin: 0; font-family: monospace; }
                pre { margin: 0; padding: 20px; background: #1e1e1e; color: #d4d4d4; overflow: auto; }
              </style>
            </head>
            <body>
              <pre><code>${response.data.source.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>
            </body>
          </html>
        `);
        sourceWindow.document.close();
      }
    } catch (err) {
      console.error("Failed to fetch source:", err);
      setError(err instanceof Error ? err.message : "載入源碼失敗");
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold mb-2">React Email 模板</h3>
        <p className="text-sm text-gray-600">
          以下模板使用 React Email 技術構建，存儲在 Git 倉庫中。如需修改請在本地開發環境編輯。
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {templates.map((template) => (
          <Card key={template.name} className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-base">{template.display_name}</CardTitle>
                  <CardDescription className="text-xs mt-1">{template.name}</CardDescription>
                </div>
                <Badge variant="outline">{template.category}</Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-gray-600">{template.description}</p>

              {/* Variables */}
              {template.variables.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-700 mb-2">變數 ({template.variables.length}):</p>
                  <div className="flex flex-wrap gap-1">
                    {template.variables.slice(0, 5).map((variable) => (
                      <Badge key={variable.name} variant="secondary" className="text-xs">
                        {variable.name}
                      </Badge>
                    ))}
                    {template.variables.length > 5 && (
                      <Badge variant="secondary" className="text-xs">
                        +{template.variables.length - 5}
                      </Badge>
                    )}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2">
                <Button size="sm" variant="default" onClick={() => handlePreviewTemplate(template)} className="flex-1">
                  <Eye className="mr-2 h-4 w-4" />
                  預覽
                </Button>
                <Button size="sm" variant="outline" onClick={() => handleViewSource(template)}>
                  <Code className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {templates.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>未找到 React Email 模板</p>
        </div>
      )}

      <PreviewDialog template={selectedTemplate} open={previewOpen} onClose={() => setPreviewOpen(false)} />
    </div>
  );
}
