"use client";

import { EmailAutomationManagement } from "@/components/email-automation-management";
import { EmailHistoryTable } from "@/components/email-history-table";
import { EmailTestModePanel } from "@/components/email-test-mode-panel";
import { ScheduledEmailsTable } from "@/components/scheduled-emails-table";
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

const DRAGGABLE_VARIABLES: Record<string, { label: string; desc: string }[]> = {
  application_submitted_student: [
    { label: "student_name", desc: "學生姓名" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "submission_date", desc: "申請日期" },
    { label: "application_id", desc: "申請編號" },
    { label: "scholarship_amount", desc: "獎學金金額" },
    { label: "semester", desc: "申請學期" },
  ],
  application_submitted_admin: [
    { label: "student_name", desc: "學生姓名" },
    { label: "student_id", desc: "學生學號" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "submission_date", desc: "申請時間" },
    { label: "application_id", desc: "申請編號" },
    { label: "admin_portal_url", desc: "管理系統網址" },
  ],
  professor_review_notification: [
    { label: "professor_name", desc: "教授姓名" },
    { label: "student_name", desc: "學生姓名" },
    { label: "student_id", desc: "學生學號" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "review_deadline", desc: "審查截止日期" },
    { label: "review_url", desc: "審查連結" },
  ],
  professor_review_submitted_admin: [
    { label: "professor_name", desc: "教授姓名" },
    { label: "student_name", desc: "學生姓名" },
    { label: "student_id", desc: "學生學號" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "review_result", desc: "審查結果" },
    { label: "completion_date", desc: "完成時間" },
    { label: "admin_portal_url", desc: "管理系統網址" },
  ],
  review_deadline_reminder: [
    { label: "professor_name", desc: "教授姓名" },
    { label: "student_name", desc: "學生姓名" },
    { label: "student_id", desc: "學生學號" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "review_deadline", desc: "審查截止日期" },
    { label: "days_remaining", desc: "剩餘天數" },
    { label: "review_url", desc: "審查連結" },
  ],
  supplement_request_student: [
    { label: "student_name", desc: "學生姓名" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "application_id", desc: "申請編號" },
    { label: "supplement_items", desc: "補件項目" },
    { label: "supplement_deadline", desc: "補件截止日期" },
    { label: "submission_method", desc: "補件方式" },
    { label: "supplement_url", desc: "補件上傳連結" },
  ],
  application_result_approved: [
    { label: "student_name", desc: "學生姓名" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "application_id", desc: "申請編號" },
    { label: "approved_amount", desc: "核定金額" },
    { label: "approved_semester", desc: "核定學期" },
    { label: "effective_date", desc: "生效日期" },
    { label: "next_steps", desc: "後續步驟" },
  ],
  application_result_rejected: [
    { label: "student_name", desc: "學生姓名" },
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "application_id", desc: "申請編號" },
    { label: "rejection_reason", desc: "未通過原因" },
  ],
  application_deadline_reminder: [
    { label: "scholarship_name", desc: "獎學金名稱" },
    { label: "application_deadline", desc: "申請截止日期" },
    { label: "days_remaining", desc: "剩餘天數" },
    { label: "scholarship_amount", desc: "獎學金金額" },
    { label: "eligibility_criteria", desc: "申請條件" },
    { label: "application_url", desc: "申請連結" },
  ],
  system_maintenance_notice: [
    { label: "maintenance_start", desc: "維護開始時間" },
    { label: "maintenance_end", desc: "維護結束時間" },
    { label: "maintenance_duration", desc: "維護時長" },
    { label: "maintenance_details", desc: "維護內容" },
  ],
  award_notification: [
    { label: "recipient_name", desc: "獲獎者姓名" },
    { label: "award_name", desc: "獎項名稱" },
    { label: "award_semester", desc: "獲獎學期" },
    { label: "award_amount", desc: "獎金金額" },
    { label: "ceremony_date", desc: "頒獎典禮日期" },
    { label: "award_notes", desc: "注意事項" },
  ],
};

