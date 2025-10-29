"use client";

import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  RefreshCw,
  Clock,
  CheckCircle,
  XCircle,
  Eye,
  Edit3,
  Save,
  X,
} from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import apiClient from "@/lib/api";
import {
  EmailStatus,
  getEmailStatusLabel,
  getEmailStatusVariant,
} from "@/lib/enums";

interface ScheduledEmailsTableProps {
  className?: string;
  currentUserRole: string;
}

interface ScheduledEmailItem {
  id: number;
  recipient_email: string;
  cc_emails?: string;
  bcc_emails?: string;
  subject: string;
  body: string;
  scheduled_for: string;
  status: string;
  requires_approval: boolean;
  approved_by_user_id?: number;
  approved_at?: string;
  approval_notes?: string;
  priority: number;
  is_due: boolean;
  is_ready_to_send: boolean;
  application_app_id?: string;
  scholarship_type_name?: string;
  created_by_username?: string;
  approved_by_username?: string;
  email_category?: string;
}

interface ScheduledEmailsFilters {
  status: string;
  scholarship_type_id: string;
  requires_approval: string;
  email_category: string;
  scheduled_from: string;
  scheduled_to: string;
}

export function ScheduledEmailsTable({
  className,
  currentUserRole,
}: ScheduledEmailsTableProps) {
  const [scheduledEmails, setScheduledEmails] = useState<ScheduledEmailItem[]>(
    []
  );
  const [loading, setLoading] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState<ScheduledEmailItem | null>(
    null
  );
  const [pagination, setPagination] = useState({
    skip: 0,
    limit: 50,
    total: 0,
  });
  const [filters, setFilters] = useState<ScheduledEmailsFilters>({
    status: "all",
    scholarship_type_id: "all",
    requires_approval: "all",
    email_category: "all",
    scheduled_from: "",
    scheduled_to: "",
  });
  const [isEditMode, setIsEditMode] = useState(false);
  const [editingSubject, setEditingSubject] = useState("");
  const [editingBody, setEditingBody] = useState("");

  const loadScheduledEmails = async () => {
    setLoading(true);
    try {
      // Convert datetime filters to ISO datetime format
      const processedFilters = { ...filters };
      if (processedFilters.scheduled_from) {
        processedFilters.scheduled_from = `${processedFilters.scheduled_from}:00Z`;
      }
      if (processedFilters.scheduled_to) {
        processedFilters.scheduled_to = `${processedFilters.scheduled_to}:59Z`;
      }

      const params = {
        skip: pagination.skip,
        limit: pagination.limit,
        ...Object.fromEntries(
          Object.entries(processedFilters).filter(
            ([_, v]) => v !== "" && v !== "all"
          )
        ),
      };

      const response =
        await apiClient.emailManagement.getScheduledEmails(params);
      if (response.success && response.data) {
        const { items, total } = response.data;
        setScheduledEmails(items);
        setPagination(prev => ({
          ...prev,
          total,
        }));
      }
    } catch (error) {
      console.error("Failed to load scheduled emails:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleApproveEmail = async (emailId: number, notes?: string) => {
    try {
      const response = await apiClient.emailManagement.approveScheduledEmail(
        emailId,
        notes
      );
      if (response.success) {
        // Reload the scheduled emails to show updated status
        await loadScheduledEmails();
      }
    } catch (error) {
      console.error("Failed to approve email:", error);
    }
  };

  const handleCancelEmail = async (emailId: number) => {
    try {
      const response =
        await apiClient.emailManagement.cancelScheduledEmail(emailId);
      if (response.success) {
        // Reload the scheduled emails to show updated status
        await loadScheduledEmails();
      }
    } catch (error) {
      console.error("Failed to cancel email:", error);
    }
  };

  useEffect(() => {
    loadScheduledEmails();
  }, [pagination.skip, filters]);

  const getPriorityLabel = (priority: number) => {
    if (priority <= 3) return "高";
    if (priority <= 6) return "中";
    return "低";
  };

  const getPriorityVariant = (
    priority: number
  ): "default" | "secondary" | "destructive" | "outline" => {
    if (priority <= 3) return "destructive";
    if (priority <= 6) return "default";
    return "secondary";
  };

  const getEmailCategoryLabel = (category?: string) => {
    const categoryLabels: Record<string, string> = {
      APPLICATION_WHITELIST: "申請通知－白名單",
      APPLICATION_STUDENT: "申請通知－申請者",
      RECOMMENDATION_PROFESSOR: "推薦通知－指導教授",
      REVIEW_COLLEGE: "審核通知－學院",
      SUPPLEMENT_STUDENT: "補件通知－申請者",
      RESULT_PROFESSOR: "結果通知－指導教授",
      RESULT_COLLEGE: "結果通知－學院",
      RESULT_STUDENT: "結果通知－申請者",
      ROSTER_STUDENT: "造冊通知－申請者",
      SYSTEM: "系統通知",
      OTHER: "其他",
    };
    return categoryLabels[category || ""] || "未分類";
  };

  const getCategoryVariant = (
    category?: string
  ): "default" | "secondary" | "destructive" | "outline" => {
    if (!category) return "default";
    if (category.includes("APPLICATION")) return "default";
    if (category.includes("RECOMMENDATION")) return "secondary";
    if (category.includes("REVIEW")) return "outline";
    if (category.includes("RESULT")) return "destructive";
    return "default";
  };

  const renderTemplateVariables = (content: string) => {
    if (!content) return content;

    // Match variables in {variable} format
    return content.split(/(\{[^}]+\})/g).map((part, index) => {
      if (part.match(/^\{[^}]+\}$/)) {
        const variableName = part.slice(1, -1);
        return (
          <span
            key={index}
            className="inline-block px-2 py-1 mx-1 text-xs bg-blue-100 text-blue-800 rounded-md border border-blue-200"
          >
            {variableName}
          </span>
        );
      }
      return part;
    });
  };

  const handleEditClick = () => {
    if (selectedEmail) {
      setEditingSubject(selectedEmail.subject);
      setEditingBody(selectedEmail.body);
      setIsEditMode(true);
    }
  };

  const handleSaveEdit = async () => {
    if (!selectedEmail) return;

    try {
      await apiClient.emailManagement.updateScheduledEmail(selectedEmail.id, {
        subject: editingSubject,
        body: editingBody,
      });

      // Update the email in the list
      setScheduledEmails(prev =>
        prev.map(email =>
          email.id === selectedEmail.id
            ? { ...email, subject: editingSubject, body: editingBody }
            : email
        )
      );

      // Update selected email
      setSelectedEmail(prev =>
        prev ? { ...prev, subject: editingSubject, body: editingBody } : null
      );
      setIsEditMode(false);
    } catch (error) {
      console.error("Failed to update scheduled email:", error);
    }
  };

  const handleCancelEdit = () => {
    setIsEditMode(false);
    setEditingSubject("");
    setEditingBody("");
  };

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-nycu-navy-800">
          排程郵件管理
        </h3>
        <Button
          onClick={loadScheduledEmails}
          variant="outline"
          size="sm"
          disabled={loading}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`}
          />
          重新載入
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-5 gap-4">
            <div>
              <Label className="text-sm font-medium">狀態</Label>
              <Select
                value={filters.status}
                onValueChange={value =>
                  setFilters(prev => ({ ...prev, status: value }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value={EmailStatus.PENDING}>待發送</SelectItem>
                  <SelectItem value={EmailStatus.SENT}>已發送</SelectItem>
                  <SelectItem value={EmailStatus.CANCELLED}>已取消</SelectItem>
                  <SelectItem value={EmailStatus.FAILED}>發送失敗</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm font-medium">需要審核</Label>
              <Select
                value={filters.requires_approval}
                onValueChange={value =>
                  setFilters(prev => ({ ...prev, requires_approval: value }))
                }
              >
                <SelectTrigger className="h-8">
                  <SelectValue placeholder="全部" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部</SelectItem>
                  <SelectItem value="true">需要審核</SelectItem>
                  <SelectItem value="false">不需要審核</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-sm font-medium">排程開始時間</Label>
              <Input
                type="datetime-local"
                value={filters.scheduled_from}
                onChange={e =>
                  setFilters(prev => ({
                    ...prev,
                    scheduled_from: e.target.value,
                  }))
                }
                className="h-8"
              />
            </div>
            <div>
              <Label className="text-sm font-medium">排程結束時間</Label>
              <Input
                type="datetime-local"
                value={filters.scheduled_to}
                onChange={e =>
                  setFilters(prev => ({
                    ...prev,
                    scheduled_to: e.target.value,
                  }))
                }
                className="h-8"
              />
            </div>
            <div className="flex items-end">
              <Button
                onClick={() =>
                  setFilters({
                    status: "all",
                    scholarship_type_id: "all",
                    requires_approval: "all",
                    email_category: "all",
                    scheduled_from: "",
                    scheduled_to: "",
                  })
                }
                variant="outline"
                size="sm"
                className="h-8"
              >
                清除篩選
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Scheduled Emails Table */}
      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                <span className="text-nycu-navy-600">載入中...</span>
              </div>
            </div>
          ) : scheduledEmails.length > 0 ? (
            <div className="space-y-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>排程時間</TableHead>
                    <TableHead>收件者</TableHead>
                    <TableHead>主旨</TableHead>
                    <TableHead>狀態</TableHead>
                    <TableHead>需要審核</TableHead>
                    <TableHead>優先度</TableHead>
                    <TableHead>查看內容</TableHead>
                    <TableHead>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {scheduledEmails.map(email => (
                    <TableRow key={email.id}>
                      <TableCell>
                        <div className="flex flex-col">
                          <span>
                            {new Date(email.scheduled_for).toLocaleString(
                              "zh-TW"
                            )}
                          </span>
                          {email.is_due && (
                            <Badge
                              variant="destructive"
                              className="mt-1 text-xs"
                            >
                              已到期
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {email.recipient_email}
                      </TableCell>
                      <TableCell className="max-w-[300px] truncate">
                        {email.subject}
                      </TableCell>
                      <TableCell>
                        <Badge variant={getEmailStatusVariant(email.status as EmailStatus)}>
                          {getEmailStatusLabel(email.status as EmailStatus)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {email.requires_approval ? (
                          email.approved_by_user_id ? (
                            <div className="flex flex-col">
                              <Badge variant="default" className="mb-1">
                                已審核
                              </Badge>
                              {email.approved_at && (
                                <span className="text-xs text-gray-500">
                                  {new Date(
                                    email.approved_at
                                  ).toLocaleDateString("zh-TW")}
                                </span>
                              )}
                            </div>
                          ) : (
                            <Badge variant="destructive">待審核</Badge>
                          )
                        ) : (
                          <Badge variant="secondary">不需要</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant={getPriorityVariant(email.priority)}>
                          {getPriorityLabel(email.priority)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setSelectedEmail(email)}
                            >
                              <Eye className="h-4 w-4 mr-1" />
                              查看模板
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
                            <DialogHeader>
                              <DialogTitle>排程郵件內容</DialogTitle>
                              <DialogDescription>
                                即將寄出的郵件模板內容預覽
                              </DialogDescription>
                            </DialogHeader>
                            {selectedEmail && (
                              <div className="space-y-6">
                                <div className="grid grid-cols-2 gap-6">
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">
                                      收件者
                                    </Label>
                                    <p className="text-sm text-gray-900">
                                      {selectedEmail.recipient_email}
                                    </p>
                                  </div>
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">
                                      排程時間
                                    </Label>
                                    <p className="text-sm text-gray-900">
                                      {new Date(
                                        selectedEmail.scheduled_for
                                      ).toLocaleString("zh-TW")}
                                    </p>
                                  </div>
                                  {selectedEmail.cc_emails && (
                                    <div className="space-y-2">
                                      <Label className="text-sm font-medium text-gray-700">
                                        副本收件者 (CC)
                                      </Label>
                                      <p className="text-sm text-gray-900">
                                        {selectedEmail.cc_emails}
                                      </p>
                                    </div>
                                  )}
                                  {selectedEmail.bcc_emails && (
                                    <div className="space-y-2">
                                      <Label className="text-sm font-medium text-gray-700">
                                        密件副本 (BCC)
                                      </Label>
                                      <p className="text-sm text-gray-900">
                                        {selectedEmail.bcc_emails}
                                      </p>
                                    </div>
                                  )}
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">
                                      郵件類別
                                    </Label>
                                    <div>
                                      <Badge
                                        variant={getCategoryVariant(
                                          selectedEmail.email_category
                                        )}
                                      >
                                        {getEmailCategoryLabel(
                                          selectedEmail.email_category
                                        )}
                                      </Badge>
                                    </div>
                                  </div>
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">
                                      狀態
                                    </Label>
                                    <div>
                                      <Badge
                                        variant={getEmailStatusVariant(
                                          selectedEmail.status as EmailStatus
                                        )}
                                      >
                                        {getEmailStatusLabel(selectedEmail.status as EmailStatus)}
                                      </Badge>
                                    </div>
                                  </div>
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">
                                      優先度
                                    </Label>
                                    <div>
                                      <Badge
                                        variant={getPriorityVariant(
                                          selectedEmail.priority
                                        )}
                                      >
                                        {getPriorityLabel(
                                          selectedEmail.priority
                                        )}
                                      </Badge>
                                    </div>
                                  </div>
                                  <div className="space-y-2">
                                    <Label className="text-sm font-medium text-gray-700">
                                      需要審核
                                    </Label>
                                    <div>
                                      <Badge
                                        variant={
                                          selectedEmail.requires_approval
                                            ? "destructive"
                                            : "secondary"
                                        }
                                      >
                                        {selectedEmail.requires_approval
                                          ? "需要審核"
                                          : "不需要審核"}
                                      </Badge>
                                    </div>
                                  </div>
                                  {selectedEmail.approved_by_username && (
                                    <div className="space-y-2">
                                      <Label className="text-sm font-medium text-gray-700">
                                        審核者
                                      </Label>
                                      <p className="text-sm text-gray-900">
                                        {selectedEmail.approved_by_username}
                                      </p>
                                    </div>
                                  )}
                                  {selectedEmail.approval_notes && (
                                    <div className="col-span-2 space-y-2">
                                      <Label className="text-sm font-medium text-gray-700">
                                        審核備註
                                      </Label>
                                      <p className="text-sm text-blue-800 bg-blue-50 p-3 rounded-md border border-blue-200">
                                        {selectedEmail.approval_notes}
                                      </p>
                                    </div>
                                  )}
                                </div>
                                <div className="space-y-3">
                                  <div className="flex items-center justify-between">
                                    <Label className="text-sm font-medium text-gray-700">
                                      主旨
                                    </Label>
                                    {currentUserRole === "super_admin" &&
                                      selectedEmail.status === EmailStatus.PENDING &&
                                      !isEditMode && (
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          onClick={handleEditClick}
                                          className="h-6 px-2 text-xs"
                                        >
                                          <Edit3 className="h-3 w-3 mr-1" />
                                          編輯
                                        </Button>
                                      )}
                                  </div>
                                  {isEditMode ? (
                                    <div className="space-y-2">
                                      <Input
                                        value={editingSubject}
                                        onChange={e =>
                                          setEditingSubject(e.target.value)
                                        }
                                        className="text-sm"
                                        placeholder="請輸入主旨"
                                      />
                                      <div className="flex gap-2">
                                        <Button
                                          size="sm"
                                          onClick={handleSaveEdit}
                                          className="h-6 px-2 text-xs"
                                        >
                                          <Save className="h-3 w-3 mr-1" />
                                          儲存
                                        </Button>
                                        <Button
                                          size="sm"
                                          variant="outline"
                                          onClick={handleCancelEdit}
                                          className="h-6 px-2 text-xs"
                                        >
                                          <X className="h-3 w-3 mr-1" />
                                          取消
                                        </Button>
                                      </div>
                                    </div>
                                  ) : (
                                    <div className="text-sm font-medium bg-gray-50 p-3 rounded-md border">
                                      {renderTemplateVariables(
                                        selectedEmail.subject
                                      )}
                                    </div>
                                  )}
                                </div>
                                <div className="space-y-3">
                                  <Label className="text-sm font-medium text-gray-700">
                                    郵件內容模板
                                  </Label>
                                  {isEditMode ? (
                                    <Textarea
                                      value={editingBody}
                                      onChange={e =>
                                        setEditingBody(e.target.value)
                                      }
                                      className="min-h-64 text-sm"
                                      placeholder="請輸入郵件內容"
                                    />
                                  ) : (
                                    <div className="bg-gray-50 p-4 rounded-md border max-h-96 overflow-y-auto">
                                      <div className="whitespace-pre-wrap text-sm leading-relaxed text-gray-900">
                                        {renderTemplateVariables(
                                          selectedEmail.body
                                        )}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </DialogContent>
                        </Dialog>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          {email.status === EmailStatus.PENDING &&
                            email.requires_approval &&
                            !email.approved_by_user_id &&
                            currentUserRole === "super_admin" && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleApproveEmail(email.id)}
                                className="text-green-600 border-green-200 hover:bg-green-50"
                              >
                                <CheckCircle className="h-4 w-4 mr-1" />
                                審核通過
                              </Button>
                            )}
                          {email.status === EmailStatus.PENDING && (
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => handleCancelEmail(email.id)}
                            >
                              <XCircle className="h-4 w-4 mr-1" />
                              取消
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between">
                <div className="text-sm text-gray-500">
                  顯示 {pagination.skip + 1} -{" "}
                  {Math.min(
                    pagination.skip + pagination.limit,
                    pagination.total
                  )}
                  共 {pagination.total} 筆
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={pagination.skip === 0}
                    onClick={() =>
                      setPagination(prev => ({
                        ...prev,
                        skip: Math.max(0, prev.skip - prev.limit),
                      }))
                    }
                  >
                    上一頁
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={
                      pagination.skip + pagination.limit >= pagination.total
                    }
                    onClick={() =>
                      setPagination(prev => ({
                        ...prev,
                        skip: prev.skip + prev.limit,
                      }))
                    }
                  >
                    下一頁
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              <Clock className="h-16 w-16 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium">尚無排程郵件</p>
              <p className="text-sm mt-2">系統排程的郵件會顯示在這裡</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
