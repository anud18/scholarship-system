"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { apiClient } from "@/lib/api";
import type {
  DistributionStudent,
  QuotaStatus,
} from "@/lib/api/modules/manual-distribution";
import { User } from "@/types/user";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Loader2, Save, CheckCircle2, AlertCircle } from "lucide-react";

interface ManualDistributionPanelProps {
  user: User;
  scholarshipType: { code: string; name: string };
}

export function ManualDistributionPanel({
  scholarshipType,
}: ManualDistributionPanelProps) {
  const {
    scholarshipConfig,
    selectedAcademicYear,
    selectedSemester,
  } = useCollegeManagement();

  // Resolve the scholarship type ID from config
  const scholarshipTypeId = useMemo(() => {
    const config = scholarshipConfig.find(
      (c) => c.code === scholarshipType.code || c.name === scholarshipType.name
    );
    return config?.id ?? null;
  }, [scholarshipConfig, scholarshipType]);

  const [students, setStudents] = useState<DistributionStudent[]>([]);
  const [quotaStatus, setQuotaStatus] = useState<QuotaStatus>({});
  const [localAllocations, setLocalAllocations] = useState<Map<number, string | null>>(new Map());
  const [collegeFilter, setCollegeFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const subTypeKeys = useMemo(() => Object.keys(quotaStatus), [quotaStatus]);

  // Compute locally-adjusted quota counts
  const localQuotaCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const subType of subTypeKeys) {
      counts[subType] = 0;
    }
    for (const [, subType] of localAllocations) {
      if (subType) {
        counts[subType] = (counts[subType] ?? 0) + 1;
      }
    }
    return counts;
  }, [localAllocations, subTypeKeys]);

  const fetchData = useCallback(async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester) return;
    setIsLoading(true);
    setSaveMessage(null);
    try {
      const [studentsResp, quotaResp] = await Promise.all([
        apiClient.manualDistribution.getStudents(
          scholarshipTypeId,
          selectedAcademicYear,
          selectedSemester
        ),
        apiClient.manualDistribution.getQuotaStatus(
          scholarshipTypeId,
          selectedAcademicYear,
          selectedSemester
        ),
      ]);

      if (studentsResp.success && studentsResp.data) {
        setStudents(studentsResp.data);
        // Initialize localAllocations from server state
        const initial = new Map<number, string | null>();
        for (const s of studentsResp.data) {
          initial.set(s.ranking_item_id, s.allocated_sub_type);
        }
        setLocalAllocations(initial);
      }
      if (quotaResp.success && quotaResp.data) {
        setQuotaStatus(quotaResp.data);
      }
    } finally {
      setIsLoading(false);
    }
  }, [scholarshipTypeId, selectedAcademicYear, selectedSemester]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCheckbox = (rankingItemId: number, subTypeCode: string) => {
    setLocalAllocations((prev) => {
      const next = new Map(prev);
      // Radio-like: if already checked, uncheck; otherwise set exclusively
      const current = next.get(rankingItemId);
      next.set(rankingItemId, current === subTypeCode ? null : subTypeCode);
      return next;
    });
  };

  const handleSave = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const allocations = Array.from(localAllocations.entries()).map(
        ([ranking_item_id, sub_type_code]) => ({ ranking_item_id, sub_type_code })
      );
      const resp = await apiClient.manualDistribution.allocate({
        scholarship_type_id: scholarshipTypeId,
        academic_year: selectedAcademicYear,
        semester: selectedSemester,
        allocations,
      });
      if (resp.success) {
        setSaveMessage({ type: "success", text: `已儲存 ${resp.data?.updated_count ?? 0} 筆分配` });
        // Refresh quota from server
        const quotaResp = await apiClient.manualDistribution.getQuotaStatus(
          scholarshipTypeId,
          selectedAcademicYear,
          selectedSemester
        );
        if (quotaResp.success && quotaResp.data) {
          setQuotaStatus(quotaResp.data);
        }
      } else {
        setSaveMessage({ type: "error", text: resp.message || "儲存失敗" });
      }
    } catch {
      setSaveMessage({ type: "error", text: "儲存時發生錯誤" });
    } finally {
      setIsSaving(false);
    }
  };

  const handleFinalize = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester) return;
    setIsFinalizing(true);
    setSaveMessage(null);
    try {
      const resp = await apiClient.manualDistribution.finalize({
        scholarship_type_id: scholarshipTypeId,
        academic_year: selectedAcademicYear,
        semester: selectedSemester,
      });
      if (resp.success && resp.data) {
        setSaveMessage({
          type: "success",
          text: `分發完成：核准 ${resp.data.approved_count} 人，拒絕 ${resp.data.rejected_count} 人`,
        });
        await fetchData();
      } else {
        setSaveMessage({ type: "error", text: resp.message || "確認分發失敗" });
      }
    } catch {
      setSaveMessage({ type: "error", text: "確認分發時發生錯誤" });
    } finally {
      setIsFinalizing(false);
    }
  };

  // Filter students
  const filteredStudents = useMemo(() => {
    return students.filter((s) => {
      if (collegeFilter && s.college_code !== collegeFilter) return false;
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        return (
          s.student_name.toLowerCase().includes(q) ||
          s.student_id.toLowerCase().includes(q) ||
          s.department_name.toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [students, collegeFilter, searchQuery]);

  // Unique college codes for filter dropdown
  const collegeCodes = useMemo(
    () => Array.from(new Set(students.map((s) => s.college_code).filter(Boolean))).sort(),
    [students]
  );

  if (!scholarshipTypeId) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>無法找到獎學金類型設定，請重新整理頁面。</AlertDescription>
      </Alert>
    );
  }

  if (!selectedAcademicYear || !selectedSemester) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>請先選擇學年度與學期。</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="flex gap-4">
      {/* Main content - 3/4 width */}
      <div className="flex-1 min-w-0">
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">手動分發 — {scholarshipType.name}</CardTitle>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSave}
                  disabled={isSaving || isLoading}
                >
                  {isSaving ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                  ) : (
                    <Save className="h-4 w-4 mr-1" />
                  )}
                  儲存
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="sm" disabled={isFinalizing || isLoading || isSaving}>
                      {isFinalizing ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-1" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 mr-1" />
                      )}
                      確認分發
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>確認執行分發？</AlertDialogTitle>
                      <AlertDialogDescription>
                        確認後將鎖定分發結果，已分配的申請將標記為「核准」，未分配的將標記為「拒絕」。此操作無法還原。
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>取消</AlertDialogCancel>
                      <AlertDialogAction onClick={handleFinalize}>確認執行</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>

            {/* Filter bar */}
            <div className="flex gap-2 mt-3">
              <select
                className="border rounded px-2 py-1 text-sm"
                value={collegeFilter}
                onChange={(e) => setCollegeFilter(e.target.value)}
              >
                <option value="">全部學院</option>
                {collegeCodes.map((code) => (
                  <option key={code} value={code}>
                    {students.find((s) => s.college_code === code)?.college_name || code}
                  </option>
                ))}
              </select>
              <Input
                className="h-8 text-sm"
                placeholder="搜尋姓名、學號、系所..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </CardHeader>

          <CardContent className="p-0">
            {saveMessage && (
              <div className={`mx-4 mb-3 p-2 rounded text-sm ${saveMessage.type === "success" ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"}`}>
                {saveMessage.text}
              </div>
            )}

            {isLoading ? (
              <div className="flex justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="bg-gray-50 border-b">
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">排名</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">申請類型</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">學院</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">系所</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">年級</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">姓名</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">國籍</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">入學日期</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">學號</th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600 whitespace-nowrap">申請性質</th>
                      {subTypeKeys.map((key) => (
                        <th
                          key={key}
                          className="px-3 py-2 text-center font-medium text-gray-600 whitespace-nowrap"
                        >
                          {quotaStatus[key]?.display_name || key}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredStudents.length === 0 ? (
                      <tr>
                        <td colSpan={10 + subTypeKeys.length} className="px-4 py-8 text-center text-gray-500">
                          {students.length === 0 ? "尚無已確認排名的學生資料" : "無符合篩選條件的學生"}
                        </td>
                      </tr>
                    ) : (
                      filteredStudents.map((student) => {
                        const allocated = localAllocations.get(student.ranking_item_id);
                        return (
                          <tr
                            key={student.ranking_item_id}
                            className="border-b hover:bg-gray-50 transition-colors"
                          >
                            <td className="px-3 py-2 font-medium">{student.rank_position}</td>
                            <td className="px-3 py-2">
                              <div className="flex flex-wrap gap-1">
                                {student.applied_sub_types.map((t) => (
                                  <Badge key={t} variant="outline" className="text-xs">
                                    {t}
                                  </Badge>
                                ))}
                              </div>
                            </td>
                            <td className="px-3 py-2 whitespace-nowrap">{student.college_name || student.college_code}</td>
                            <td className="px-3 py-2 whitespace-nowrap">{student.department_name}</td>
                            <td className="px-3 py-2 whitespace-nowrap">{student.grade}</td>
                            <td className="px-3 py-2 whitespace-nowrap font-medium">{student.student_name}</td>
                            <td className="px-3 py-2 whitespace-nowrap">{student.nationality}</td>
                            <td className="px-3 py-2 whitespace-nowrap">{student.enrollment_date}</td>
                            <td className="px-3 py-2 whitespace-nowrap font-mono text-xs">{student.student_id}</td>
                            <td className="px-3 py-2 whitespace-nowrap">{student.application_identity}</td>
                            {subTypeKeys.map((key) => {
                              const isChecked = allocated === key;
                              const applicable = student.applied_sub_types.includes(key);
                              return (
                                <td key={key} className="px-3 py-2 text-center">
                                  <input
                                    type="checkbox"
                                    className="h-4 w-4 cursor-pointer"
                                    checked={isChecked}
                                    disabled={!applicable}
                                    title={applicable ? `分配至 ${quotaStatus[key]?.display_name || key}` : "學生未申請此類型"}
                                    onChange={() => handleCheckbox(student.ranking_item_id, key)}
                                  />
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Quota sidebar - 1/4 width */}
      <div className="w-64 shrink-0">
        <Card className="sticky top-4">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">配額狀況</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {subTypeKeys.length === 0 ? (
              <p className="text-sm text-gray-500">尚無配額資料</p>
            ) : (
              subTypeKeys.map((key) => {
                const status = quotaStatus[key];
                if (!status) return null;
                const localCount = localQuotaCounts[key] ?? 0;
                const remaining = status.total - localCount;
                const color =
                  remaining <= 0
                    ? "text-red-600 bg-red-50"
                    : remaining <= 2
                    ? "text-amber-600 bg-amber-50"
                    : "text-green-600 bg-green-50";
                return (
                  <div key={key} className={`rounded p-2 ${color}`}>
                    <div className="font-medium text-sm">{status.display_name}</div>
                    <div className="text-xs mt-1">
                      已分配：{localCount} / {status.total}
                      <span className="ml-2">剩餘：{remaining}</span>
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
