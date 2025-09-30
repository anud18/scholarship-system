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
  Calculator,
  FileText,
  Download,
  Send,
} from "lucide-react";
import { getTranslation } from "@/lib/i18n";

interface Application {
  id: number;
  app_id: string;
  student_name: string;
  student_no: string;
  scholarship_type: string;
  sub_type: string;
  total_score: number;
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
  semester?: string;
  isFinalized: boolean;
  onRankingChange: (newOrder: Application[]) => void;
  onReviewApplication: (applicationId: number) => void;
  onExecuteDistribution: () => void;
  onFinalizeRanking: () => void;
  locale?: "zh" | "en";
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
  calculateTotalScore,
}: {
  application: Application;
  index: number;
  totalQuota: number;
  locale: "zh" | "en";
  isFinalized: boolean;
  onReviewApplication: (applicationId: number) => void;
  reviewScores: { [key: number]: any };
  handleScoreUpdate: (appId: number, field: string, value: any) => void;
  calculateTotalScore: (scores: any) => string;
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
    if (app.is_allocated) {
      return (
        <Badge variant="default" className="bg-green-100 text-green-800">
          <CheckCircle className="w-3 h-3 mr-1" />
          {locale === "zh" ? "獲分配" : "Allocated"}
        </Badge>
      );
    } else {
      return (
        <Badge variant="secondary" className="bg-red-100 text-red-800">
          <XCircle className="w-3 h-3 mr-1" />
          {locale === "zh" ? "未分配" : "Not Allocated"}
        </Badge>
      );
    }
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
          <p className="font-medium">{application.student_name}</p>
          <p className="text-sm text-gray-500">{application.student_no}</p>
          <p className="text-xs text-gray-400">{application.app_id}</p>
        </div>
      </TableCell>

      <TableCell className="text-center">
        <div className="flex flex-col items-center gap-1">
          <Badge variant="outline" className="font-mono">
            {application.total_score?.toFixed(2) || "N/A"}
          </Badge>
        </div>
      </TableCell>

      <TableCell className="text-center">
        {getStatusBadge(application)}
      </TableCell>

      <TableCell className="text-center">
        <div className="flex justify-center gap-1">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="ghost" size="sm">
                <Eye className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>{application.student_name} - 審查詳情</DialogTitle>
                <DialogDescription>
                  {application.app_id} | 排名: #{application.rank_position}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                {/* Score Breakdown */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium">
                      學術成績 (30%)
                    </label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={reviewScores[application.id]?.academic || ""}
                      onChange={e =>
                        handleScoreUpdate(
                          application.id,
                          "academic",
                          Number(e.target.value)
                        )
                      }
                      disabled={isFinalized}
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium">
                      教授推薦 (40%)
                    </label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={
                        reviewScores[application.id]?.professor_review || ""
                      }
                      onChange={e =>
                        handleScoreUpdate(
                          application.id,
                          "professor_review",
                          Number(e.target.value)
                        )
                      }
                      disabled={isFinalized}
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium">
                      學院標準 (20%)
                    </label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={
                        reviewScores[application.id]?.college_criteria || ""
                      }
                      onChange={e =>
                        handleScoreUpdate(
                          application.id,
                          "college_criteria",
                          Number(e.target.value)
                        )
                      }
                      disabled={isFinalized}
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium">
                      特殊情況 (10%)
                    </label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={
                        reviewScores[application.id]?.special_circumstances ||
                        ""
                      }
                      onChange={e =>
                        handleScoreUpdate(
                          application.id,
                          "special_circumstances",
                          Number(e.target.value)
                        )
                      }
                      disabled={isFinalized}
                    />
                  </div>
                </div>

                {/* Total Score */}
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                  <div className="flex items-center justify-between">
                    <span className="font-medium">總分:</span>
                    <Badge variant="default" className="text-lg px-3 py-1">
                      {calculateTotalScore(reviewScores[application.id])}
                    </Badge>
                  </div>
                </div>

                {/* Review Comments */}
                <div>
                  <label className="text-sm font-medium">審查意見</label>
                  <Textarea
                    value={reviewScores[application.id]?.comments || ""}
                    onChange={e =>
                      handleScoreUpdate(
                        application.id,
                        "comments",
                        e.target.value
                      )
                    }
                    disabled={isFinalized}
                    rows={3}
                  />
                </div>

                {/* Recommendation */}
                <div>
                  <label className="text-sm font-medium">推薦結果</label>
                  <Select
                    value={reviewScores[application.id]?.recommendation || ""}
                    onValueChange={value =>
                      handleScoreUpdate(application.id, "recommendation", value)
                    }
                    disabled={isFinalized}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇推薦結果" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="approve">核准</SelectItem>
                      <SelectItem value="reject">駁回</SelectItem>
                      <SelectItem value="conditional">有條件核准</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {!isFinalized && (
                  <div className="flex justify-end gap-2">
                    <Button variant="outline">取消</Button>
                    <Button onClick={() => onReviewApplication(application.id)}>
                      <Save className="h-4 w-4 mr-2" />
                      儲存審查
                    </Button>
                  </div>
                )}
              </div>
            </DialogContent>
          </Dialog>
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
  onRankingChange,
  onReviewApplication,
  onExecuteDistribution,
  onFinalizeRanking,
  locale = "zh",
}: CollegeRankingTableProps) {
  const t = (key: string) => getTranslation(locale, key);

  const [localApplications, setLocalApplications] =
    useState<Application[]>(applications);
  const [selectedApplication, setSelectedApplication] =
    useState<Application | null>(null);
  const [reviewScores, setReviewScores] = useState<{ [key: number]: any }>({});

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

    setLocalApplications(items => {
      const oldIndex = items.findIndex(
        item => item.id.toString() === active.id
      );
      const newIndex = items.findIndex(item => item.id.toString() === over.id);

      const newItems = arrayMove(items, oldIndex, newIndex);

      // Update rank positions
      const updatedItems = newItems.map((item, index) => ({
        ...item,
        rank_position: index + 1,
        is_allocated: index < totalQuota, // Update allocation based on new position
      }));

      onRankingChange(updatedItems);
      return updatedItems;
    });
  };

  const handleScoreUpdate = (appId: number, field: string, value: number) => {
    setReviewScores(prev => ({
      ...prev,
      [appId]: {
        ...prev[appId],
        [field]: value,
      },
    }));
  };

  const calculateTotalScore = (scores: any) => {
    const weights = {
      academic: 0.3,
      professor_review: 0.4,
      college_criteria: 0.2,
      special_circumstances: 0.1,
    };

    return (
      (scores?.academic || 0) * weights.academic +
      (scores?.professor_review || 0) * weights.professor_review +
      (scores?.college_criteria || 0) * weights.college_criteria +
      (scores?.special_circumstances || 0) * weights.special_circumstances
    ).toFixed(2);
  };

  const allocatedCount = localApplications.filter(
    app => app.is_allocated
  ).length;
  const remainingQuota = Math.max(0, totalQuota - allocatedCount);

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
              <Trophy className="h-8 w-8 text-green-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">
                  {locale === "zh" ? "可分配配額" : "Available Quota"}
                </p>
                <p className="text-2xl font-bold">{totalQuota}</p>
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

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center">
              <AlertCircle className="h-8 w-8 text-orange-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-gray-600">
                  {locale === "zh" ? "剩餘配額" : "Remaining Quota"}
                </p>
                <p className="text-2xl font-bold text-orange-600">
                  {remainingQuota}
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
                  ? `學年度 ${academicYear}${semester ? ` - ${semester}` : ""}`
                  : `AY ${academicYear}${semester ? ` - ${semester}` : ""}`}
              </CardDescription>
            </div>

            <div className="flex gap-2">
              {!isFinalized && (
                <>
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
                    onClick={onFinalizeRanking}
                  >
                    <Save className="h-4 w-4 mr-2" />
                    {locale === "zh" ? "確認排名" : "Finalize Ranking"}
                  </Button>
                </>
              )}

              <Button variant="outline" size="sm">
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
                  <TableHead className="w-12">
                    {locale === "zh" ? "排名" : "Rank"}
                  </TableHead>
                  <TableHead>{locale === "zh" ? "學生" : "Student"}</TableHead>
                  <TableHead className="text-center">
                    {locale === "zh" ? "分數" : "Score"}
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
                      calculateTotalScore={calculateTotalScore}
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
    </div>
  );
}
