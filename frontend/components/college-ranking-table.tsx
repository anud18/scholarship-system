"use client";

import { useState, useEffect } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
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
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  GripVertical,
  Eye,
  Edit3,
  Save,
  Trophy,
  Users,
  AlertCircle,
  CheckCircle,
  XCircle,
  FileText,
  Download,
  Send,
  Upload,
  FileSpreadsheet,
} from "lucide-react";
import { getTranslation } from "@/lib/i18n";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import * as XLSX from "xlsx";
import { ApplicationReviewDialog } from "@/components/common/ApplicationReviewDialog";
import { Application as ApplicationType, User } from "@/lib/api";

interface Application {
  id: number;
  app_id: string;
  student_name: string;
  student_id: string;
  academy_name?: string;
  academy_code?: string;
  department_name?: string;
  scholarship_type: string;
  sub_type: string;
  eligible_subtypes?: string[];  // Eligible sub-scholarship types
  rank_position: number;
  is_allocated: boolean;
  status: string;
  review_status?: string;
}

interface CollegeRankingTableProps {
  applications: Application[];
  totalQuota: number;
  subTypeCode: string;
  academicYear: number;
  semester?: string | null;
  isFinalized: boolean;
  rankingId?: number;
  onRankingChange: (newOrder: Application[]) => void;
  onReviewApplication: (applicationId: number, action: 'approve' | 'reject', comments?: string) => void;
  onExecuteDistribution: () => void;
  onFinalizeRanking: () => void;
  onImportExcel?: (data: any[]) => Promise<void>;
  locale?: "zh" | "en";
  subTypeMeta?: Record<string, { label: string; label_en: string; code?: string }>;
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error';
}

