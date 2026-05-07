"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { ProgressTimeline } from "@/components/progress-timeline";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { ApplicationFormDataDisplay } from "@/components/application-form-data-display";
import { ApplicationAuditTrail } from "@/components/application-audit-trail";
import { ProfessorAssignmentDropdown } from "@/components/professor-assignment-dropdown";
import {
  FileText,
  Eye,
  Loader2,
  User as UserIcon,
  AlertCircle,
  CheckCircle,
  XCircle,
  Trash2,
  FileQuestion,
  Info,
  ClipboardList,
  Upload,
  GraduationCap,
  History,
  Settings,
  CreditCard,
  Shield,
  ShieldCheck,
  ShieldX,
  Send,
} from "lucide-react";
import { Locale } from "@/lib/validators";
import { Application, HistoricalApplication, User } from "@/lib/api";
import api from "@/lib/api";
import { useStudentPreview } from "@/hooks/use-student-preview";
import {
  useReferenceData,
  getStudyingStatusName,
  getDegreeName,
  getDepartmentName,
  getGenderName,
  getIdentityName,
  getSchoolIdentityName,
  getAcademyName,
  getEnrollTypeName,
} from "@/hooks/use-reference-data";
import {
  ApplicationStatus,
  getApplicationStatusLabel,
  getApplicationStatusBadgeVariant,
} from "@/lib/enums";
import {
  getApplicationTimeline,
  getDocumentLabel,
  fetchApplicationFiles,
  formatFieldName,
} from "@/lib/utils/application-helpers";
import { getCurrentSemesterROC, toROCYear } from "@/src/utils/dateUtils";

interface ApplicationReviewDialogProps {
  application: Application | HistoricalApplication | null;
  role: "college" | "admin" | "super_admin";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  locale?: "zh" | "en";
  academicYear?: number;
  user?: User;

  // College-specific handlers (optional)
  onApprove?: (id: number, comments?: string) => void;
  onReject?: (id: number, comments?: string) => void;
  onRequestDocs?: (app: Application) => void;
  onDelete?: (app: Application) => void;

  // Admin-specific handlers (optional)
  onAdminApprove?: (id: number) => void;
  onAdminReject?: (id: number) => void;

  // Callback for successful review submission (to trigger data refresh)
  onReviewSubmitted?: () => void;
}

// Helper component to display a single field with fallback
function FieldDisplay({
  label,
  value,
  locale = "zh",
}: {
  label: string;
  value: any;
  locale?: "zh" | "en";
}) {
  const displayValue = value !== null && value !== undefined ? String(value) : null;

  return (
    <div className="p-2 bg-muted/50 rounded">
      <p className="text-xs text-muted-foreground">{label}</p>
      {displayValue !== null ? (
        <p className="text-sm font-medium">{displayValue}</p>
      ) : (
        <p className="text-sm text-orange-600">
          {locale === "zh" ? "無法獲取" : "Unavailable"}
        </p>
      )}
    </div>
  );
}

