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
  getApplicationTimeline,
  getStatusColor,
  getStatusName,
  getDocumentLabel,
  fetchApplicationFiles,
  ApplicationStatus,
  formatFieldName,
} from "@/lib/utils/application-helpers";
import { getCurrentSemesterROC, toROCYear } from "@/src/utils/dateUtils";

interface ApplicationReviewDialogProps {
  application: Application | HistoricalApplication | null;
  role: "college" | "admin";
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
  const [error, setError] = useState<string | null>(null);
  const [reviewComment, setReviewComment] = useState("");
  const [detailedApplication, setDetailedApplication] = useState<Application | null>(null);
  const [isLoading, setIsLoading] = useState(false);

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

  // Handle admin approval
  const handleAdminApprove = async () => {
    if (!detailedApplication) return;

    setIsSubmittingStatus(true);
    try {
      const response = await api.applications.updateApplicationStatus(
        detailedApplication.id,
        {
          status: "approved",
          comments: adminComments,
        }
      );

      console.log("Approval response:", response);

      // 檢查是否成功（success 為 true 或 response 中有 data）
      if (response?.success || response?.data) {
        toast.success(
          locale === "zh" ? "核准成功" : "Approval Successful",
          {
            description: locale === "zh" ? "申請已核准" : "Application has been approved",
          }
        );
        setAdminComments("");
        // Refresh application data
        loadApplicationDetails(detailedApplication.id);
        // Call the callback if provided
        onAdminApprove?.(detailedApplication.id);
      } else {
        toast.error(
          locale === "zh" ? "核准失敗" : "Approval Failed",
          {
            description: response?.message || (locale === "zh" ? "無法核准此申請" : "Could not approve this application"),
          }
        );
      }
    } catch (error) {
      console.error("Admin approve error:", error);
      toast.error(
        locale === "zh" ? "錯誤" : "Error",
        {
          description: error instanceof Error ? error.message : (locale === "zh" ? "核准過程中發生錯誤" : "An error occurred during approval"),
        }
      );
    } finally {
      setIsSubmittingStatus(false);
    }
  };