// SortableItem component for drag and drop
function SortableItem({
  application,
  index,
  totalQuota,
  locale,
  isFinalized,
  onReviewApplication,
  reviewScores,
  handleScoreUpdate,
  subTypeMeta,
  academicYear,
  onViewDetails,
}: {
  application: Application;
  index: number;
  totalQuota: number;
  locale: "zh" | "en";
  isFinalized: boolean;
  onReviewApplication: (applicationId: number, action: 'approve' | 'reject', comments?: string) => void;
  reviewScores: { [key: number]: any };
  handleScoreUpdate: (appId: number, field: string, value: any) => void;
  subTypeMeta?: Record<string, { label: string; label_en: string; code?: string }>;
  academicYear: number;
  onViewDetails: (app: Application) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition } =
    useSortable({ id: application.id.toString(), disabled: isFinalized });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  const getRankBadge = (position: number) => {
    if (position <= 3) {
      const colors = {
        1: "bg-yellow-100 text-yellow-800 border-yellow-300",
        2: "bg-gray-100 text-gray-800 border-gray-300",
        3: "bg-orange-100 text-orange-800 border-orange-300",
      };
      return (
        <Badge
          variant="outline"
          className={colors[position as keyof typeof colors]}
        >
          <Trophy className="w-3 h-3 mr-1" />#{position}
        </Badge>
      );
    }
    return <Badge variant="outline">#{position}</Badge>;
  };

  const getStatusBadge = (app: Application) => {
    // Check for rejected status first (highest priority)
    if (app.status === 'rejected') {
      return (
        <Badge variant="destructive" className="bg-red-100 text-red-800">
          <XCircle className="w-3 h-3 mr-1" />
          {locale === "zh" ? "駁回" : "Rejected"}
        </Badge>
      );
    }

    if (app.is_allocated) {
      return (
        <Badge variant="default" className="bg-green-100 text-green-800">
          <CheckCircle className="w-3 h-3 mr-1" />
          {locale === "zh" ? "獲分配" : "Allocated"}
        </Badge>
      );
    } else {
      return (
        <Badge variant="secondary" className="bg-gray-100 text-gray-800">
          <XCircle className="w-3 h-3 mr-1" />
          {locale === "zh" ? "未分配" : "Not Allocated"}
        </Badge>
      );
    }
  };

  const getSubtypeBadgeColor = (subtype: string) => {
    const subtypeUpper = subtype.toUpperCase();
    if (subtypeUpper.includes("NSTC")) {
      return "bg-blue-100 text-blue-800 border-blue-300";
    } else if (subtypeUpper.includes("MOE_1W") || subtypeUpper.includes("1W")) {
      return "bg-green-100 text-green-800 border-green-300";
    } else if (subtypeUpper.includes("MOE_2W") || subtypeUpper.includes("2W")) {
      return "bg-yellow-100 text-yellow-800 border-yellow-300";
    } else if (subtypeUpper.includes("GENERAL")) {
      return "bg-gray-100 text-gray-800 border-gray-300";
    } else {
      return "bg-purple-100 text-purple-800 border-purple-300";
    }
  };

  const getSubtypeLabel = (subtype: string) => {
    const meta =
      subTypeMeta?.[subtype] ||
      subTypeMeta?.[subtype.toUpperCase()] ||
      subTypeMeta?.[subtype.toLowerCase()];
    if (!meta) {
      return subtype.toUpperCase();
    }
    return (locale === "zh" ? meta.label : meta.label_en || meta.label) || subtype;
  };

  return (
    <TableRow
      ref={setNodeRef}
      style={style}
      className={`${application.is_allocated ? "bg-green-50" : "bg-gray-50"}`}
    >
      <TableCell>
        <div className="flex items-center gap-2">
          {!isFinalized && (
            <div {...attributes} {...listeners} className="cursor-grab">
              <GripVertical className="h-4 w-4 text-gray-400" />
            </div>
          )}
          {getRankBadge(application.rank_position)}
        </div>
      </TableCell>

      <TableCell>
        <div className="space-y-1">
          <p className="font-medium text-sm">{application.student_name}</p>
          <p className="text-xs text-gray-400">{application.app_id}</p>
        </div>
      </TableCell>

      <TableCell className="text-center text-sm text-gray-600">
        {application.student_id || (locale === "zh" ? "未提供" : "N/A")}
      </TableCell>

      <TableCell className="text-center">
        <div className="flex flex-col gap-0.5">
          <span className="font-medium text-sm">
            {application.academy_name || "-"}
          </span>
          <span className="text-xs text-muted-foreground">
            {application.department_name || "-"}
          </span>
        </div>
      </TableCell>

      <TableCell className="text-center">
        <div className="flex flex-wrap justify-center gap-1">
          {application.eligible_subtypes && application.eligible_subtypes.length > 0 ? (
            application.eligible_subtypes.map((subtype, idx) => (
              <Badge
                key={idx}
                variant="outline"
                className={`text-xs ${getSubtypeBadgeColor(subtype)}`}
              >
                {getSubtypeLabel(subtype)}
              </Badge>
            ))
          ) : (
            <span className="text-xs text-gray-400">-</span>
          )}
        </div>
      </TableCell>

      <TableCell className="text-center">
        {getStatusBadge(application)}
      </TableCell>

      <TableCell className="text-center">
        <div className="flex justify-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onViewDetails(application)}
          >
            <Eye className="h-4 w-4" />
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}

export function CollegeRankingTable({
  applications,
  totalQuota,
  subTypeCode,
  academicYear,
  semester,
  isFinalized,
  rankingId,
  onRankingChange,
  onReviewApplication,
  onExecuteDistribution,
  onFinalizeRanking,
  onImportExcel,
  locale = "zh",
  subTypeMeta,
  saveStatus = 'idle',
}: CollegeRankingTableProps) {
  const t = (key: string) => getTranslation(locale, key);
  const formatSemesterLabel = (value?: string | null) => {
    if (!value) {
      return locale === "zh" ? "全年" : "Yearly";
    }

    const lower = value.toLowerCase();

    if (lower === "first") {
      return locale === "zh" ? "第一學期" : "1st Semester";
    }

    if (lower === "second") {
      return locale === "zh" ? "第二學期" : "2nd Semester";
    }

    return value;
  };

  const [localApplications, setLocalApplications] =
    useState<Application[]>(applications);
  const [selectedApplication, setSelectedApplication] =
    useState<Application | null>(null);
  const [reviewScores, setReviewScores] = useState<{ [key: number]: any }>({});
  const [isImportDialogOpen, setIsImportDialogOpen] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [selectedAppForDialog, setSelectedAppForDialog] =
    useState<Application | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  useEffect(() => {
    // Sort applications by rank position
    const sortedApps = [...applications].sort(
      (a, b) => a.rank_position - b.rank_position
    );
    setLocalApplications(sortedApps);
  }, [applications]);

  const handleDragEnd = (event: any) => {
    const { active, over } = event;

    if (!over || active.id === over.id || isFinalized) {
      return;
    }

    const oldIndex = localApplications.findIndex(
      item => item.id.toString() === active.id
    );
    const newIndex = localApplications.findIndex(
      item => item.id.toString() === over.id
    );

    const newItems = arrayMove(localApplications, oldIndex, newIndex);

    // Update rank positions only - allocation status is set by distribution execution
    const updatedItems = newItems.map((item, index) => ({
      ...item,
      rank_position: index + 1,
      // is_allocated is not updated here - only set after distribution execution
    }));

    // Update local state first, then notify parent
    setLocalApplications(updatedItems);
    // Call parent callback outside of setState to avoid setState-in-render error
    onRankingChange(updatedItems);
  };

  const handleScoreUpdate = (appId: number, field: string, value: any) => {
    setReviewScores(prev => ({
      ...prev,
      [appId]: {
        ...prev[appId],
        [field]: value,
      },
    }));
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.xls')) {
      toast.error("請上傳 Excel 檔案 (.xlsx 或 .xls)");
      return;
    }

    setIsImporting(true);

    try {
      // Read Excel file
      const data = await file.arrayBuffer();
      const uint8Array = new Uint8Array(data);
      const workbook = XLSX.read(uint8Array, { type: 'array' });
      const worksheet = workbook.Sheets[workbook.SheetNames[0]];
      const jsonData = XLSX.utils.sheet_to_json(worksheet);

      // Parse Excel data - expected columns: 學號, 姓名, 排名
      const importData = jsonData.map((row: any) => ({
        student_id: row['學號'] || row['student_id'] || '',
        student_name: row['姓名'] || row['student_name'] || row['name'] || '',
        rank_position: parseInt(row['排名'] || row['rank_position'] || row['rank'] || '0'),
      })).filter(item => item.student_id && item.rank_position > 0);

      if (importData.length === 0) {
        toast.error("Excel 檔案中沒有找到有效的排名資料");
        setIsImporting(false);
        return;
      }

      // Call import handler if provided
      if (onImportExcel) {
        await onImportExcel(importData);
        toast.success(`成功匯入 ${importData.length} 筆排名資料`);
        setIsImportDialogOpen(false);
      }
    } catch (error) {
      console.error('Excel import error:', error);
      toast.error(error instanceof Error ? error.message : "無法讀取 Excel 檔案");
    } finally {
      setIsImporting(false);
      // Reset file input
      event.target.value = '';
    }
  };

  const handleTemplateDownload = () => {
    try {
      // Extract current students from localApplications with blank rankings
      const templateData = localApplications.map((app) => ({
        '學號': app.student_id || '',
        '姓名': app.student_name || '',
        '排名': '',  // Blank for user to fill
      }));

      // Create worksheet
      const worksheet = XLSX.utils.json_to_sheet(templateData);

      // Set column widths for better readability
      worksheet['!cols'] = [
        { wch: 15 },  // 學號
        { wch: 20 },  // 姓名
        { wch: 10 },  // 排名
      ];

      // Create workbook
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, '排名範本');

      // Generate filename
      const filename = `排名範本_${subTypeCode}_${academicYear}.xlsx`;

      // Download file
      XLSX.writeFile(workbook, filename);

      toast.success(`已下載範本檔案：${filename}`);
    } catch (error) {
      console.error('Template download error:', error);
      toast.error(error instanceof Error ? error.message : "無法產生範本檔案");
    }
  };

  const handleExportRanking = () => {
    try {
      // Prepare export data with all columns
      const exportData = localApplications.map((app) => {
        // Format eligible subtypes
        const eligibleSubtypes = app.eligible_subtypes
          ? app.eligible_subtypes.join(', ')
          : '-';

        // Format status
        let statusText = '';
        if (app.status === 'rejected') {
          statusText = locale === 'zh' ? '駁回' : 'Rejected';
        } else if (app.is_allocated) {
          statusText = locale === 'zh' ? '獲分配' : 'Allocated';
        } else {
          statusText = locale === 'zh' ? '未分配' : 'Not Allocated';
        }

        return {
          '排名': app.rank_position,
          '學號': app.student_id || '',
          '姓名': app.student_name || '',
          '學院': app.academy_name || '-',
          '系所': app.department_name || '-',
          '符合子類別': eligibleSubtypes,
          '狀態': statusText,
        };
      });

      // Create worksheet
      const worksheet = XLSX.utils.json_to_sheet(exportData);

      // Set column widths for better readability
      worksheet['!cols'] = [
        { wch: 8 },   // 排名
        { wch: 15 },  // 學號
        { wch: 20 },  // 姓名
        { wch: 20 },  // 學院
        { wch: 25 },  // 系所
        { wch: 30 },  // 符合子類別
        { wch: 12 },  // 狀態
      ];

      // Create workbook
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, '排名匯出');

      // Generate filename with timestamp
      const timestamp = new Date().toISOString().split('T')[0];
      const filename = `排名匯出_${subTypeCode}_${academicYear}_${timestamp}.xlsx`;

      // Download file
      XLSX.writeFile(workbook, filename);

      toast.success(`已匯出 ${exportData.length} 筆排名資料`);
    } catch (error) {
      console.error('Export error:', error);
      toast.error(error instanceof Error ? error.message : "無法匯出排名資料");
    }
  };

  const allocatedCount = localApplications.filter(
    app => app.is_allocated
  ).length;

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center">
              <Users className="h-8 w-8 text-blue-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">
                  {locale === "zh" ? "總申請數" : "Total Applications"}
                </p>
                <p className="text-2xl font-bold">{localApplications.length}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center">
              <CheckCircle className="h-8 w-8 text-emerald-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">
                  {locale === "zh" ? "已分配" : "Allocated"}
                </p>
                <p className="text-2xl font-bold text-emerald-600">
                  {allocatedCount}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Ranking Table */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Trophy className="h-5 w-5" />
                {locale === "zh" ? "申請排名" : "Application Ranking"}
                <Badge variant="outline">{subTypeCode}</Badge>
              </CardTitle>
              <CardDescription>
                {locale === "zh"
                  ? `學年度 ${academicYear} - ${formatSemesterLabel(semester)}`
                  : `AY ${academicYear} - ${formatSemesterLabel(semester)}`}
              </CardDescription>
            </div>

            <div className="flex gap-2">
              {!isFinalized && saveStatus !== 'idle' && (
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-md bg-gray-50 border">
                  {saveStatus === 'saving' && (
                    <>
                      <div className="h-2 w-2 bg-blue-500 rounded-full animate-pulse" />
                      <span className="text-sm text-blue-700">
                        {locale === 'zh' ? '儲存中...' : 'Saving...'}
                      </span>
                    </>
                  )}
                  {saveStatus === 'saved' && (
                    <>
                      <div className="h-2 w-2 bg-green-500 rounded-full" />
                      <span className="text-sm text-green-700">
                        {locale === 'zh' ? '已儲存' : 'Saved'}
                      </span>
                    </>
                  )}
                  {saveStatus === 'error' && (
                    <>
                      <div className="h-2 w-2 bg-red-500 rounded-full" />
                      <span className="text-sm text-red-700">
                        {locale === 'zh' ? '儲存失敗' : 'Save Failed'}
                      </span>
                    </>
                  )}
                </div>
              )}
              {!isFinalized && (
                <>
                  <Dialog open={isImportDialogOpen} onOpenChange={setIsImportDialogOpen}>
                    <DialogTrigger asChild>
                      <Button variant="outline" size="sm">
                        <Upload className="h-4 w-4 mr-2" />
                        {locale === "zh" ? "匯入排名" : "Import Ranking"}
                      </Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader>
                        <DialogTitle>
                          {locale === "zh" ? "匯入排名資料" : "Import Ranking Data"}
                        </DialogTitle>
                        <DialogDescription>
                          {locale === "zh"
                            ? "上傳包含學號、姓名、排名的 Excel 檔案"
                            : "Upload an Excel file containing Student ID, Name, and Rank"}
                        </DialogDescription>
                      </DialogHeader>

                      <div className="space-y-4">
                        {/* Instructions */}
                        <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                          <h4 className="text-sm font-semibold text-blue-900 mb-2">
                            {locale === "zh" ? "檔案格式要求" : "File Format Requirements"}
                          </h4>
                          <ul className="text-sm text-blue-800 space-y-1">
                            <li>• {locale === "zh" ? "Excel 格式 (.xlsx 或 .xls)" : "Excel format (.xlsx or .xls)"}</li>
                            <li>• {locale === "zh" ? "必需欄位：學號、姓名、排名" : "Required columns: Student ID, Name, Rank"}</li>
                            <li>• {locale === "zh" ? "排名必須為正整數 (1, 2, 3...)" : "Rank must be positive integers (1, 2, 3...)"}</li>
                          </ul>
                        </div>

                        {/* Template Download */}
                        <div className="flex items-center gap-2">
                          <FileSpreadsheet className="h-5 w-5 text-gray-500" />
                          <Button variant="link" className="text-sm p-0" onClick={handleTemplateDownload}>
                            {locale === "zh" ? "下載範本檔案" : "Download Template"}
                          </Button>
                        </div>

                        {/* File Upload */}
                        <div>
                          <label htmlFor="excel-upload" className="block text-sm font-medium mb-2">
                            {locale === "zh" ? "選擇檔案" : "Select File"}
                          </label>
                          <Input
                            id="excel-upload"
                            type="file"
                            accept=".xlsx,.xls"
                            onChange={handleFileUpload}
                            disabled={isImporting}
                          />
                        </div>

                        {isImporting && (
                          <div className="text-center py-4">
                            <p className="text-sm text-gray-600">
                              {locale === "zh" ? "正在處理檔案..." : "Processing file..."}
                            </p>
                          </div>
                        )}
                      </div>
                    </DialogContent>
                  </Dialog>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={onExecuteDistribution}
                  >
                    <Send className="h-4 w-4 mr-2" />
                    {locale === "zh" ? "執行分配" : "Execute Distribution"}
                  </Button>
                  <Button
                    variant="default"
                    size="sm"
                    onClick={() => onFinalizeRanking()}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    {locale === "zh" ? "確認排名" : "Finalize Ranking"}
                  </Button>
                </>
              )}

              <Button variant="outline" size="sm" onClick={handleExportRanking}>
                <Download className="h-4 w-4 mr-2" />
                {locale === "zh" ? "匯出" : "Export"}
              </Button>
            </div>
          </div>
        </CardHeader>

        <CardContent>
          {isFinalized && (
            <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800 flex items-center gap-2">
                <CheckCircle className="h-4 w-4" />
                {locale === "zh"
                  ? "此排名已確認，無法再修改"
                  : "This ranking has been finalized and cannot be modified"}
              </p>
            </div>
          )}

          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16">
                    {locale === "zh" ? "排名" : "Rank"}
                  </TableHead>
                  <TableHead className="w-48">
                    {locale === "zh" ? "學生" : "Student"}
                  </TableHead>
                  <TableHead className="w-36 text-center">
                    {locale === "zh" ? "學號" : "Student ID"}
                  </TableHead>
                  <TableHead className="w-40 text-center">
                    {locale === "zh" ? "學院/系所" : "College/Dept"}
                  </TableHead>
                  <TableHead className="text-center">
                    {locale === "zh" ? "符合子類別" : "Eligible Types"}
                  </TableHead>
                  <TableHead className="text-center">
                    {locale === "zh" ? "狀態" : "Status"}
                  </TableHead>
                  <TableHead className="text-center">
                    {locale === "zh" ? "操作" : "Actions"}
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <SortableContext
                  items={localApplications.map(app => app.id.toString())}
                  strategy={verticalListSortingStrategy}
                >
                  {localApplications.map((app, index) => (
                    <SortableItem
                      key={app.id}
                      application={app}
                      index={index}
                      totalQuota={totalQuota}
                      locale={locale}
                      isFinalized={isFinalized}
                      onReviewApplication={onReviewApplication}
                      reviewScores={reviewScores}
                      handleScoreUpdate={handleScoreUpdate}
                      subTypeMeta={subTypeMeta}
                      academicYear={academicYear}
                      onViewDetails={setSelectedAppForDialog}
                    />
                  ))}
                </SortableContext>
              </TableBody>
            </Table>
          </DndContext>
        </CardContent>
      </Card>

      {/* Quota Line Indicator */}
      {totalQuota < localApplications.length && (
        <Card className="border-orange-200 bg-orange-50">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-orange-800">
              <AlertCircle className="h-5 w-5" />
              <p className="font-medium">
                {locale === "zh"
                  ? `配額線: 前 ${totalQuota} 名學生將獲得分配`
                  : `Quota Line: Top ${totalQuota} students will be allocated`}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Application Review Dialog */}
      {selectedAppForDialog && (
        <ApplicationReviewDialog
          application={selectedAppForDialog as unknown as ApplicationType}
          role="college"
          open={!!selectedAppForDialog}
          onOpenChange={(open) => !open && setSelectedAppForDialog(null)}
          locale={locale}
          academicYear={academicYear}
          onApprove={(id, comments) => onReviewApplication(id, 'approve', comments)}
          onReject={(id, comments) => onReviewApplication(id, 'reject', comments)}
        />
      )}
    </div>
  );
}