// Student Preview Display Component
function StudentPreviewDisplay({
  studentId,
  academicYear,
  locale = "zh",
  studyingStatuses,
  degrees,
  departments,
  genders,
  academies,
  identities,
  schoolIdentities,
  enrollTypes,
}: {
  studentId: string;
  academicYear?: number;
  locale?: "zh" | "en";
  studyingStatuses: Array<{ id: number; name: string }>;
  degrees: Array<{ id: number; name: string }>;
  departments: Array<{ id: number; code: string; name: string; academy_code?: string | null }>;
  genders: Array<{ id: number; name: string }>;
  academies: Array<{ id: number; code: string; name: string }>;
  identities: Array<{ id: number; name: string }>;
  schoolIdentities: Array<{ id: number; name: string }>;
  enrollTypes: Array<{ degree_id: number; code: string; name: string; name_en?: string; degree_name?: string }>;
}) {
  const { previewData, isLoading, error, fetchPreview } = useStudentPreview();

  useEffect(() => {
    if (studentId) {
      // If academicYear is not provided, use current academic year
      let yearToUse = academicYear;
      if (!yearToUse) {
        // Get current semester (e.g., "114-1") and extract year
        const currentSemester = getCurrentSemesterROC();
        const [yearStr] = currentSemester.split("-");
        yearToUse = parseInt(yearStr, 10);
      }

      fetchPreview(studentId, yearToUse);
    }
  }, [studentId, academicYear, fetchPreview]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full mb-2" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  // Display basic info - always show fields even if there's an error
  return (
    <div className="space-y-4">
      {/* Error Alert - show at top if there's an error */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {locale === "zh" ? "無法載入學生資料" : "Failed to load student data"}
          </AlertDescription>
        </Alert>
      )}

      {/* Basic Information Section - All API Fields Grouped */}
      <div className="space-y-4">
        {/* 基本資訊 */}
        <div>
          <h5 className="text-xs font-semibold mb-3">
            {locale === "zh" ? "基本資訊" : "Basic Information"}
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <FieldDisplay
              label={locale === "zh" ? "學號" : "Student ID"}
              value={previewData?.basic?.std_stdcode}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "姓名" : "Name"}
              value={previewData?.basic?.std_cname}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "英文姓名" : "English Name"}
              value={previewData?.basic?.std_ename}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "身分證字號" : "ID Number"}
              value={previewData?.basic?.std_pid}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "性別" : "Gender"}
              value={
                previewData?.basic?.std_sex
                  ? getGenderName(Number(previewData.basic.std_sex), genders)
                  : undefined
              }
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "生日" : "Date of Birth"}
              value={previewData?.basic?.std_bdate}
              locale={locale}
            />
          </div>
        </div>

        <Separator />

        {/* 學籍資訊 */}
        <div>
          <h5 className="text-xs font-semibold mb-3">
            {locale === "zh" ? "學籍資訊" : "Academic Registration"}
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <FieldDisplay
              label={locale === "zh" ? "學院" : "Academy"}
              value={previewData?.basic?.std_academyno ? getAcademyName(previewData.basic.std_academyno, academies) : undefined}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "系所" : "Department"}
              value={previewData?.basic?.std_depno ? getDepartmentName(previewData.basic.std_depno, departments) : undefined}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "學位" : "Degree"}
              value={
                previewData?.basic?.std_degree
                  ? getDegreeName(Number(previewData.basic.std_degree), degrees)
                  : undefined
              }
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "在學狀態" : "Studying Status"}
              value={
                previewData?.basic?.std_studingstatus
                  ? getStudyingStatusName(Number(previewData.basic.std_studingstatus), studyingStatuses)
                  : undefined
              }
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "學籍狀態" : "Registration Status"}
              value={previewData?.basic?.mgd_title}
              locale={locale}
            />
          </div>
        </div>

        <Separator />

        {/* 入學資訊 */}
        <div>
          <h5 className="text-xs font-semibold mb-3">
            {locale === "zh" ? "入學資訊" : "Enrollment Information"}
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <FieldDisplay
              label={locale === "zh" ? "入學年度/學期" : "Enrollment Year/Term"}
              value={previewData?.basic?.std_enrollyear ? `${previewData.basic.std_enrollyear}/${previewData.basic.std_enrollterm || "-"}` : undefined}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "入學方式" : "Enrollment Type"}
              value={
                previewData?.basic?.std_enrolltype
                  ? getEnrollTypeName(
                      Number(previewData.basic.std_enrolltype),
                      previewData.basic.std_degree ? Number(previewData.basic.std_degree) : undefined,
                      enrollTypes
                    )
                  : undefined
              }
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "就讀學期數" : "Terms Enrolled"}
              value={previewData?.basic?.std_termcount}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "最高學歷學校" : "Highest Education"}
              value={previewData?.basic?.std_highestschname}
              locale={locale}
            />
          </div>
        </div>

        <Separator />

        {/* 個人資訊 */}
        <div>
          <h5 className="text-xs font-semibold mb-3">
            {locale === "zh" ? "個人資訊" : "Personal Information"}
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <FieldDisplay
              label={locale === "zh" ? "學生身分" : "Student Identity"}
              value={
                previewData?.basic?.std_identity
                  ? getIdentityName(Number(previewData.basic.std_identity), identities)
                  : undefined
              }
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "在學身分" : "School Identity"}
              value={
                previewData?.basic?.std_schoolid
                  ? getSchoolIdentityName(Number(previewData.basic.std_schoolid), schoolIdentities)
                  : undefined
              }
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "國籍" : "Nationality"}
              value={previewData?.basic?.std_nation}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "僑居地" : "Overseas Residence"}
              value={previewData?.basic?.std_overseaplace}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "是否直升博士" : "Direct PhD"}
              value={previewData?.basic?.ToDoctor ? (locale === "zh" ? "是" : "Yes") : (locale === "zh" ? "否" : "No")}
              locale={locale}
            />
          </div>
        </div>

        <Separator />

        {/* 聯絡資訊 */}
        <div>
          <h5 className="text-xs font-semibold mb-3">
            {locale === "zh" ? "聯絡資訊" : "Contact Information"}
          </h5>
          <div className="grid grid-cols-2 gap-3">
            <FieldDisplay
              label="Email"
              value={previewData?.basic?.com_email}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "手機" : "Phone"}
              value={previewData?.basic?.com_cellphone}
              locale={locale}
            />
            <FieldDisplay
              label={locale === "zh" ? "通訊地址" : "Address"}
              value={previewData?.basic?.com_commadd}
              locale={locale}
            />
          </div>
        </div>
      </div>

      {/* Term Data Section with Tabs */}
      {previewData?.recent_terms && previewData.recent_terms.length > 0 ? (
        <div>
          <h4 className="text-sm font-semibold mb-3">
            {locale === "zh" ? "學期資料" : "Term Data"}
          </h4>
          <Tabs defaultValue="0" className="w-full">
            <TabsList className="grid w-full" style={{ gridTemplateColumns: `repeat(${previewData?.recent_terms?.length || 0}, 1fr)` }}>
              {previewData?.recent_terms?.map((term, index) => (
                <TabsTrigger key={index} value={String(index)}>
                  {term.academic_year}-
                  {term.term === "1" ? (locale === "zh" ? "上" : "1st") : (locale === "zh" ? "下" : "2nd")}
                </TabsTrigger>
              ))}
            </TabsList>
            {previewData?.recent_terms?.map((term, index) => (
              <TabsContent key={index} value={String(index)} className="space-y-4 mt-4">
                {/* Basic Term Info */}
                <div>
                  <h5 className="text-xs font-semibold mb-2 text-muted-foreground">
                    {locale === "zh" ? "基本資訊" : "Basic Information"}
                  </h5>
                  <div className="grid grid-cols-2 gap-2">
                    <FieldDisplay
                      label={locale === "zh" ? "學年度" : "Academic Year"}
                      value={term.academic_year}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "學期" : "Term"}
                      value={term.term === "1" ? (locale === "zh" ? "上學期" : "1st Semester") : (locale === "zh" ? "下學期" : "2nd Semester")}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "就讀學期數" : "Term Count"}
                      value={term.term_count}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "在學狀態" : "Studying Status"}
                      value={term.studying_status !== null && term.studying_status !== undefined ? getStudyingStatusName(term.studying_status, studyingStatuses) : null}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "學位" : "Degree"}
                      value={term.degree !== null && term.degree !== undefined ? getDegreeName(term.degree, degrees) : null}
                      locale={locale}
                    />
                  </div>
                </div>

                {/* Academic Organization */}
                <div>
                  <h5 className="text-xs font-semibold mb-2 text-muted-foreground">
                    {locale === "zh" ? "學院系所" : "Academy & Department"}
                  </h5>
                  <div className="grid grid-cols-2 gap-2">
                    <FieldDisplay
                      label={locale === "zh" ? "學院代碼" : "Academy Code"}
                      value={term.academy_no}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "學院名稱" : "Academy Name"}
                      value={term.academy_name}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "系所代碼" : "Department Code"}
                      value={term.dept_no}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "系所名稱" : "Department Name"}
                      value={term.dept_name}
                      locale={locale}
                    />
                  </div>
                </div>

                {/* Academic Performance */}
                <div>
                  <h5 className="text-xs font-semibold mb-2 text-muted-foreground">
                    {locale === "zh" ? "成績資訊" : "Academic Performance"}
                  </h5>
                  <div className="grid grid-cols-2 gap-2">
                    <FieldDisplay
                      label="GPA"
                      value={term.gpa !== null && term.gpa !== undefined ? term.gpa.toFixed(2) : null}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "學業成績 GPA" : "A-Score GPA"}
                      value={term.ascore_gpa !== null && term.ascore_gpa !== undefined ? term.ascore_gpa.toFixed(2) : null}
                      locale={locale}
                    />
                  </div>
                </div>

                {/* Ranking Information */}
                <div>
                  <h5 className="text-xs font-semibold mb-2 text-muted-foreground">
                    {locale === "zh" ? "排名資訊" : "Ranking Information"}
                  </h5>
                  <div className="grid grid-cols-2 gap-2">
                    <FieldDisplay
                      label={locale === "zh" ? "全校排名" : "Overall Ranking"}
                      value={term.placings}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "全校排名百分比" : "Overall Ranking %"}
                      value={term.placings_rate !== null && term.placings_rate !== undefined ? `${(term.placings_rate * 100).toFixed(1)}%` : null}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "系所排名" : "Department Ranking"}
                      value={term.dept_placing}
                      locale={locale}
                    />
                    <FieldDisplay
                      label={locale === "zh" ? "系所排名百分比" : "Department Ranking %"}
                      value={term.dept_placing_rate !== null && term.dept_placing_rate !== undefined ? `${(term.dept_placing_rate * 100).toFixed(1)}%` : null}
                      locale={locale}
                    />
                  </div>
                </div>
              </TabsContent>
            ))}
          </Tabs>
        </div>
      ) : (
        <div className="text-center py-8 bg-muted/30 rounded-lg">
          <p className="text-sm text-muted-foreground">
            {locale === "zh" ? "無學期資料" : "No term data available"}
          </p>
        </div>
      )}
    </div>
  );
}

