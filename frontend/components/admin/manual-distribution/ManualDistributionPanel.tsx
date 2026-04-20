"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { apiClient } from "@/lib/api";
import type {
  DistributionStudent,
  QuotaStatus,
  SubTypeYearCol,
  DistributionHistoryRecord,
  RestoreRequest,
  DistributionSummaryResult,
  DistributionSummaryGroup,
  AllocationSuggestion,
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
import {
  Loader2,
  Save,
  CheckCircle2,
  AlertCircle,
  Download,
  Clock,
  Eye,
} from "lucide-react";

interface ManualDistributionPanelProps {
  user: User;
  scholarshipType: { id: number; code: string; name: string };
}

/** Local allocation state for a student: which (sub_type, year) they're assigned to */
interface LocalAlloc {
  sub_type: string;
  year: number;
}

/** Composite key for a (sub_type, year) column: "nstc:114" */
function makeColKey(sub_type: string, year: number) {
  return `${sub_type}:${year}`;
}

/**
 * Derive abbreviated display name from sub_type code and full display_name.
 * nstc           → "國科會"
 * moe_1w/moe_2w  → "教育部+1" / "教育部+2"
 * other          → truncated display_name
 */
function getSubTypeShortName(sub_type: string, display_name: string): string {
  if (sub_type === "nstc") return "國科會";
  const moeMatch = sub_type.match(/^moe_(\d+)w$/);
  if (moeMatch) return `教育部+${moeMatch[1]}`;
  return display_name.length > 7
    ? display_name.slice(0, 6) + "…"
    : display_name;
}

export function ManualDistributionPanel({
  scholarshipType,
}: ManualDistributionPanelProps) {
  const {
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

  // Use the ID directly from the prop (provided by the admin available-combinations endpoint)
  const scholarshipTypeId = scholarshipType.id;

  const [students, setStudents] = useState<DistributionStudent[]>([]);
  const [quotaStatus, setQuotaStatus] = useState<QuotaStatus>({});
  // Map<ranking_item_id, LocalAlloc | null>
  const [localAllocations, setLocalAllocations] = useState<
    Map<number, LocalAlloc | null>
  >(new Map());
  const [collegeFilter, setCollegeFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [saveMessage, setSaveMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [history, setHistory] = useState<DistributionHistoryRecord[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [showHistoryDialog, setShowHistoryDialog] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [isGeneratingRosters, setIsGeneratingRosters] = useState(false);
  const [showDistributionSummary, setShowDistributionSummary] = useState(false);
  const [isLoadingSummary, setIsLoadingSummary] = useState(false);
  const [distributionSummary, setDistributionSummary] =
    useState<DistributionSummaryResult | null>(null);
  const [rosterResult, setRosterResult] = useState<{
    rosters_created: number;
    rosters: Array<{
      roster_code: string;
      sub_type: string;
      allocation_year: number;
      project_number: string | null;
      qualified_count: number;
      total_amount: string;
    }>;
  } | null>(null);
  const [previewApplied, setPreviewApplied] = useState(false);

  /**
   * Flatten quota status into (sub_type × year) columns, ordered by:
   * - sub_type (by appearance order in quotaStatus keys)
   * - year descending (current year first, then prior years)
   */
  const subTypeCols = useMemo<SubTypeYearCol[]>(() => {
    const cols: SubTypeYearCol[] = [];
    for (const [sub_type, stData] of Object.entries(quotaStatus)) {
      const years = Object.keys(stData.by_year)
        .map(Number)
        .sort((a, b) => b - a); // descending: 114, 113, 112
      const isMultiYear = years.length > 1;
      const shortName = getSubTypeShortName(sub_type, stData.display_name);
      for (const year of years) {
        const yData = stData.by_year[String(year)];
        if (!yData || yData.total <= 0) continue;
        // Multi-year sub-types (e.g. nstc): prefix with year → "114 國科會", "113 國科會"
        // Single-year sub-types (e.g. moe_1w): just the short name → "教育部+1"
        const display_name = isMultiYear ? `${year} ${shortName}` : shortName;
        cols.push({
          sub_type,
          year,
          display_name,
          total: yData.total,
          remaining: yData.remaining,
          key: makeColKey(sub_type, year),
        });
      }
    }
    return cols;
  }, [quotaStatus]);

  /** Count how many local allocations are using each (sub_type, year) slot */
  const localAllocCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const col of subTypeCols) counts[col.key] = 0;
    for (const [, alloc] of localAllocations) {
      if (alloc) {
        const k = makeColKey(alloc.sub_type, alloc.year);
        counts[k] = (counts[k] ?? 0) + 1;
      }
    }
    return counts;
  }, [localAllocations, subTypeCols]);

  const fetchData = useCallback(async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    setIsLoading(true);
    setSaveMessage(null);
    setPreviewApplied(false);
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
        const allocMap = new Map<number, LocalAlloc | null>();
        for (const s of studentsResp.data) {
          if (s.allocated_sub_type) {
            allocMap.set(s.ranking_item_id, {
              sub_type: s.allocated_sub_type,
              year: s.allocation_year ?? selectedAcademicYear!,
            });
          } else {
            allocMap.set(s.ranking_item_id, null);
          }
        }

        // Load preview separately (optional — failure should not break the page)
        let previewSuggestions: AllocationSuggestion[] = [];
        try {
          const previewResp =
            await apiClient.manualDistribution.getAutoAllocatePreview(
              scholarshipTypeId,
              selectedAcademicYear,
              selectedSemester
            );
          if (previewResp.success && previewResp.data) {
            previewSuggestions = previewResp.data.suggestions;
          }
        } catch {
          // Preview is optional; proceed without it
        }

        // Apply auto-preview suggestions for unallocated students
        let hasPreview = false;
        for (const suggestion of previewSuggestions) {
          if (
            suggestion.sub_type_code &&
            suggestion.allocation_year &&
            !allocMap.get(suggestion.ranking_item_id)
          ) {
            allocMap.set(suggestion.ranking_item_id, {
              sub_type: suggestion.sub_type_code,
              year: suggestion.allocation_year,
            });
            hasPreview = true;
          }
        }
        setPreviewApplied(hasPreview);

        setLocalAllocations(allocMap);
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

  const handleCheckbox = (
    rankingItemId: number,
    sub_type: string,
    year: number
  ) => {
    setLocalAllocations(prev => {
      const next = new Map(prev);
      const cur = next.get(rankingItemId);
      // Radio-like: clicking active → uncheck; clicking other → set exclusively
      if (cur?.sub_type === sub_type && cur?.year === year) {
        next.set(rankingItemId, null);
      } else {
        next.set(rankingItemId, { sub_type, year });
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const allocations = Array.from(localAllocations.entries()).map(
        ([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_year: alloc?.year ?? null,
        })
      );
      const resp = await apiClient.manualDistribution.allocate({
        scholarship_type_id: scholarshipTypeId,
        academic_year: selectedAcademicYear,
        semester: selectedSemester,
        allocations,
      });
      if (resp.success) {
        setSaveMessage({
          type: "success",
          text: `已儲存 ${resp.data?.updated_count ?? 0} 筆分配`,
        });
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
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
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
        // Reload data directly instead of using fetchData
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
          const initial = new Map<number, LocalAlloc | null>();
          for (const s of studentsResp.data) {
            if (s.allocated_sub_type) {
              initial.set(s.ranking_item_id, {
                sub_type: s.allocated_sub_type,
                year: s.allocation_year ?? selectedAcademicYear!,
              });
            } else {
              initial.set(s.ranking_item_id, null);
            }
          }
          setLocalAllocations(initial);
        }
        if (quotaResp.success && quotaResp.data) {
          setQuotaStatus(quotaResp.data);
        }
      } else {
        setSaveMessage({ type: "error", text: resp.message || "確認分發失敗" });
      }
    } catch (error) {
      console.error("Finalize error:", error);
      setSaveMessage({ type: "error", text: "確認分發時發生錯誤" });
    } finally {
      setIsFinalizing(false);
    }
  };

  const handleGenerateRosters = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    setIsGeneratingRosters(true);
    setSaveMessage(null);
    setRosterResult(null);
    try {
      const resp =
        await apiClient.manualDistribution.generateRostersFromDistribution({
          scholarship_type_id: scholarshipTypeId,
          academic_year: selectedAcademicYear,
          semester: selectedSemester,
          student_verification_enabled: false,
        });
      if (resp.success && resp.data) {
        setRosterResult(resp.data);
        setSaveMessage({
          type: "success",
          text: `已產生 ${resp.data.rosters_created} 個造冊`,
        });
      } else {
        setSaveMessage({ type: "error", text: resp.message || "造冊產生失敗" });
      }
    } catch (error) {
      console.error("Generate rosters error:", error);
      setSaveMessage({ type: "error", text: "造冊產生時發生錯誤" });
    } finally {
      setIsGeneratingRosters(false);
    }
  };

  const loadDistributionSummary = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    setIsLoadingSummary(true);
    setDistributionSummary(null);
    setShowDistributionSummary(true);
    try {
      const resp = await apiClient.manualDistribution.getDistributionSummary(
        scholarshipTypeId,
        selectedAcademicYear,
        selectedSemester
      );
      if (resp.success && resp.data) {
        setDistributionSummary(resp.data);
      } else {
        setSaveMessage({
          type: "error",
          text: resp.message || "無法載入分發名單",
        });
      }
    } catch (error) {
      console.error("Load distribution summary error:", error);
      setSaveMessage({ type: "error", text: "載入分發名單時發生錯誤" });
    } finally {
      setIsLoadingSummary(false);
    }
  };

  const loadHistory = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    setIsLoadingHistory(true);
    try {
      const resp = await apiClient.manualDistribution.getHistory(
        scholarshipTypeId,
        selectedAcademicYear,
        selectedSemester
      );
      if (resp.success && resp.data) {
        setHistory(resp.data);
        setShowHistoryDialog(true);
      } else {
        setSaveMessage({
          type: "error",
          text: resp.message || "載入歷史記錄失敗",
        });
      }
    } catch (error) {
      console.error("Load history error:", error);
      setSaveMessage({ type: "error", text: "載入歷史記錄失敗" });
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleRestore = async (historyId: number) => {
    if (!scholarshipTypeId) return;
    setIsRestoring(true);
    try {
      const resp = await apiClient.manualDistribution.restoreFromHistory(
        scholarshipTypeId,
        { history_id: historyId }
      );
      if (resp.success && resp.data) {
        setSaveMessage({
          type: "success",
          text: `成功還原 ${resp.data.restored_count} 筆分配紀錄`,
        });
        setShowHistoryDialog(false);
        // Reload data by calling the fetch function directly
        const [studentsResp, quotaResp] = await Promise.all([
          apiClient.manualDistribution.getStudents(
            scholarshipTypeId,
            selectedAcademicYear!,
            selectedSemester!
          ),
          apiClient.manualDistribution.getQuotaStatus(
            scholarshipTypeId,
            selectedAcademicYear!,
            selectedSemester!
          ),
        ]);
        if (studentsResp.success && studentsResp.data) {
          setStudents(studentsResp.data);
          const initial = new Map<number, LocalAlloc | null>();
          for (const s of studentsResp.data) {
            if (s.allocated_sub_type) {
              initial.set(s.ranking_item_id, {
                sub_type: s.allocated_sub_type,
                year: s.allocation_year ?? selectedAcademicYear!,
              });
            } else {
              initial.set(s.ranking_item_id, null);
            }
          }
          setLocalAllocations(initial);
        }
        if (quotaResp.success && quotaResp.data) {
          setQuotaStatus(quotaResp.data);
        }
      } else {
        setSaveMessage({ type: "error", text: resp.message || "還原失敗" });
      }
    } catch (error) {
      console.error("Restore error:", error);
      setSaveMessage({ type: "error", text: "還原時發生錯誤" });
    } finally {
      setIsRestoring(false);
    }
  };

  // Apply filters
  const filteredStudents = useMemo(() => {
    return students.filter(s => {
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
    const groups: {
      collegeCode: string;
      collegeName: string;
      students: DistributionStudent[];
    }[] = [];
    const seen = new Map<string, DistributionStudent[]>();
    for (const s of filteredStudents) {
      const key = s.college_code || "";
      if (!seen.has(key)) {
        seen.set(key, []);
        groups.push({
          collegeCode: key,
          collegeName: s.college_name || key,
          students: seen.get(key)!,
        });
      }
      seen.get(key)!.push(s);
    }
    return groups;
  }, [filteredStudents]);

  const collegeCodes = useMemo(
    () =>
      Array.from(
        new Set(students.map(s => s.college_code).filter(Boolean))
      ).sort(),
    [students]
  );

  if (!scholarshipTypeId) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          無法找到獎學金類型設定，請重新整理頁面。
        </AlertDescription>
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
      {/* Main table area */}
      <div className="flex-1 min-w-0 space-y-3">
        {/* Top bar */}
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
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={localAllocations.size === 0 || isLoading}
                  >
                    清空所有分配
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>確認清空所有分配？</AlertDialogTitle>
                    <AlertDialogDescription>
                      此操作將清除目前所有學生的獎學金分配。這是可還原的，可在儲存前取消。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => {
                        setLocalAllocations(new Map());
                      }}
                    >
                      確認清空
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
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
                儲存目前配置
              </Button>
              <label className="cursor-pointer inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded border border-slate-300 bg-white hover:bg-slate-50 text-slate-700">
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                  />
                </svg>
                匯入已領月份數
                <input
                  type="file"
                  accept=".xlsx"
                  className="hidden"
                  onChange={async e => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    try {
                      const result =
                        await apiClient.manualDistribution.importReceivedMonths(
                          scholarshipTypeId,
                          selectedAcademicYear,
                          selectedSemester,
                          file
                        );
                      if (result.success && result.data) {
                        const { matched, not_found } = result.data;
                        setSaveMessage({
                          type: "success",
                          text: `成功匯入 ${matched} 筆${not_found.length > 0 ? `，${not_found.length} 筆學號未找到` : ""}`,
                        });
                        await fetchData();
                      }
                    } catch (err) {
                      setSaveMessage({
                        type: "error",
                        text: "匯入失敗，請確認檔案格式",
                      });
                    }
                    e.target.value = "";
                  }}
                />
              </label>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    size="sm"
                    disabled={isFinalizing || isLoading || isSaving}
                  >
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
                      確認後將鎖定分發結果，已分配的申請將標記為「核准」，未分配的將標記為「拒絕」。您可以在日後透過「查看歷史」功能還原到之前的分配狀態。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction onClick={handleFinalize}>
                      確認執行
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <Button
                variant="outline"
                size="sm"
                onClick={loadHistory}
                disabled={isLoadingHistory || isLoading}
              >
                {isLoadingHistory ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                ) : (
                  <Clock className="h-4 w-4 mr-1" />
                )}
                查看歷史
              </Button>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isGeneratingRosters || isLoading}
                  >
                    {isGeneratingRosters ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <Download className="h-4 w-4 mr-1" />
                    )}
                    生成造冊
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>確認產生造冊？</AlertDialogTitle>
                    <AlertDialogDescription>
                      系統將依據已完成分發的結果，針對每個（子類型 ×
                      配額年度）組合各產生一份造冊。此操作需要分發已完成（已確認分發）。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction onClick={handleGenerateRosters}>
                      確認產生
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <Button
                variant="outline"
                size="sm"
                onClick={loadDistributionSummary}
                disabled={isLoadingSummary || isLoading}
              >
                {isLoadingSummary ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                ) : (
                  <Eye className="h-4 w-4 mr-1" />
                )}
                查看分發名單
              </Button>
            </div>
          </div>

          {/* Filters row */}
          <div className="flex flex-wrap gap-2 items-end">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">
                學年度
              </label>
              <select
                className="border rounded px-2 py-1.5 text-sm border-slate-200"
                value={selectedAcademicYear ?? ""}
                onChange={e =>
                  setSelectedAcademicYear(
                    e.target.value ? Number(e.target.value) : undefined
                  )
                }
              >
                <option value="">選擇學年度</option>
                {(availableOptions?.academic_years ?? []).map(yr => (
                  <option key={yr} value={yr}>
                    {yr} 學年度
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">學期</label>
              <select
                className="border rounded px-2 py-1.5 text-sm border-slate-200"
                value={selectedSemester ?? ""}
                onChange={e => setSelectedSemester(e.target.value || undefined)}
              >
                <option value="">選擇學期</option>
                {(availableOptions?.semesters ?? []).map(s => (
                  <option key={s} value={s}>
                    {semesterLabel(s)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-slate-500">
                所屬學院
              </label>
              <select
                className="border rounded px-2 py-1.5 text-sm border-slate-200"
                value={collegeFilter}
                onChange={e => setCollegeFilter(e.target.value)}
              >
                <option value="">全部學院</option>
                {collegeCodes.map(code => (
                  <option key={code} value={code}>
                    {students.find(s => s.college_code === code)
                      ?.college_name || code}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1 flex-1 min-w-[180px]">
              <label className="text-xs font-medium text-slate-500">
                學生姓名 / 學號
              </label>
              <Input
                className="h-[34px] text-sm border-slate-200"
                placeholder="搜尋姓名、學號、系所..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
          </div>
        </div>

        {/* Save message */}
        {saveMessage && (
          <div
            className={`px-4 py-2 rounded text-sm ${saveMessage.type === "success" ? "bg-green-50 text-green-700 border border-green-200" : "bg-red-50 text-red-700 border border-red-200"}`}
          >
            {saveMessage.text}
          </div>
        )}

        {/* Roster generation result */}
        {rosterResult && rosterResult.rosters.length > 0 && (
          <div className="bg-blue-50 border border-blue-200 rounded px-4 py-3">
            <p className="text-sm font-semibold text-blue-800 mb-2">
              已產生 {rosterResult.rosters_created} 個造冊：
            </p>
            <div className="space-y-1">
              {rosterResult.rosters.map(r => (
                <div
                  key={r.roster_code}
                  className="text-xs text-blue-700 flex gap-3"
                >
                  <span className="font-mono">{r.roster_code}</span>
                  <span>
                    {r.sub_type} {r.allocation_year} 年度
                  </span>
                  {r.project_number && (
                    <span className="text-blue-500">
                      計畫：{r.project_number}
                    </span>
                  )}
                  <span className="text-blue-600">
                    合格 {r.qualified_count} 人，${r.total_amount}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Auto-preview notice */}
        {previewApplied && (
          <div className="mb-4 rounded-md bg-blue-50 p-3 text-sm text-blue-700">
            已自動預設分配，請確認後儲存
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-3 border-b border-slate-200 flex items-center justify-between">
            <span className="text-sm font-semibold text-slate-700">
              學生申請名冊與核配作業
            </span>
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
              <table
                className="w-full text-left border-collapse text-xs"
                style={{ minWidth: `${950 + subTypeCols.length * 85}px` }}
              >
                <thead className="bg-slate-50 text-[13px] text-slate-600">
                  {/* Row 1 */}
                  <tr>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold w-10 whitespace-nowrap text-[11px]"
                    >
                      排序
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold w-32 text-[11px]"
                    >
                      申請類別
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-8 bg-red-50"
                    >
                      取消
                    </th>
                    {subTypeCols.length > 0 && (
                      <th
                        colSpan={subTypeCols.length}
                        className="px-3 py-2 border border-slate-200 text-center font-semibold bg-blue-50 text-blue-700"
                      >
                        獲獎獎學金類別（核配勾選）
                      </th>
                    )}
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] w-16"
                    >
                      學院
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] w-20"
                    >
                      系所
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-12"
                    >
                      學期數
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-16"
                    >
                      已領月份數
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] w-24"
                    >
                      姓名
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] w-20"
                    >
                      國籍
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] text-red-600 w-20"
                    >
                      入學日期
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] w-16"
                    >
                      學號
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold text-[11px] w-12"
                    >
                      身份
                    </th>
                  </tr>
                  {/* Row 2 — (year × sub_type) column names */}
                  {subTypeCols.length > 0 && (
                    <tr className="bg-blue-50/50 text-[11px] text-center">
                      {subTypeCols.map(col => (
                        <th
                          key={col.key}
                          className="px-2 py-1.5 border border-slate-200 whitespace-nowrap"
                        >
                          <span
                            className={`font-semibold ${col.year < (selectedAcademicYear ?? 9999) ? "text-orange-600" : "text-slate-700"}`}
                          >
                            {col.display_name}
                          </span>
                        </th>
                      ))}
                    </tr>
                  )}
                </thead>
                <tbody>
                  {filteredStudents.length === 0 ? (
                    <tr>
                      <td
                        colSpan={10 + subTypeCols.length}
                        className="px-4 py-10 text-center text-slate-500"
                      >
                        {students.length === 0
                          ? "尚無已確認排名的學生資料"
                          : "無符合篩選條件的學生"}
                      </td>
                    </tr>
                  ) : (
                    studentsByCollege.map(
                      ({
                        collegeCode,
                        collegeName,
                        students: collegeStudents,
                      }) => (
                        <>
                          {/* College group header */}
                          <tr
                            key={`group-${collegeCode}`}
                            className="bg-slate-100"
                          >
                            <td
                              colSpan={10 + subTypeCols.length}
                              className="px-4 py-1.5 text-xs font-bold text-slate-600 border-y border-slate-300"
                            >
                              {collegeName || collegeCode}
                            </td>
                          </tr>
                          {collegeStudents.map(student => {
                            const curAlloc = localAllocations.get(
                              student.ranking_item_id
                            );
                            return (
                              <tr
                                key={student.ranking_item_id}
                                className="border-b border-slate-100 hover:bg-slate-50 transition-colors"
                              >
                                <td className="px-1.5 py-1.5 border-r border-slate-100 text-center font-bold text-slate-700 text-[11px]">
                                  {student.rank_position}
                                </td>
                                <td className="px-1.5 py-1.5 border-r border-slate-100 leading-snug text-[10px]">
                                  {student.applied_sub_types.length > 0 ? (
                                    student.applied_sub_types.map((t, i) => {
                                      const displayName = getSubTypeShortName(
                                        t,
                                        quotaStatus[t]?.display_name || t
                                      );
                                      return (
                                        <div
                                          key={t}
                                          className="text-[11px] text-slate-600"
                                        >
                                          {i + 1}. {displayName}
                                        </div>
                                      );
                                    })
                                  ) : (
                                    <span className="text-[11px] text-slate-400">
                                      —
                                    </span>
                                  )}
                                </td>
                                {/* Cancel allocation button */}
                                <td className="px-1 py-1.5 border-r border-slate-100 text-center">
                                  {curAlloc ? (
                                    <button
                                      onClick={() => {
                                        setLocalAllocations(prev => {
                                          const next = new Map(prev);
                                          next.set(
                                            student.ranking_item_id,
                                            null
                                          );
                                          return next;
                                        });
                                      }}
                                      className="px-2 py-1 text-xs bg-red-50 text-red-600 hover:bg-red-100 rounded border border-red-200 cursor-pointer transition-colors"
                                      title="取消此學生的分配"
                                    >
                                      ✕
                                    </button>
                                  ) : (
                                    <span className="text-[10px] text-slate-300">
                                      —
                                    </span>
                                  )}
                                </td>
                                {subTypeCols.map(col => {
                                  const isApplied =
                                    student.applied_sub_types.includes(
                                      col.sub_type
                                    );
                                  const isRejected = (
                                    student.rejected_sub_types || []
                                  ).includes(col.sub_type);
                                  const isChecked =
                                    curAlloc?.sub_type === col.sub_type &&
                                    curAlloc?.year === col.year;
                                  const localUsed =
                                    localAllocCounts[col.key] ?? 0;
                                  const atCapacity =
                                    col.total > 0 &&
                                    localUsed >= col.total &&
                                    !isChecked;
                                  const disabled =
                                    !isApplied || isRejected || atCapacity;
                                  return (
                                    <td
                                      key={col.key}
                                      className={`px-0.5 py-1.5 border-r border-slate-100 text-center ${
                                        !isApplied
                                          ? "opacity-40"
                                          : isRejected
                                            ? "opacity-40 bg-red-50"
                                            : ""
                                      }`}
                                    >
                                      <input
                                        type="checkbox"
                                        className="h-5 w-5 cursor-pointer rounded accent-blue-600"
                                        checked={isChecked}
                                        disabled={disabled}
                                        title={
                                          !isApplied
                                            ? `未申請 ${col.display_name}`
                                            : isRejected
                                              ? `教授不推薦 ${col.display_name}`
                                              : atCapacity
                                                ? `${col.display_name} 名額已滿`
                                                : isChecked
                                                  ? "點擊取消分配"
                                                  : `分配至 ${col.display_name}`
                                        }
                                        onChange={() =>
                                          handleCheckbox(
                                            student.ranking_item_id,
                                            col.sub_type,
                                            col.year
                                          )
                                        }
                                      />
                                    </td>
                                  );
                                })}
                                <td className="px-3 py-2.5 border-r border-slate-100 whitespace-nowrap">
                                  {student.college_name || student.college_code}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 whitespace-nowrap">
                                  {student.department_name}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 text-center whitespace-nowrap">
                                  {student.term_count ?? "-"}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 text-center whitespace-nowrap">
                                  <span className={student.received_months_source === "imported" ? "text-blue-600 font-medium" : ""}>{student.received_months ?? "-"}</span>
                                  {student.received_months_source === "imported" && <span className="ml-0.5 text-[9px] text-blue-400">匯</span>}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 font-medium whitespace-nowrap">
                                  {student.student_name}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 text-slate-500 whitespace-nowrap">
                                  {student.nationality}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 text-center tabular-nums whitespace-nowrap">
                                  {student.enrollment_date}
                                </td>
                                <td className="px-3 py-2.5 border-r border-slate-100 font-mono text-xs whitespace-nowrap">
                                  {student.student_id}
                                </td>
                                <td className="px-3 py-2.5 text-xs font-semibold whitespace-nowrap">
                                  {student.is_renewal ? (
                                    <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-300">
                                      {student.renewal_year || ""} 續領
                                      {student.renewal_sub_type || ""}
                                    </span>
                                  ) : (
                                    <span
                                      className={
                                        student.application_identity.includes(
                                          "新申請"
                                        )
                                          ? "text-amber-600"
                                          : "text-blue-600"
                                      }
                                    >
                                      {student.application_identity}
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </>
                      )
                    )
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
            <li>
              依「學院初審排序」手動勾選欲核配的獎學金類別，每位學生限勾選一項。
            </li>
            <li>
              <span className="text-orange-600 font-semibold">橘色欄位</span>
              為前年度補發名額，可分配給本年度學生使用。
            </li>
            <li>
              右側「即時剩餘名額」即時反映目前勾選狀況；額度用罄後該欄位停用。
            </li>
            <li>
              核配完成後點擊「儲存目前配置」，確認無誤後再執行「確認分發」。
            </li>
          </ul>
        </div>
      </div>

      {/* Quota sidebar */}
      <div className="w-64 shrink-0">
        <div className="sticky top-4 bg-white rounded-xl border-2 border-blue-200 shadow-sm overflow-hidden">
          <div className="bg-blue-600 px-4 py-2.5 flex items-center justify-between">
            <span className="text-white font-bold text-sm">即時剩餘名額</span>
            <span className="text-[10px] bg-white/20 text-white px-2 py-0.5 rounded-full">
              Auto-Sync
            </span>
          </div>
          <div className="p-3 space-y-1.5">
            {subTypeCols.length === 0 ? (
              <p className="text-xs text-slate-400 py-2 text-center">
                尚無配額資料
              </p>
            ) : (
              subTypeCols.map(col => {
                const used = localAllocCounts[col.key] ?? 0;
                const remaining = col.total - used;
                const isFull = remaining <= 0;
                const isLow = !isFull && remaining <= 2;
                const isPriorYear = col.year < (selectedAcademicYear ?? 9999);
                return (
                  <div
                    key={col.key}
                    className={`px-3 py-2 rounded-lg border ${
                      isFull
                        ? "bg-red-50 border-red-200"
                        : isPriorYear
                          ? "bg-orange-50 border-orange-200"
                          : isLow
                            ? "bg-amber-50 border-amber-200"
                            : "bg-slate-50 border-slate-100"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <span
                        className={`text-[11px] leading-tight flex-1 ${isPriorYear ? "text-orange-700" : "text-slate-600"}`}
                      >
                        {col.display_name}
                      </span>
                      <span
                        className={`text-sm font-bold tabular-nums shrink-0 ${
                          isFull
                            ? "text-red-600"
                            : isPriorYear
                              ? "text-orange-600"
                              : isLow
                                ? "text-amber-600"
                                : "text-blue-700"
                        }`}
                      >
                        {used.toString().padStart(2, "0")} /{" "}
                        {col.total.toString().padStart(2, "0")}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* History Dialog */}
      {/* Distribution Summary Dialog */}
      {showDistributionSummary && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-lg max-w-4xl w-full max-h-[85vh] flex flex-col">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                <Eye className="h-5 w-5" />
                分發結果名單
              </h2>
              <button
                onClick={() => setShowDistributionSummary(false)}
                className="text-slate-400 hover:text-slate-600 text-2xl leading-none"
              >
                ×
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {isLoadingSummary ? (
                <div className="flex justify-center py-12">
                  <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
                </div>
              ) : !distributionSummary ||
                distributionSummary.groups.length === 0 ? (
                <p className="text-center text-slate-500 py-8">
                  尚未完成分發，或無已分配的學生
                </p>
              ) : (
                <div className="space-y-6">
                  <div className="text-sm text-slate-600">
                    共 {distributionSummary.total_allocated} 位學生已分發到{" "}
                    {distributionSummary.groups.length} 個獎學金類別
                  </div>
                  {distributionSummary.groups.map(group => (
                    <div
                      key={`${group.sub_type}-${group.allocation_year}`}
                      className="border border-slate-200 rounded-lg overflow-hidden"
                    >
                      <div className="bg-slate-50 px-4 py-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm text-slate-800">
                            {getSubTypeShortName(
                              group.sub_type,
                              group.sub_type
                            )}
                          </span>
                          <span className="text-xs text-slate-500 font-mono">
                            ({group.sub_type})
                          </span>
                          <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                            {group.allocation_year} 年度配額
                          </span>
                        </div>
                        <span className="text-sm font-medium text-slate-700">
                          {group.count} 人
                        </span>
                      </div>
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-slate-100 text-xs text-slate-500">
                            <th className="text-left px-4 py-2">排名</th>
                            <th className="text-left px-4 py-2">學號</th>
                            <th className="text-left px-4 py-2">姓名</th>
                            <th className="text-left px-4 py-2">學院</th>
                            <th className="text-left px-4 py-2">系所</th>
                          </tr>
                        </thead>
                        <tbody>
                          {group.students
                            .sort((a, b) => a.rank_position - b.rank_position)
                            .map(student => (
                              <tr
                                key={student.ranking_item_id}
                                className="border-b border-slate-50 hover:bg-slate-50"
                              >
                                <td className="px-4 py-1.5 text-slate-400">
                                  {student.rank_position}
                                </td>
                                <td className="px-4 py-1.5 font-mono text-xs">
                                  {student.student_id}
                                </td>
                                <td className="px-4 py-1.5 font-medium">
                                  {student.student_name}
                                </td>
                                <td className="px-4 py-1.5">
                                  {student.college_name || student.college_code}
                                </td>
                                <td className="px-4 py-1.5 text-slate-600">
                                  {student.department_name}
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-slate-200 flex justify-end">
              <Button
                variant="outline"
                onClick={() => setShowDistributionSummary(false)}
              >
                關閉
              </Button>
            </div>
          </div>
        </div>
      )}

      {showHistoryDialog && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-lg max-w-2xl w-full max-h-[80vh] flex flex-col">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                <Clock className="h-5 w-5" />
                分配歷史記錄
              </h2>
              <button
                onClick={() => setShowHistoryDialog(false)}
                className="text-slate-400 hover:text-slate-600 text-2xl leading-none"
              >
                ×
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              {history.length === 0 ? (
                <p className="text-center text-slate-500 py-8">尚無歷史記錄</p>
              ) : (
                <div className="space-y-2">
                  {history.map(record => (
                    <div
                      key={record.id}
                      className="p-3 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-sm text-slate-900">
                            {record.operation_type === "save"
                              ? "📝 儲存"
                              : record.operation_type === "finalize"
                                ? "✓ 確認分發"
                                : "↶ 還原"}
                          </div>
                          <div className="text-xs text-slate-600 mt-1">
                            {record.change_summary}
                          </div>
                          <div className="text-xs text-slate-400 mt-1">
                            {record.created_at
                              ? new Date(record.created_at).toLocaleString(
                                  "zh-TW",
                                  {
                                    year: "numeric",
                                    month: "2-digit",
                                    day: "2-digit",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    second: "2-digit",
                                  }
                                )
                              : "未知時間"}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          onClick={() => handleRestore(record.id)}
                          disabled={isRestoring}
                          className="shrink-0"
                        >
                          {isRestoring ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            "還原"
                          )}
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="p-4 border-t border-slate-200 flex justify-end">
              <Button
                variant="outline"
                onClick={() => setShowHistoryDialog(false)}
              >
                關閉
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