export function EmailPanel({ user }: EmailPanelProps) {
  const [emailTab, setEmailTab] = useState("");
  const [emailTemplate, setEmailTemplate] = useState<EmailTemplate | null>(
    null
  );
  const [loadingTemplate, setLoadingTemplate] = useState(false);
  const [emailManagementTab, setEmailManagementTab] = useState("templates");
  const [emailTemplateTab, setEmailTemplateTab] = useState<"single" | "bulk">(
    "single"
  );
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [loadingEmailTemplates, setLoadingEmailTemplates] = useState(false);
  const [saving, setSaving] = useState(false);

  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  // Load email template when emailTab changes
  useEffect(() => {
    const loadTemplate = async () => {
      // Don't load if emailTab is empty
      if (!emailTab) {
        setEmailTemplate(null);
        return;
      }
      setLoadingTemplate(true);
      try {
        const response = await apiClient.admin.getEmailTemplate(emailTab);
        if (response.success && response.data) {
          setEmailTemplate({
            ...response.data,
            key: emailTab,
          });
        } else {
          // Initialize empty template
          setEmailTemplate({
            key: emailTab,
            subject_template: "",
            body_template: "",
            recipient_options: [],
            max_recipients: null,
            sending_type: "single",
            requires_approval: false,
            cc: null,
            bcc: null,
            updated_at: null,
          });
        }
      } catch (error) {
        console.error("Failed to load email template:", error);
        // Initialize empty template on error
        setEmailTemplate({
          key: emailTab,
          subject_template: "",
          body_template: "",
          recipient_options: [],
          max_recipients: null,
          sending_type: "single",
          requires_approval: false,
          cc: null,
          bcc: null,
          updated_at: null,
        });
      } finally {
        setLoadingTemplate(false);
      }
    };
    loadTemplate();
  }, [emailTab]);

  const handleTemplateChange = (field: keyof EmailTemplate, value: string) => {
    setEmailTemplate(prev => {
      if (!prev) return null;
      return { ...prev, [field]: value };
    });
  };

  const handleDropVariable = (
    variable: string,
    field: "subject_template" | "body_template",
    e: React.DragEvent
  ) => {
    e.preventDefault();
    const ref = field === "subject_template" ? subjectRef : bodyRef;
    if (!ref.current || !emailTemplate) return;

    const el = ref.current;
    const start = el.selectionStart || 0;
    const end = el.selectionEnd || 0;
    const old = emailTemplate[field] || "";
    const newValue = old.slice(0, start) + `{${variable}}` + old.slice(end);
    handleTemplateChange(field, newValue);

    // Set cursor position after the inserted variable
    setTimeout(() => {
      el.focus();
      el.selectionStart = el.selectionEnd = start + `{${variable}}`.length;
    }, 0);
  };

  const handleSaveTemplate = async () => {
    if (!emailTemplate) return;
    setSaving(true);
    try {
      const response = await apiClient.admin.updateEmailTemplate(emailTemplate);
      if (response.success && response.data) {
        setEmailTemplate(response.data);
      }
    } catch (error) {
      console.error("Failed to save email template:", error);
    } finally {
      setSaving(false);
    }
  };

  // Load email templates by sending type
  const loadEmailTemplatesBySendingType = async (
    sendingType: "single" | "bulk"
  ) => {
    setLoadingEmailTemplates(true);
    try {
      const response =
        await apiClient.admin.getEmailTemplatesBySendingType(sendingType);
      if (response.success && response.data) {
        setEmailTemplates(response.data);
        // Set the first template as selected if no template is currently selected
        if (
          response.data.length > 0 &&
          (!emailTab || !response.data.find(t => t.key === emailTab))
        ) {
          setEmailTab(response.data[0].key);
        }
      } else {
        setEmailTemplates([]);
        setEmailTab(""); // Reset email tab if no templates found
      }
    } catch (error) {
      console.error("Error loading email templates:", error);
      setEmailTemplates([]);
      setEmailTab(""); // Reset email tab on error
    }
    setLoadingEmailTemplates(false);
  };

  const getFilteredEmailTemplates = () => {
    // 中文標籤映射
    const labelMap: Record<string, string> = {
      application_submitted_student: "學生申請確認通知",
      application_submitted_admin: "管理員新申請通知",
      professor_review_notification: "教授審查通知",
      professor_review_submitted_admin: "教授審查結果通知",
      scholarship_announcement: "獎學金公告",
      application_deadline_reminder: "申請截止提醒",
    };

    return emailTemplates.map(template => ({
      key: template.key,
      label: labelMap[template.key] || template.key,
    }));
  };

  // Load email templates when sending type tab changes
  useEffect(() => {
    loadEmailTemplatesBySendingType(emailTemplateTab);
  }, [emailTemplateTab]);

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
          <TabsContent value="templates" className="space-y-6 mt-6">
            {/* 獎學金選擇 tabs */}
            <Card className="border-nycu-purple-100 bg-nycu-purple-50">
              <CardHeader className="pb-3">
                <CardTitle className="text-lg text-nycu-navy-800">
                  郵件模板類型
                </CardTitle>
                <CardDescription>
                  選擇要管理的郵件模板類型
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Tabs
                  value={emailTemplateTab}
                  onValueChange={value =>
                    setEmailTemplateTab(value as "single" | "bulk")
                  }
                >
                  <TabsList className="grid grid-cols-2 h-auto">
                    <TabsTrigger
                      value="single"
                      className="flex flex-col items-center p-3"
                    >
                      <Mail className="h-4 w-4 mb-1" />
                      <span className="text-xs">單一寄信</span>
                      <span className="text-xs text-nycu-navy-500">
                        個別通知
                      </span>
                    </TabsTrigger>
                    <TabsTrigger
                      value="bulk"
                      className="flex flex-col items-center p-3"
                    >
                      <Users className="h-4 w-4 mb-1" />
                      <span className="text-xs">批量寄信</span>
                      <span className="text-xs text-nycu-navy-500">
                        群發通知
                      </span>
                    </TabsTrigger>
                  </TabsList>
                </Tabs>
              </CardContent>
            </Card>

            {/* 通知類型選擇 */}
            <Card className="border-nycu-blue-100 bg-nycu-blue-50">
              <CardContent className="pt-4">
                <div className="flex items-center gap-4">
                  <Label className="text-nycu-navy-700 font-medium">
                    選擇通知類型
                  </Label>
                  {loadingEmailTemplates && (
                    <span className="text-sm text-gray-500">
                      載入中...
                    </span>
                  )}
                  <select
                    className="px-3 py-2 border border-nycu-blue-200 rounded-lg bg-white text-nycu-navy-700 focus:ring-2 focus:ring-nycu-blue-500 focus:border-transparent"
                    value={emailTab}
                    onChange={e => setEmailTab(e.target.value)}
                  >
                    {getFilteredEmailTemplates().length === 0 ? (
                      <option value="">載入中...</option>
                    ) : (
                      <>
                        <option value="">請選擇通知類型</option>
                        {getFilteredEmailTemplates().map(t => (
                          <option key={t.key} value={t.key}>
                            {t.label}
                          </option>
                        ))}
                      </>
                    )}
                  </select>
                </div>
              </CardContent>
            </Card>

            {/* 可拖曳變數 */}
            <Card className="border-nycu-orange-100 bg-nycu-orange-50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm text-nycu-navy-700">
                  可用變數 (可拖曳至模板中)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {DRAGGABLE_VARIABLES[emailTab]?.map(v => (
                    <span
                      key={v.label}
                      draggable
                      onDragStart={e =>
                        e.dataTransfer.setData("text/plain", v.label)
                      }
                      className="inline-flex items-center px-3 py-1 bg-gradient-to-r from-nycu-orange-500 to-nycu-orange-600 text-white rounded-full cursor-move text-sm font-medium shadow-sm hover:shadow-md transition-all duration-200 hover:from-nycu-orange-600 hover:to-nycu-orange-700"
                      title={`拖曳此變數: ${v.desc}`}
                    >
                      <span className="mr-1">📧</span>
                      {v.desc}
                    </span>
                  ))}
                </div>
                <p className="text-xs text-nycu-navy-600 mt-2">
                  💡
                  提示：將變數拖曳到下方的標題或內容欄位中，系統會自動插入對應的變數代碼
                </p>
              </CardContent>
            </Card>

            {loadingTemplate ? (
              <Card className="border-nycu-blue-200">
                <CardContent className="flex items-center justify-center py-8">
                  <div className="flex items-center gap-3">
                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                    <span className="text-nycu-navy-600">
                      載入模板中...
                    </span>
                  </div>
                </CardContent>
              </Card>
            ) : emailTemplate ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* 編輯區域 */}
                <div className="space-y-4">
                  <Card className="border-nycu-blue-200">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg text-nycu-navy-800">
                        模板編輯
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {/* 標題模板 */}
                      <div className="space-y-2">
                        <Label className="text-nycu-navy-700 font-medium">
                          📧 郵件標題
                        </Label>
                        <Input
                          ref={subjectRef}
                          value={emailTemplate.subject_template}
                          onChange={e =>
                            handleTemplateChange(
                              "subject_template",
                              e.target.value
                            )
                          }
                          onDrop={e =>
                            handleDropVariable(
                              e.dataTransfer.getData("text/plain"),
                              "subject_template",
                              e
                            )
                          }
                          onDragOver={e => e.preventDefault()}
                          placeholder="輸入郵件標題模板，可拖曳變數進來"
                          className="border-nycu-blue-200 focus:ring-nycu-blue-500"
                        />
                      </div>

                      {/* 內容模板 */}
                      <div className="space-y-2">
                        <Label className="text-nycu-navy-700 font-medium">
                          📝 郵件內容
                        </Label>
                        <Textarea
                          ref={bodyRef}
                          rows={8}
                          value={emailTemplate.body_template}
                          onChange={e =>
                            handleTemplateChange(
                              "body_template",
                              e.target.value
                            )
                          }
                          onDrop={e =>
                            handleDropVariable(
                              e.dataTransfer.getData("text/plain"),
                              "body_template",
                              e
                            )
                          }
                          onDragOver={e => e.preventDefault()}
                          placeholder="輸入郵件內容模板，可拖曳變數進來&#10;&#10;範例：&#10;親愛的 {professor_name} 教授，您好！&#10;&#10;獎學金申請案件 {app_id} 需要您的審核..."
                          className="border-nycu-blue-200 focus:ring-nycu-blue-500 resize-none"
                        />
                      </div>

                      {/* 收件者選項 */}
                      <div className="space-y-3">
                        <Label className="text-nycu-navy-700 font-medium">
                          📧 收件者選項
                        </Label>
                        <div className="p-4 bg-nycu-blue-50 rounded-lg border border-nycu-blue-200">
                          <div className="grid grid-cols-1 gap-3">
                            {emailTemplate.recipient_options &&
                            emailTemplate.recipient_options.length > 0 ? (
                              emailTemplate.recipient_options.map(
                                (option, index) => (
                                  <div
                                    key={index}
                                    className="flex items-center justify-between p-3 bg-white rounded-lg border border-gray-200"
                                  >
                                    <div className="flex-1">
                                      <div className="flex items-center gap-3">
                                        <div className="flex items-center space-x-2">
                                          <input
                                            type="radio"
                                            name="recipient_option"
                                            value={option.value}
                                            className="text-nycu-blue-600 focus:ring-nycu-blue-500"
                                            readOnly
                                          />
                                          <span className="font-medium text-nycu-navy-800">
                                            {option.label}
                                          </span>
                                        </div>
                                        <Badge
                                          variant="outline"
                                          className="text-xs"
                                        >
                                          {option.value}
                                        </Badge>
                                      </div>
                                      <p className="text-sm text-gray-600 mt-1 ml-5">
                                        {option.description}
                                      </p>
                                    </div>
                                  </div>
                                )
                              )
                            ) : (
                              <div className="text-center py-4 text-gray-500">
                                <Users className="h-8 w-8 mx-auto mb-2 text-gray-400" />
                                <p>此模板尚未配置收件者選項</p>
                                <p className="text-sm">
                                  請聯繫超級管理員進行配置
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* 郵件設定 */}
                      <div className="space-y-3">
                        <Label className="text-nycu-navy-700 font-medium">
                          ⚙️ 郵件設定
                        </Label>
                        <div className="grid grid-cols-1 gap-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                          {/* 寄信類型 */}
                          <div className="space-y-2">
                            <Label className="text-sm text-gray-600">
                              寄信類型
                            </Label>
                            <div className="flex items-center gap-4">
                              <Badge
                                variant={
                                  emailTemplate.sending_type === "single"
                                    ? "default"
                                    : "outline"
                                }
                              >
                                {emailTemplate.sending_type === "single"
                                  ? "單一寄信"
                                  : "批量寄信"}
                              </Badge>
                              {emailTemplate.max_recipients && (
                                <span className="text-sm text-gray-600">
                                  最大收件者數:{" "}
                                  {emailTemplate.max_recipients}
                                </span>
                              )}
                              {emailTemplate.requires_approval && (
                                <Badge
                                  variant="secondary"
                                  className="text-xs"
                                >
                                  需要審核
                                </Badge>
                              )}
                            </div>
                          </div>

                          {/* CC/BCC 設定 */}
                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                              <Label className="text-sm text-gray-600">
                                CC 副本
                              </Label>
                              <Input
                                value={emailTemplate.cc || ""}
                                onChange={e =>
                                  handleTemplateChange(
                                    "cc",
                                    e.target.value
                                  )
                                }
                                placeholder="多個以逗號分隔"
                                className="border-gray-300 focus:ring-nycu-blue-500 text-sm"
                              />
                            </div>
                            <div className="space-y-2">
                              <Label className="text-sm text-gray-600">
                                BCC 密件副本
                              </Label>
                              <Input
                                value={emailTemplate.bcc || ""}
                                onChange={e =>
                                  handleTemplateChange(
                                    "bcc",
                                    e.target.value
                                  )
                                }
                                placeholder="多個以逗號分隔"
                                className="border-gray-300 focus:ring-nycu-blue-500 text-sm"
                              />
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* 儲存按鈕 */}
                      <div className="flex justify-end pt-2">
                        <Button
                          onClick={handleSaveTemplate}
                          disabled={saving}
                          className="nycu-gradient text-white min-w-[120px] nycu-shadow hover:opacity-90 transition-opacity"
                        >
                          {saving ? (
                            <div className="flex items-center gap-2">
                              <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent"></div>
                              <span>儲存中...</span>
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Save className="h-4 w-4" />
                              儲存模板
                            </div>
                          )}
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* 即時預覽區域 */}
                <div className="space-y-4">
                  <Card className="border-green-200 bg-green-50">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg text-nycu-navy-800 flex items-center gap-2">
                        <Eye className="h-5 w-5 text-green-600" />
                        即時預覽
                      </CardTitle>
                      <CardDescription>
                        模板變數會自動替換為範例數據
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      {/* 郵件預覽 */}
                      <div className="bg-white border border-green-200 rounded-lg shadow-sm">
                        {/* 郵件標頭 */}
                        <div className="border-b border-green-100 p-4 bg-gradient-to-r from-green-50 to-green-100">
                          <div className="space-y-2 text-sm">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-600">
                                寄件者:
                              </span>
                              <span className="text-nycu-navy-700">
                                獎學金系統 &lt;scholarship@nycu.edu.tw&gt;
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-gray-600">
                                收件者:
                              </span>
                              <span className="text-nycu-navy-700">
                                {emailTab === "professor_notify"
                                  ? "教授信箱"
                                  : "審核人員信箱"}
                              </span>
                            </div>
                            {emailTemplate.cc && (
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-gray-600">
                                  CC:
                                </span>
                                <span className="text-nycu-navy-700">
                                  {emailTemplate.cc}
                                </span>
                              </div>
                            )}
                          </div>
                        </div>

                        {/* 郵件內容 */}
                        <div className="p-4">
                          {/* 標題預覽 */}
                          <div className="mb-4">
                            <Label className="text-sm font-medium text-gray-600 mb-1 block">
                              郵件標題:
                            </Label>
                            <div className="text-lg font-bold text-nycu-navy-800 p-3 bg-nycu-blue-50 rounded-lg border border-nycu-blue-200 flex flex-wrap items-center gap-1">
                              {(() => {
                                const parts =
                                  emailTemplate.subject_template.split(
                                    /(\{\w+\})/
                                  );
                                return parts.map((part, index) => {
                                  const match = part.match(/^\{(\w+)\}$/);
                                  if (match) {
                                    const variable = DRAGGABLE_VARIABLES[
                                      emailTab
                                    ]?.find(v => v.label === match[1]);
                                    return (
                                      <span
                                        key={index}
                                        className="inline-flex items-center px-1.5 py-0.5 bg-gray-200 text-gray-700 rounded-full text-xs font-medium border border-gray-300"
                                      >
                                        {variable
                                          ? variable.desc
                                          : match[1]}
                                      </span>
                                    );
                                  }
                                  return <span key={index}>{part}</span>;
                                });
                              })()}
                            </div>
                          </div>

                          {/* 內容預覽 */}
                          <div>
                            <Label className="text-sm font-medium text-gray-600 mb-1 block">
                              郵件內容:
                            </Label>
                            <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 min-h-[200px]">
                              <div className="whitespace-pre-line text-nycu-navy-700 leading-relaxed">
                                {(() => {
                                  const parts =
                                    emailTemplate.body_template.split(
                                      /(\{\w+\})/
                                    );
                                  return parts.map((part, index) => {
                                    const match =
                                      part.match(/^\{(\w+)\}$/);
                                    if (match) {
                                      const variable =
                                        DRAGGABLE_VARIABLES[
                                          emailTab
                                        ]?.find(
                                          v => v.label === match[1]
                                        );
                                      return (
                                        <span
                                          key={index}
                                          className="inline-flex items-center px-1.5 py-0.5 bg-gray-200 text-gray-700 rounded-full text-xs font-medium border border-gray-300"
                                        >
                                          {variable
                                            ? variable.desc
                                            : match[1]}
                                        </span>
                                      );
                                    }
                                    return (
                                      <span
                                        key={index}
                                        className="whitespace-pre-line"
                                      >
                                        {part}
                                      </span>
                                    );
                                  });
                                })()}
                              </div>
                            </div>
                          </div>

                          {/* 系統簽名 */}
                          <div className="mt-4 pt-4 border-t border-gray-200">
                            <div className="text-sm text-gray-600">
                              <p>此為系統自動發送郵件，請勿直接回覆</p>
                              <p className="mt-1">
                                國立陽明交通大學教務處
                              </p>
                              <p>獎學金申請與簽核系統</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              </div>
            ) : (
              <Card className="border-gray-200">
                <CardContent className="flex items-center justify-center py-8">
                  <div className="text-center text-gray-500">
                    <FileText className="h-12 w-12 mx-auto mb-3 text-gray-400" />
                    <p>請選擇通知類型以載入模板</p>
                  </div>
                </CardContent>
              </Card>
            )}
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
