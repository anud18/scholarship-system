"use client";

import { AdminConfigurationManagement } from "@/components/admin-configuration-management";
import { AdminRuleManagement } from "@/components/admin-rule-management";
import { EmailHistoryTable } from "@/components/email-history-table";
import { EmailTestModePanel } from "@/components/email-test-mode-panel";
import { QuotaManagement } from "@/components/quota-management";
import { ScheduledEmailsTable } from "@/components/scheduled-emails-table";
import { ScholarshipWorkflowMermaid } from "@/components/ScholarshipWorkflowMermaid";
import SystemConfigurationManagement from "@/components/system-configuration-management";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { UserEditModal } from "@/components/user-edit-modal";
import apiClient, {
  AnnouncementCreate,
  AnnouncementUpdate,
  EmailTemplate,
  HistoricalApplication,
  HistoricalApplicationFilters,
  NotificationResponse,
  ScholarshipConfiguration,
  ScholarshipPermission,
  ScholarshipRule,
  SystemStats,
  UserCreate,
  UserListResponse,
  UserStats,
  Workflow,
} from "@/lib/api";
import {
  AlertCircle,
  Clock,
  Database,
  Edit,
  Eye,
  FileText,
  Mail,
  MessageSquare,
  Plus,
  RefreshCw,
  Save,
  Send,
  Settings,
  Trash2,
  Upload,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

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

interface AdminManagementInterfaceProps {
  user: User;
}

// This will be loaded dynamically from the API based on sending type;

const TEMPLATE_VARIABLES: Record<string, string[]> = {
  professor_notify: ["app_id", "professor_name"],
  college_notify: ["app_id"],
};

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

export function AdminManagementInterface({
  user,
}: AdminManagementInterfaceProps) {
  // 工作流程狀態
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loadingWorkflows, setLoadingWorkflows] = useState(false);
  const [workflowsError, setWorkflowsError] = useState<string | null>(null);

  // 獎學金規則狀態
  const [scholarshipRules, setScholarshipRules] = useState<ScholarshipRule[]>(
    []
  );
  const [loadingRules, setLoadingRules] = useState(false);
  const [rulesError, setRulesError] = useState<string | null>(null);
  const [selectedRule, setSelectedRule] = useState<ScholarshipRule | null>(
    null
  );
  const [showRuleDetails, setShowRuleDetails] = useState(false);
  const [showRuleForm, setShowRuleForm] = useState(false);
  const [editingRule, setEditingRule] = useState<ScholarshipRule | null>(null);
  const [ruleFormLoading, setRuleFormLoading] = useState(false);
  const [selectedScholarshipTab, setSelectedScholarshipTab] =
    useState("scholarship-1");
  const [selectedAcademicYear, setSelectedAcademicYear] = useState(114);
  const [selectedSemester, setSelectedSemester] = useState<string | null>(
    "first"
  );
  const [ruleTypeFilter, setRuleTypeFilter] = useState<
    "initial" | "renewal" | "all"
  >("all");
  const [scholarshipTypes, setScholarshipTypes] = useState<any[]>([]);
  const [loadingScholarshipTypes, setLoadingScholarshipTypes] = useState(false);

  // Scholarship Configurations for Workflow
  const [scholarshipConfigurations, setScholarshipConfigurations] = useState<
    ScholarshipConfiguration[]
  >([]);
  const [loadingConfigurations, setLoadingConfigurations] = useState(false);
  const [selectedConfigurationId, setSelectedConfigurationId] = useState<
    number | undefined
  >();

  // 系統統計狀態
  const [systemStats, setSystemStats] = useState<SystemStats>({
    totalUsers: 0,
    activeApplications: 0,
    completedReviews: 0,
    systemUptime: "0%",
    avgResponseTime: "0ms",
    storageUsed: "0TB",
    pendingReviews: 0,
    totalScholarships: 0,
  });
  const [loadingStats, setLoadingStats] = useState(false);
  const [statsError, setStatsError] = useState<string | null>(null);

  const [emailTab, setEmailTab] = useState("");
  const [emailTemplate, setEmailTemplate] = useState<EmailTemplate | null>(
    null
  );

  // Email Management states
  const [emailManagementTab, setEmailManagementTab] = useState("templates");
  const [emailHistory, setEmailHistory] = useState<any[]>([]);
  const [scheduledEmails, setScheduledEmails] = useState<any[]>([]);
  const [loadingEmailHistory, setLoadingEmailHistory] = useState(false);
  const [loadingScheduledEmails, setLoadingScheduledEmails] = useState(false);
  const [emailHistoryPagination, setEmailHistoryPagination] = useState({
    skip: 0,
    limit: 50,
    total: 0,
  });
  const [scheduledEmailsPagination, setScheduledEmailsPagination] = useState({
    skip: 0,
    limit: 50,
    total: 0,
  });
  const [emailHistoryFilters, setEmailHistoryFilters] = useState({
    email_category: "",
    status: "",
    scholarship_type_id: "",
    recipient_email: "",
    date_from: "",
    date_to: "",
  });
  const [scheduledEmailsFilters, setScheduledEmailsFilters] = useState({
    status: "",
    scholarship_type_id: "",
    requires_approval: "",
    email_category: "",
    scheduled_from: "",
    scheduled_to: "",
  });
  const [loadingTemplate, setLoadingTemplate] = useState(false);

  // Email Template states by sending type
  const [emailTemplateTab, setEmailTemplateTab] = useState<"single" | "bulk">(
    "single"
  );
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([]);
  const [loadingEmailTemplates, setLoadingEmailTemplates] = useState(false);
  const [saving, setSaving] = useState(false);

  // Scholarship Email Template states
  const [scholarshipEmailTab, setScholarshipEmailTab] = useState("system");
  const [scholarshipEmailTemplates, setScholarshipEmailTemplates] = useState<
    any[]
  >([]);
  const [loadingScholarshipTemplates, setLoadingScholarshipTemplates] =
    useState(false);
  const [currentScholarshipTemplate, setCurrentScholarshipTemplate] =
    useState<any>(null);
  const [myScholarships, setMyScholarships] = useState<any[]>([]);

  // 歷史申請相關狀態
  const [historicalApplications, setHistoricalApplications] = useState<
    HistoricalApplication[]
  >([]);
  const [historicalApplicationsGroups, setHistoricalApplicationsGroups] =
    useState<Record<string, HistoricalApplication[]>>({});
  const [activeHistoricalTab, setActiveHistoricalTab] = useState<string>("all");
  const [loadingHistoricalApplications, setLoadingHistoricalApplications] =
    useState(false);
  const [historicalApplicationsError, setHistoricalApplicationsError] =
    useState<string | null>(null);
  const [
    historicalApplicationsPagination,
    setHistoricalApplicationsPagination,
  ] = useState({
    page: 1,
    size: 20,
    total: 0,
    pages: 0,
  });
  const [historicalApplicationsFilters, setHistoricalApplicationsFilters] =
    useState<HistoricalApplicationFilters>({
      page: 1,
      size: 20,
      status: "",
      scholarship_type: "",
      academic_year: undefined,
      semester: "",
      search: "",
    });

  // 系統公告相關狀態
  const [announcements, setAnnouncements] = useState<NotificationResponse[]>(
    []
  );
  const [loadingAnnouncements, setLoadingAnnouncements] = useState(false);
  const [announcementsError, setAnnouncementsError] = useState<string | null>(
    null
  );
  const [showAnnouncementForm, setShowAnnouncementForm] = useState(false);
  const [editingAnnouncement, setEditingAnnouncement] =
    useState<NotificationResponse | null>(null);
  const [announcementForm, setAnnouncementForm] = useState<AnnouncementCreate>({
    title: "",
    message: "",
    notification_type: "info",
    priority: "normal",
  });
  const [announcementPagination, setAnnouncementPagination] = useState({
    page: 1,
    size: 10,
    total: 0,
  });

  // 當前用戶的獎學金權限
  const [
    currentUserScholarshipPermissions,
    setCurrentUserScholarshipPermissions,
  ] = useState<ScholarshipPermission[]>([]);
  const [hasQuotaPermission, setHasQuotaPermission] = useState(false);

  // 使用者管理相關狀態
  const [users, setUsers] = useState<UserListResponse[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [userStats, setUserStats] = useState<UserStats>({
    total_users: 0,
    role_distribution: {},
    active_users: 0,
    inactive_users: 0,
    recent_registrations: 0,
  });
  const [showUserForm, setShowUserForm] = useState(false);
  const [editingUser, setEditingUser] = useState<UserListResponse | null>(null);
  const [userForm, setUserForm] = useState<UserCreate>({
    nycu_id: "",
    email: "",
    name: "",
    role: "student",
    user_type: "student",
    status: "在學",
    dept_code: "",
    dept_name: "",
    comment: "",
    raw_data: {
      chinese_name: "",
      english_name: "",
    },
    // 向後相容性欄位
    username: "",
    full_name: "",
    chinese_name: "",
    english_name: "",
    password: "",
    student_no: "",
  });
  const [userPagination, setUserPagination] = useState({
    page: 1,
    size: 10,
    total: 0,
  });
  const [userSearch, setUserSearch] = useState("");
  const [userRoleFilter, setUserRoleFilter] = useState("");
  const [userFormLoading, setUserFormLoading] = useState(false);

  // 獎學金權限管理狀態
  const [scholarshipPermissions, setScholarshipPermissions] = useState<
    ScholarshipPermission[]
  >([]);
  const [loadingPermissions, setLoadingPermissions] = useState(false);
  const [permissionsError, setPermissionsError] = useState<string | null>(null);
  const [availableScholarships, setAvailableScholarships] = useState<
    Array<{ id: number; name: string; name_en?: string; code: string }>
  >([]);
  const [loadingScholarships, setLoadingScholarships] = useState(false);

  // 使用 useCallback 來確保 onPermissionChange 捕獲最新的狀態
  const handlePermissionChange = useCallback(
    (permissions: any[]) => {
      // 更新該用戶的獎學金權限
      const userId = editingUser?.id;
      if (userId) {
        // 移除該用戶的舊權限
        const otherUserPermissions = scholarshipPermissions.filter(
          p => p.user_id !== Number(userId)
        );

        // 處理新權限，保留現有權限的 ID
        const newPermissions = permissions.map(permission => {
          const scholarship = availableScholarships.find(
            s => s.id === permission.scholarship_id
          );

          // 檢查是否已存在此權限（通過 scholarship_id 匹配）
          const existingPermission = scholarshipPermissions.find(
            p =>
              p.user_id === Number(userId) &&
              p.scholarship_id === permission.scholarship_id
          );

          return {
            ...permission,
            // 如果已存在，保留原 ID；否則使用新 ID
            id: existingPermission ? existingPermission.id : permission.id,
            user_id: Number(userId), // 確保 user_id 正確
            scholarship_name: scholarship?.name || "未知獎學金",
            scholarship_name_en: scholarship?.name_en,
          };
        });

        const updatedPermissions = [...otherUserPermissions, ...newPermissions];
        setScholarshipPermissions(updatedPermissions);
      }
    },
    [editingUser, scholarshipPermissions, availableScholarships]
  );

  const subjectRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

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
          setEmailTemplate(response.data);
        } else {
          // Initialize with empty template if none exists
          setEmailTemplate({
            key: emailTab,
            subject_template: "",
            body_template: "",
            cc: null,
            bcc: null,
            updated_at: null,
          });
        }
      } catch (error) {
        console.error("Failed to load email template:", error);
        // Initialize with empty template on error
        setEmailTemplate({
          key: emailTab,
          subject_template: "",
          body_template: "",
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

  // Scholarship Email Template functions
  const loadScholarshipEmailTemplates = async (scholarshipTypeId: number) => {
    setLoadingScholarshipTemplates(true);
    try {
      const response =
        await apiClient.admin.getScholarshipEmailTemplates(scholarshipTypeId);
      if (response.success && response.data) {
        setScholarshipEmailTemplates(response.data.items);
      }
    } catch (error: any) {
      console.error("Failed to load scholarship email templates:", error);
      // If it's a permission error, switch back to system mode
      if (
        error?.response?.status === 400 ||
        error?.message?.includes("permission")
      ) {
        setScholarshipEmailTab("system");
        alert("您沒有權限存取此獎學金的郵件模板");
      }
      setScholarshipEmailTemplates([]);
    } finally {
      setLoadingScholarshipTemplates(false);
    }
  };

  const loadScholarshipEmailTemplate = async (
    scholarshipTypeId: number,
    templateKey: string
  ) => {
    try {
      const response = await apiClient.admin.getScholarshipEmailTemplate(
        scholarshipTypeId,
        templateKey
      );
      if (response.success && response.data) {
        setCurrentScholarshipTemplate(response.data);
      }
    } catch (error) {
      console.error("Failed to load scholarship email template:", error);
      setCurrentScholarshipTemplate(null);
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
      label:
        labelMap[template.key] ||
        template.key.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase()),
    }));
  };

  // Email Management functions
  const loadEmailHistory = async () => {
    setLoadingEmailHistory(true);
    try {
      const params = {
        skip: emailHistoryPagination.skip,
        limit: emailHistoryPagination.limit,
        ...Object.fromEntries(
          Object.entries(emailHistoryFilters).filter(([_, v]) => v !== "")
        ),
      };

      const response = await apiClient.emailManagement.getEmailHistory(params);
      if (response.success && response.data) {
        const { items, total } = response.data;
        setEmailHistory(items);
        setEmailHistoryPagination(prev => ({
          ...prev,
          total,
        }));
      }
    } catch (error) {
      console.error("Failed to load email history:", error);
    } finally {
      setLoadingEmailHistory(false);
    }
  };

  const loadScheduledEmails = async () => {
    setLoadingScheduledEmails(true);
    try {
      const params = {
        skip: scheduledEmailsPagination.skip,
        limit: scheduledEmailsPagination.limit,
        ...Object.fromEntries(
          Object.entries(scheduledEmailsFilters).filter(([_, v]) => v !== "")
        ),
      };

      const response =
        await apiClient.emailManagement.getScheduledEmails(params);
      if (response.success && response.data) {
        const { items, total } = response.data;
        setScheduledEmails(items);
        setScheduledEmailsPagination(prev => ({
          ...prev,
          total,
        }));
      }
    } catch (error) {
      console.error("Failed to load scheduled emails:", error);
    } finally {
      setLoadingScheduledEmails(false);
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

  // Load email data when the email management tab changes
  useEffect(() => {
    if (emailManagementTab === "history") {
      loadEmailHistory();
    } else if (emailManagementTab === "scheduled") {
      loadScheduledEmails();
    }
  }, [
    emailManagementTab,
    emailHistoryPagination.skip,
    scheduledEmailsPagination.skip,
    emailHistoryFilters,
    scheduledEmailsFilters,
  ]);

  // 系統公告相關函數
  // 獲取歷史申請資料
  const fetchHistoricalApplications = useCallback(async () => {
    // 檢查用戶認證狀態
    if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
      setHistoricalApplicationsError("用戶未認證或不具有管理員權限");
      setLoadingHistoricalApplications(false);
      return;
    }

    setLoadingHistoricalApplications(true);
    setHistoricalApplicationsError(null);

    try {
      // 構建篩選條件，如果選中的是特定獎學金類型，則添加該篩選
      const filters = {
        ...historicalApplicationsFilters,
        scholarship_type:
          activeHistoricalTab === "all" ? "" : activeHistoricalTab,
      };

      const response = await apiClient.admin.getHistoricalApplications(filters);

      if (response.success && response.data) {
        const applications = response.data.items || [];
        setHistoricalApplications(applications);

        setHistoricalApplicationsPagination({
          page: response.data.page,
          size: response.data.size,
          total: response.data.total,
          pages: response.data.pages,
        });
        setHistoricalApplicationsError(null);
      } else {
        const errorMsg = response.message || "獲取歷史申請失敗";
        setHistoricalApplicationsError(errorMsg);
      }
    } catch (error: any) {
      console.error("獲取歷史申請資料失敗:", error);
      const errorMsg = error?.message || error?.response?.data?.message || "網路錯誤或伺服器未回應";
      setHistoricalApplicationsError(errorMsg);
    } finally {
      setLoadingHistoricalApplications(false);
    }
  }, [historicalApplicationsFilters, activeHistoricalTab, user]);

  const fetchAnnouncements = async () => {
    // 檢查用戶認證狀態
    if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
      setAnnouncementsError("用戶未認證或不具有管理員權限");
      setLoadingAnnouncements(false);
      return;
    }

    setLoadingAnnouncements(true);
    setAnnouncementsError(null);

    try {
      const response = await apiClient.admin.getAllAnnouncements(
        announcementPagination.page,
        announcementPagination.size
      );

      if (response.success && response.data) {
        setAnnouncements(response.data.items || []);
        setAnnouncementPagination(prev => ({
          ...prev,
          total: response.data?.total || 0,
        }));
        // 清除錯誤信息
        setAnnouncementsError(null);
      } else {
        const errorMsg = response.message || "獲取公告失敗";
        setAnnouncementsError(errorMsg);
      }
    } catch (error) {
      const errorMsg =
        error instanceof Error ? error.message : "網絡錯誤，請檢查連接";
      setAnnouncementsError(errorMsg);
    } finally {
      setLoadingAnnouncements(false);
    }
  };

  const handleAnnouncementFormChange = (
    field: keyof AnnouncementCreate,
    value: string
  ) => {
    setAnnouncementForm(prev => ({ ...prev, [field]: value }));
  };

  const handleCreateAnnouncement = async () => {
    if (!announcementForm.title || !announcementForm.message) return;

    try {
      const response =
        await apiClient.admin.createAnnouncement(announcementForm);

      if (response.success) {
        setShowAnnouncementForm(false);
        setAnnouncementForm({
          title: "",
          message: "",
          notification_type: "info",
          priority: "normal",
        });
        fetchAnnouncements();
      } else {
        alert("創建公告失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "創建公告失敗: " + (error instanceof Error ? error.message : "網絡錯誤")
      );
    }
  };

  const handleUpdateAnnouncement = async () => {
    if (
      !editingAnnouncement ||
      !announcementForm.title ||
      !announcementForm.message
    )
      return;

    try {
      const response = await apiClient.admin.updateAnnouncement(
        editingAnnouncement.id,
        announcementForm as AnnouncementUpdate
      );

      if (response.success) {
        setEditingAnnouncement(null);
        setShowAnnouncementForm(false);
        setAnnouncementForm({
          title: "",
          message: "",
          notification_type: "info",
          priority: "normal",
        });
        fetchAnnouncements();
      } else {
        alert("更新公告失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "更新公告失敗: " + (error instanceof Error ? error.message : "網絡錯誤")
      );
    }
  };

  const handleDeleteAnnouncement = async (id: number) => {
    if (!confirm("確定要刪除此公告嗎？")) return;

    try {
      const response = await apiClient.admin.deleteAnnouncement(id);

      if (response.success) {
        fetchAnnouncements();
      } else {
        alert("刪除公告失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "刪除公告失敗: " + (error instanceof Error ? error.message : "網絡錯誤")
      );
    }
  };

  const handleEditAnnouncement = (announcement: NotificationResponse) => {
    setEditingAnnouncement(announcement);
    setAnnouncementForm({
      title: announcement.title,
      title_en: announcement.title_en,
      message: announcement.message,
      message_en: announcement.message_en,
      notification_type: announcement.notification_type as any,
      priority: announcement.priority as any,
      action_url: announcement.action_url,
      expires_at: announcement.expires_at,
      metadata: announcement.metadata,
    });
    setShowAnnouncementForm(true);
  };

  const resetAnnouncementForm = () => {
    setShowAnnouncementForm(false);
    setEditingAnnouncement(null);
    setAnnouncementForm({
      title: "",
      message: "",
      notification_type: "info",
      priority: "normal",
    });
  };

  // 載入當前用戶的獎學金權限
  useEffect(() => {
    const fetchCurrentUserPermissions = async () => {
      // Super admin has all permissions - no need to check database
      if (user.role === "super_admin") {
        setHasQuotaPermission(true);
        setCurrentUserScholarshipPermissions([]); // Not needed for super admin
        return;
      }

      // For regular admin, check if they have any scholarship permissions
      if (user.role === "admin") {
        try {
          const response =
            await apiClient.admin.getCurrentUserScholarshipPermissions();
          if (response.success && response.data) {
            setCurrentUserScholarshipPermissions(response.data);
            // Check if user has any scholarship permissions (needed for quota management)
            setHasQuotaPermission(response.data.length > 0);
          } else {
            setHasQuotaPermission(false);
          }
        } catch (error) {
          console.error("Failed to fetch user scholarship permissions:", error);
          setHasQuotaPermission(false);
        }
      } else {
        // College and professor users don't have quota management access
        setHasQuotaPermission(false);
      }
    };

    if (user) {
      fetchCurrentUserPermissions();
    }
  }, [user]);

  // 載入獎學金相關模板當切換獎學金時
  useEffect(() => {
    const loadScholarshipData = async () => {
      if (scholarshipEmailTab !== "system" && scholarshipEmailTab) {
        const scholarshipTypeId = parseInt(scholarshipEmailTab);
        await loadScholarshipEmailTemplates(scholarshipTypeId);
      } else {
        // Reset to system mode
        setScholarshipEmailTemplates([]);
      }

      // Reset email tab to first available template
      const availableTemplates = getFilteredEmailTemplates();
      if (
        availableTemplates.length > 0 &&
        availableTemplates[0].key !== emailTab
      ) {
        setEmailTab(availableTemplates[0].key);
      }
    };

    loadScholarshipData();
  }, [scholarshipEmailTab]);

  // 獲取所有歷史申請以建立 tab 列表
  const fetchAllHistoricalApplicationsForTabs = useCallback(async () => {
    if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
      return;
    }

    try {
      // 分頁獲取所有申請來建立 tab 列表，遵守 API 的 size <= 100 限制
      let allApplications: HistoricalApplication[] = [];
      let currentPage = 1;
      let hasMore = true;

      while (hasMore) {
        const response = await apiClient.admin.getHistoricalApplications({
          page: currentPage,
          size: 100, // 使用 API 允許的最大值
          status: "",
          scholarship_type: "",
          academic_year: undefined,
          semester: "",
          search: "",
        });

        if (response.success && response.data) {
          const pageApplications = response.data.items || [];
          allApplications = [...allApplications, ...pageApplications];

          // 檢查是否還有更多數據
          hasMore =
            pageApplications.length === 100 &&
            currentPage < response.data.pages;
          currentPage++;
        } else {
          hasMore = false;
        }
      }

      // 按獎學金類型分組以建立 tab
      const groups: Record<string, HistoricalApplication[]> = {};
      allApplications.forEach(app => {
        const scholarshipType =
          app.scholarship_name || app.scholarship_type_code || "未知類型";
        if (!groups[scholarshipType]) {
          groups[scholarshipType] = [];
        }
        groups[scholarshipType].push(app);
      });
      setHistoricalApplicationsGroups(groups);

      // 設置第一個 tab 為默認
      const tabKeys = Object.keys(groups);
      if (tabKeys.length > 0 && activeHistoricalTab === "all") {
        setActiveHistoricalTab("all"); // 保持全部為默認
      }
    } catch (error) {
      console.error("獲取歷史申請 tab 資料失敗:", error);
    }
  }, [user, activeHistoricalTab]);

  // 歷史申請資料載入
  useEffect(() => {
    // 只在用戶已認證且具有管理員權限時載入歷史申請
    if (user && (user.role === "admin" || user.role === "super_admin")) {
      fetchHistoricalApplications();
    }
  }, [fetchHistoricalApplications, user]);

  // 初始載入時獲取所有歷史申請以建立 tab
  useEffect(() => {
    if (user && (user.role === "admin" || user.role === "super_admin")) {
      fetchAllHistoricalApplicationsForTabs();
    }
  }, [fetchAllHistoricalApplicationsForTabs, user]);

  // 載入系統公告
  useEffect(() => {
    // 檢查用戶是否已認證且具有管理員權限
    if (user && (user.role === "admin" || user.role === "super_admin")) {
      fetchAnnouncements();
    }
  }, [announcementPagination.page, announcementPagination.size, user]);

  // 載入用戶有權限的獎學金列表
  useEffect(() => {
    const fetchMyScholarships = async () => {
      if (user && (user.role === "admin" || user.role === "super_admin")) {
        try {
          const response = await apiClient.admin.getMyScholarships();
          if (response.success && response.data) {
            setMyScholarships(response.data);

            // If user has scholarships and current tab is not valid, reset to first scholarship or system
            if (response.data.length > 0 && scholarshipEmailTab !== "system") {
              const currentScholarshipId = parseInt(scholarshipEmailTab);
              const hasPermission = response.data.some(
                s => s.id === currentScholarshipId
              );
              if (!hasPermission) {
                setScholarshipEmailTab("system"); // Reset to system if no permission for current scholarship
              }
            }
          }
        } catch (error) {
          console.error("Failed to fetch user scholarships:", error);
          setMyScholarships([]);
          setScholarshipEmailTab("system"); // Reset to system on error
        }
      }
    };

    fetchMyScholarships();
  }, [user]);

  // Load email templates when sending type tab changes
  useEffect(() => {
    loadEmailTemplatesBySendingType(emailTemplateTab);
  }, [emailTemplateTab]);

  // 使用者管理相關函數
  const fetchUsers = async () => {
    setLoadingUsers(true);
    setUsersError(null);

    try {
      // 根據當前使用者角色決定請求哪些角色
      let rolesParam = "college,admin,super_admin,professor";
      if (user.role === "admin") {
        rolesParam = "college,admin,professor"; // admin 使用者不能看到 super_admin
      }
      // 轉換為大寫傳送給後端
      rolesParam = rolesParam
        .split(",")
        .map(role => role.trim().toUpperCase())
        .join(",");
      const params: any = {
        page: userPagination.page,
        size: userPagination.size,
        roles: rolesParam,
      };

      if (userSearch) params.search = userSearch;
      if (userRoleFilter) params.role = userRoleFilter;

      const response = await apiClient.users.getAll(params);

      if (response.success && response.data) {
        // 後端已經根據roles參數過濾了正確的角色，不需要前端再過濾
        const managementUsers = response.data.items || [];

        // 對使用者列表進行角色排序
        const sortedUsers = managementUsers.sort((a, b) => {
          const roleOrder = {
            super_admin: 1,
            admin: 2,
            college: 3,
            professor: 4,
          };

          const aOrder = roleOrder[a.role as keyof typeof roleOrder] || 999;
          const bOrder = roleOrder[b.role as keyof typeof roleOrder] || 999;

          return aOrder - bOrder;
        });

        setUsers(sortedUsers);
        setUserPagination(prev => ({
          ...prev,
          total: sortedUsers.length, // 使用過濾後的數量
        }));
      } else {
        const errorMsg = response.message || "獲取使用者失敗";
        setUsersError(errorMsg);
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : "網絡錯誤";
      setUsersError(errorMsg);
    } finally {
      setLoadingUsers(false);
    }
  };

  const fetchUserStats = async () => {
    try {
      const response = await apiClient.users.getStats();
      if (response.success && response.data) {
        setUserStats(response.data);
      }
    } catch (error) {
      console.error("獲取使用者統計失敗:", error);
    }
  };

  const handleUserFormChange = (field: keyof UserCreate, value: any) => {
    setUserForm(prev => ({ ...prev, [field]: value }));

    // 當角色改變時，處理獎學金權限
    if (field === "role") {
      // 如果角色不是 college 或 admin，清除該用戶的所有獎學金權限
      if (!["college", "admin"].includes(value)) {
        if (editingUser) {
          // 編輯現有用戶時，清除該用戶的權限
          setScholarshipPermissions(prev =>
            prev.filter(p => p.user_id !== Number(editingUser.id))
          );
        } else {
          // 創建新用戶時，清除臨時權限
          setScholarshipPermissions(prev => prev.filter(p => p.user_id !== -1));
        }
      }
    }
  };

  const handleCreateUser = async () => {
    if (!userForm.nycu_id || !userForm.role) return;

    setUserFormLoading(true);

    try {
      // First create the user
      const response = await apiClient.users.create(userForm);

      if (response.success) {
        // If user creation successful and we have scholarship permissions to save
        const newUserId = response.data?.id;
        if (
          newUserId &&
          ["college", "admin", "super_admin"].includes(userForm.role)
        ) {
          // Get temporary permissions (user_id = -1) for the new user
          const tempPermissions = scholarshipPermissions.filter(
            p => p.user_id === -1
          );
          if (tempPermissions.length > 0) {
            // Save scholarship permissions for the new user
            for (const permission of tempPermissions) {
              try {
                await apiClient.admin.createScholarshipPermission({
                  user_id: newUserId,
                  scholarship_id: permission.scholarship_id,
                  comment: permission.comment || "",
                });
              } catch (permError) {
                console.error(
                  "Failed to create scholarship permission:",
                  permError
                );
              }
            }
          }
        }

        // Clean up temporary permissions
        setScholarshipPermissions(prev => prev.filter(p => p.user_id !== -1));

        setShowUserForm(false);
        resetUserForm();
        await fetchUsers();
        await fetchUserStats();
        await fetchScholarshipPermissions(); // 重新載入權限列表
      } else {
        alert("建立使用者權限失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "建立使用者權限失敗: " +
          (error instanceof Error ? error.message : "網絡錯誤")
      );
    } finally {
      setUserFormLoading(false);
    }
  };

  const handleUpdateUser = async () => {
    if (!editingUser || !userForm.role) return;

    setUserFormLoading(true);

    try {
      // First update the user
      const response = await apiClient.users.update(editingUser.id, userForm);

      if (response.success) {
        // Handle scholarship permissions for college/admin/super_admin roles
        if (["college", "admin", "super_admin"].includes(userForm.role)) {
          // Get the permissions that should be saved (from the UI state - only those that are actually selected)
          // Note: scholarshipPermissions state is updated by onPermissionChange when user changes selection
          const permissionsToSave = scholarshipPermissions.filter(
            p => p.user_id === Number(editingUser.id)
          );

          // Force refresh permissions from backend to get the latest state
          const refreshResponse =
            await apiClient.admin.getScholarshipPermissions();
          if (refreshResponse.success && refreshResponse.data) {
            const freshPermissions = refreshResponse.data;
            const freshUserPermissions = freshPermissions.filter(
              p => p.user_id === Number(editingUser.id)
            );

            // Use fresh permissions for comparison
            const permissionsToRemove = freshUserPermissions.filter(
              currentPerm =>
                !permissionsToSave.some(
                  savePerm =>
                    savePerm.scholarship_id === currentPerm.scholarship_id
                )
            );

            // Step 1: Delete permissions that are no longer selected
            for (const currentPerm of permissionsToRemove) {
              try {
                await apiClient.admin.deleteScholarshipPermission(
                  currentPerm.id
                );
              } catch (permError) {
                console.error(
                  "Failed to delete scholarship permission:",
                  permError
                );
                alert(
                  `權限刪除失敗: ${permError instanceof Error ? permError.message : "未知錯誤"}`
                );
              }
            }

            // Step 2: Create new permissions for newly selected scholarships
            const permissionsToCreate = permissionsToSave.filter(
              savePerm =>
                !freshUserPermissions.some(
                  currentPerm =>
                    currentPerm.scholarship_id === savePerm.scholarship_id
                )
            );

            for (const permission of permissionsToCreate) {
              try {
                await apiClient.admin.createScholarshipPermission({
                  user_id: Number(editingUser.id),
                  scholarship_id: permission.scholarship_id,
                  comment: permission.comment || "",
                });
              } catch (permError) {
                console.error(
                  "Failed to create scholarship permission:",
                  permError
                );
                alert(
                  `權限創建失敗: ${permError instanceof Error ? permError.message : "未知錯誤"}`
                );
              }
            }
          }
        } else {
          // For non-college/admin roles, remove all scholarship permissions
          const currentUserPermissions = scholarshipPermissions.filter(
            p => p.user_id === Number(editingUser.id) && p.id > 0
          );
          for (const permission of currentUserPermissions) {
            try {
              await apiClient.admin.deleteScholarshipPermission(permission.id);
            } catch (permError) {
              console.error(
                "Failed to delete scholarship permission:",
                permError
              );
            }
          }
        }

        setEditingUser(null);
        setShowUserForm(false);
        resetUserForm();
        await fetchUsers();
        await fetchScholarshipPermissions(); // 重新載入權限列表
      } else {
        alert("更新使用者權限失敗: " + (response.message || "未知錯誤"));
      }
    } catch (error) {
      alert(
        "更新使用者權限失敗: " +
          (error instanceof Error ? error.message : "網絡錯誤")
      );
    } finally {
      setUserFormLoading(false);
    }
  };

  const handleEditUser = (user: UserListResponse) => {
    setEditingUser(user);
    setUserForm({
      nycu_id: user.nycu_id,
      email: user.email,
      name: user.name,
      role: user.role as any,
      user_type: user.user_type as any,
      status: user.status as any,
      dept_code: user.dept_code || "",
      dept_name: user.dept_name || "",
      comment: user.comment || "",
      raw_data: {
        chinese_name: user.raw_data?.chinese_name || "",
        english_name: user.raw_data?.english_name || "",
      },
      // 向後相容性欄位
      username: user.username || "",
      full_name: user.full_name || "",
      chinese_name: user.chinese_name || "",
      english_name: user.english_name || "",
      password: "", // 編輯時不需要密碼
      student_no: user.student_no || "",
    });

    // 載入該用戶的現有獎學金權限
    const userPermissions = scholarshipPermissions.filter(
      p => p.user_id === Number(user.id)
    );

    setShowUserForm(true);
  };

  const resetUserForm = () => {
    setShowUserForm(false);
    setEditingUser(null);
    // Clean up temporary permissions
    setScholarshipPermissions(prev => prev.filter(p => p.user_id !== -1));
    setUserForm({
      nycu_id: "",
      email: "",
      name: "",
      role: "college",
      user_type: "student",
      status: "在學",
      dept_code: "",
      dept_name: "",
      comment: "",
      raw_data: {
        chinese_name: "",
        english_name: "",
      },
      // 向後相容性欄位
      username: "",
      full_name: "",
      chinese_name: "",
      english_name: "",
      password: "",
      student_no: "",
    });
  };

  const getRoleLabel = (role: string) => {
    const roleMap: Record<string, string> = {
      student: "學生",
      professor: "教授",
      college: "學院",
      admin: "管理員",
      super_admin: "超級管理員",
    };
    return roleMap[role] || role;
  };

  // 處理搜尋和篩選 - 重置到第一頁
  const handleSearch = () => {
    setUserPagination(prev => ({ ...prev, page: 1 }));
    // fetchUsers() 會由 useEffect 自動觸發
  };

  // 清除篩選條件
  const clearFilters = () => {
    setUserSearch("");
    setUserRoleFilter("");
    setUserPagination(prev => ({ ...prev, page: 1 }));
  };

  const handleUserSubmit = () => {
    if (editingUser) {
      handleUpdateUser();
    } else {
      handleCreateUser();
    }
  };

  // 載入使用者數據
  useEffect(() => {
    fetchUsers();
  }, [userPagination.page, userPagination.size, userSearch, userRoleFilter]);

  // 載入使用者統計（只在初次載入時執行）
  useEffect(() => {
    fetchUserStats();
  }, []);

  // 載入系統管理數據（只在初次載入時執行）
  useEffect(() => {
    fetchWorkflows();
    fetchScholarshipRules();
    fetchSystemStats();
    fetchScholarshipPermissions();
    fetchAvailableScholarships();
    fetchScholarshipConfigurations();
  }, []);

  // 獲取獎學金配置列表
  const fetchScholarshipConfigurations = async () => {
    setLoadingConfigurations(true);

    try {
      const response = await apiClient.admin.getScholarshipConfigurations();
      if (response.success && response.data) {
        setScholarshipConfigurations(response.data);
        // 預設選擇第一個配置
        if (response.data.length > 0 && !selectedConfigurationId) {
          setSelectedConfigurationId(response.data[0].id);
        }
      }
    } catch (error) {
      console.error("Failed to load scholarship configurations:", error);
    } finally {
      setLoadingConfigurations(false);
    }
  };

  // 獲取工作流程列表 (保留原有功能)
  const fetchWorkflows = async () => {
    setLoadingWorkflows(true);
    setWorkflowsError(null);

    try {
      const response = await apiClient.admin.getWorkflows();
      if (response.success && response.data) {
        setWorkflows(response.data);
      } else {
        setWorkflowsError(response.message || "獲取工作流程失敗");
      }
    } catch (error) {
      setWorkflowsError(error instanceof Error ? error.message : "網絡錯誤");
    } finally {
      setLoadingWorkflows(false);
    }
  };

  // 獲取獎學金規則列表
  const fetchScholarshipRules = async () => {
    setLoadingRules(true);
    setRulesError(null);

    try {
      const response = await apiClient.admin.getScholarshipRules();
      if (response.success && response.data) {
        setScholarshipRules(response.data);
      } else {
        setRulesError(response.message || "獲取獎學金規則失敗");
      }
    } catch (error) {
      setRulesError(error instanceof Error ? error.message : "網絡錯誤");
    } finally {
      setLoadingRules(false);
    }
  };

  // 處理查看規則詳情
  const handleViewRuleDetails = (rule: ScholarshipRule) => {
    setSelectedRule(rule);
    setShowRuleDetails(true);
  };

  // 處理新增規則
  const handleCreateRule = () => {
    setEditingRule(null);
    setShowRuleForm(true);
  };

  // 處理編輯規則
  const handleEditRule = (rule: ScholarshipRule) => {
    setEditingRule(rule);
    setShowRuleForm(true);
  };

  // 處理規則表單提交
  const handleRuleSubmit = async (ruleData: Partial<ScholarshipRule>) => {
    setRuleFormLoading(true);
    try {
      if (editingRule) {
        if (editingRule.id == null) {
          throw new Error("規則缺少 ID，無法更新");
        }
        // 更新規則
        const response = await apiClient.admin.updateScholarshipRule(
          editingRule.id,
          ruleData
        );
        if (response.success) {
          await fetchScholarshipRules(); // 重新載入規則列表
          setShowRuleForm(false);
          setEditingRule(null);
        } else {
          throw new Error(response.message || "更新規則失敗");
        }
      } else {
        // 建立新規則
        const response = await apiClient.admin.createScholarshipRule(ruleData);
        if (response.success) {
          await fetchScholarshipRules(); // 重新載入規則列表
          setShowRuleForm(false);
        } else {
          throw new Error(response.message || "建立規則失敗");
        }
      }
    } catch (error) {
      console.error("規則操作失敗:", error);
      alert(`操作失敗: ${error instanceof Error ? error.message : "未知錯誤"}`);
    } finally {
      setRuleFormLoading(false);
    }
  };

  // 處理刪除規則
  const handleDeleteRule = async (rule: ScholarshipRule) => {
    if (rule.id == null) {
      alert("規則缺少 ID，無法刪除");
      return;
    }

    if (!confirm(`確定要刪除規則「${rule.rule_name}」嗎？此操作無法復原。`)) {
      return;
    }

    try {
      const response = await apiClient.admin.deleteScholarshipRule(rule.id);
      if (response.success) {
        await fetchScholarshipRules(); // 重新載入規則列表
      } else {
        throw new Error(response.message || "刪除規則失敗");
      }
    } catch (error) {
      console.error("刪除規則失敗:", error);
      alert(`刪除失敗: ${error instanceof Error ? error.message : "未知錯誤"}`);
    }
  };

  // 處理複製規則
  const handleCopyRule = async (rule: ScholarshipRule) => {
    const copyData = {
      ...rule,
      rule_name: `${rule.rule_name} (複製)`,
      id: undefined,
      created_at: undefined,
      updated_at: undefined,
      created_by: undefined,
      updated_by: undefined,
    };
    setEditingRule(copyData as ScholarshipRule);
    setShowRuleForm(true);
  };

  // 處理切換初領狀態
  const handleToggleInitialEnabled = async (
    rule: ScholarshipRule,
    enabled: boolean
  ) => {
    try {
      if (rule.id == null) {
        throw new Error("規則缺少 ID，無法更新");
      }
      const response = await apiClient.admin.updateScholarshipRule(rule.id, {
        is_initial_enabled: enabled,
      });
      if (response.success) {
        await fetchScholarshipRules();
      }
    } catch (error) {
      console.error("更新初領狀態失敗:", error);
    }
  };

  // 處理切換續領狀態
  const handleToggleRenewalEnabled = async (
    rule: ScholarshipRule,
    enabled: boolean
  ) => {
    try {
      if (rule.id == null) {
        throw new Error("規則缺少 ID，無法更新");
      }
      const response = await apiClient.admin.updateScholarshipRule(rule.id, {
        is_renewal_enabled: enabled,
      });
      if (response.success) {
        await fetchScholarshipRules();
      }
    } catch (error) {
      console.error("更新續領狀態失敗:", error);
    }
  };

  // 處理切換整體狀態
  const handleToggleActive = async (rule: ScholarshipRule, active: boolean) => {
    try {
      if (rule.id == null) {
        throw new Error("規則缺少 ID，無法更新");
      }
      const response = await apiClient.admin.updateScholarshipRule(rule.id, {
        is_active: active,
      });
      if (response.success) {
        await fetchScholarshipRules();
      }
    } catch (error) {
      console.error("更新規則狀態失敗:", error);
    }
  };

  // 獲取獎學金類型列表
  const fetchScholarshipTypes = async () => {
    console.log(
      "🔍 Fetching scholarship types for user:",
      user?.role,
      user?.nycu_id
    );
    setLoadingScholarshipTypes(true);
    try {
      // Use the new API that returns only scholarships the user has permission to manage
      const response = await apiClient.admin.getMyScholarships();
      console.log("📊 Scholarship types response:", response);

      if (response.success && response.data) {
        console.log(
          "✅ Found scholarship types:",
          response.data.length,
          "types"
        );
        setScholarshipTypes(response.data);
      } else {
        console.log("❌ Failed to get scholarship types:", response.message);
        setScholarshipTypes([]);
      }
    } catch (error) {
      console.error("❌ Failed to fetch scholarship types:", error);
      // Fallback to empty array so UI doesn't break
      setScholarshipTypes([]);
    } finally {
      setLoadingScholarshipTypes(false);
    }
  };

  // Update scholarship type when child component modifies it
  const handleScholarshipTypeUpdate = (id: number, updates: Partial<any>) => {
    setScholarshipTypes(prev =>
      prev.map(type => (type.id === id ? { ...type, ...updates } : type))
    );
  };

  // 根據獎學金 tab 和篩選條件過濾規則
  const getFilteredRules = () => {
    let filtered = [...scholarshipRules];

    // 根據選擇的獎學金 tab 過濾
    if (selectedScholarshipTab !== "templates") {
      const scholarshipId = parseInt(
        selectedScholarshipTab.replace("scholarship-", "")
      );
      filtered = filtered.filter(
        rule => rule.scholarship_type_id === scholarshipId
      );
    } else {
      // 只顯示模板
      filtered = filtered.filter(rule => rule.is_template === true);
    }

    // 根據學年度和學期過濾
    filtered = filtered.filter(rule => {
      if (rule.academic_year && rule.academic_year !== selectedAcademicYear) {
        return false;
      }
      // 確保學期值正確對應
      if (rule.semester) {
        const ruleSemester = rule.semester;
        if (ruleSemester !== selectedSemester) {
          return false;
        }
      }
      return true;
    });

    // 根據初領/續領過濾
    if (ruleTypeFilter !== "all") {
      filtered = filtered.filter(rule => {
        if (ruleTypeFilter === "initial") {
          return rule.is_initial_enabled;
        } else if (ruleTypeFilter === "renewal") {
          return rule.is_renewal_enabled;
        }
        return true;
      });
    }

    // 按優先級排序 (數字越小優先級越高，1 在最上面)
    return filtered.sort((a, b) => a.priority - b.priority);
  };

  // 組件載入時獲取資料
  useEffect(() => {
    fetchScholarshipTypes();
    fetchScholarshipRules();
  }, []);

  // 獲取系統統計
  const fetchSystemStats = async () => {
    setLoadingStats(true);
    setStatsError(null);

    try {
      const response = await apiClient.admin.getSystemStats();
      if (response.success && response.data) {
        setSystemStats(response.data);
      } else {
        setStatsError(response.message || "獲取系統統計失敗");
      }
    } catch (error) {
      setStatsError(error instanceof Error ? error.message : "網絡錯誤");
    } finally {
      setLoadingStats(false);
    }
  };

  // 獲取獎學金權限列表
  const fetchScholarshipPermissions = async () => {
    setLoadingPermissions(true);
    setPermissionsError(null);

    try {
      const response = await apiClient.admin.getScholarshipPermissions();

      if (response.success && response.data) {
        setScholarshipPermissions(response.data);
      } else {
        setPermissionsError(response.message || "獲取獎學金權限失敗");
      }
    } catch (error) {
      console.error("Error fetching permissions:", error);
      if (error instanceof Error) {
        setPermissionsError(error.message);
      } else {
        setPermissionsError("網絡錯誤");
      }
    } finally {
      setLoadingPermissions(false);
    }
  };

  // 獲取可用獎學金列表
  const fetchAvailableScholarships = async () => {
    setLoadingScholarships(true);

    try {
      const response = await apiClient.admin.getAllScholarshipsForPermissions();
      if (response.success && response.data) {
        setAvailableScholarships(response.data);
      }
    } catch (error) {
      console.error("獲取獎學金列表失敗:", error);
    } finally {
      setLoadingScholarships(false);
    }
  };

  // 檢查用戶認證和權限
  if (!user) {
    return (
      <div className="space-y-6">
        <div className="text-center py-12">
          <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
          <h2 className="text-2xl font-bold text-red-600 mb-2">需要登入</h2>
          <p className="text-gray-600 mb-6">您需要登入才能訪問系統管理功能</p>
          <Button
            onClick={() => (window.location.href = "/dev-login")}
            className="nycu-gradient text-white"
          >
            前往登入
          </Button>
        </div>
      </div>
    );
  }

  if (user.role !== "admin" && user.role !== "super_admin") {
    return (
      <div className="space-y-6">
        <div className="text-center py-12">
          <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
          <h2 className="text-2xl font-bold text-red-600 mb-2">權限不足</h2>
          <p className="text-gray-600 mb-6">您沒有權限訪問系統管理功能</p>
          <p className="text-sm text-gray-500">
            當前角色: {getRoleLabel(user.role)}
          </p>
        </div>
      </div>
    );
  }

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

      <Tabs defaultValue="dashboard" className="space-y-4">
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
          {loadingStats ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                <span className="text-nycu-navy-600">載入系統統計中...</span>
              </div>
            </div>
          ) : statsError ? (
            <div className="text-center py-12">
              <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
              <p className="text-lg font-medium text-red-600 mb-2">
                載入系統統計失敗
              </p>
              <p className="text-sm text-gray-600 mb-4">{statsError}</p>
              <Button
                onClick={fetchSystemStats}
                variant="outline"
                className="border-red-300 text-red-600 hover:bg-red-50"
              >
                重試
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    總使用者數
                  </CardTitle>
                  <Users className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.totalUsers}
                  </div>
                  <p className="text-xs text-muted-foreground">系統註冊用戶</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    進行中申請
                  </CardTitle>
                  <FileText className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.activeApplications}
                  </div>
                  <p className="text-xs text-muted-foreground">待處理案件</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    待審核申請
                  </CardTitle>
                  <Clock className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.pendingReviews}
                  </div>
                  <p className="text-xs text-muted-foreground">等待審核</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    系統正常運行時間
                  </CardTitle>
                  <Settings className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.systemUptime}
                  </div>
                  <p className="text-xs text-muted-foreground">本月平均</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    平均回應時間
                  </CardTitle>
                  <Database className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.avgResponseTime}
                  </div>
                  <p className="text-xs text-muted-foreground">API 回應時間</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    儲存空間使用
                  </CardTitle>
                  <Database className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.storageUsed}
                  </div>
                  <p className="text-xs text-muted-foreground">總容量 10TB</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    完成審核
                  </CardTitle>
                  <FileText className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.completedReviews}
                  </div>
                  <p className="text-xs text-muted-foreground">本月完成</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="text-sm font-medium">
                    獎學金種類
                  </CardTitle>
                  <FileText className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">
                    {systemStats.totalScholarships}
                  </div>
                  <p className="text-xs text-muted-foreground">可用獎學金</p>
                </CardContent>
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="workflows" className="space-y-4">
          {loadingConfigurations ? (
            <div className="flex items-center justify-center py-8">
              <div className="flex items-center gap-3">
                <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                <span className="text-nycu-navy-600">載入獎學金配置中...</span>
              </div>
            </div>
          ) : (
            <ScholarshipWorkflowMermaid
              configurations={scholarshipConfigurations}
              selectedConfigId={selectedConfigurationId}
              onConfigChange={setSelectedConfigurationId}
            />
          )}
        </TabsContent>

        <TabsContent value="rules" className="space-y-4">
          {loadingScholarshipTypes ? (
            <Card>
              <CardContent className="flex items-center justify-center py-8">
                <div className="flex items-center gap-3">
                  <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                  <span className="text-nycu-navy-600">
                    載入獎學金類型中...
                  </span>
                </div>
              </CardContent>
            </Card>
          ) : scholarshipTypes.length === 0 ? (
            <Card>
              <CardContent className="text-center py-12">
                <AlertCircle className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium text-gray-600 mb-2">
                  沒有可管理的獎學金
                </p>
                <p className="text-sm text-gray-500">
                  請聯繫系統管理員分配獎學金管理權限
                </p>
              </CardContent>
            </Card>
          ) : (
            <AdminRuleManagement scholarshipTypes={scholarshipTypes} />
          )}
        </TabsContent>

        <TabsContent value="configurations" className="space-y-4">
          {loadingScholarshipTypes ? (
            <Card>
              <CardContent className="flex items-center justify-center py-8">
                <div className="flex items-center gap-3">
                  <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                  <span className="text-nycu-navy-600">
                    載入獎學金類型中...
                  </span>
                </div>
              </CardContent>
            </Card>
          ) : scholarshipTypes.length === 0 ? (
            <Card>
              <CardContent className="text-center py-12">
                <AlertCircle className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium text-gray-600 mb-2">
                  沒有可管理的獎學金
                </p>
                <p className="text-sm text-gray-500">
                  請聯繫系統管理員分配獎學金管理權限
                </p>
              </CardContent>
            </Card>
          ) : (
            <AdminConfigurationManagement
              scholarshipTypes={scholarshipTypes}
              onScholarshipTypeUpdate={handleScholarshipTypeUpdate}
            />
          )}
        </TabsContent>

        <TabsContent value="users" className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">使用者權限管理</h3>
            <div className="flex gap-2">
              <Button
                onClick={() => setShowUserForm(true)}
                className="nycu-gradient text-white"
              >
                <Plus className="h-4 w-4 mr-1" />
                新增使用者權限
              </Button>
              <Button variant="outline">
                <Upload className="h-4 w-4 mr-1" />
                批次匯入
              </Button>
            </div>
          </div>

          {/* 使用者統計卡片 */}
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  總使用者數
                </CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {userStats.total_users || 0}
                </div>
                <p className="text-xs text-muted-foreground">系統註冊用戶</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">
                  活躍使用者
                </CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {userStats.active_users || 0}
                </div>
                <p className="text-xs text-muted-foreground">最近30天登入</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">學生用戶</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {userStats.role_distribution?.student || 0}
                </div>
                <p className="text-xs text-muted-foreground">學生角色</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">本月新增</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {userStats.recent_registrations || 0}
                </div>
                <p className="text-xs text-muted-foreground">最近30天</p>
              </CardContent>
            </Card>
          </div>

          {/* 搜尋和篩選 */}
          <Card className="border-nycu-blue-200">
            <CardContent className="pt-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <Label>搜尋使用者</Label>
                  <Input
                    placeholder="姓名、信箱或 NYCU ID"
                    value={userSearch}
                    onChange={e => setUserSearch(e.target.value)}
                    className="border-nycu-blue-200"
                  />
                </div>
                <div>
                  <Label>角色篩選</Label>
                  <select
                    value={userRoleFilter}
                    onChange={e => setUserRoleFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
                  >
                    <option value="">全部管理角色</option>
                    <option value="super_admin">超級管理員</option>
                    <option value="admin">管理員</option>
                    <option value="college">學院</option>
                    <option value="professor">教授</option>
                  </select>
                </div>
                <div className="flex items-end gap-2">
                  <Button
                    onClick={handleSearch}
                    className="flex-1 nycu-gradient text-white"
                  >
                    搜尋
                  </Button>
                  <Button
                    onClick={clearFilters}
                    variant="outline"
                    className="border-nycu-blue-300 text-nycu-blue-600 hover:bg-nycu-blue-50"
                  >
                    清除
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 使用者列表 */}
          <Card className="border-nycu-blue-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                使用者權限列表
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {loadingUsers ? (
                <div className="flex items-center justify-center py-8">
                  <div className="flex items-center gap-3">
                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                    <span className="text-nycu-navy-600">載入使用者中...</span>
                  </div>
                </div>
              ) : usersError ? (
                <div className="text-center py-12">
                  <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
                  <p className="text-lg font-medium text-red-600 mb-2">
                    載入使用者失敗
                  </p>
                  <p className="text-sm text-gray-600 mb-4">{usersError}</p>
                  <Button
                    onClick={fetchUsers}
                    variant="outline"
                    className="border-red-300 text-red-600 hover:bg-red-50"
                  >
                    重試
                  </Button>
                </div>
              ) : users.length > 0 ? (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="font-bold px-5 py-3">
                          使用者資訊
                        </TableHead>
                        <TableHead className="font-bold px-5 py-3">
                          角色
                        </TableHead>
                        <TableHead className="font-bold px-5 py-3 w-40">
                          單位
                        </TableHead>
                        <TableHead className="font-bold px-5 py-3">
                          獎學金管理權限
                        </TableHead>
                        <TableHead className="font-bold px-5 py-3">
                          註冊時間
                        </TableHead>
                        <TableHead className="font-bold px-5 py-3">
                          最後登入
                        </TableHead>
                        <TableHead className="font-bold px-5 py-3">
                          權限操作
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {users.map(user => {
                        const userPermissions = scholarshipPermissions.filter(
                          p => p.user_id === Number(user.id)
                        );
                        return (
                          <TableRow key={user.id}>
                            <TableCell className="px-5 py-4 align-middle">
                              <div className="space-y-1">
                                <div className="font-medium">{user.name}</div>
                                <div className="text-sm text-gray-500">
                                  {user.email}
                                </div>
                                <div className="text-sm text-gray-500">
                                  @{user.nycu_id}
                                </div>
                                {user.raw_data?.chinese_name && (
                                  <div className="text-sm text-gray-500">
                                    中文名: {user.raw_data.chinese_name}
                                  </div>
                                )}
                                {user.raw_data?.english_name && (
                                  <div className="text-sm text-gray-500">
                                    英文名: {user.raw_data.english_name}
                                  </div>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="px-5 py-4 align-middle">
                              <Badge
                                variant={
                                  user.role === "super_admin"
                                    ? "destructive"
                                    : user.role === "admin"
                                      ? "default"
                                      : user.role === "college"
                                        ? "secondary"
                                        : user.role === "professor"
                                          ? "outline"
                                          : "default"
                                }
                                className="text-xs px-3 py-1 rounded-full whitespace-nowrap"
                              >
                                {getRoleLabel(user.role)}
                              </Badge>
                            </TableCell>
                            <TableCell className="px-5 py-4 align-middle w-40">
                              <div className="space-y-1">
                                {user.dept_name ? (
                                  <div className="text-sm font-medium text-gray-900 truncate">
                                    {user.dept_name}
                                  </div>
                                ) : (
                                  <div className="text-sm text-gray-400">
                                    未設定
                                  </div>
                                )}
                                {user.dept_code && (
                                  <div className="text-xs text-gray-500">
                                    代碼: {user.dept_code}
                                  </div>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="px-5 py-4 align-middle">
                              <div className="flex flex-wrap gap-2 min-h-[32px]">
                                {loadingPermissions ? (
                                  <div className="text-xs text-gray-400">
                                    載入中...
                                  </div>
                                ) : user.role === "super_admin" ? (
                                  <>
                                    {availableScholarships.map(scholarship => (
                                      <Badge
                                        key={scholarship.id}
                                        variant="default"
                                        className="text-xs px-3 py-1 rounded-full mb-1"
                                      >
                                        {scholarship.name}
                                      </Badge>
                                    ))}
                                    <div className="text-xs text-green-600 font-medium w-full">
                                      擁有所有獎學金權限
                                    </div>
                                  </>
                                ) : user.role === "professor" ? (
                                  <div className="text-xs text-amber-600 font-medium">
                                    教授無需管理權限
                                  </div>
                                ) : userPermissions.length === 0 ? (
                                  <div className="text-xs text-gray-400">
                                    無獎學金權限
                                  </div>
                                ) : (
                                  userPermissions.map(permission => (
                                    <Badge
                                      key={permission.id}
                                      variant="secondary"
                                      className="text-xs px-3 py-1 rounded-full mb-1"
                                    >
                                      {permission.scholarship_name}
                                    </Badge>
                                  ))
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="px-5 py-4 align-middle">
                              <div className="text-sm text-gray-600">
                                {new Date(user.created_at).toLocaleDateString(
                                  "zh-TW",
                                  {
                                    year: "numeric",
                                    month: "2-digit",
                                    day: "2-digit",
                                  }
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="px-5 py-4 align-middle">
                              <div className="text-sm text-gray-600">
                                {user.last_login_at
                                  ? new Date(user.last_login_at).toLocaleString(
                                      "zh-TW",
                                      {
                                        year: "numeric",
                                        month: "2-digit",
                                        day: "2-digit",
                                        hour: "2-digit",
                                        minute: "2-digit",
                                        second: "2-digit",
                                        hour12: false,
                                      }
                                    )
                                  : "從未登入"}
                              </div>
                            </TableCell>
                            <TableCell className="px-5 py-4 align-middle">
                              <div className="flex gap-1">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleEditUser(user)}
                                  className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                                >
                                  <Edit className="h-4 w-4" />
                                  {user.role === "professor"
                                    ? "更改角色"
                                    : "編輯權限"}
                                </Button>
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>

                  {/* 分頁 */}
                  <div className="flex items-center justify-between p-4 border-t">
                    <div className="text-sm text-gray-600">
                      顯示 {(userPagination.page - 1) * userPagination.size + 1}{" "}
                      到{" "}
                      {Math.min(
                        userPagination.page * userPagination.size,
                        userPagination.total
                      )}{" "}
                      筆，共 {userPagination.total} 筆
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setUserPagination(prev => ({
                            ...prev,
                            page: prev.page - 1,
                          }))
                        }
                        disabled={userPagination.page <= 1}
                      >
                        上一頁
                      </Button>
                      <span className="flex items-center px-3 text-sm">
                        第 {userPagination.page} 頁
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          setUserPagination(prev => ({
                            ...prev,
                            page: prev.page + 1,
                          }))
                        }
                        disabled={
                          userPagination.page * userPagination.size >=
                          userPagination.total
                        }
                      >
                        下一頁
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  <Users className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                  <p className="text-lg font-medium">尚無使用者權限資料</p>
                  <p className="text-sm mt-2 mb-4">
                    點擊「新增使用者權限」開始設定使用者權限
                  </p>
                  <Button onClick={fetchUsers} variant="outline" size="sm">
                    重新載入
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* 使用者編輯 Modal */}
          <UserEditModal
            isOpen={showUserForm}
            onClose={() => setShowUserForm(false)}
            editingUser={editingUser}
            userForm={userForm}
            onUserFormChange={handleUserFormChange}
            onSubmit={handleUserSubmit}
            isLoading={userFormLoading}
            scholarshipPermissions={scholarshipPermissions}
            availableScholarships={availableScholarships}
            onPermissionChange={handlePermissionChange}
          />
        </TabsContent>

        {hasQuotaPermission && (
          <TabsContent value="quota" className="space-y-4">
            <QuotaManagement />
          </TabsContent>
        )}

        <TabsContent value="history" className="space-y-4">
          <Card className="academic-card border-nycu-blue-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
                <FileText className="h-5 w-5 text-nycu-blue-600" />
                歷史申請
              </CardTitle>
              <CardDescription>
                查看所有歷史申請記錄及其狀態，按獎學金類型分類
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* 獎學金類型 Tab 區域 */}
              <Tabs
                value={activeHistoricalTab}
                onValueChange={setActiveHistoricalTab}
                className="w-full"
              >
                <TabsList className="flex w-full mb-6">
                  <TabsTrigger
                    key="all"
                    value="all"
                    className="flex-1 flex items-center justify-center gap-2"
                  >
                    <span>全部申請</span>
                    <Badge variant="secondary" className="text-xs">
                      {Object.values(historicalApplicationsGroups).reduce(
                        (total, apps) => total + apps.length,
                        0
                      )}
                    </Badge>
                  </TabsTrigger>
                  {Object.keys(historicalApplicationsGroups).map(
                    scholarshipType => (
                      <TabsTrigger
                        key={scholarshipType}
                        value={scholarshipType}
                        className="flex-1 flex items-center justify-center gap-2"
                      >
                        <span>{scholarshipType}</span>
                        <Badge variant="secondary" className="text-xs">
                          {historicalApplicationsGroups[scholarshipType].length}
                        </Badge>
                      </TabsTrigger>
                    )
                  )}
                </TabsList>

                {/* 全部申請 Tab */}
                <TabsContent key="all" value="all" className="space-y-4 mt-6">
                  <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                    <h3 className="text-lg font-semibold text-blue-900 mb-2">
                      全部歷史申請
                    </h3>
                    <p className="text-sm text-blue-700">
                      顯示所有類型的歷史申請記錄，共{" "}
                      {historicalApplications.length} 筆
                    </p>
                  </div>
                  <div className="space-y-4">
                    {/* 篩選控制區 */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
                      <div>
                        <Label htmlFor="status-filter">狀態篩選</Label>
                        <Select
                          value={historicalApplicationsFilters.status || "all"}
                          onValueChange={value =>
                            setHistoricalApplicationsFilters(prev => ({
                              ...prev,
                              status: value === "all" ? "" : value,
                              page: 1,
                            }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="選擇狀態" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">全部狀態</SelectItem>
                            <SelectItem value="submitted">已提交</SelectItem>
                            <SelectItem value="under_review">審核中</SelectItem>
                            <SelectItem value="approved">已通過</SelectItem>
                            <SelectItem value="rejected">已拒絕</SelectItem>
                            <SelectItem value="cancelled">已取消</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor="year-filter">學年度</Label>
                        <Select
                          value={
                            historicalApplicationsFilters.academic_year?.toString() ||
                            "all"
                          }
                          onValueChange={value =>
                            setHistoricalApplicationsFilters(prev => ({
                              ...prev,
                              academic_year:
                                value && value !== "all"
                                  ? parseInt(value)
                                  : undefined,
                              page: 1,
                            }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="選擇學年度" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">全部學年度</SelectItem>
                            <SelectItem value="114">114學年度</SelectItem>
                            <SelectItem value="113">113學年度</SelectItem>
                            <SelectItem value="112">112學年度</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor="semester-filter">學期</Label>
                        <Select
                          value={
                            historicalApplicationsFilters.semester || "all"
                          }
                          onValueChange={value =>
                            setHistoricalApplicationsFilters(prev => ({
                              ...prev,
                              semester: value === "all" ? "" : value,
                              page: 1,
                            }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="選擇學期" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">全部學期</SelectItem>
                            <SelectItem value="first">第一學期</SelectItem>
                            <SelectItem value="second">第二學期</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      <div>
                        <Label htmlFor="search-input">搜尋</Label>
                        <Input
                          id="search-input"
                          placeholder="搜尋學生姓名、學號或申請編號"
                          value={historicalApplicationsFilters.search}
                          onChange={e =>
                            setHistoricalApplicationsFilters(prev => ({
                              ...prev,
                              search: e.target.value,
                              page: 1,
                            }))
                          }
                        />
                      </div>
                    </div>

                    {/* 操作按鈕 */}
                    <div className="flex justify-between items-center">
                      <div className="text-sm text-gray-600">
                        共 {historicalApplicationsPagination.total} 筆申請記錄
                      </div>
                      <Button
                        onClick={fetchHistoricalApplications}
                        disabled={loadingHistoricalApplications}
                        variant="outline"
                        size="sm"
                      >
                        <RefreshCw
                          className={`h-4 w-4 mr-2 ${loadingHistoricalApplications ? "animate-spin" : ""}`}
                        />
                        刷新
                      </Button>
                    </div>

                    {/* 錯誤顯示 */}
                    {historicalApplicationsError && (
                      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                        <div className="flex items-center gap-2 text-red-700">
                          <AlertCircle className="h-4 w-4" />
                          <span className="font-medium">載入失敗</span>
                        </div>
                        <p className="text-red-600 text-sm mt-1">
                          {historicalApplicationsError}
                        </p>
                      </div>
                    )}

                    {/* 載入狀態 */}
                    {loadingHistoricalApplications && (
                      <div className="flex items-center justify-center py-8">
                        <div className="flex items-center gap-3">
                          <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                          <span className="text-nycu-navy-600">
                            載入歷史申請中...
                          </span>
                        </div>
                      </div>
                    )}

                    {/* 申請列表 */}
                    {!loadingHistoricalApplications &&
                      !historicalApplicationsError && (
                        <div className="border rounded-lg overflow-hidden">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>申請編號</TableHead>
                                <TableHead>學生資訊</TableHead>
                                <TableHead>獎學金類型</TableHead>
                                <TableHead>學年度/學期</TableHead>
                                <TableHead>狀態</TableHead>
                                <TableHead>申請時間</TableHead>
                                <TableHead>金額</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {historicalApplications.length === 0 ? (
                                <TableRow>
                                  <TableCell
                                    colSpan={7}
                                    className="text-center py-8 text-gray-500"
                                  >
                                    沒有找到符合條件的申請記錄
                                  </TableCell>
                                </TableRow>
                              ) : (
                                historicalApplications.map(application => (
                                  <TableRow key={application.id}>
                                    <TableCell className="font-medium">
                                      {application.app_id}
                                    </TableCell>
                                    <TableCell>
                                      <div>
                                        <div className="font-medium">
                                          {application.student_name}
                                        </div>
                                        <div className="text-sm text-gray-500">
                                          {application.student_id}
                                        </div>
                                        {application.student_department && (
                                          <div className="text-xs text-gray-400">
                                            {application.student_department}
                                          </div>
                                        )}
                                      </div>
                                    </TableCell>
                                    <TableCell>
                                      <div>
                                        <div className="font-medium">
                                          {application.scholarship_name}
                                        </div>
                                        {application.sub_scholarship_type &&
                                          application.sub_scholarship_type !==
                                            "GENERAL" && (
                                            <div className="text-sm text-gray-500">
                                              {application.sub_scholarship_type}
                                            </div>
                                          )}
                                        {application.is_renewal && (
                                          <Badge
                                            variant="outline"
                                            className="text-xs mt-1"
                                          >
                                            續領
                                          </Badge>
                                        )}
                                      </div>
                                    </TableCell>
                                    <TableCell>
                                      <div className="text-sm">
                                        {application.academic_year}學年度
                                        {application.semester && (
                                          <div className="text-xs text-gray-500">
                                            {application.semester === "first"
                                              ? "第一學期"
                                              : "第二學期"}
                                          </div>
                                        )}
                                      </div>
                                    </TableCell>
                                    <TableCell>
                                      <Badge
                                        variant="secondary"
                                        className={
                                          application.status === "approved"
                                            ? "bg-green-100 text-green-700"
                                            : application.status === "rejected"
                                              ? "bg-red-100 text-red-700"
                                              : application.status ===
                                                  "under_review"
                                                ? "bg-yellow-100 text-yellow-700"
                                                : "bg-gray-100 text-gray-700"
                                        }
                                      >
                                        {application.status_name ||
                                          application.status}
                                      </Badge>
                                    </TableCell>
                                    <TableCell>
                                      <div className="text-sm">
                                        {new Date(
                                          application.created_at
                                        ).toLocaleDateString("zh-TW")}
                                      </div>
                                      {application.submitted_at && (
                                        <div className="text-xs text-gray-500">
                                          提交：
                                          {new Date(
                                            application.submitted_at
                                          ).toLocaleDateString("zh-TW")}
                                        </div>
                                      )}
                                    </TableCell>
                                    <TableCell>
                                      {application.amount ? (
                                        <div className="font-medium">
                                          NT${" "}
                                          {Number(
                                            application.amount
                                          ).toLocaleString()}
                                        </div>
                                      ) : (
                                        <span className="text-gray-400">-</span>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      )}

                    {/* 分頁控制 */}
                    {historicalApplicationsPagination.total > 0 && (
                      <div className="flex items-center justify-between">
                        <div className="text-sm text-gray-600">
                          第{" "}
                          {(historicalApplicationsPagination.page - 1) *
                            historicalApplicationsPagination.size +
                            1}{" "}
                          -{" "}
                          {Math.min(
                            historicalApplicationsPagination.page *
                              historicalApplicationsPagination.size,
                            historicalApplicationsPagination.total
                          )}{" "}
                          筆，共 {historicalApplicationsPagination.total} 筆
                        </div>
                        <div className="flex items-center gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setHistoricalApplicationsFilters(prev => ({
                                ...prev,
                                page: (prev.page ?? 2) - 1,
                              }));
                            }}
                            disabled={
                              historicalApplicationsPagination.page <= 1
                            }
                          >
                            上一頁
                          </Button>
                          <span className="text-sm">
                            第 {historicalApplicationsPagination.page} /{" "}
                            {historicalApplicationsPagination.pages} 頁
                          </span>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setHistoricalApplicationsFilters(prev => ({
                                ...prev,
                                page: (prev.page ?? 0) + 1,
                              }));
                            }}
                            disabled={
                              historicalApplicationsPagination.page >=
                              historicalApplicationsPagination.pages
                            }
                          >
                            下一頁
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>

                {/* 各獎學金類型的 Tab */}
                {Object.keys(historicalApplicationsGroups).map(
                  scholarshipType => (
                    <TabsContent
                      key={scholarshipType}
                      value={scholarshipType}
                      className="space-y-4 mt-6"
                    >
                      <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                        <h3 className="text-lg font-semibold text-blue-900 mb-2">
                          {scholarshipType}
                        </h3>
                        <p className="text-sm text-blue-700">
                          此類型共有{" "}
                          {historicalApplicationsGroups[scholarshipType].length}{" "}
                          筆申請記錄
                        </p>
                      </div>

                      <div className="space-y-4">
                        {/* 篩選控制區 */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg">
                          <div>
                            <Label htmlFor="status-filter">狀態篩選</Label>
                            <Select
                              value={
                                historicalApplicationsFilters.status || "all"
                              }
                              onValueChange={value =>
                                setHistoricalApplicationsFilters(prev => ({
                                  ...prev,
                                  status: value === "all" ? "" : value,
                                  page: 1,
                                }))
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="選擇狀態" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="all">全部狀態</SelectItem>
                                <SelectItem value="submitted">
                                  已提交
                                </SelectItem>
                                <SelectItem value="under_review">
                                  審核中
                                </SelectItem>
                                <SelectItem value="approved">已通過</SelectItem>
                                <SelectItem value="rejected">已拒絕</SelectItem>
                                <SelectItem value="cancelled">
                                  已取消
                                </SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          <div>
                            <Label htmlFor="year-filter">學年度</Label>
                            <Select
                              value={
                                historicalApplicationsFilters.academic_year?.toString() ||
                                "all"
                              }
                              onValueChange={value =>
                                setHistoricalApplicationsFilters(prev => ({
                                  ...prev,
                                  academic_year:
                                    value && value !== "all"
                                      ? parseInt(value)
                                      : undefined,
                                  page: 1,
                                }))
                              }
                            >
                              <SelectTrigger>
                                <SelectValue placeholder="選擇學年度" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="all">全部學年度</SelectItem>
                                <SelectItem value="114">114學年度</SelectItem>
                                <SelectItem value="113">113學年度</SelectItem>
                                <SelectItem value="112">112學年度</SelectItem>
                              </SelectContent>
                            </Select>
                          </div>

                          <div>
                            <Label htmlFor="search-input">搜尋</Label>
                            <Input
                              id="search-input"
                              placeholder="搜尋學生姓名、學號或申請編號"
                              value={historicalApplicationsFilters.search}
                              onChange={e =>
                                setHistoricalApplicationsFilters(prev => ({
                                  ...prev,
                                  search: e.target.value,
                                  page: 1,
                                }))
                              }
                            />
                          </div>
                        </div>

                        {/* 操作按鈕 */}
                        <div className="flex justify-between items-center">
                          <div className="text-sm text-gray-600">
                            {scholarshipType} 共{" "}
                            {
                              historicalApplicationsGroups[scholarshipType]
                                .length
                            }{" "}
                            筆申請記錄
                          </div>
                          <Button
                            onClick={fetchHistoricalApplications}
                            disabled={loadingHistoricalApplications}
                            variant="outline"
                            size="sm"
                          >
                            <RefreshCw
                              className={`h-4 w-4 mr-2 ${loadingHistoricalApplications ? "animate-spin" : ""}`}
                            />
                            刷新
                          </Button>
                        </div>

                        {/* 申請列表 - 只顯示當前類型的申請 */}
                        <div className="border rounded-lg overflow-hidden">
                          <Table>
                            <TableHeader>
                              <TableRow>
                                <TableHead>申請編號</TableHead>
                                <TableHead>學生資訊</TableHead>
                                <TableHead>學年度/學期</TableHead>
                                <TableHead>狀態</TableHead>
                                <TableHead>申請時間</TableHead>
                                <TableHead>金額</TableHead>
                              </TableRow>
                            </TableHeader>
                            <TableBody>
                              {historicalApplicationsGroups[scholarshipType]
                                .length === 0 ? (
                                <TableRow>
                                  <TableCell
                                    colSpan={6}
                                    className="text-center py-8 text-gray-500"
                                  >
                                    沒有找到 {scholarshipType} 的申請記錄
                                  </TableCell>
                                </TableRow>
                              ) : (
                                historicalApplicationsGroups[
                                  scholarshipType
                                ].map(application => (
                                  <TableRow key={application.id}>
                                    <TableCell className="font-medium">
                                      {application.app_id}
                                    </TableCell>
                                    <TableCell>
                                      <div>
                                        <div className="font-medium">
                                          {application.student_name}
                                        </div>
                                        <div className="text-sm text-gray-500">
                                          {application.student_id}
                                        </div>
                                        {application.student_department && (
                                          <div className="text-xs text-gray-400">
                                            {application.student_department}
                                          </div>
                                        )}
                                      </div>
                                    </TableCell>
                                    <TableCell>
                                      <div className="text-sm">
                                        {application.academic_year}學年度
                                        {application.semester && (
                                          <div className="text-xs text-gray-500">
                                            {application.semester === "first"
                                              ? "第一學期"
                                              : "第二學期"}
                                          </div>
                                        )}
                                      </div>
                                    </TableCell>
                                    <TableCell>
                                      <Badge
                                        variant="secondary"
                                        className={
                                          application.status === "approved"
                                            ? "bg-green-100 text-green-700"
                                            : application.status === "rejected"
                                              ? "bg-red-100 text-red-700"
                                              : application.status ===
                                                  "under_review"
                                                ? "bg-yellow-100 text-yellow-700"
                                                : "bg-gray-100 text-gray-700"
                                        }
                                      >
                                        {application.status_name ||
                                          application.status}
                                      </Badge>
                                    </TableCell>
                                    <TableCell>
                                      <div className="text-sm">
                                        {new Date(
                                          application.created_at
                                        ).toLocaleDateString("zh-TW")}
                                      </div>
                                      {application.submitted_at && (
                                        <div className="text-xs text-gray-500">
                                          提交：
                                          {new Date(
                                            application.submitted_at
                                          ).toLocaleDateString("zh-TW")}
                                        </div>
                                      )}
                                    </TableCell>
                                    <TableCell>
                                      {application.amount ? (
                                        <div className="font-medium">
                                          NT${" "}
                                          {Number(
                                            application.amount
                                          ).toLocaleString()}
                                        </div>
                                      ) : (
                                        <span className="text-gray-400">-</span>
                                      )}
                                    </TableCell>
                                  </TableRow>
                                ))
                              )}
                            </TableBody>
                          </Table>
                        </div>
                      </div>
                    </TabsContent>
                  )
                )}
              </Tabs>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="announcements" className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold">系統公告管理</h3>
            <Button
              onClick={() => setShowAnnouncementForm(true)}
              className="nycu-gradient text-white"
            >
              <Plus className="h-4 w-4 mr-1" />
              新增公告
            </Button>
          </div>

          {/* 公告表單 */}
          {showAnnouncementForm && (
            <Card className="border-nycu-blue-200">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <MessageSquare className="h-5 w-5" />
                  {editingAnnouncement ? "編輯公告" : "新增公告"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>公告標題 *</Label>
                    <Input
                      value={announcementForm.title}
                      onChange={e =>
                        handleAnnouncementFormChange("title", e.target.value)
                      }
                      placeholder="輸入公告標題"
                      className="border-nycu-blue-200"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>英文標題</Label>
                    <Input
                      value={announcementForm.title_en || ""}
                      onChange={e =>
                        handleAnnouncementFormChange("title_en", e.target.value)
                      }
                      placeholder="English title (optional)"
                      className="border-nycu-blue-200"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>公告內容 *</Label>
                  <Textarea
                    value={announcementForm.message}
                    onChange={e =>
                      handleAnnouncementFormChange("message", e.target.value)
                    }
                    placeholder="輸入公告內容"
                    rows={4}
                    className="border-nycu-blue-200"
                  />
                </div>

                <div className="space-y-2">
                  <Label>英文內容</Label>
                  <Textarea
                    value={announcementForm.message_en || ""}
                    onChange={e =>
                      handleAnnouncementFormChange("message_en", e.target.value)
                    }
                    placeholder="English message (optional)"
                    rows={3}
                    className="border-nycu-blue-200"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label>公告類型</Label>
                    <select
                      value={announcementForm.notification_type}
                      onChange={e =>
                        handleAnnouncementFormChange(
                          "notification_type",
                          e.target.value
                        )
                      }
                      className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
                    >
                      <option value="info">資訊</option>
                      <option value="warning">警告</option>
                      <option value="error">錯誤</option>
                      <option value="success">成功</option>
                      <option value="reminder">提醒</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>優先級</Label>
                    <select
                      value={announcementForm.priority}
                      onChange={e =>
                        handleAnnouncementFormChange("priority", e.target.value)
                      }
                      className="w-full px-3 py-2 border border-nycu-blue-200 rounded-md"
                    >
                      <option value="low">低</option>
                      <option value="normal">一般</option>
                      <option value="high">高</option>
                      <option value="urgent">緊急</option>
                    </select>
                  </div>
                  <div className="space-y-2">
                    <Label>行動連結</Label>
                    <Input
                      value={announcementForm.action_url || ""}
                      onChange={e =>
                        handleAnnouncementFormChange(
                          "action_url",
                          e.target.value
                        )
                      }
                      placeholder="/path/to/action"
                      className="border-nycu-blue-200"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>過期時間</Label>
                  <Input
                    type="datetime-local"
                    value={
                      announcementForm.expires_at
                        ? new Date(announcementForm.expires_at)
                            .toISOString()
                            .slice(0, 16)
                        : ""
                    }
                    onChange={e =>
                      handleAnnouncementFormChange(
                        "expires_at",
                        e.target.value
                          ? new Date(e.target.value).toISOString()
                          : ""
                      )
                    }
                    className="border-nycu-blue-200"
                  />
                </div>

                <div className="flex gap-2 pt-4">
                  <Button
                    onClick={
                      editingAnnouncement
                        ? handleUpdateAnnouncement
                        : handleCreateAnnouncement
                    }
                    disabled={
                      !announcementForm.title || !announcementForm.message
                    }
                    className="nycu-gradient text-white"
                  >
                    <Save className="h-4 w-4 mr-1" />
                    {editingAnnouncement ? "更新公告" : "建立公告"}
                  </Button>
                  <Button variant="outline" onClick={resetAnnouncementForm}>
                    取消
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* 公告列表 */}
          <Card className="border-nycu-blue-200">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertCircle className="h-5 w-5" />
                系統公告列表
              </CardTitle>
            </CardHeader>
            <CardContent className="p-6">
              {loadingAnnouncements ? (
                <div className="flex items-center justify-center py-8">
                  <div className="flex items-center gap-3">
                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                    <span className="text-nycu-navy-600">載入公告中...</span>
                  </div>
                </div>
              ) : announcementsError ? (
                <div className="text-center py-12">
                  <AlertCircle className="h-16 w-16 mx-auto mb-4 text-red-400" />
                  <p className="text-lg font-medium text-red-600 mb-2">
                    載入公告失敗
                  </p>
                  <p className="text-sm text-gray-600 mb-4">
                    {announcementsError}
                  </p>
                  <Button
                    onClick={fetchAnnouncements}
                    variant="outline"
                    className="border-red-300 text-red-600 hover:bg-red-50"
                  >
                    重試
                  </Button>
                </div>
              ) : announcements.length > 0 ? (
                <div className="space-y-6">
                  {announcements.map(announcement => (
                    <div
                      key={announcement.id}
                      className="p-5 border border-gray-200 rounded-lg hover:border-nycu-blue-300 transition-colors bg-white shadow-sm"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1 pr-4">
                          <div className="flex items-center gap-2 mb-3">
                            <h4 className="font-semibold text-nycu-navy-800 text-lg">
                              {announcement.title}
                            </h4>
                            <Badge
                              variant={
                                announcement.notification_type === "error"
                                  ? "destructive"
                                  : announcement.notification_type === "warning"
                                    ? "secondary"
                                    : announcement.notification_type ===
                                        "success"
                                      ? "default"
                                      : "outline"
                              }
                            >
                              {announcement.notification_type}
                            </Badge>
                            <Badge variant="outline">
                              {announcement.priority}
                            </Badge>
                          </div>
                          <p className="text-gray-700 mb-3 leading-relaxed">
                            {announcement.message}
                          </p>
                          <div className="text-sm text-gray-500 bg-gray-50 p-2 rounded">
                            建立時間:{" "}
                            {new Date(announcement.created_at).toLocaleString(
                              "zh-TW",
                              {
                                year: "numeric",
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                                second: "2-digit",
                                hour12: false,
                              }
                            )}
                            {announcement.expires_at && (
                              <span className="ml-4">
                                過期時間:{" "}
                                {new Date(
                                  announcement.expires_at
                                ).toLocaleString("zh-TW", {
                                  year: "numeric",
                                  month: "2-digit",
                                  day: "2-digit",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                  second: "2-digit",
                                  hour12: false,
                                })}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-col gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleEditAnnouncement(announcement)}
                            className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                          >
                            <Edit className="h-4 w-4 mr-1" />
                            編輯
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              handleDeleteAnnouncement(announcement.id)
                            }
                            className="hover:bg-red-50 hover:border-red-300 hover:text-red-600"
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            刪除
                          </Button>
                        </div>
                      </div>
                    </div>
                  ))}

                  {/* 分頁控制 */}
                  {announcementPagination.total >
                    announcementPagination.size && (
                    <div className="flex items-center justify-between pt-6 border-t border-gray-200">
                      <div className="text-sm text-gray-600">
                        顯示第{" "}
                        {(announcementPagination.page - 1) *
                          announcementPagination.size +
                          1}{" "}
                        -{" "}
                        {Math.min(
                          announcementPagination.page *
                            announcementPagination.size,
                          announcementPagination.total
                        )}{" "}
                        項，共 {announcementPagination.total} 項公告
                      </div>
                      <div className="flex gap-3">
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={announcementPagination.page <= 1}
                          onClick={() =>
                            setAnnouncementPagination(prev => ({
                              ...prev,
                              page: prev.page - 1,
                            }))
                          }
                          className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                        >
                          ← 上一頁
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={
                            announcementPagination.page *
                              announcementPagination.size >=
                            announcementPagination.total
                          }
                          onClick={() =>
                            setAnnouncementPagination(prev => ({
                              ...prev,
                              page: prev.page + 1,
                            }))
                          }
                          className="hover:bg-nycu-blue-50 hover:border-nycu-blue-300"
                        >
                          下一頁 →
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  <MessageSquare className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                  <p className="text-lg font-medium">尚無系統公告</p>
                  <p className="text-sm mt-2 mb-4">
                    點擊「新增公告」開始建立系統公告
                  </p>
                  <Button
                    onClick={fetchAnnouncements}
                    variant="outline"
                    size="sm"
                  >
                    重新載入
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="settings" className="space-y-4">
          <SystemConfigurationManagement />
        </TabsContent>

        <TabsContent value="email" className="space-y-4">
          <Card className="academic-card border-nycu-blue-200">
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
                    <Mail className="h-5 w-5 text-nycu-blue-600" />
                    郵件管理
                  </CardTitle>
                  <CardDescription>
                    管理郵件模板、查看歷史記錄、管理排程郵件
                  </CardDescription>
                </div>
                <Link href="/admin/email-management">
                  <Button variant="outline" size="sm" className="gap-2">
                    <Send className="h-4 w-4" />
                    進階郵件管理
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent>
              <Tabs
                value={emailManagementTab}
                onValueChange={setEmailManagementTab}
              >
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="templates">郵件模板</TabsTrigger>
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
        </TabsContent>
      </Tabs>
    </div>
  );
}
