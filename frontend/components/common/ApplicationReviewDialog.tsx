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
import { toast } from "@/hooks/use-toast";
import { ProgressTimeline } from "@/components/progress-timeline";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { ApplicationFormDataDisplay } from "@/components/application-form-data-display";
import { ApplicationAuditTrail } from "@/components/application-audit-trail";
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
} from "lucide-react";
import { Locale } from "@/lib/validators";
import { Application, HistoricalApplication, User } from "@/lib/api";
import api from "@/lib/api";
import { useStudentPreview } from "@/hooks/use-student-preview";
import {
  getApplicationTimeline,
  getStatusColor,
  getStatusName,
  getDocumentLabel,
  fetchApplicationFiles,
  ApplicationStatus,
  formatFieldName,
} from "@/lib/utils/application-helpers";

interface ApplicationReviewDialogProps {
  application: Application | HistoricalApplication | null;
  role: "college" | "admin";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  locale?: "zh" | "en";
  academicYear?: number;
  user?: User;

  // College-specific handlers (optional)
  onApprove?: (id: number) => void;
  onReject?: (id: number) => void;
  onRequestDocs?: (app: Application) => void;
  onDelete?: (app: Application) => void;
}

// Student Preview Display Component
function StudentPreviewDisplay({
  studentId,
  academicYear,
  locale = "zh",
}: {
  studentId: string;
  academicYear?: number;
  locale?: "zh" | "en";
}) {
  const { previewData, isLoading, error, fetchPreview } = useStudentPreview();

  useEffect(() => {
    if (studentId) {
      fetchPreview(studentId, academicYear);
    }
  }, [studentId, academicYear, fetchPreview]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-red-500">
        {locale === "zh" ? "無法載入學期資料" : "Failed to load term data"}
      </p>
    );
  }

  if (!previewData?.recent_terms || previewData.recent_terms.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {locale === "zh" ? "無學期資料" : "No term data available"}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {previewData.recent_terms.map((term) => (
        <div
          key={`${term.academic_year}-${term.term}`}
          className="bg-muted/50 rounded-md p-3"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-sm">
              {term.academic_year}-
              {term.term === "1"
                ? locale === "zh"
                  ? "上"
                  : "1st"
                : locale === "zh"
                  ? "下"
                  : "2nd"}
            </span>
            <div className="flex items-center gap-3">
              {term.gpa !== undefined && (
                <Badge variant="outline" className="text-xs">
                  GPA: {term.gpa.toFixed(2)}
                </Badge>
              )}
              {term.credits !== undefined && (
                <span className="text-sm text-muted-foreground">
                  {term.credits} {locale === "zh" ? "學分" : "cr"}
                </span>
              )}
            </div>
          </div>
          {term.rank !== undefined && (
            <p className="text-sm text-muted-foreground">
              {locale === "zh" ? "排名" : "Rank"}: {term.rank}
            </p>
          )}
        </div>
      ))}
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

  // Load form configuration and files when dialog opens
  useEffect(() => {
    if (open && application) {
      loadApplicationFiles();
      loadFormConfig();
    }
  }, [open, application]);

  // Load form configuration (field and document labels)
  const loadFormConfig = async () => {
    if (!application) return;

    setIsLoadingLabels(true);
    setIsLoadingFields(true);
    setError(null);

    try {
      // Get scholarship_type
      let scholarshipType = (application as Application).scholarship_type || (application as HistoricalApplication).scholarship_type_code;

      if (!scholarshipType && (application as Application).scholarship_type_id) {
        try {
          const scholarshipResponse = await api.scholarships.getById(
            (application as Application).scholarship_type_id!
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
    if (!application) return;

    setIsLoadingFiles(true);
    try {
      const appData = application as Application;
      // Try to get files from submitted_form_data.documents
      if (appData.submitted_form_data?.documents) {
        const files = appData.submitted_form_data.documents.map((doc: any) => ({
          id: doc.file_id,
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
        const files = await fetchApplicationFiles(application.id);
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

    const previewUrl = `/api/v1/preview?fileId=${file.id}&filename=${encodeURIComponent(filename)}&type=${encodeURIComponent(file.file_type)}&applicationId=${application?.id}&token=${token}`;

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
    if (application && onApprove) {
      onApprove(application.id);
    }
  };

  // Handle reject
  const handleReject = () => {
    if (application && onReject) {
      onReject(application.id);
    }
  };

  // Handle request documents
  const handleRequestDocs = () => {
    if (application && onRequestDocs) {
      onRequestDocs(application as Application);
    }
  };

  // Handle delete
  const handleDelete = () => {
    if (application && onDelete) {
      onDelete(application as Application);
    }
  };

  if (!application) return null;

  // Normalize application data for display
  const displayData = {
    id: application.id,
    app_id: application.app_id,
    student_id: (application as Application).student_id || (application as HistoricalApplication).student_id || "",
    student_name: (application as Application).student_name || (application as HistoricalApplication).student_name || "",
    scholarship_type: (application as Application).scholarship_type || (application as HistoricalApplication).scholarship_type_code || "",
    scholarship_name: (application as Application).scholarship_name || (application as HistoricalApplication).scholarship_name || "",
    status: application.status,
    status_name: (application as HistoricalApplication).status_name,
    created_at: application.created_at,
    submitted_at: (application as Application).submitted_at || (application as HistoricalApplication).submitted_at,
    gpa: (application as Application).gpa,
    class_ranking_percent: (application as Application).class_ranking_percent,
    dept_ranking_percent: (application as Application).dept_ranking_percent,
    student_termcount: (application as Application).student_termcount,
    department: (application as Application).department || (application as HistoricalApplication).student_department,
  };

  const tabCount = role === "college" ? 6 : 5;

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

          <Tabs defaultValue="basic" className="flex-1 overflow-hidden flex flex-col">
            <TabsList className={`grid w-full grid-cols-${tabCount}`}>
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
              <TabsTrigger value="audit">
                <History className="h-4 w-4 mr-1" />
                {locale === "zh" ? "操作紀錄" : "Audit"}
              </TabsTrigger>
            </TabsList>

            <div className="flex-1 overflow-y-auto">
              {/* Basic Information Tab */}
              <TabsContent value="basic" className="space-y-4 mt-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">
                      {locale === "zh" ? "基本資訊" : "Basic Information"}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "申請者" : "Applicant"}
                        </Label>
                        <p className="text-sm">{displayData.student_name || "N/A"}</p>
                      </div>
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "學號" : "Student ID"}
                        </Label>
                        <p className="text-sm">{displayData.student_id || "N/A"}</p>
                      </div>
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "就讀學期數" : "Terms"}
                        </Label>
                        <p className="text-sm">{displayData.student_termcount || "-"}</p>
                      </div>
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "系所" : "Department"}
                        </Label>
                        <p className="text-sm">{displayData.department || "-"}</p>
                      </div>
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "獎學金類型" : "Scholarship Type"}
                        </Label>
                        <p className="text-sm">
                          {displayData.scholarship_name || displayData.scholarship_type}
                        </p>
                      </div>
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "申請狀態" : "Status"}
                        </Label>
                        <div>
                          <Badge variant={getStatusColor(displayData.status as ApplicationStatus)}>
                            {displayData.status_name || getStatusName(displayData.status as ApplicationStatus, locale)}
                          </Badge>
                        </div>
                      </div>
                      <div>
                        <Label className="font-medium">
                          {locale === "zh" ? "建立時間" : "Created At"}
                        </Label>
                        <p className="text-sm">
                          {new Date(displayData.created_at).toLocaleDateString(
                            locale === "zh" ? "zh-TW" : "en-US"
                          )}
                        </p>
                      </div>
                      {displayData.submitted_at && (
                        <div>
                          <Label className="font-medium">
                            {locale === "zh" ? "提交時間" : "Submitted At"}
                          </Label>
                          <p className="text-sm">
                            {new Date(displayData.submitted_at).toLocaleDateString(
                              locale === "zh" ? "zh-TW" : "en-US"
                            )}
                          </p>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {/* Academic Information */}
                {(displayData.gpa || displayData.class_ranking_percent || displayData.dept_ranking_percent) && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-lg">
                        {locale === "zh" ? "學術資訊" : "Academic Information"}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="grid grid-cols-3 gap-4">
                        {displayData.gpa && (
                          <div>
                            <Label className="font-medium">GPA</Label>
                            <p className="text-sm">{displayData.gpa}</p>
                          </div>
                        )}
                        {displayData.class_ranking_percent && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "班級排名" : "Class Ranking"}
                            </Label>
                            <p className="text-sm">{displayData.class_ranking_percent}%</p>
                          </div>
                        )}
                        {displayData.dept_ranking_percent && (
                          <div>
                            <Label className="font-medium">
                              {locale === "zh" ? "系所排名" : "Department Ranking"}
                            </Label>
                            <p className="text-sm">{displayData.dept_ranking_percent}%</p>
                          </div>
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
                    <ProgressTimeline steps={getApplicationTimeline(application as Application, locale)} />
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
                      <ApplicationFormDataDisplay
                        formData={application as Application}
                        locale={locale}
                        fieldLabels={fieldLabels}
                      />
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
                      {locale === "zh" ? "學生基本資訊" : "Student Basic Information"}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className="text-sm font-medium text-muted-foreground">
                          {locale === "zh" ? "學號" : "Student ID"}
                        </Label>
                        <p className="text-sm font-medium mt-1">{displayData.student_id || "-"}</p>
                      </div>
                      <div>
                        <Label className="text-sm font-medium text-muted-foreground">
                          {locale === "zh" ? "姓名" : "Name"}
                        </Label>
                        <p className="text-sm font-medium mt-1">{displayData.student_name || "-"}</p>
                      </div>
                      <div>
                        <Label className="text-sm font-medium text-muted-foreground">
                          {locale === "zh" ? "就讀學期數" : "Terms"}
                        </Label>
                        <p className="text-sm font-medium mt-1">{displayData.student_termcount || "-"}</p>
                      </div>
                      <div>
                        <Label className="text-sm font-medium text-muted-foreground">
                          {locale === "zh" ? "系所" : "Department"}
                        </Label>
                        <p className="text-sm font-medium mt-1">{displayData.department || "-"}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">
                      {locale === "zh" ? "近期學期成績" : "Recent Term Grades"}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <StudentPreviewDisplay
                      studentId={displayData.student_id}
                      academicYear={academicYear}
                      locale={locale}
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