export function ApplicationReviewDialog({
  application,
  role,
  open,
  onOpenChange,
  locale = "zh",
  academicYear,
  user,
  onApprove,
  onReject,
  onRequestDocs,
  onDelete,
  onAdminApprove,
  onAdminReject,
  onReviewSubmitted,
}: ApplicationReviewDialogProps) {
  const [applicationFiles, setApplicationFiles] = useState<any[]>([]);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
    downloadUrl?: string;
  } | null>(null);
  const [isPreviewDialogOpen, setIsPreviewDialogOpen] = useState(false);
  const [documentLabels, setDocumentLabels] = useState<{
    [key: string]: { zh?: string; en?: string };
  }>({});
  const [isLoadingLabels, setIsLoadingLabels] = useState(false);
  const [fieldLabels, setFieldLabels] = useState<{
    [key: string]: { zh?: string; en?: string };
  }>({});
  const [applicationFields, setApplicationFields] = useState<string[]>([]);
  const [isLoadingFields, setIsLoadingFields] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reviewComment, setReviewComment] = useState("");
  const [detailedApplication, setDetailedApplication] = useState<Application | null>(null);

  // Sub-type review state (for unified review system)
  const [subTypes, setSubTypes] = useState<any[]>([]);
  const [reviewItems, setReviewItems] = useState<Array<{
    sub_type_code: string;
    recommendation: 'approve' | 'reject' | 'pending';
    comments?: string;
  }>>([]);
  const [existingReview, setExistingReview] = useState<any>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingSubTypes, setIsLoadingSubTypes] = useState(false);

  const {
    studyingStatuses,
    degrees,
    departments,
    genders,
    academies,
    identities,
    schoolIdentities,
    enrollTypes,
  } = useReferenceData();

  // Admin management states
  const [professorInfo, setProfessorInfo] = useState<any>(null);
  const [bankVerificationLoading, setBankVerificationLoading] = useState(false);
  const [adminComments, setAdminComments] = useState("");
  const [isSubmittingStatus, setIsSubmittingStatus] = useState(false);

  // Get field label
  const getFieldLabel = (
    fieldName: string,
    locale: Locale,
    fieldLabels?: { [key: string]: { zh?: string; en?: string } }
  ) => {
    if (fieldLabels && fieldLabels[fieldName]) {
      return locale === "zh"
        ? fieldLabels[fieldName].zh
        : fieldLabels[fieldName].en || fieldLabels[fieldName].zh || fieldName;
    }
    return formatFieldName(fieldName, locale);
  };

  // Check if scholarship requires professor review
  const requiresProfessorReview =
    (detailedApplication as Application)?.scholarship_configuration?.requires_professor_recommendation ||
    false;

  // Check if user can assign professors
  const canAssignProfessor =
    user && ["admin", "super_admin", "college"].includes(user.role);

  // Check if user can verify bank accounts
  const canVerifyBank =
    user && ["admin", "super_admin", "college"].includes(user.role);

  // Handle professor assignment
  const handleProfessorAssigned = (professor: any) => {
    setProfessorInfo(professor);
  };

  // NOTE: Old admin approve/reject handlers removed - admin now uses unified sub-type review system

  // Handle bank verification
  const handleBankVerification = async () => {
    if (!detailedApplication) return;

    setBankVerificationLoading(true);
    try {
      const response = await api.bankVerification.verifyBankAccount(
        detailedApplication.id
      );
      if (response.success) {
        toast.success(
          locale === "zh" ? "郵局驗證成功" : "Post Office Verification Successful",
          {
            description: locale === "zh" ? "郵局帳戶驗證已完成" : "Post office account verification completed",
          }
        );
        // Refresh application data
        if (detailedApplication) {
          loadApplicationDetails(detailedApplication.id);
        }
      } else {
        toast.error(
          locale === "zh" ? "郵局驗證失敗" : "Post Office Verification Failed",
          {
            description: response.message || (locale === "zh" ? "無法完成郵局帳戶驗證" : "Could not complete post office account verification"),
          }
        );
      }
    } catch (error) {
      console.error("Post office verification error:", error);
      toast.error(
        locale === "zh" ? "郵局驗證錯誤" : "Post Office Verification Error",
        {
          description: locale === "zh" ? "郵局帳戶驗證過程中發生錯誤" : "An error occurred during post office account verification",
        }
      );
    } finally {
      setBankVerificationLoading(false);
    }
  };

  // Get post office verification status (支援新舊兩種資料格式)
  const getBankVerificationStatus = () => {
    if (!detailedApplication) return null;

    // 新版：檢查 bank_verification 物件中的分開狀態
    const bankVerification = (detailedApplication as Application).meta_data?.bank_verification;
    const accountNumberStatus = bankVerification?.account_number_status;
    const accountHolderStatus = bankVerification?.account_holder_status;

    // 如果有分開狀態，判斷整體驗證狀態
    if (accountNumberStatus || accountHolderStatus) {
      const allVerified = accountNumberStatus === "verified" && accountHolderStatus === "verified";
      const anyFailed = accountNumberStatus === "failed" || accountHolderStatus === "failed";
      const anyNeedsReview = accountNumberStatus === "needs_review" || accountHolderStatus === "needs_review";

      if (allVerified) {
        return {
          status: "verified",
          icon: <ShieldCheck className="h-5 w-5 text-green-600" />,
          label: locale === "zh" ? "已驗證" : "Verified",
          description:
            locale === "zh"
              ? "郵局帳戶已通過驗證"
              : "Post office account has been verified",
          variant: "default" as const,
        };
      } else if (anyFailed) {
        return {
          status: "failed",
          icon: <ShieldX className="h-5 w-5 text-red-600" />,
          label: locale === "zh" ? "驗證失敗" : "Verification Failed",
          description:
            locale === "zh"
              ? "郵局帳戶驗證失敗"
              : "Post office account verification failed",
          variant: "destructive" as const,
        };
      } else if (anyNeedsReview) {
        return {
          status: "needs_review",
          icon: <Shield className="h-5 w-5 text-yellow-600" />,
          label: locale === "zh" ? "需人工檢閱" : "Needs Review",
          description:
            locale === "zh"
              ? "郵局帳戶需要人工檢閱"
              : "Post office account needs manual review",
          variant: "secondary" as const,
        };
      } else {
        return {
          status: "pending",
          icon: <Shield className="h-5 w-5 text-yellow-600" />,
          label: locale === "zh" ? "待驗證" : "Pending",
          description:
            locale === "zh"
              ? "郵局帳戶待驗證"
              : "Post office account pending verification",
          variant: "secondary" as const,
        };
      }
    }

    // 舊版：向下相容舊的 bank_verification_status 欄位
    const bankVerified =
      (detailedApplication as Application).meta_data?.bank_verification_status === "verified";
    const bankVerificationFailed =
      (detailedApplication as Application).meta_data?.bank_verification_status === "failed";
    const bankVerificationPending =
      (detailedApplication as Application).meta_data?.bank_verification_status === "pending";

    if (bankVerified) {
      return {
        status: "verified",
        icon: <ShieldCheck className="h-5 w-5 text-green-600" />,
        label: locale === "zh" ? "已驗證" : "Verified",
        description:
          locale === "zh"
            ? "郵局帳戶已通過驗證"
            : "Post office account has been verified",
        variant: "default" as const,
      };
    } else if (bankVerificationFailed) {
      return {
        status: "failed",
        icon: <ShieldX className="h-5 w-5 text-red-600" />,
        label: locale === "zh" ? "驗證失敗" : "Verification Failed",
        description:
          locale === "zh"
            ? "郵局帳戶驗證失敗"
            : "Post office account verification failed",
        variant: "destructive" as const,
      };
    } else if (bankVerificationPending) {
      return {
        status: "pending",
        icon: <Shield className="h-5 w-5 text-yellow-600" />,
        label: locale === "zh" ? "驗證中" : "Verification Pending",
        description:
          locale === "zh"
            ? "郵局帳戶驗證進行中"
            : "Post office account verification in progress",
        variant: "secondary" as const,
      };
    } else {
      return {
        status: "not_verified",
        icon: <CreditCard className="h-5 w-5 text-gray-500" />,
        label: locale === "zh" ? "未驗證" : "Not Verified",
        description:
          locale === "zh"
            ? "郵局帳戶尚未驗證"
            : "Post office account not verified yet",
        variant: "outline" as const,
      };
    }
  };

  // Load application details
  const loadApplicationDetails = async (id: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.applications.getApplicationById(id);
      if (response.success && response.data) {
        setDetailedApplication(response.data as Application);
      } else {
        throw new Error(response.message || "Failed to load application details");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      toast.error(
        locale === "zh" ? "錯誤" : "Error",
        {
          description: err instanceof Error ? err.message : "Could not fetch application details",
        }
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Load sub-types and existing review for college and admin users
  const loadSubTypesAndReview = async (applicationId: number) => {
    setIsLoadingSubTypes(true);
    try {
      // Get available sub-types (route based on role)
      const subTypesResponse = (role === "admin" || role === "super_admin")
        ? await api.admin.getReviewableSubTypes(applicationId)
        : await api.college.getSubTypes(applicationId);
      if (subTypesResponse.success && subTypesResponse.data) {
        const availableSubTypes = subTypesResponse.data;
        setSubTypes(availableSubTypes);

        // Initialize items based on available sub-types
        const initialItems = availableSubTypes.map((subType: any) => ({
          sub_type_code: subType.value,
          recommendation: 'pending' as const,
          comments: "",
        }));

        // Try to get existing review (route based on role)
        try {
          const reviewResponse = (role === "admin" || role === "super_admin")
            ? await api.admin.getApplicationReview(applicationId)
            : await api.college.getReview(applicationId);
          if (reviewResponse.success && reviewResponse.data && reviewResponse.data.id > 0) {
            setExistingReview(reviewResponse.data);

            // Merge existing review items with all available sub-types
            const existingItems = reviewResponse.data.items || [];
            const mergedItems = availableSubTypes.map((subType: any) => {
              const existingItem = existingItems.find(
                (item: any) => item.sub_type_code === subType.value
              );

              if (existingItem) {
                // Ensure all fields are correctly mapped
                return {
                  sub_type_code: existingItem.sub_type_code,
                  recommendation: existingItem.recommendation as 'approve' | 'reject' | 'pending',
                  comments: existingItem.comments || "",
                };
              }

              return {
                sub_type_code: subType.value,
                recommendation: 'pending' as const,
                comments: "",
              };
            });

            // Debug logging
            console.log('📋 Loaded existing review:', {
              reviewId: reviewResponse.data.id,
              reviewedAt: reviewResponse.data.reviewed_at,
              existingItemsCount: existingItems.length,
              mergedItemsCount: mergedItems.length,
              mergedItems: mergedItems
            });

            setReviewItems(mergedItems);
          } else {
            // No existing review, use initial items
            setExistingReview(null);
            setReviewItems(initialItems);
          }
        } catch (e) {
          // No existing review, use initial items
          setExistingReview(null);
          setReviewItems(initialItems);
        }
      }
    } catch (err) {
      console.error("Error loading sub-types and review:", err);
    } finally {
      setIsLoadingSubTypes(false);
    }
  };

  // Load form configuration and files when dialog opens
  useEffect(() => {
    if (open && application) {
      loadApplicationDetails(application.id);
      // Reset review comment when opening a new application
      setReviewComment("");
      setAdminComments("");

      // Load sub-types and existing review for college, admin, and super_admin users
      if (["college", "admin", "super_admin"].includes(role)) {
        loadSubTypesAndReview(application.id);
      }
    } else {
      setDetailedApplication(null);
      // Clear form state when dialog closes
      setReviewComment("");
      setAdminComments("");
      setReviewItems([]);
      setSubTypes([]);
      setExistingReview(null);
      setIsLoadingSubTypes(false);
    }
  }, [open, application, role]);

  useEffect(() => {
    if (detailedApplication) {
      loadApplicationFiles();
      loadFormConfig();
    }
  }, [detailedApplication]);

  // Load form configuration (field and document labels)
  const loadFormConfig = async () => {
    if (!detailedApplication) return;

    setIsLoadingLabels(true);
    setIsLoadingFields(true);
    setError(null);

    try {
      // Get scholarship_type
      let scholarshipType = detailedApplication.scholarship_type;

      if (!scholarshipType && detailedApplication.scholarship_type_id) {
        try {
          const scholarshipResponse = await api.scholarships.getById(
            detailedApplication.scholarship_type_id
          );
          if (scholarshipResponse.success && scholarshipResponse.data) {
            scholarshipType = scholarshipResponse.data.code;
          }
        } catch (error) {
          console.error("Failed to get scholarship type:", error);
        }
      }

      if (!scholarshipType) {
        console.error("Cannot determine scholarship type");
        setDocumentLabels({});
        setFieldLabels({});
        setApplicationFields([]);
        setIsLoadingLabels(false);
        setIsLoadingFields(false);
        return;
      }

      const response = await api.applicationFields.getFormConfig(scholarshipType);
      if (response.success && response.data) {
        // Process document labels
        if (response.data.documents) {
          const labels: { [key: string]: { zh?: string; en?: string } } = {};
          response.data.documents.forEach((doc) => {
            labels[doc.document_name] = {
              zh: doc.document_name,
              en: doc.document_name_en || doc.document_name,
            };
          });
          setDocumentLabels(labels);
        }

        // Process field labels
        if (response.data.fields) {
          const fieldLabels: { [key: string]: { zh?: string; en?: string } } = {};
          const fieldNames: string[] = [];

          response.data.fields.forEach((field) => {
            fieldLabels[field.field_name] = {
              zh: field.field_label,
              en: field.field_label_en || field.field_label,
            };
            fieldNames.push(field.field_name);
          });

          setFieldLabels(fieldLabels);
          setApplicationFields(fieldNames);
        }
      }
    } catch (error) {
      console.error("Failed to load form config:", error);
      setDocumentLabels({});
      setFieldLabels({});
      setApplicationFields([]);
    } finally {
      setIsLoadingLabels(false);
      setIsLoadingFields(false);
    }
  };

  // Load application files
  const loadApplicationFiles = async () => {
    if (!detailedApplication) return;

    setIsLoadingFiles(true);
    try {
      const appData = detailedApplication;
      // Try to get files from submitted_form_data.documents
      if (appData.submitted_form_data?.documents) {
        const files = appData.submitted_form_data.documents.map((doc: any) => ({
          id: doc.file_id || doc.id,
          filename: doc.filename,
          original_filename: doc.original_filename,
          file_size: doc.file_size,
          mime_type: doc.mime_type,
          file_type: doc.document_type,
          file_path: doc.file_path,
          download_url: doc.download_url,
          is_verified: doc.is_verified,
          uploaded_at: doc.upload_time,
        }));
        setApplicationFiles(files);
      } else {
        // Fallback to old method
        const files = await fetchApplicationFiles(detailedApplication.id);
        setApplicationFiles(files);
      }
    } catch (error) {
      console.error("Failed to load application files:", error);
      setApplicationFiles([]);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  // Handle file preview
  const handleFilePreview = (file: any) => {
    const filename = file.filename || file.original_filename;

    if (!file.file_path) {
      console.error("No file path available for preview");
      return;
    }

    const urlParts = file.file_path.split("?");
    if (urlParts.length < 2) {
      console.error("Invalid file URL format");
      return;
    }

    const urlParams = new URLSearchParams(urlParts[1]);
    const token = urlParams.get("token");

    if (!token) {
      console.error("No token found in file URL");
      return;
    }

    const previewUrl = `/api/v1/preview?fileId=${file.id}&filename=${encodeURIComponent(filename)}&type=${encodeURIComponent(file.file_type)}&applicationId=${detailedApplication?.id}&token=${token}`;

    let fileType = "other";
    if (filename.toLowerCase().endsWith(".pdf")) {
      fileType = "application/pdf";
    } else if (
      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"].some((ext) =>
        filename.toLowerCase().endsWith(ext)
      )
    ) {
      fileType = "image";
    }

    const downloadUrl = file.download_url || file.file_path;

    setPreviewFile({
      url: previewUrl,
      filename: filename,
      type: fileType,
      downloadUrl: downloadUrl,
    });
    setIsPreviewDialogOpen(true);
  };

  // Update review item
  const updateReviewItem = (subTypeCode: string, field: string, value: any) => {
    setReviewItems(prev =>
      prev.map(item => {
        if (item.sub_type_code === subTypeCode) {
          return { ...item, [field]: value };
        }
        return item;
      })
    );
  };

  // Get sub-type label
  const getSubTypeLabel = (subTypeCode: string) => {
    const subType = subTypes.find((st: any) => st.value === subTypeCode);
    return subType?.label || subTypeCode;
  };

  // Helper function to safely convert error messages to strings
  const safeErrorMessage = (error: any): string => {
    if (typeof error === 'string') {
      return error;
    }
    if (error && typeof error === 'object') {
      // Handle Error objects
      if (error.message && typeof error.message === 'string') {
        return error.message;
      }
      // Handle arrays (e.g., validation errors)
      if (Array.isArray(error)) {
        return error.map(e => safeErrorMessage(e)).join(', ');
      }
      // Handle objects with detail field
      if (error.detail) {
        return safeErrorMessage(error.detail);
      }
      // Fallback: stringify the object
      try {
        return JSON.stringify(error);
      } catch {
        return String(error);
      }
    }
    return String(error || 'Unknown error');
  };

  // Submit review using unified format (multi-role: college or admin)
  const submitReview = async () => {
    if (!detailedApplication || !reviewItems.length) return;

    setIsSubmitting(true);
    setError(null);

    try {
      // Filter out pending items - only send approve/reject items to API
      const filteredItems = reviewItems
        .filter(item => item.recommendation === 'approve' || item.recommendation === 'reject')
        .map(item => ({
          sub_type_code: item.sub_type_code,
          recommendation: item.recommendation as 'approve' | 'reject',
          comments: item.comments || "",
        }));

      if (filteredItems.length === 0) {
        toast.error(
          locale === "zh" ? "錯誤" : "Error",
          {
            description: locale === "zh"
              ? "請至少對一個子項目做出審核決定"
              : "Please make a decision for at least one sub-type",
          }
        );
        setIsSubmitting(false);
        return;
      }

      // Validate that all rejected items have comments
      const rejectedWithoutComments = filteredItems.filter(
        item => item.recommendation === 'reject' && (!item.comments || item.comments.trim() === '')
      );

      if (rejectedWithoutComments.length > 0) {
        const itemNames = rejectedWithoutComments
          .map(item => getSubTypeLabel(item.sub_type_code))
          .join('、');
        toast.error(
          locale === "zh" ? "錯誤" : "Error",
          {
            description: locale === "zh"
              ? `以下項目選擇拒絕但未填寫理由：${itemNames}`
              : `The following items are rejected without reason: ${itemNames}`,
          }
        );
        setIsSubmitting(false);
        return;
      }

      const submissionData = {
        items: filteredItems,
      };

      // Route submission based on role
      const response = (role === "admin" || role === "super_admin")
        ? await api.admin.submitApplicationReview(detailedApplication.id, submissionData)
        : await api.college.submitReview(detailedApplication.id, submissionData);

      if (response.success) {
        toast.success(
          locale === "zh" ? "成功" : "Success",
          {
            description: locale === "zh" ? "審核意見已成功提交" : "Review submitted successfully",
          }
        );

        // Call the callback to refresh data in parent component
        if (onReviewSubmitted) {
          onReviewSubmitted();
        }

        // Close dialog
        onOpenChange(false);
      } else {
        throw new Error(safeErrorMessage(response.message) || "Failed to submit review");
      }
    } catch (err: any) {
      console.error("Failed to submit review:", err);

      // Extract detailed error message from various possible locations
      let errorMessage = "Failed to submit review";

      // Check for API response error details (FastAPI HTTPException)
      if (err?.response?.data?.detail) {
        errorMessage = typeof err.response.data.detail === 'string'
          ? err.response.data.detail
          : JSON.stringify(err.response.data.detail);
      }
      // Check for API response message (our ApiResponse format)
      else if (err?.response?.data?.message) {
        errorMessage = safeErrorMessage(err.response.data.message);
      }
      // Check for standard Error message
      else if (err?.message) {
        errorMessage = safeErrorMessage(err.message);
      }
      // Fallback to generic error extraction
      else {
        errorMessage = safeErrorMessage(err);
      }

      toast.error(
        locale === "zh" ? "錯誤" : "Error",
        {
          description: errorMessage,
        }
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  // Legacy handlers for backward compatibility (not used with new review system)
  const handleApprove = async () => {
    if (detailedApplication && onApprove && !isSubmitting) {
      try {
        setIsSubmitting(true);
        await onApprove(detailedApplication.id, reviewComment);
        // Close dialog after successful approval
        onOpenChange(false);
      } catch (error) {
        console.error('Failed to approve application:', error);
        // Error handling is done in the parent component (toast notification)
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  const handleReject = async () => {
    if (detailedApplication && onReject && !isSubmitting) {
      try {
        setIsSubmitting(true);
        await onReject(detailedApplication.id, reviewComment);
        // Close dialog after successful rejection
        onOpenChange(false);
      } catch (error) {
        console.error('Failed to reject application:', error);
        // Error handling is done in the parent component (toast notification)
      } finally {
        setIsSubmitting(false);
      }
    }
  };

  // Handle request documents
  const handleRequestDocs = () => {
    if (detailedApplication && onRequestDocs) {
      onRequestDocs(detailedApplication as Application);
    }
  };

  // Handle delete
  const handleDelete = () => {
    if (detailedApplication && onDelete) {
      onDelete(detailedApplication as Application);
    }
  };

  if (!application) return null;

  // Helper function to format date with time
  const formatDateTime = (dateString: string | undefined | null) => {
    if (!dateString) return null;
    try {
      return new Date(dateString).toLocaleString(
        locale === "zh" ? "zh-TW" : "en-US",
        {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          hour12: false,
        }
      );
    } catch {
      return null;
    }
  };

  // Normalize application data for display
  const displayData = {
    id: detailedApplication?.id ?? application.id,
    app_id: detailedApplication?.app_id ?? application.app_id,
    student_id: detailedApplication?.student_id ?? (application as Application).student_id ?? (application as HistoricalApplication).student_id ?? "",
    student_name: detailedApplication?.student_name ?? (application as Application).student_name ?? (application as HistoricalApplication).student_name ?? "",
    scholarship_type: detailedApplication?.scholarship_type ?? (application as Application).scholarship_type ?? (application as HistoricalApplication).scholarship_type_code ?? "",
    scholarship_name: detailedApplication?.scholarship_name ?? (application as Application).scholarship_name ?? (application as HistoricalApplication).scholarship_name ?? "",
    scholarship_type_zh: detailedApplication?.scholarship_type_zh ?? (application as Application).scholarship_type_zh,
    status: detailedApplication?.status ?? application.status,
    status_name: (detailedApplication as HistoricalApplication)?.status_name ?? (application as HistoricalApplication).status_name,
    academic_year: detailedApplication?.academic_year ?? (application as Application).academic_year,
    semester: detailedApplication?.semester ?? (application as Application).semester,
    amount: detailedApplication?.amount ?? (application as Application).amount,
    currency: (detailedApplication as any)?.currency ?? "TWD",
    is_renewal: detailedApplication?.is_renewal ?? (application as Application).is_renewal ?? false,
    created_at: detailedApplication?.created_at ?? application.created_at,
    submitted_at: detailedApplication?.submitted_at ?? (application as Application).submitted_at ?? (application as HistoricalApplication).submitted_at,
    reviewed_at: detailedApplication?.reviewed_at ?? (application as Application).reviewed_at,
    approved_at: detailedApplication?.approved_at ?? (application as Application).approved_at,
    gpa: detailedApplication?.gpa ?? (application as Application).gpa,
    class_ranking_percent: detailedApplication?.class_ranking_percent ?? (application as Application).class_ranking_percent,
    dept_ranking_percent: detailedApplication?.dept_ranking_percent ?? (application as Application).dept_ranking_percent,
    student_termcount: detailedApplication?.student_data?.std_termcount ?? (application as Application).student_data?.std_termcount,
    academy_name: (detailedApplication as any)?.academy_name ?? (application as Application).academy_code,
    academy_code: detailedApplication?.academy_code ?? (application as Application).academy_code,
    department: getDepartmentName(detailedApplication?.student_data?.std_depno, departments) ?? detailedApplication?.student_data?.std_depno,
    department_name: (detailedApplication as any)?.department_name ?? getDepartmentName(detailedApplication?.student_data?.std_depno, departments) ?? (application as Application).department,
    department_code: detailedApplication?.department_code ?? (application as Application).department_code,
    degree: (detailedApplication as any)?.degree,
    degree_name: (detailedApplication as any)?.degree ? getDegreeName((detailedApplication as any).degree, degrees) : undefined,
    professor_review_items: (detailedApplication as any)?.professor_review_items ?? [],
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {role === "college"
                ? locale === "zh"
                  ? "學院審核"
                  : "College Review"
                : locale === "zh"
                  ? "申請詳情"
                  : "Application Details"}{" "}
              - {displayData.app_id || `APP-${displayData.id}`}
            </DialogTitle>
            <DialogDescription>
              {displayData.student_name} ({displayData.student_id}) -{" "}
              {displayData.scholarship_name || displayData.scholarship_type}
            </DialogDescription>
          </DialogHeader>

          {isLoading ? (
            <div className="flex items-center justify-center flex-1">
              <Loader2 className="h-8 w-8 animate-spin text-nycu-blue-500" />
            </div>
          ) : error ? (
            <div className="flex items-center justify-center flex-1">
              <Alert variant="destructive" className="w-auto">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            </div>
          ) : detailedApplication ? (
            <Tabs defaultValue="basic" className="flex-1 overflow-hidden flex flex-col">
              <TabsList className={role === "college" ? "grid w-full grid-cols-6" : "grid w-full grid-cols-7"}>
                <TabsTrigger value="basic">
                  <Info className="h-4 w-4 mr-1" />
                  {locale === "zh" ? "基本資訊" : "Basic"}
                </TabsTrigger>
                <TabsTrigger value="form">
                  <ClipboardList className="h-4 w-4 mr-1" />
                  {locale === "zh" ? "表單內容" : "Form"}
                </TabsTrigger>
                <TabsTrigger value="documents">
                  <Upload className="h-4 w-4 mr-1" />
                  {locale === "zh" ? "上傳文件" : "Documents"}
                </TabsTrigger>
                <TabsTrigger value="student">
                  <GraduationCap className="h-4 w-4 mr-1" />
                  {locale === "zh" ? "學生資訊" : "Student"}
                </TabsTrigger>
                {["college", "admin", "super_admin"].includes(role) && (
                  <TabsTrigger value="review">
                    <CheckCircle className="h-4 w-4 mr-1" />
                    {locale === "zh" ? "審核操作" : "Review"}
                  </TabsTrigger>
                )}
                {["admin", "super_admin"].includes(role) && (
                  <TabsTrigger value="management">
                    <Settings className="h-4 w-4 mr-1" />
                    {locale === "zh" ? "管理" : "Management"}
                  </TabsTrigger>
                )}
                <TabsTrigger value="audit">
                  <History className="h-4 w-4 mr-1" />
                  {locale === "zh" ? "操作紀錄" : "Audit"}
                </TabsTrigger>
              </TabsList>

              <div className="flex-1 overflow-y-auto">
                {/* Basic Information Tab */}
                <TabsContent value="basic" className="space-y-4 mt-4">
                  {/* Application Information Section */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "申請資訊" : "Application Information"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "申請編號" : "Application ID"}
                          </Label>
                          <p className="text-sm font-mono">{displayData.app_id || `APP-${displayData.id}`}</p>
                        </div>
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "申請狀態" : "Status"}
                          </Label>
                          <div className="flex items-center gap-2">
                            <Badge variant={getApplicationStatusBadgeVariant(displayData.status as ApplicationStatus)}>
                              {displayData.status_name || getApplicationStatusLabel(displayData.status as ApplicationStatus, locale)}
                            </Badge>
                            {displayData.is_renewal && (
                              <Badge variant="outline" className="text-blue-600 border-blue-300">
                                {locale === "zh" ? "續領" : "Renewal"}
                              </Badge>
                            )}
                          </div>
                        </div>
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "學年度" : "Academic Year"}
                          </Label>
                          <p className="text-sm">{displayData.academic_year || "-"}</p>
                        </div>
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "學期" : "Semester"}
                          </Label>
                          <p className="text-sm">
                            {displayData.semester === "first"
                              ? (locale === "zh" ? "上學期" : "First")
                              : displayData.semester === "second"
                              ? (locale === "zh" ? "下學期" : "Second")
                              : displayData.semester === "yearly"
                              ? (locale === "zh" ? "全年" : "Yearly")
                              : displayData.semester || "-"}
                          </p>
                        </div>
                        <div className="col-span-2">
                          <Label className="font-medium">
                            {locale === "zh" ? "獎學金名稱" : "Scholarship Name"}
                          </Label>
                          <p className="text-sm">
                            {displayData.scholarship_name || displayData.scholarship_type_zh || displayData.scholarship_type}
                          </p>
                        </div>
                        {displayData.amount && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "獎學金金額" : "Amount"}
                            </Label>
                            <p className="text-sm font-medium text-green-600">
                              {displayData.currency} {displayData.amount?.toLocaleString()}
                            </p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Student Information Section */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "學生資訊" : "Student Information"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "姓名" : "Name"}
                          </Label>
                          <p className="text-sm">{displayData.student_name || "N/A"}</p>
                        </div>
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "學號" : "Student ID"}
                          </Label>
                          <p className="text-sm font-mono">{displayData.student_id || "N/A"}</p>
                        </div>
                        {displayData.academy_name && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "學院" : "Academy"}
                            </Label>
                            <p className="text-sm">{displayData.academy_name}</p>
                          </div>
                        )}
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "系所" : "Department"}
                          </Label>
                          <p className="text-sm">{displayData.department_name || displayData.department || "-"}</p>
                        </div>
                        {displayData.degree_name && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "學位" : "Degree"}
                            </Label>
                            <p className="text-sm">{displayData.degree_name}</p>
                          </div>
                        )}
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "就讀學期數" : "Terms Enrolled"}
                          </Label>
                          <p className="text-sm">{displayData.student_termcount || "-"}</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>

                  {/* Status & Timeline Section */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "狀態與時間" : "Status & Timeline"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "建立時間" : "Created At"}
                          </Label>
                          <p className="text-sm">
                            {formatDateTime(displayData.created_at) || "-"}
                          </p>
                        </div>
                        {displayData.submitted_at && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "提交時間" : "Submitted At"}
                            </Label>
                            <p className="text-sm">
                              {formatDateTime(displayData.submitted_at) || "-"}
                            </p>
                          </div>
                        )}
                        {displayData.reviewed_at && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "審核時間" : "Reviewed At"}
                            </Label>
                            <p className="text-sm">
                              {formatDateTime(displayData.reviewed_at) || "-"}
                            </p>
                          </div>
                        )}
                        {displayData.approved_at && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "核准時間" : "Approved At"}
                            </Label>
                            <p className="text-sm">
                              {formatDateTime(displayData.approved_at) || "-"}
                            </p>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Professor Review Results (college/admin only) */}
                  {["college", "admin", "super_admin"].includes(role) &&
                    displayData.professor_review_items?.length > 0 && (
                      <Card>
                        <CardHeader>
                          <CardTitle className="text-lg">
                            {locale === "zh" ? "教授審查結果" : "Professor Review"}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-2">
                            {displayData.professor_review_items.map(
                              (item: any, idx: number) => (
                                <div
                                  key={`${item.sub_type_code}-${idx}`}
                                  className={`p-3 rounded border ${
                                    item.recommendation === "approve"
                                      ? "border-emerald-200 bg-emerald-50"
                                      : "border-red-200 bg-red-50"
                                  }`}
                                >
                                  <div className="flex items-center gap-2">
                                    <Badge
                                      variant={
                                        item.recommendation === "approve"
                                          ? "outline"
                                          : "destructive"
                                      }
                                      className={
                                        item.recommendation === "approve"
                                          ? "border-emerald-500 text-emerald-700 bg-white"
                                          : ""
                                      }
                                    >
                                      {getSubTypeLabel(item.sub_type_code)}
                                      :{" "}
                                      {item.recommendation === "approve"
                                        ? locale === "zh"
                                          ? "推薦"
                                          : "Approve"
                                        : locale === "zh"
                                        ? "不推薦"
                                        : "Reject"}
                                    </Badge>
                                  </div>
                                  {item.comments && (
                                    <div className="mt-2">
                                      <Label className="text-xs font-medium">
                                        {item.recommendation === "reject"
                                          ? locale === "zh"
                                            ? "不同意理由"
                                            : "Reason for Reject"
                                          : locale === "zh"
                                          ? "備註"
                                          : "Comments"}
                                      </Label>
                                      <p className="text-sm mt-1 whitespace-pre-wrap">
                                        {item.comments}
                                      </p>
                                    </div>
                                  )}
                                </div>
                              )
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    )}

                  {/* Progress Timeline */}
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "審核進度" : "Review Progress"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ProgressTimeline steps={getApplicationTimeline(detailedApplication, locale)} />
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Form Content Tab */}
                <TabsContent value="form" className="space-y-4 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "申請表單內容" : "Application Form Content"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {error ? (
                        <Alert variant="destructive">
                          <AlertDescription>
                            {locale === "zh" ? "載入失敗" : "Loading failed"}: {error}
                          </AlertDescription>
                        </Alert>
                      ) : isLoadingFields ? (
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span className="text-sm text-muted-foreground">
                            {locale === "zh" ? "載入表單資料中..." : "Loading form data..."}
                          </span>
                        </div>
                      ) : (
                        <>
                          {/* Debug logging for form data */}
                          {(() => {
                            console.log(
                              "🔍 Form Tab - detailedApplication:",
                              detailedApplication
                            );
                            console.log(
                              "🔍 Form Tab - submitted_form_data:",
                              detailedApplication?.submitted_form_data
                            );
                            console.log(
                              "🔍 Form Tab - fields:",
                              detailedApplication?.submitted_form_data?.fields
                            );
                            return null;
                          })()}

                          <ApplicationFormDataDisplay
                            formData={detailedApplication}
                            locale={locale}
                            fieldLabels={fieldLabels}
                          />
                        </>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Documents Tab */}
                <TabsContent value="documents" className="space-y-4 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "已上傳文件" : "Uploaded Files"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {isLoadingFiles ? (
                        <div className="flex items-center gap-2">
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span className="text-sm text-muted-foreground">
                            {locale === "zh" ? "載入文件中..." : "Loading files..."}
                          </span>
                        </div>
                      ) : applicationFiles.length > 0 ? (
                        <div className="space-y-2">
                          {applicationFiles.map((file: any, index: number) => (
                            <div
                              key={file.id || index}
                              className="flex items-center justify-between p-3 bg-muted/50 rounded-md border"
                            >
                              <div className="flex items-center gap-3">
                                <FileText className="h-5 w-5 text-muted-foreground" />
                                <div>
                                  <p className="text-sm font-medium">
                                    {file.filename || file.original_filename}
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {file.file_type
                                      ? getDocumentLabel(
                                          file.file_type,
                                          locale,
                                          documentLabels[file.file_type]
                                        )
                                      : "Other"}
                                    {file.file_size ? ` • ${Math.round(file.file_size / 1024)}KB` : ""}
                                  </p>
                                </div>
                              </div>
                              {file.file_path && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleFilePreview(file)}
                                >
                                  <Eye className="h-4 w-4 mr-1" />
                                  {locale === "zh" ? "預覽" : "Preview"}
                                </Button>
                              )}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8">
                          <FileText className="h-12 w-12 mx-auto mb-2 text-muted-foreground" />
                          <p className="text-sm text-muted-foreground">
                            {locale === "zh" ? "尚未上傳任何文件" : "No files uploaded yet"}
                          </p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Student Information Tab */}
                <TabsContent value="student" className="space-y-4 mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "學生資訊" : "Student Information"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <StudentPreviewDisplay
                        studentId={displayData.student_id}
                        academicYear={academicYear}
                        locale={locale}
                        studyingStatuses={studyingStatuses}
                        degrees={degrees}
                        departments={departments}
                        genders={genders}
                        academies={academies}
                        identities={identities}
                        schoolIdentities={schoolIdentities}
                        enrollTypes={enrollTypes}
                      />
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* Review Actions Tab (College, Admin, Super Admin) */}
                {["college", "admin", "super_admin"].includes(role) && (
                  <TabsContent value="review" className="space-y-6 mt-4">
                    {existingReview && (
                      <Alert className="border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950/20">
                        <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                        <AlertDescription className="text-blue-800 dark:text-blue-300">
                          {locale === "zh"
                            ? `您已於 ${new Date(existingReview.reviewed_at).toLocaleString('zh-TW', {
                                year: 'numeric',
                                month: '2-digit',
                                day: '2-digit',
                                hour: '2-digit',
                                minute: '2-digit',
                                hour12: false
                              })} 提交過審核意見，以下為之前的審核內容`
                            : `You submitted a review on ${new Date(existingReview.reviewed_at).toLocaleString('en-US', {
                                year: 'numeric',
                                month: '2-digit',
                                day: '2-digit',
                                hour: '2-digit',
                                minute: '2-digit',
                                hour12: false
                              })}`}
                        </AlertDescription>
                      </Alert>
                    )}
                    {subTypes.length > 0 && reviewItems.length > 0 ? (
                      <Card>
                        <CardHeader className="space-y-1.5">
                          <CardTitle className="text-xl">
                            {locale === "zh" ? "子項目審核" : "Sub-type Reviews"}
                          </CardTitle>
                          <p className="text-sm text-muted-foreground">
                            {locale === "zh"
                              ? "請針對每個獎學金子項目進行審核並提供意見"
                              : "Please review each scholarship sub-type and provide your feedback"}
                          </p>
                        </CardHeader>
                        <CardContent className="space-y-6">
                          {/* Review Items */}
                          <div className="space-y-6">
                            {reviewItems.map((item, index) => (
                              <div
                                key={item.sub_type_code}
                                className={`
                                  rounded-lg border-2 transition-colors
                                  ${item.recommendation === 'approve' ? 'border-green-200 bg-green-50/50 dark:border-green-800 dark:bg-green-950/20' :
                                    item.recommendation === 'reject' ? 'border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20' :
                                    'border-border bg-card'}
                                `}
                              >
                                <div className="p-4 space-y-4">
                                  {/* Header with title and status badge */}
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="flex-1">
                                      <h4 className="font-semibold text-base leading-tight">
                                        {getSubTypeLabel(item.sub_type_code)}
                                      </h4>
                                      <p className="text-xs text-muted-foreground mt-1">
                                        {locale === "zh" ? `項目 ${index + 1} / ${reviewItems.length}` : `Item ${index + 1} / ${reviewItems.length}`}
                                      </p>
                                    </div>
                                    <Badge
                                      variant={
                                        item.recommendation === 'approve' ? 'default' :
                                        item.recommendation === 'reject' ? 'destructive' :
                                        'secondary'
                                      }
                                      className="shrink-0"
                                    >
                                      {item.recommendation === 'approve' ? (
                                        <>
                                          <CheckCircle className="h-3 w-3 mr-1" />
                                          {locale === "zh" ? "同意" : "Approved"}
                                        </>
                                      ) : item.recommendation === 'reject' ? (
                                        <>
                                          <XCircle className="h-3 w-3 mr-1" />
                                          {locale === "zh" ? "拒絕" : "Rejected"}
                                        </>
                                      ) : (
                                        locale === "zh" ? "待決定" : "Pending"
                                      )}
                                    </Badge>
                                  </div>

                                  {/* Action buttons */}
                                  <div className="flex gap-2">
                                    <Button
                                      size="default"
                                      variant="outline"
                                      onClick={() => updateReviewItem(item.sub_type_code, 'recommendation', 'approve')}
                                      className={`flex-1 h-11 transition-colors ${
                                        item.recommendation === 'approve'
                                          ? 'bg-green-600 hover:bg-green-700 text-white border-green-600'
                                          : item.recommendation === 'pending'
                                          ? 'bg-green-50 hover:bg-green-100 text-green-700 border-green-300 dark:bg-green-950/20 dark:text-green-400 dark:border-green-800 dark:hover:bg-green-950/30'
                                          : 'hover:bg-accent'
                                      }`}
                                    >
                                      <CheckCircle className="h-4 w-4 mr-2" />
                                      {locale === "zh" ? "同意" : "Approve"}
                                    </Button>
                                    <Button
                                      size="default"
                                      variant="outline"
                                      onClick={() => updateReviewItem(item.sub_type_code, 'recommendation', 'reject')}
                                      className={`flex-1 h-11 transition-colors ${
                                        item.recommendation === 'reject'
                                          ? 'bg-red-600 hover:bg-red-700 text-white border-red-600'
                                          : item.recommendation === 'pending'
                                          ? 'bg-red-50 hover:bg-red-100 text-red-700 border-red-300 dark:bg-red-950/20 dark:text-red-400 dark:border-red-800 dark:hover:bg-red-950/30'
                                          : 'hover:bg-accent'
                                      }`}
                                    >
                                      <XCircle className="h-4 w-4 mr-2" />
                                      {locale === "zh" ? "拒絕" : "Reject"}
                                    </Button>
                                  </div>

                                  {/* Comments field */}
                                  <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                                      {locale === "zh" ? "審核意見" : "Review Comments"}
                                      {item.recommendation === 'reject' ? (
                                        <span className="text-red-600 font-medium ml-1">
                                          * ({locale === "zh" ? "必填" : "Required"})
                                        </span>
                                      ) : (
                                        <span className="text-muted-foreground font-normal ml-1">
                                          ({locale === "zh" ? "選填" : "Optional"})
                                        </span>
                                      )}
                                    </label>
                                    <Textarea
                                      placeholder={
                                        item.recommendation === 'reject'
                                          ? (locale === "zh" ? "拒絕時必須填寫理由..." : "Reason required for rejection...")
                                          : (locale === "zh" ? "請填寫審核意見或建議..." : "Enter your review comments or suggestions...")
                                      }
                                      value={item.comments || ""}
                                      onChange={(e) => updateReviewItem(item.sub_type_code, 'comments', e.target.value)}
                                      className={`min-h-[100px] resize-none ${
                                        item.recommendation === 'reject' && (!item.comments || item.comments.trim() === '')
                                          ? 'border-red-500 focus-visible:ring-red-500'
                                          : ''
                                      }`}
                                    />
                                    {item.recommendation === 'reject' && (!item.comments || item.comments.trim() === '') && (
                                      <p className="text-sm text-red-600 mt-1">
                                        {locale === "zh" ? "拒絕時必須填寫理由" : "Reason is required for rejection"}
                                      </p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>

                          {/* Submit section with summary */}
                          <div className="pt-4 border-t space-y-4">
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-muted-foreground">
                                {locale === "zh" ? "審核進度" : "Review Progress"}
                              </span>
                              <span className="font-medium">
                                {reviewItems.filter(item => item.recommendation !== 'pending').length} / {reviewItems.length}
                              </span>
                            </div>

                            {reviewItems.filter(item => item.recommendation !== 'pending').length === 0 && (
                              <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-500 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md p-3">
                                <AlertCircle className="h-4 w-4 shrink-0" />
                                <span>
                                  {locale === "zh"
                                    ? "請至少對一個子項目做出審核決定"
                                    : "Please make a decision for at least one sub-type"}
                                </span>
                              </div>
                            )}

                            {reviewItems.some(item =>
                              item.recommendation === 'reject' && (!item.comments || item.comments.trim() === '')
                            ) && (
                              <div className="flex items-center gap-2 text-sm text-red-600 dark:text-red-500 bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-md p-3">
                                <AlertCircle className="h-4 w-4 shrink-0" />
                                <span>
                                  {locale === "zh"
                                    ? "有拒絕項目尚未填寫理由"
                                    : "Some rejected items are missing reasons"}
                                </span>
                              </div>
                            )}

                            <Button
                              onClick={submitReview}
                              className="w-full h-11"
                              disabled={
                                isSubmitting ||
                                reviewItems.filter(item => item.recommendation !== 'pending').length === 0 ||
                                reviewItems.some(item => item.recommendation === 'reject' && (!item.comments || item.comments.trim() === ''))
                              }
                              size="lg"
                            >
                              {isSubmitting ? (
                                <>
                                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                  {locale === "zh" ? "提交中..." : "Submitting..."}
                                </>
                              ) : (
                                <>
                                  <Send className="h-4 w-4 mr-2" />
                                  {locale === "zh" ? "提交審核意見" : "Submit Review"}
                                </>
                              )}
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ) : isLoadingSubTypes ? (
                      <Card>
                        <CardContent className="py-12 text-center">
                          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-muted-foreground" />
                          <p className="text-muted-foreground">
                            {locale === "zh" ? "載入審核表單中..." : "Loading review form..."}
                          </p>
                        </CardContent>
                      </Card>
                    ) : (
                      <Card>
                        <CardContent className="py-12 text-center">
                          <p className="text-muted-foreground">
                            {locale === "zh"
                              ? "此申請無可審核的子類型"
                              : "No reviewable sub-types for this application"}
                          </p>
                        </CardContent>
                      </Card>
                    )}
                  </TabsContent>
                )}

                {/* Management Tab (Admin and Super Admin) */}
                {["admin", "super_admin"].includes(role) && (
                  <TabsContent value="management" className="space-y-4 mt-4">
                    {/* Post Office Verification Section */}
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                          <CreditCard className="h-5 w-5" />
                          {locale === "zh"
                            ? "郵局帳戶驗證"
                            : "Post Office Account Verification"}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-4">
                          {(() => {
                            const bankStatus = getBankVerificationStatus();
                            if (!bankStatus) return null;

                            return (
                              <>
                                <div className="flex items-center justify-between">
                                  <div className="flex items-center gap-3">
                                    {bankStatus.icon}
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <span className="font-medium">
                                          {bankStatus.label}
                                        </span>
                                        <Badge variant={bankStatus.variant}>
                                          {bankStatus.label}
                                        </Badge>
                                      </div>
                                      <p className="text-sm text-muted-foreground mt-1">
                                        {bankStatus.description}
                                      </p>
                                    </div>
                                  </div>
                                  {canVerifyBank &&
                                    bankStatus.status === "not_verified" && (
                                      <Button
                                        onClick={handleBankVerification}
                                        disabled={bankVerificationLoading}
                                        size="sm"
                                      >
                                        {bankVerificationLoading ? (
                                          <>
                                            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                            {locale === "zh"
                                              ? "驗證中..."
                                              : "Verifying..."}
                                          </>
                                        ) : (
                                          <>
                                            <Shield className="h-4 w-4 mr-2" />
                                            {locale === "zh"
                                              ? "開始驗證"
                                              : "Start Verification"}
                                          </>
                                        )}
                                      </Button>
                                    )}
                                </div>

                                {/* Bank verification details */}
                                {(detailedApplication as Application).meta_data?.bank_verification_details && (
                                  <div className="p-3 bg-muted rounded-lg">
                                    <h4 className="text-sm font-medium mb-2">
                                      {locale === "zh"
                                        ? "驗證詳情"
                                        : "Verification Details"}
                                    </h4>
                                    <div className="text-sm text-muted-foreground space-y-1">
                                      {(detailedApplication as Application).meta_data?.bank_verification_details
                                        ?.verified_at && (
                                        <p>
                                          {locale === "zh"
                                            ? "驗證時間: "
                                            : "Verified at: "}
                                          {new Date(
                                            (detailedApplication as Application).meta_data?.bank_verification_details.verified_at
                                          ).toLocaleString()}
                                        </p>
                                      )}
                                      {(detailedApplication as Application).meta_data?.bank_verification_details
                                        .account_holder && (
                                        <p>
                                          {locale === "zh"
                                            ? "帳戶持有人: "
                                            : "Account holder: "}
                                          {
                                            (detailedApplication as Application).meta_data
                                              ?.bank_verification_details.account_holder
                                          }
                                        </p>
                                      )}
                                      {(detailedApplication as Application).meta_data?.bank_verification_details
                                        ?.confidence_score !== null &&
                                        (detailedApplication as Application).meta_data?.bank_verification_details
                                          ?.confidence_score !== undefined && (
                                        <p>
                                          {locale === "zh"
                                            ? "信心分數: "
                                            : "Confidence score: "}
                                          {(
                                            ((detailedApplication as Application).meta_data
                                              ?.bank_verification_details
                                              ?.confidence_score ?? 0) * 100
                                          ).toFixed(1)}
                                          %
                                        </p>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {/* Show error message if verification failed */}
                                {bankStatus.status === "failed" &&
                                  (detailedApplication as Application).meta_data?.bank_verification_error && (
                                    <Alert variant="destructive">
                                      <AlertCircle className="h-4 w-4" />
                                      <AlertDescription>
                                        {locale === "zh"
                                          ? "驗證失敗原因: "
                                          : "Verification failed: "}
                                        {(detailedApplication as Application).meta_data?.bank_verification_error}
                                      </AlertDescription>
                                    </Alert>
                                  )}
                              </>
                            );
                          })()}
                        </div>
                      </CardContent>
                    </Card>

                    {/* Professor Review Section - Only show if scholarship requires professor review */}
                    {requiresProfessorReview && (
                      <Card>
                        <CardHeader>
                          <CardTitle className="text-lg">
                            {locale === "zh" ? "教授審查" : "Professor Review"}
                          </CardTitle>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-4">
                            {/* Current Professor Info */}
                            {((detailedApplication as Application).professor_id || professorInfo) && (
                              <div>
                                <Label className="text-sm font-medium">
                                  {locale === "zh"
                                    ? "目前指派教授"
                                    : "Current Assigned Professor"}
                                </Label>
                                <div className="flex items-center gap-2 mt-2">
                                  <UserIcon className="h-4 w-4" />
                                  <Badge variant="secondary">
                                    {professorInfo?.name ||
                                      (detailedApplication as Application).professor?.name ||
                                      (detailedApplication as Application).professor_id}
                                  </Badge>
                                  {(professorInfo?.nycu_id ||
                                    (detailedApplication as Application).professor?.nycu_id) && (
                                    <span className="text-sm text-muted-foreground">
                                      (
                                      {professorInfo?.nycu_id ||
                                        (detailedApplication as Application).professor?.nycu_id}
                                      )
                                    </span>
                                  )}
                                </div>
                                {(professorInfo?.dept_name ||
                                  (detailedApplication as Application).professor?.dept_name) && (
                                  <p className="text-sm text-muted-foreground mt-1">
                                    {professorInfo?.dept_name ||
                                      (detailedApplication as Application).professor?.dept_name}
                                  </p>
                                )}
                              </div>
                            )}

                            {/* Professor Assignment Dropdown - Only for admins */}
                            {canAssignProfessor && (
                              <div>
                                <Label className="text-sm font-medium">
                                  {locale === "zh"
                                    ? "指派/變更教授"
                                    : "Assign/Change Professor"}
                                </Label>
                                <div className="mt-2">
                                  <ProfessorAssignmentDropdown
                                    applicationId={detailedApplication.id}
                                    currentProfessorId={
                                      (detailedApplication as Application).professor?.nycu_id ||
                                      professorInfo?.nycu_id
                                    }
                                    onAssigned={handleProfessorAssigned}
                                  />
                                </div>
                              </div>
                            )}

                            {/* No Professor Assigned */}
                            {!(detailedApplication as Application).professor_id && !professorInfo && (
                              <div className="flex items-center gap-2 p-3 bg-orange-50 border border-orange-200 rounded-md">
                                <AlertCircle className="h-4 w-4 text-orange-600" />
                                <span className="text-sm text-orange-700">
                                  {locale === "zh"
                                    ? "尚未指派教授"
                                    : "Professor not assigned yet"}
                                </span>
                              </div>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    )}

                    {/* NOTE: Old admin review UI removed - admin now uses unified sub-type review system (same as college) */}
                  </TabsContent>
                )}

                {/* Audit Trail Tab */}
                <TabsContent value="audit" className="mt-4">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "操作紀錄" : "Audit Trail"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ApplicationAuditTrail applicationId={displayData.id} locale={locale} />
                    </CardContent>
                  </Card>
                </TabsContent>
              </div>
            </Tabs>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* File Preview Dialog */}
      <FilePreviewDialog
        isOpen={isPreviewDialogOpen}
        onClose={() => setIsPreviewDialogOpen(false)}
        file={previewFile}
        locale={locale}
      />
    </>
  );
}