  // Handle admin rejection
  const handleAdminReject = async () => {
    if (!detailedApplication) return;

    setIsSubmittingStatus(true);
    try {
      const response = await api.applications.updateApplicationStatus(
        detailedApplication.id,
        {
          status: "rejected",
          comments: adminComments,
        }
      );

      console.log("Rejection response:", response);

      // 檢查是否成功（success 為 true 或 response 中有 data）
      if (response?.success || response?.data) {
        toast.success(
          locale === "zh" ? "駁回成功" : "Rejection Successful",
          {
            description: locale === "zh" ? "申請已駁回" : "Application has been rejected",
          }
        );
        setAdminComments("");
        // Refresh application data
        loadApplicationDetails(detailedApplication.id);
        // Call the callback if provided
        onAdminReject?.(detailedApplication.id);
      } else {
        toast.error(
          locale === "zh" ? "駁回失敗" : "Rejection Failed",
          {
            description: response?.message || (locale === "zh" ? "無法駁回此申請" : "Could not reject this application"),
          }
        );
      }
    } catch (error) {
      console.error("Admin reject error:", error);
      toast.error(
        locale === "zh" ? "錯誤" : "Error",
        {
          description: error instanceof Error ? error.message : (locale === "zh" ? "駁回過程中發生錯誤" : "An error occurred during rejection"),
        }
      );
    } finally {
      setIsSubmittingStatus(false);
    }
  };

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
          locale === "zh" ? "銀行驗證成功" : "Bank Verification Successful",
          {
            description: locale === "zh" ? "銀行帳戶驗證已完成" : "Bank account verification completed",
          }
        );
        // Refresh application data
        if (detailedApplication) {
          loadApplicationDetails(detailedApplication.id);
        }
      } else {
        toast.error(
          locale === "zh" ? "銀行驗證失敗" : "Bank Verification Failed",
          {
            description: response.message || (locale === "zh" ? "無法完成銀行帳戶驗證" : "Could not complete bank account verification"),
          }
        );
      }
    } catch (error) {
      console.error("Bank verification error:", error);
      toast.error(
        locale === "zh" ? "銀行驗證錯誤" : "Bank Verification Error",
        {
          description: locale === "zh" ? "銀行帳戶驗證過程中發生錯誤" : "An error occurred during bank account verification",
        }
      );
    } finally {
      setBankVerificationLoading(false);
    }
  };

  // Get bank verification status
  const getBankVerificationStatus = () => {
    if (!detailedApplication) return null;

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
            ? "銀行帳戶已通過驗證"
            : "Bank account has been verified",
        variant: "default" as const,
      };
    } else if (bankVerificationFailed) {
      return {
        status: "failed",
        icon: <ShieldX className="h-5 w-5 text-red-600" />,
        label: locale === "zh" ? "驗證失敗" : "Verification Failed",
        description:
          locale === "zh"
            ? "銀行帳戶驗證失敗"
            : "Bank account verification failed",
        variant: "destructive" as const,
      };
    } else if (bankVerificationPending) {
      return {
        status: "pending",
        icon: <Shield className="h-5 w-5 text-yellow-600" />,
        label: locale === "zh" ? "驗證中" : "Verification Pending",
        description:
          locale === "zh"
            ? "銀行帳戶驗證進行中"
            : "Bank account verification in progress",
        variant: "secondary" as const,
      };
    } else {
      return {
        status: "not_verified",
        icon: <CreditCard className="h-5 w-5 text-gray-500" />,
        label: locale === "zh" ? "未驗證" : "Not Verified",
        description:
          locale === "zh"
            ? "銀行帳戶尚未驗證"
            : "Bank account not verified yet",
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

  // Load form configuration and files when dialog opens
  useEffect(() => {
    if (open && application) {
      loadApplicationDetails(application.id);
      // Reset review comment when opening a new application
      setReviewComment("");
      setAdminComments("");
    } else {
      setDetailedApplication(null);
      // Clear form state when dialog closes
      setReviewComment("");
      setAdminComments("");
    }
  }, [open, application]);

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
          id: doc.document_id || doc.file_id || doc.id,
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

  // Handle approve
  const handleApprove = () => {
    if (detailedApplication && onApprove) {
      onApprove(detailedApplication.id, reviewComment);
    }
  };

  // Handle reject
  const handleReject = () => {
    if (detailedApplication && onReject) {
      onReject(detailedApplication.id, reviewComment);
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
              <TabsList className={role === "college" ? "grid w-full grid-cols-6" : "grid w-full grid-cols-6"}>
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
                {role === "college" && (
                  <TabsTrigger value="review">
                    <CheckCircle className="h-4 w-4 mr-1" />
                    {locale === "zh" ? "審核操作" : "Review"}
                  </TabsTrigger>
                )}
                {role === "admin" && (
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
                            <Badge variant={getStatusColor(displayData.status as ApplicationStatus)}>
                              {displayData.status_name || getStatusName(displayData.status as ApplicationStatus, locale)}
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
                              : displayData.semester === "annual"
                              ? (locale === "zh" ? "全年" : "Annual")
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

                {/* Review Actions Tab (College only) */}
                {role === "college" && (
                  <TabsContent value="review" className="space-y-4 mt-4">
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-lg">
                          {locale === "zh" ? "學院審核意見" : "College Review Comments"}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Textarea
                          placeholder={
                            locale === "zh"
                              ? "請輸入學院審核意見..."
                              : "Enter college review comments..."
                          }
                          value={reviewComment}
                          onChange={(e) => setReviewComment(e.target.value)}
                          className="min-h-[100px]"
                        />
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader>
                        <CardTitle className="text-lg">
                          {locale === "zh" ? "審核操作" : "Review Actions"}
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-2">
                        <div className="flex gap-2">
                          <Button onClick={handleApprove} className="flex-1" disabled={!onApprove}>
                            <CheckCircle className="h-4 w-4 mr-1" />
                            {locale === "zh" ? "學院核准" : "Approve"}
                          </Button>
                          <Button
                            variant="destructive"
                            onClick={handleReject}
                            className="flex-1"
                            disabled={!onReject}
                          >
                            <XCircle className="h-4 w-4 mr-1" />
                            {locale === "zh" ? "學院駁回" : "Reject"}
                          </Button>
                        </div>
                        <Button
                          variant="outline"
                          onClick={handleRequestDocs}
                          className="w-full border-orange-200 text-orange-600 hover:bg-orange-50 hover:text-orange-700"
                          disabled={!onRequestDocs}
                        >
                          <FileQuestion className="h-4 w-4 mr-1" />
                          {locale === "zh" ? "要求補件" : "Request Documents"}
                        </Button>
                        <Button
                          variant="outline"
                          onClick={handleDelete}
                          className="w-full border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
                          disabled={!onDelete}
                        >
                          <Trash2 className="h-4 w-4 mr-1" />
                          {locale === "zh" ? "刪除申請" : "Delete Application"}
                        </Button>
                      </CardContent>
                    </Card>
                  </TabsContent>
                )}

                {/* Management Tab (Admin only) */}
                {role === "admin" && (
                  <TabsContent value="management" className="space-y-4 mt-4">
                    {/* Bank Verification Section */}
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                          <CreditCard className="h-5 w-5" />
                          {locale === "zh"
                            ? "銀行帳戶驗證"
                            : "Bank Account Verification"}
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

                    {/* Admin Review Actions */}
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-lg">
                          {locale === "zh" ? "管理審核操作" : "Admin Review Actions"}
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div>
                          <Label className="text-sm font-medium mb-2">
                            {locale === "zh" ? "審核意見/理由" : "Review Comments/Reason"}
                          </Label>
                          <Textarea
                            placeholder={
                              locale === "zh"
                                ? "請輸入核准或駁回的理由..."
                                : "Enter reason for approval or rejection..."
                            }
                            value={adminComments}
                            onChange={(e) => setAdminComments(e.target.value)}
                            className="min-h-[100px]"
                          />
                        </div>
                        <div className="flex gap-2">
                          <Button
                            onClick={handleAdminApprove}
                            className="flex-1"
                            disabled={isSubmittingStatus}
                          >
                            {isSubmittingStatus ? (
                              <>
                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                {locale === "zh" ? "處理中..." : "Processing..."}
                              </>
                            ) : (
                              <>
                                <CheckCircle className="h-4 w-4 mr-1" />
                                {locale === "zh" ? "管理員核准" : "Admin Approve"}
                              </>
                            )}
                          </Button>
                          <Button
                            variant="destructive"
                            onClick={handleAdminReject}
                            className="flex-1"
                            disabled={isSubmittingStatus}
                          >
                            {isSubmittingStatus ? (
                              <>
                                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                                {locale === "zh" ? "處理中..." : "Processing..."}
                              </>
                            ) : (
                              <>
                                <XCircle className="h-4 w-4 mr-1" />
                                {locale === "zh" ? "管理員駁回" : "Admin Reject"}
                              </>
                            )}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
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
