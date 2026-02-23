"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { apiClient } from "@/lib/api";
import type {
  DistributionStudent,
  QuotaStatus,
} from "@/lib/api/modules/manual-distribution";
import { User } from "@/types/user";
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
import { Loader2, Save, CheckCircle2, AlertCircle, Download } from "lucide-react";

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
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    availableOptions,
  } = useCollegeManagement();

  const semesterLabel = (s: string) => {
    if (s === "first") return "第一學期";
    if (s === "second") return "第二學期";
    if (s === "yearly") return "全年";
    return s;
  };

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

  // Count local allocations per sub-type
  const localAllocCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const subType of subTypeKeys) counts[subType] = 0;
    for (const [, subType] of localAllocations) {
      if (subType) counts[subType] = (counts[subType] ?? 0) + 1;
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
      // Radio-like: clicking checked → uncheck; clicking unchecked → set exclusively
      next.set(rankingItemId, next.get(rankingItemId) === subTypeCode ? null : subTypeCode);
      return next;
    });
  };

  const handleSave = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const allocations = Array.from(localAllocations.entries()).map(
        ([ranking_item_id, sub_type_code]: [number, string | null]) => ({ ranking_item_id, sub_type_code })
      );
      const resp = await apiClient.manualDistribution.allocate({
        scholarship_type_id: scholarshipTypeId,
        academic_year: selectedAcademicYear,
        semester: selectedSemester,
        allocations,
      });
      if (resp.success) {
        setSaveMessage({ type: "success", text: `已儲存 ${resp.data?.updated_count ?? 0} 筆分配` });
        const quotaResp = await apiClient.manualDistribution.getQuotaStatus(
          scholarshipTypeId,
          selectedAcademicYear,
          selectedSemester
        );
        if (quotaResp.success && quotaResp.data) setQuotaStatus(quotaResp.data);
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

  // Apply filters
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

  // Group students by college
  const studentsByCollege = useMemo(() => {
    const groups: { collegeCode: string; collegeName: string; students: DistributionStudent[] }[] = [];
    const seen = new Map<string, DistributionStudent[]>();
    for (const s of filteredStudents) {
      const key = s.college_code || "";
      if (!seen.has(key)) {
        seen.set(key, []);
        groups.push({ collegeCode: key, collegeName: s.college_name || key, students: seen.get(key)! });
      }
      seen.get(key)!.push(s);
    }
    return groups;
  }, [filteredStudents]);

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
      {/* Main table area — 3/4 width */}
      <div className="flex-1 min-w-0 space-y-3">

        {/* Top bar: title + filters + actions */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h2 className="font-bold text-base flex items-center gap-2 text-slate-800">
              手動分發 — {scholarshipType.name}
            </h2>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" disabled>
                <Download className="h-4 w-4 mr-1" />
                匯出 Excel
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleSave}
                disabled={isSaving || isLoading}
              >
                {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                儲存目前配置
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button size="sm" disabled={isFinalizing || isLoading || isSaving}>
                    {isFinalizing ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <CheckCircle2 className="h-4 w-4 mr-1" />}
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

          {/* Filters row */}
          <div className="flex flex-wrap gap-2 items-end">
            {/* Academic year */}
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">學年度</label>
              <select
                className="border rounded px-2 py-1.5 text-sm border-slate-200"
                value={selectedAcademicYear ?? ""}
                onChange={(e) => setSelectedAcademicYear(e.target.value ? Number(e.target.value) : undefined)}
              >
                <option value="">選擇學年度</option>
                {(availableOptions?.academic_years ?? []).map((yr) => (
                  <option key={yr} value={yr}>{yr} 學年度</option>
                ))}
              </select>
            </div>
            {/* Semester */}
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">學期</label>
              <select
                className="border rounded px-2 py-1.5 text-sm border-slate-200"
                value={selectedSemester ?? ""}
                onChange={(e) => setSelectedSemester(e.target.value || undefined)}
              >
                <option value="">選擇學期</option>
                {(availableOptions?.semesters ?? []).map((s) => (
                  <option key={s} value={s}>{semesterLabel(s)}</option>
                ))}
              </select>
            </div>
            {/* College filter */}
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">所屬學院</label>
              <select
                className="border rounded px-2 py-1.5 text-sm border-slate-200"
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
            </div>
            {/* Search */}
            <div className="flex flex-col gap-1 flex-1 min-w-[180px]">
              <label className="text-xs font-medium text-slate-500">學生姓名 / 學號</label>
              <Input
                className="h-[34px] text-sm border-slate-200"
                placeholder="搜尋姓名、學號、系所..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Save message */}
        {saveMessage && (
          <div className={`px-4 py-2 rounded text-sm ${saveMessage.type === "success" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}>
            {saveMessage.text}
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-3 border-b border-slate-200 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">學生申請名冊與核配作業</span>
            <span className="text-xs text-slate-400">
              {filteredStudents.length > 0
                ? `共 ${filteredStudents.length} 筆紀錄`
                : students.length > 0
                ? "無符合篩選條件的學生"
                : ""}
            </span>
          </div>

          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-sm" style={{ minWidth: `${900 + subTypeKeys.length * 90}px` }}>
                <thead className="bg-slate-50 text-[13px] text-slate-600">
                  {/* Row 1 */}
                  <tr>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 text-center font-semibold w-14 whitespace-nowrap">
                      學院<br/>初審<br/>排序
                    </th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold w-44">
                      申請獎學金類別
                    </th>
                    {subTypeKeys.length > 0 && (
                      <th
                        colSpan={subTypeKeys.length}
                        className="px-3 py-2 border border-slate-200 text-center font-semibold bg-blue-50 text-blue-700"
                      >
                        獲獎獎學金類別（核配勾選）
                      </th>
                    )}
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap">學院</th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap">系所</th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 text-center font-semibold w-14">年級</th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap">學生姓名</th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap">國籍</th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap text-red-600">
                      入學日期<br/>(民國年)
                    </th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap">學號</th>
                    <th rowSpan={2} className="px-3 py-2 border border-slate-200 font-semibold whitespace-nowrap">申請身份</th>
                  </tr>
                  {/* Row 2 — sub-type column names */}
                  {subTypeKeys.length > 0 && (
                    <tr className="bg-blue-50/50 text-[11px] text-center">
                      {subTypeKeys.map((key) => (
                        <th key={key} className="px-2 py-1.5 border border-slate-200 text-slate-500 whitespace-nowrap">
                          {quotaStatus[key]?.display_name || key}
                        </th>
                      ))}
                    </tr>
                  )}
                </thead>
                <tbody>
                  {filteredStudents.length === 0 ? (
                    <tr>
                      <td
                        colSpan={9 + subTypeKeys.length}
                        className="px-4 py-10 text-center text-slate-500"
                      >
                        {students.length === 0
                          ? "尚無已確認排名的學生資料"
                          : "無符合篩選條件的學生"}
                      </td>
                    </tr>
                  ) : (
                    studentsByCollege.map(({ collegeCode, collegeName, students: collegeStudents }) => (
                      <>
                        {/* College group header */}
                        <tr key={`group-${collegeCode}`} className="bg-slate-100">
                          <td
                            colSpan={9 + subTypeKeys.length}
                            className="px-4 py-1.5 text-xs font-bold text-slate-600 border-y border-slate-300"
                          >
                            {collegeName || collegeCode}
                          </td>
                        </tr>
                        {collegeStudents.map((student) => {
                          const allocated = localAllocations.get(student.ranking_item_id);
                          return (
                            <tr
                              key={student.ranking_item_id}
                              className="border-b border-slate-100 hover:bg-slate-50 transition-colors"
                            >
                              <td className="px-3 py-2.5 border-r border-slate-100 text-center font-bold text-slate-700">
                                {student.rank_position}
                              </td>
                              <td className="px-3 py-2.5 border-r border-slate-100 leading-snug">
                                {student.applied_sub_types.length > 0 ? (
                                  student.applied_sub_types.map((t, i) => (
                                    <div key={t} className="text-[11px] text-slate-600">
                                      {i + 1}. {quotaStatus[t]?.display_name || t}
                                    </div>
                                  ))
                                ) : (
                                  <span className="text-[11px] text-slate-400">—</span>
                                )}
                              </td>
                              {subTypeKeys.map((key) => {
                                const isChecked = allocated === key;
                                const atCapacity =
                                  !!quotaStatus[key] &&
                                  quotaStatus[key].total > 0 &&
                                  localAllocCounts[key] >= quotaStatus[key].total &&
                                  !isChecked;
                                return (
                                  <td key={key} className="px-2 py-2.5 border-r border-slate-100 text-center">
                                    <input
                                      type="checkbox"
                                      className="h-5 w-5 cursor-pointer rounded accent-blue-600"
                                      checked={isChecked}
                                      disabled={atCapacity}
                                      title={
                                        atCapacity
                                          ? `${quotaStatus[key]?.display_name || key} 名額已滿`
                                          : isChecked
                                          ? "點擊取消分配"
                                          : `分配至 ${quotaStatus[key]?.display_name || key}`
                                      }
                                      onChange={() => handleCheckbox(student.ranking_item_id, key)}
                                    />
                                  </td>
                                );
                              })}
                              <td className="px-3 py-2.5 border-r border-slate-100 whitespace-nowrap">{student.college_name || student.college_code}</td>
                              <td className="px-3 py-2.5 border-r border-slate-100 whitespace-nowrap">{student.department_name}</td>
                              <td className="px-3 py-2.5 border-r border-slate-100 text-center whitespace-nowrap">{student.grade}</td>
                              <td className="px-3 py-2.5 border-r border-slate-100 font-medium whitespace-nowrap">{student.student_name}</td>
                              <td className="px-3 py-2.5 border-r border-slate-100 text-slate-500 whitespace-nowrap">{student.nationality}</td>
                              <td className="px-3 py-2.5 border-r border-slate-100 text-center tabular-nums whitespace-nowrap">{student.enrollment_date}</td>
                              <td className="px-3 py-2.5 border-r border-slate-100 font-mono text-xs whitespace-nowrap">{student.student_id}</td>
                              <td className="px-3 py-2.5 text-xs font-semibold whitespace-nowrap">
                                <span className={
                                  student.application_identity.includes("新申請")
                                    ? "text-amber-600"
                                    : "text-blue-600"
                                }>
                                  {student.application_identity}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Usage tip */}
        <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg flex gap-2 text-xs text-blue-800">
          <span className="shrink-0 mt-0.5">ℹ️</span>
          <ul className="list-disc list-inside space-y-0.5">
            <li>依「學院初審排序」手動勾選欲核配的獎學金類別，每位學生限勾選一項。</li>
            <li>右側「即時剩餘名額」即時反映目前勾選狀況；額度用罄後該欄位停用。</li>
            <li>核配完成後點擊「儲存目前配置」，確認無誤後再執行「確認分發」。</li>
          </ul>
        </div>
      </div>

      {/* Quota sidebar — fixed width */}
      <div className="w-56 shrink-0">
        <div className="sticky top-4 bg-white rounded-xl border-2 border-blue-200 shadow-sm overflow-hidden">
          <div className="bg-blue-600 px-4 py-2.5 flex items-center justify-between">
            <span className="text-white font-bold text-sm">即時剩餘名額</span>
            <span className="text-[10px] bg-white/20 text-white px-2 py-0.5 rounded-full">Auto-Sync</span>
          </div>
          <div className="p-3 space-y-2">
            {subTypeKeys.length === 0 ? (
              <p className="text-xs text-slate-400 py-2 text-center">尚無配額資料</p>
            ) : (
              subTypeKeys.map((key) => {
                const q = quotaStatus[key];
                if (!q) return null;
                const used = localAllocCounts[key] ?? 0;
                const remaining = q.total - used;
                const isFull = remaining <= 0;
                const isLow = !isFull && remaining <= 2;
                return (
                  <div
                    key={key}
                    className={`flex items-center justify-between px-3 py-2 rounded-lg ${
                      isFull
                        ? "bg-red-50 border border-red-200"
                        : isLow
                        ? "bg-amber-50 border border-amber-200"
                        : "bg-slate-50 border border-slate-100"
                    }`}
                  >
                    <span className="text-xs text-slate-600 leading-tight">{q.display_name}</span>
                    <span className={`text-sm font-bold tabular-nums ${
                      isFull ? "text-red-600" : isLow ? "text-amber-600" : "text-blue-700"
                    }`}>
                      {used.toString().padStart(2, "0")} / {q.total.toString().padStart(2, "0")}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
