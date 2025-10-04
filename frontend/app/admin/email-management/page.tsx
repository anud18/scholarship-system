"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useToast } from "@/components/ui/use-toast";
import { Loader2, Mail, Send, Search, Filter, RefreshCw } from "lucide-react";

interface EmailHistory {
  id: number;
  recipient_email: string;
  subject: string;
  body: string;
  status: string;
  sent_at: string;
  email_category?: string;
  error_message?: string;
  template_key?: string;
}

interface EmailTemplate {
  key: string;
  subject_template: string;
  body_template: string;
  sending_type: string;
  requires_approval: boolean;
}

interface SendTestEmailRequest {
  template_key: string;
  recipient_email: string;
  test_data: Record<string, string>;
}

export default function EmailManagementPage() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [emailHistory, setEmailHistory] = useState<EmailHistory[]>([]);
  const [totalEmails, setTotalEmails] = useState(0);
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);

  // Filters
  const [searchEmail, setSearchEmail] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);

  // Test email dialog
  const [testDialogOpen, setTestDialogOpen] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<string>("");
  const [testRecipient, setTestRecipient] = useState("");
  const [testData, setTestData] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);

  // Fetch email history
  const fetchEmailHistory = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: ((page - 1) * pageSize).toString(),
        limit: pageSize.toString(),
      });

      if (searchEmail) {
        params.append("recipient_email", searchEmail);
      }
      if (statusFilter !== "all") {
        params.append("status", statusFilter);
      }

      const token = localStorage.getItem("auth_token");
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/email-management/history?${params}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      const result = await response.json();
      if (result.success && result.data) {
        setEmailHistory(result.data.items || []);
        setTotalEmails(result.data.total || 0);
      }
    } catch (error) {
      console.error("Failed to fetch email history:", error);
      toast({
        title: "錯誤",
        description: "無法載入郵件歷史記錄",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  // Fetch email templates
  const fetchTemplates = async () => {
    try {
      const token = localStorage.getItem("auth_token");
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/email-management/templates`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      const result = await response.json();
      if (result.success && result.data) {
        setTemplates(result.data);
      }
    } catch (error) {
      console.error("Failed to fetch templates:", error);
    }
  };

  // Send test email
  const sendTestEmail = async () => {
    if (!selectedTemplate || !testRecipient) {
      toast({
        title: "錯誤",
        description: "請選擇模板並填寫收件人",
        variant: "destructive",
      });
      return;
    }

    setSending(true);
    try {
      const token = localStorage.getItem("auth_token");
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/email-management/send-test`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            template_key: selectedTemplate,
            recipient_email: testRecipient,
            test_data: testData,
          }),
        }
      );

      const result = await response.json();
      if (result.success) {
        toast({
          title: "成功",
          description: `測試郵件已發送至 ${testRecipient}`,
        });
        setTestDialogOpen(false);
        setTestRecipient("");
        setTestData({});
        setSelectedTemplate("");
        fetchEmailHistory(); // Refresh history
      } else {
        toast({
          title: "發送失敗",
          description: result.message || "無法發送測試郵件",
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Failed to send test email:", error);
      toast({
        title: "錯誤",
        description: "發送測試郵件時發生錯誤",
        variant: "destructive",
      });
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    fetchEmailHistory();
    fetchTemplates();
  }, [page, searchEmail, statusFilter]);

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "sent":
        return <Badge className="bg-green-500">已發送</Badge>;
      case "failed":
        return <Badge className="bg-red-500">失敗</Badge>;
      case "pending":
        return <Badge className="bg-yellow-500">待發送</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">郵件管理</h1>
        <Dialog open={testDialogOpen} onOpenChange={setTestDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Send className="mr-2 h-4 w-4" />
              發送測試郵件
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>發送測試郵件</DialogTitle>
              <DialogDescription>
                選擇郵件模板並填寫測試數據以發送測試郵件
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>郵件模板</Label>
                <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
                  <SelectTrigger>
                    <SelectValue placeholder="選擇郵件模板" />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((template) => (
                      <SelectItem key={template.key} value={template.key}>
                        {template.key} - {template.subject_template}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>收件人信箱</Label>
                <Input
                  type="email"
                  placeholder="example@nycu.edu.tw"
                  value={testRecipient}
                  onChange={(e) => setTestRecipient(e.target.value)}
                />
              </div>

              <div className="space-y-2">
                <Label>測試數據（JSON 格式）</Label>
                <p className="text-sm text-gray-500">
                  常用變數: student_name, scholarship_name, application_id, submit_date 等
                </p>
                <Input
                  placeholder='{"student_name": "測試學生", "scholarship_name": "測試獎學金"}'
                  value={JSON.stringify(testData)}
                  onChange={(e) => {
                    try {
                      setTestData(JSON.parse(e.target.value || "{}"));
                    } catch {
                      // Ignore invalid JSON
                    }
                  }}
                />
              </div>

              <Button
                onClick={sendTestEmail}
                disabled={sending}
                className="w-full"
              >
                {sending ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    發送中...
                  </>
                ) : (
                  <>
                    <Send className="mr-2 h-4 w-4" />
                    發送測試郵件
                  </>
                )}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>郵件歷史記錄</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Filters */}
          <div className="flex gap-4">
            <div className="flex-1">
              <Input
                placeholder="搜尋收件人信箱..."
                value={searchEmail}
                onChange={(e) => {
                  setSearchEmail(e.target.value);
                  setPage(1);
                }}
                className="max-w-md"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(value) => {
                setStatusFilter(value);
                setPage(1);
              }}
            >
              <SelectTrigger className="w-40">
                <SelectValue placeholder="狀態篩選" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">全部狀態</SelectItem>
                <SelectItem value="sent">已發送</SelectItem>
                <SelectItem value="failed">失敗</SelectItem>
                <SelectItem value="pending">待發送</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" size="icon" onClick={fetchEmailHistory}>
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>

          {/* Email History Table */}
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>發送時間</TableHead>
                  <TableHead>收件人</TableHead>
                  <TableHead>主旨</TableHead>
                  <TableHead>模板</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8">
                      <Loader2 className="h-6 w-6 animate-spin mx-auto" />
                    </TableCell>
                  </TableRow>
                ) : emailHistory.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-8 text-gray-500">
                      無郵件記錄
                    </TableCell>
                  </TableRow>
                ) : (
                  emailHistory.map((email) => (
                    <TableRow key={email.id}>
                      <TableCell className="whitespace-nowrap">
                        {new Date(email.sent_at).toLocaleString("zh-TW")}
                      </TableCell>
                      <TableCell>{email.recipient_email}</TableCell>
                      <TableCell className="max-w-xs truncate">
                        {email.subject}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{email.template_key || "-"}</Badge>
                      </TableCell>
                      <TableCell>{getStatusBadge(email.status)}</TableCell>
                      <TableCell>
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button variant="ghost" size="sm">
                              查看
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="max-w-3xl">
                            <DialogHeader>
                              <DialogTitle>郵件詳情</DialogTitle>
                            </DialogHeader>
                            <div className="space-y-4">
                              <div>
                                <Label>收件人</Label>
                                <p className="mt-1">{email.recipient_email}</p>
                              </div>
                              <div>
                                <Label>主旨</Label>
                                <p className="mt-1">{email.subject}</p>
                              </div>
                              <div>
                                <Label>內容</Label>
                                <ScrollArea className="h-96 mt-2 border rounded-lg p-4">
                                  <pre className="whitespace-pre-wrap text-sm">
                                    {email.body}
                                  </pre>
                                </ScrollArea>
                              </div>
                              {email.error_message && (
                                <div>
                                  <Label className="text-red-600">錯誤訊息</Label>
                                  <p className="mt-1 text-red-600">
                                    {email.error_message}
                                  </p>
                                </div>
                              )}
                            </div>
                          </DialogContent>
                        </Dialog>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-600">
              共 {totalEmails} 筆記錄，第 {page} 頁
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                上一頁
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={emailHistory.length < pageSize}
              >
                下一頁
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
