"use client";

import { useState, useEffect, useCallback } from "react";
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
import { ConfigSelector } from "../shared/ConfigSelector";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
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
  School,
  Award,
  Building,
  Info,
} from "lucide-react";
import { toast } from "sonner";
import { useReferenceData, getStudyingStatusName, getAcademyName, getDepartmentName } from "@/hooks/use-reference-data";
import { useScholarshipData } from "@/hooks/use-scholarship-data";
import * as XLSX from "xlsx";
import { apiClient } from "@/lib/api";

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
    activeTab,
    collegeQuotaInfo,
    setCollegeQuotaInfo,
    showDeleteDialog,
    setShowDeleteDialog,
    applicationToDelete,
    setApplicationToDelete,
    showDocumentRequestDialog,
    setShowDocumentRequestDialog,
    applicationToRequestDocs,
    setApplicationToRequestDocs,
    dataVersion,
    incrementDataVersion,
  } = useCollegeManagement();

  // Fetch reference data (studying statuses, academies, departments, etc.)
  const { studyingStatuses, academies, departments } = useReferenceData();

  // Fetch scholarship data for sub-type translations
  const { getSubTypeName } = useScholarshipData();

  // Local state for status filter
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // Fetch college quota when scholarship type, year, or semester changes
  const fetchCollegeQuota = useCallback(async () => {
    if (!activeScholarshipTab || !selectedAcademicYear) {
      setCollegeQuotaInfo(null);
      return;
    }

    try {
      // Find scholarship type ID from availableOptions
      const scholarshipType = availableOptions?.scholarship_types?.find(
        st => st.code === activeScholarshipTab
      );

      if (!scholarshipType || !scholarshipType.id) {
        console.warn("Scholarship type ID not found for:", activeScholarshipTab);
        setCollegeQuotaInfo(null);
        return;
      }

      console.log("Fetching college quota for:", {
        scholarshipTypeId: scholarshipType.id,
        academicYear: selectedAcademicYear,
        semester: selectedSemester,
      });

      const response = await apiClient.college.getQuotaStatus(
        scholarshipType.id,
        selectedAcademicYear,
        selectedSemester
      );

      if (response.success && response.data) {
        setCollegeQuotaInfo({
          collegeQuota: response.data.college_quota ?? null,
          breakdown: response.data.college_quota_breakdown ?? {},
        });
        console.log("College quota fetched:", response.data.college_quota);
      } else {
        setCollegeQuotaInfo(null);
      }
    } catch (error) {
      console.error("Failed to fetch college quota:", error);
      setCollegeQuotaInfo(null);
    }
  }, [
    activeScholarshipTab,
    selectedAcademicYear,
    selectedSemester,
    availableOptions,
    setCollegeQuotaInfo,
  ]);

  // Fetch college quota when dependencies change
  useEffect(() => {
    fetchCollegeQuota();
  }, [fetchCollegeQuota]);

  // Auto-refresh applications when switching to review tab or when data version changes
  useEffect(() => {
    // Only refresh when:
    // 1. Current tab is "review"
    // 2. Data version has changed (indicating updates from other tabs)
    if (activeTab === "review") {
      console.log(`[ApplicationReviewPanel] Auto-refreshing applications (dataVersion: ${dataVersion})`);
      fetchCollegeApplications(selectedAcademicYear, selectedSemester, activeScholarshipTab);
    }
    // Note: fetchCollegeApplications is stable from hook, no need in deps
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, dataVersion, selectedAcademicYear, selectedSemester, activeScholarshipTab]);

  // Filter applications based on status and search query
  const filteredApplications = applications.filter(app => {
    // Status filter
    if (statusFilter !== "all") {
      if (statusFilter === "pending") {
        if (app.status !== "recommended" && app.status !== "submitted") {
          return false;
        }
      } else if (app.status !== statusFilter) {
        return false;
      }
    }

    // Search filter - match student name or ID
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const studentName = (app.student_name || "").toLowerCase();
      const studentId = (app.student_id || "").toLowerCase();
      if (!studentName.includes(query) && !studentId.includes(query)) {
        return false;
      }
    }

    return true;
  });

  const handleApprove = async (appId: number, comments?: string) => {
    try {
      const result = await updateApplicationStatus(appId, "approved", comments || "學院核准通過");
      console.log(`College approved application ${appId}`, result);

      // 檢查是否自動重新執行了分發
      const redistribution = result?.redistribution_info;
      if (redistribution?.auto_redistributed) {
        const processedCount = redistribution.rankings_processed || 1;
        const successfulCount = redistribution.successful_count || 0;
        toast.success(
          locale === "zh"
            ? `審核完成並已自動重新執行分配，處理 ${processedCount} 個排名（成功 ${successfulCount} 個），分配 ${redistribution.total_allocated} 名學生`
            : `Review completed with auto-redistribution for ${processedCount} rankings (${successfulCount} successful), ${redistribution.total_allocated} students allocated`,
          { duration: 6000 }
        );
      } else {
        // 顯示成功提示
        toast.success(
          locale === "zh" ? "核准成功" : "Approval Successful",
          {
            description: locale === "zh" ? "申請已核准" : "Application has been approved",
          }
        );
      }

      // 關閉 dialog
      setSelectedApplication(null);

      // 重新載入申請列表以顯示最新狀態
      await fetchCollegeApplications(
        selectedAcademicYear,
        selectedSemester,
        activeScholarshipTab
      );

      // 觸發 dataVersion 更新，通知其他 tab 重新載入數據
      incrementDataVersion();
    } catch (error) {
      console.error("Failed to approve application:", error);
      toast.error(
        locale === "zh" ? "核准失敗" : "Approval Failed",
        {
          description: error instanceof Error ? error.message : (locale === "zh" ? "無法核准此申請" : "Could not approve this application"),
        }
      );
    }
  };

  const handleReject = async (appId: number, comments?: string) => {
    try {
      const result = await updateApplicationStatus(appId, "rejected", comments || "學院駁回申請");
      console.log(`College rejected application ${appId}`, result);

      // 檢查是否自動重新執行了分發
      const redistribution = result?.redistribution_info;
      if (redistribution?.auto_redistributed) {
        const processedCount = redistribution.rankings_processed || 1;
        const successfulCount = redistribution.successful_count || 0;
        toast.success(
          locale === "zh"
            ? `審核完成並已自動重新執行分配，處理 ${processedCount} 個排名（成功 ${successfulCount} 個），分配 ${redistribution.total_allocated} 名學生`
            : `Review completed with auto-redistribution for ${processedCount} rankings (${successfulCount} successful), ${redistribution.total_allocated} students allocated`,
          { duration: 6000 }
        );
      } else {
        // 顯示成功提示
        toast.success(
          locale === "zh" ? "駁回成功" : "Rejection Successful",
          {
            description: locale === "zh" ? "申請已駁回" : "Application has been rejected",
          }
        );
      }

      // 關閉 dialog
      setSelectedApplication(null);

      // 重新載入申請列表以顯示最新狀態
      await fetchCollegeApplications(
        selectedAcademicYear,
        selectedSemester,
        activeScholarshipTab
      );

      // 觸發 dataVersion 更新，通知其他 tab 重新載入數據
      incrementDataVersion();
    } catch (error) {
      console.error("Failed to reject application:", error);
      toast.error(
        locale === "zh" ? "駁回失敗" : "Rejection Failed",
        {
          description: error instanceof Error ? error.message : (locale === "zh" ? "無法駁回此申請" : "Could not reject this application"),
        }
      );
    }
  };

  const handleExportApplications = () => {
    try {
      if (applications.length === 0) {
        toast.error(
          locale === "zh" ? "無資料可匯出" : "No data to export",
          {
            description: locale === "zh" ? "目前沒有申請資料" : "No applications available",
          }
        );
        return;
      }

      // Prepare export data
      const exportData = applications.map((app) => {
        // Format status
        const statusText = app.status_zh || getStatusName(app.status as ApplicationStatus, locale);

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

        // Format scholarship period status (獎學金期間在學狀態)
        const studyingStatus = app.scholarship_period_status !== undefined && app.scholarship_period_status !== null
          ? getStudyingStatusName(app.scholarship_period_status, studyingStatuses)
          : "-";

        return {
          '學生姓名': app.student_name || "-",
          '學號': app.student_id || "-",
          '學院': getAcademyName(app.academy_code, academies),
          '系所': getDepartmentName(app.department_code, departments),
          '在學學期數': app.student_termcount || "-",
          '在學狀態': studyingStatus,
          '獎學金類型': app.scholarship_type_zh || app.scholarship_type || "-",
          '申請類別': applicationType,
          '狀態': statusText,
          '申請時間': applicationDate,
        };
      });

      // Create worksheet
      const worksheet = XLSX.utils.json_to_sheet(exportData);

      // Set column widths
      worksheet['!cols'] = [
        { wch: 20 }, // 學生姓名
        { wch: 15 }, // 學號
        { wch: 25 }, // 學院
        { wch: 30 }, // 系所
        { wch: 12 }, // 在學學期數
        { wch: 12 }, // 在學狀態
        { wch: 25 }, // 獎學金類型
        { wch: 12 }, // 申請類別
        { wch: 15 }, // 狀態
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

      toast.success(
        locale === "zh" ? "匯出成功" : "Export successful",
        {
          description: locale === "zh"
            ? `已匯出 ${exportData.length} 筆申請資料`
            : `Exported ${exportData.length} applications`,
        }
      );
    } catch (error) {
      console.error('Export error:', error);
      toast.error(
        locale === "zh" ? "匯出失敗" : "Export failed",
        {
          description: error instanceof Error ? error.message : (locale === "zh" ? "無法匯出資料" : "Failed to export data"),
        }
      );
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
          <ConfigSelector
            selectedCombination={selectedCombination}
            availableYears={availableOptions?.academic_years || []}
            availableSemesters={availableOptions?.semesters || []}
            onCombinationChange={(value) => {
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
            locale={locale}
          />

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
            <div className="flex items-center gap-2">
              <div className="text-2xl font-bold">
                {collegeQuotaInfo?.collegeQuota !== null && collegeQuotaInfo?.collegeQuota !== undefined
                  ? collegeQuotaInfo.collegeQuota.toLocaleString()
                  : "-"}
              </div>
              {collegeQuotaInfo?.breakdown && Object.keys(collegeQuotaInfo.breakdown).length > 0 && (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <Info className="h-4 w-4 text-slate-400 hover:text-slate-600 cursor-help transition-colors" />
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-sm bg-white border-slate-200 shadow-xl">
                      <div className="p-2">
                        <p className="font-semibold text-sm mb-3 text-slate-700">
                          {locale === "zh" ? "配額細項" : "Quota Breakdown"}
                        </p>
                        <div className="space-y-2">
                          {Object.entries(collegeQuotaInfo.breakdown).map(([subType, quota]) => (
                            <div
                              key={subType}
                              className="bg-slate-50 border border-slate-200 rounded-md p-3"
                            >
                              <div className="flex items-center justify-between space-x-5">
                                <p className="text-xs font-medium text-slate-700">
                                  {getSubTypeName(subType, locale)}
                                </p>
                                <p className="text-base font-semibold text-slate-800">
                                  {quota}
                                </p>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              )}
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
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={
                  locale === "zh"
                    ? "搜尋學生或學號..."
                    : "Search student or ID..."
                }
                className="pl-8"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
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
                <SelectItem value="partial_approve">
                  {locale === "zh" ? "部分核准" : "Partial Approval"}
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
                      {locale === "zh" ? "學院系所" : "College/Dept"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "在學學期數" : "Terms"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "在學狀態" : "Status"}
                    </TableHead>
                    <TableHead>
                      {locale === "zh" ? "獎學金類型" : "Scholarship"}
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
                  {filteredApplications.map(app => (
                    <TableRow key={app.id}>
                      {/* 1. 學生 */}
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

                      {/* 2. 學院系所 */}
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium text-sm">
                            {getAcademyName(app.academy_code, academies)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {getDepartmentName(app.department_code, departments)}
                          </span>
                        </div>
                      </TableCell>

                      {/* 3. 在學學期數 */}
                      <TableCell>
                        {app.student_termcount || "-"}
                      </TableCell>

                      {/* 4. 在學狀態（獎學金期間） */}
                      <TableCell>
                        {app.scholarship_period_status !== undefined && app.scholarship_period_status !== null
                          ? getStudyingStatusName(app.scholarship_period_status, studyingStatuses)
                          : "-"}
                      </TableCell>

                      {/* 5. 獎學金類型 */}
                      <TableCell>
                        {app.scholarship_type_zh || app.scholarship_type}
                      </TableCell>

                      {/* 6. 申請類別 */}
                      <TableCell>
                        <Badge variant={app.is_renewal ? "secondary" : "default"}>
                          {app.is_renewal ? "續領" : "初領"}
                        </Badge>
                      </TableCell>

                      {/* 7. 狀態 */}
                      <TableCell>
                        <Badge
                          variant={getStatusColor(app.status as ApplicationStatus)}
                        >
                          {app.status_zh || getStatusName(app.status as ApplicationStatus, locale)}
                        </Badge>
                      </TableCell>

                      {/* 8. 申請時間 */}
                      <TableCell>
                        {app.created_at
                          ? new Date(app.created_at).toLocaleDateString("zh-TW", {
                              year: "numeric",
                              month: "2-digit",
                              day: "2-digit",
                            })
                          : "-"}
                      </TableCell>

                      {/* 9. 操作 */}
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
        onReviewSubmitted={() => {
          // Trigger data refresh by incrementing version
          incrementDataVersion();
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
          // Close the ApplicationReviewDialog
          setSelectedApplication(null);

          // Clear delete state
          setApplicationToDelete(null);

          // Refresh the applications list
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
