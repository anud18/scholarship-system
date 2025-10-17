"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
import { ApplicationReviewDialog } from "@/components/common/ApplicationReviewDialog";
import { DeleteApplicationDialog } from "@/components/delete-application-dialog";
import { DocumentRequestForm } from "@/components/document-request-form";
import {
  getStatusColor,
  getStatusName,
  ApplicationStatus,
} from "@/lib/utils/application-helpers";
import {
  Search,
  Eye,
  Grid,
  List,
  Download,
  GraduationCap,
  Calendar,
  School,
  Award,
  Building,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import * as XLSX from "xlsx";

interface ApplicationReviewPanelProps {
  user: User;
  scholarshipType: { code: string; name: string };
}

export function ApplicationReviewPanel({
  user,
  scholarshipType,
}: ApplicationReviewPanelProps) {
  const {
    locale,
    applications,
    viewMode,
    setViewMode,
    selectedApplication,
    setSelectedApplication,
    selectedAcademicYear,
    selectedSemester,
    selectedCombination,
    setSelectedCombination,
    setSelectedAcademicYear,
    setSelectedSemester,
    availableOptions,
    rankingData,
    collegeDisplayName,
    updateApplicationStatus,
    fetchCollegeApplications,
    activeScholarshipTab,
    showDeleteDialog,
    setShowDeleteDialog,
    applicationToDelete,
    setApplicationToDelete,
    showDocumentRequestDialog,
    setShowDocumentRequestDialog,
    applicationToRequestDocs,
    setApplicationToRequestDocs,
  } = useCollegeManagement();

  const { toast } = useToast();

  const handleApprove = async (appId: number) => {
    try {
      await updateApplicationStatus(appId, "approved", "學院核准通過");
      console.log(`College approved application ${appId}`);
    } catch (error) {
      console.error("Failed to approve application:", error);
    }
  };

  const handleReject = async (appId: number) => {
    try {
      await updateApplicationStatus(appId, "rejected", "學院駁回申請");
      console.log(`College rejected application ${appId}`);
    } catch (error) {
      console.error("Failed to reject application:", error);
    }
  };

  const handleExportApplications = () => {
    try {
      if (applications.length === 0) {
        toast({
          title: locale === "zh" ? "無資料可匯出" : "No data to export",
          description: locale === "zh" ? "目前沒有申請資料" : "No applications available",
          variant: "destructive",
        });
        return;
      }

      // Prepare export data
      const exportData = applications.map((app) => {
        // Format status
        const statusText = app.status_zh || getStatusName(app.status as ApplicationStatus, locale);

        // Format review status (學院審核狀態)
        let collegeReviewStatus = "-";
        if (app.college_review_completed) {
          collegeReviewStatus = locale === "zh" ? "已審核" : "Reviewed";
        } else if (app.status === "recommended" || app.status === "submitted") {
          collegeReviewStatus = locale === "zh" ? "待審核" : "Pending";
        } else if (app.status === "under_review") {
          collegeReviewStatus = locale === "zh" ? "審核中" : "Under Review";
        }

        // Format application type
        const applicationType = app.is_renewal
          ? (locale === "zh" ? "續領" : "Renewal")
          : (locale === "zh" ? "初領" : "New");

        // Format date
        const applicationDate = app.created_at
          ? new Date(app.created_at).toLocaleDateString("zh-TW", {
              year: "numeric",
              month: "2-digit",
              day: "2-digit",
            })
          : "-";

        return {
          '學生姓名': app.student_name || "-",
          '學號': app.student_id || "-",
          '就讀學期數': app.student_termcount || "-",
          '學院': (app as any).academy_name || "-",
          '系所': (app as any).department_name || "-",
          '獎學金類型': app.scholarship_type_zh || app.scholarship_type || "-",
          '申請類別': applicationType,
          '狀態': statusText,
          '學院審核狀態': collegeReviewStatus,
          '申請時間': applicationDate,
        };
      });

      // Create worksheet
      const worksheet = XLSX.utils.json_to_sheet(exportData);

      // Set column widths
      worksheet['!cols'] = [
        { wch: 20 }, // 學生姓名
        { wch: 15 }, // 學號
        { wch: 12 }, // 就讀學期數
        { wch: 25 }, // 學院
        { wch: 30 }, // 系所
        { wch: 25 }, // 獎學金類型
        { wch: 12 }, // 申請類別
        { wch: 15 }, // 狀態
        { wch: 15 }, // 學院審核狀態
        { wch: 12 }, // 申請時間
      ];

      // Create workbook
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, '申請審核清單');

      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const scholarshipTypeCode = activeScholarshipTab || "all";
      const year = selectedAcademicYear || "all";
      const semester = selectedSemester || "all";
      const filename = `學院審核管理_${scholarshipTypeCode}_${year}_${semester}_${timestamp}.xlsx`;

      // Download file
      XLSX.writeFile(workbook, filename);

      toast({
        title: locale === "zh" ? "匯出成功" : "Export successful",
        description: locale === "zh"
          ? `已匯出 ${exportData.length} 筆申請資料`
          : `Exported ${exportData.length} applications`,
      });
    } catch (error) {
      console.error('Export error:', error);
      toast({
        title: locale === "zh" ? "匯出失敗" : "Export failed",
        description: error instanceof Error ? error.message : (locale === "zh" ? "無法匯出資料" : "Failed to export data"),
        variant: "destructive",
      });
    }
  };

  return (
    <>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            {locale === "zh"
              ? "學院審核管理"
              : "College Review Management"}{" "}
            -{" "}
            {availableOptions?.scholarship_types?.find(
              type => type.code === scholarshipType.code
            )?.name || scholarshipType.name}
          </h2>
          <p className="text-muted-foreground">
            {locale === "zh"
              ? "學院層級的獎學金申請審核"
              : "College-level scholarship application reviews"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {/* 學期學年選擇 */}
          <Select
            value={selectedCombination || ""}
            onValueChange={value => {
              setSelectedCombination(value);
              const [year, semester] = value.split("-");
              setSelectedAcademicYear(parseInt(year));
              setSelectedSemester(semester || undefined);
              // 重新載入該獎學金類型的申請資料
              fetchCollegeApplications(
                parseInt(year),
                semester || undefined,
                activeScholarshipTab
              );
            }}
          >
            <SelectTrigger className="w-48">
              <SelectValue placeholder="選擇學期">
                <div className="flex items-center">
                  <Calendar className="h-4 w-4 mr-2" />
                  {selectedCombination
                    ? `${selectedCombination.split("-")[0]} ${
                        selectedCombination.split("-")[1] === "FIRST"
                          ? "上學期"
                          : selectedCombination.split("-")[1] ===
                              "SECOND"
                            ? "下學期"
                            : selectedCombination.split("-")[1] ===
                                "YEARLY"
                              ? "全年"
                              : selectedCombination.split("-")[1]
                      }`
                    : "選擇學期"}
                </div>
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {availableOptions?.academic_years?.map(year =>
                availableOptions?.semesters?.map(semester => (
                  <SelectItem
                    key={`${year}-${semester}`}
                    value={`${year}-${semester}`}
                  >
                    {year} 學年度{" "}
                    {semester === "FIRST"
                      ? "上學期"
                      : semester === "SECOND"
                        ? "下學期"
                        : semester === "YEARLY"
                          ? "全年"
                          : semester}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>

          <Button variant="outline" size="sm" onClick={handleExportApplications}>
            <Download className="h-4 w-4 mr-1" />
            {locale === "zh" ? "匯出" : "Export"}
          </Button>
          <div className="flex items-center border rounded-md">
            <Button
              variant={viewMode === "card" ? "default" : "ghost"}
              size="sm"
              onClick={() => setViewMode("card")}
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === "table" ? "default" : "ghost"}
              size="sm"
              onClick={() => setViewMode("table")}
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Statistics */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "待審核" : "Pending Review"}
            </CardTitle>
            <GraduationCap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {
                applications.filter(
                  app =>
                    app.status === "recommended" ||
                    app.status === "submitted"
                ).length
              }
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh"
                ? "需要學院審核"
                : "Requires college review"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "審核中" : "Under Review"}
            </CardTitle>
            <Eye className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {
                applications.filter(
                  app =>
                    app.status === "under_review" ||
                    (app.status === "recommended" &&
                      app.college_review_completed)
                ).length
              }
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh" ? "學院審核中" : "College reviewing"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "學院配額" : "College Quota"}
            </CardTitle>
            <Award className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {rankingData?.collegeQuota !== undefined
                ? rankingData.collegeQuota.toLocaleString()
                : rankingData?.totalQuota !== undefined
                  ? rankingData.totalQuota.toLocaleString()
                  : "-"}
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh"
                ? "本院可分配的名額"
                : "Seats allocated to this college"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "學院名稱" : "College"}
            </CardTitle>
            <Building className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold leading-tight">
              {collegeDisplayName}
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh"
                ? "目前檢視的學院"
                : "Currently selected college"}
            </p>
          </CardContent>
        </Card>
      </div>

      {applications.length === 0 ? (
        <div className="text-center py-8">
          <School className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
          <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
            {locale === "zh"
              ? "暫無待審核申請"
              : "No Applications Pending Review"}
          </h3>
          <p className="text-nycu-navy-600">
            {locale === "zh"
              ? "目前沒有需要學院審核的申請案件"
              : "No applications currently require college review"}
          </p>
        </div>
      ) : (
        <>
          {/* Filters */}
          <div className="flex items-center gap-4">
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={
                  locale === "zh"
                    ? "搜尋學生或學號..."
                    : "Search student or ID..."
                }
                className="pl-8"
              />
            </div>
            <Select defaultValue="all">
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">
                  {locale === "zh" ? "全部狀態" : "All Status"}
                </SelectItem>
                <SelectItem value="pending">
                  {locale === "zh" ? "待審核" : "Pending"}
                </SelectItem>
                <SelectItem value="under_review">
                  {locale === "zh" ? "審核中" : "Under Review"}
                </SelectItem>
                <SelectItem value="approved">
                  {locale === "zh" ? "已核准" : "Approved"}
                </SelectItem>
                <SelectItem value="rejected">
                  {locale === "zh" ? "已駁回" : "Rejected"}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Applications View */}
          <Card>
            <CardHeader>
              <CardTitle>
                {locale === "zh" ? "申請清單" : "Applications List"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>
                      {locale === "zh" ? "學生" : "Student"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "就讀學期數" : "Terms"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "學院/系所" : "College/Dept"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh"
                        ? "獎學金類型"
                        : "Scholarship Type"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "申請類別" : "Type"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "狀態" : "Status"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "申請時間" : "Applied"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "操作" : "Actions"}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {applications.map(app => (
                    <TableRow key={app.id}>
                      <TableCell>
                        <div className="flex flex-col gap-1">
                          <span className="font-medium">
                            {app.student_name || "未提供姓名"}
                          </span>
                          <span className="text-sm text-muted-foreground">
                            {app.student_id || "未提供學號"}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {app.student_termcount || "-"}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium text-sm">
                            {(app as any).academy_name || "-"}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {(app as any).department_name || "-"}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {app.scholarship_type_zh || app.scholarship_type}
                      </TableCell>
                      <TableCell>
                        <Badge variant={app.is_renewal ? "secondary" : "default"}>
                          {app.is_renewal ? "續領" : "初領"}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={getStatusColor(app.status as ApplicationStatus)}
                        >
                          {app.status_zh || getStatusName(app.status as ApplicationStatus, locale)}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {app.created_at
                          ? new Date(
                              app.created_at
                            ).toLocaleDateString("zh-TW", {
                              year: "numeric",
                              month: "2-digit",
                              day: "2-digit",
                            })
                          : "未知日期"}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelectedApplication(app)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}

      {/* Application Review Dialog */}
      <ApplicationReviewDialog
        application={selectedApplication}
        role="college"
        open={!!selectedApplication}
        onOpenChange={(open) => !open && setSelectedApplication(null)}
        locale={locale}
        academicYear={selectedAcademicYear}
        user={user}
        onApprove={handleApprove}
        onReject={handleReject}
        onRequestDocs={(app) => {
          setApplicationToRequestDocs(app);
          setShowDocumentRequestDialog(true);
        }}
        onDelete={(app) => {
          setApplicationToDelete(app);
          setShowDeleteDialog(true);
        }}
      />

      {/* Dialogs */}
      <DeleteApplicationDialog
        open={showDeleteDialog}
        onOpenChange={(open) => {
          setShowDeleteDialog(open);
          if (!open) setApplicationToDelete(null);
        }}
        applicationId={applicationToDelete?.id}
        applicationName={applicationToDelete?.student_name}
        onSuccess={() => {
          fetchCollegeApplications(
            selectedAcademicYear,
            selectedSemester,
            activeScholarshipTab
          );
        }}
      />

      <DocumentRequestForm
        open={showDocumentRequestDialog}
        onOpenChange={(open) => {
          setShowDocumentRequestDialog(open);
          if (!open) setApplicationToRequestDocs(null);
        }}
        applicationId={applicationToRequestDocs?.id}
        applicationName={applicationToRequestDocs?.student_name}
      />
    </>
  );
}
