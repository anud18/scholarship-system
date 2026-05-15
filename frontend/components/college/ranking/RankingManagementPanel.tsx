"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { useState, useEffect, useCallback, useMemo } from "react";
import { Semester } from "@/lib/enums";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CollegeRankingTable } from "@/components/college-ranking-table";
import { ConfigSelector } from "../shared/ConfigSelector";
import { RankingCardList } from "../shared/RankingCardList";
import { Plus, Loader2, Clock, AlertTriangle, Lock } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";

// #63: surface the college-review deadline visibly on the ranking page
// and warn / lock once the deadline approaches or passes.
type DeadlineState = "none" | "ok" | "near" | "passed";

interface DeadlineInfo {
  state: DeadlineState;
  deadline?: Date;
  msToDeadline?: number;
  daysToDeadline?: number;
}

const NEAR_THRESHOLD_MS = 3 * 24 * 60 * 60 * 1000; // 3 days

function computeDeadlineInfo(deadlineISO?: string | null): DeadlineInfo {
  if (!deadlineISO) return { state: "none" };
  const deadline = new Date(deadlineISO);
  if (Number.isNaN(deadline.getTime())) return { state: "none" };
  const ms = deadline.getTime() - Date.now();
  const days = Math.floor(ms / (24 * 60 * 60 * 1000));
  if (ms <= 0) {
    return { state: "passed", deadline, msToDeadline: ms, daysToDeadline: days };
  }
  if (ms <= NEAR_THRESHOLD_MS) {
    return { state: "near", deadline, msToDeadline: ms, daysToDeadline: days };
  }
  return { state: "ok", deadline, msToDeadline: ms, daysToDeadline: days };
}

function formatCountdown(ms: number, locale: "zh" | "en"): string {
  if (ms <= 0) return locale === "zh" ? "已過期" : "expired";
  const totalMin = Math.floor(ms / 60000);
  const days = Math.floor(totalMin / (60 * 24));
  const hours = Math.floor((totalMin % (60 * 24)) / 60);
  const mins = totalMin % 60;
  if (locale === "zh") {
    if (days > 0) return `${days} 天 ${hours} 小時`;
    if (hours > 0) return `${hours} 小時 ${mins} 分鐘`;
    return `${mins} 分鐘`;
  }
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface RankingManagementPanelProps {
  user: User;
  scholarshipType: { code: string; name: string };
}

export function RankingManagementPanel({
  user,
  scholarshipType,
}: RankingManagementPanelProps) {
  const {
    locale,
    selectedRanking,
    setSelectedRanking,
    rankingData,
    setRankingData,
    isRankingLoading,
    setIsRankingLoading,
    filteredRankings,
    rankings,
    setRankings,
    scholarshipConfig,
    selectedAcademicYear,
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    selectedCombination,
    setSelectedCombination,
    availableOptions,
    activeScholarshipTab,
    editingRankingId,
    setEditingRankingId,
    editingRankingName,
    setEditingRankingName,
    showDeleteRankingDialog,
    setShowDeleteRankingDialog,
    rankingToDelete,
    setRankingToDelete,
    saveStatus,
    setSaveStatus,
    saveTimeoutRef,
    getAcademicConfig,
    getScholarshipConfig,
    setActiveTab,
    fetchCollegeApplications,
    incrementDataVersion,
    activeTab,
    dataVersion,
    fetchRankings,
  } = useCollegeManagement();

  // #91 fix: deadline fetched from the ranking-detail endpoint when a user
  // clicks into a specific ranking. Kept as a freshness fallback.
  const [activeConfigDeadline, setActiveConfigDeadline] = useState<string | null>(null);

  // Page-level deadline fetched directly from the active scholarship
  // configuration matching (scholarship_type, year, semester). This ensures
  // the deadline banner appears as soon as the panel renders, even when no
  // rankings exist for the current selection (i.e. before the user clicks
  // "建立新排名" for the first time).
  const [panelDeadline, setPanelDeadline] = useState<string | null>(null);

  const fetchRankingDetails = useCallback(
    async (rankingId: number) => {
      setIsRankingLoading(true);
      try {
        const response = await apiClient.college.getRanking(rankingId);
        if (response.success && response.data) {
          // Transform the API response
          // Shape from GET /college-review/rankings/{id} — backend's
          // CollegeRankingItemResponse. Inline because the API client doesn't
          // export a named type for this nested payload.
          interface RankingItemPayload {
            id: number;
            sub_type?: string;
            rank_position?: number;
            is_allocated?: boolean;
            college_rejected?: boolean;
            student_name?: string;
            student_id?: string;
            application?: {
              id?: number;
              app_id?: string;
              academy_name?: string;
              academy_code?: string;
              department_name?: string;
              department_code?: string;
              scholarship_type?: string;
              eligible_subtypes?: string[];
              is_renewal?: boolean;
              renewal_year?: number | null;
              status?: string;
              review_status?: string;
              student_info?: { display_name?: string; student_id?: string };
            };
          }
          const transformedApplications = (response.data.items || []).map(
            (item: RankingItemPayload) => ({
              id: item.application?.id || item.id,
              ranking_item_id: item.id,
              app_id:
                item.application?.app_id ||
                `APP-${item.application?.id || item.id}`,
              student_name:
                item.student_name ||
                item.application?.student_info?.display_name ||
                "未提供姓名",
              student_id:
                item.student_id ||
                item.application?.student_info?.student_id ||
                "N/A",
              academy_name: item.application?.academy_name,
              academy_code: item.application?.academy_code,
              department_name: item.application?.department_name,
              department_code: item.application?.department_code,
              scholarship_type: item.application?.scholarship_type,
              sub_type: item.sub_type,
              eligible_subtypes: item.application?.eligible_subtypes || [],
              rank_position: item.rank_position,
              is_allocated: item.is_allocated || false,
              is_renewal: item.application?.is_renewal || false,
              renewal_year: item.application?.renewal_year || null,
              status: item.application?.status || "pending",
              college_rejected: Boolean(item.college_rejected),
              review_status: item.application?.review_status,
            })
          );

          // #91: college_review_end is now returned directly by the ranking detail endpoint
          setActiveConfigDeadline(
            (response.data as { college_review_end?: string | null })
              .college_review_end ?? null
          );

          setRankingData({
            applications: transformedApplications,
            totalQuota: response.data.total_quota || 0,
            collegeQuota: response.data.college_quota,
            collegeQuotaBreakdown: response.data.college_quota_breakdown,
            subTypeMetadata: Array.isArray(response.data.sub_type_metadata)
              ? response.data.sub_type_metadata.reduce(
                  (
                    acc: Record<string, { code: string; [key: string]: unknown }>,
                    meta: { code?: string; [key: string]: unknown }
                  ) => {
                    if (meta.code) {
                      acc[meta.code] = meta as {
                        code: string;
                        [key: string]: unknown;
                      };
                    }
                    return acc;
                  },
                  {}
                )
              : response.data.sub_type_metadata || {},
            subTypeCode: response.data.sub_type_code || "default",
            academicYear: response.data.academic_year || 0,
            semester: response.data.semester,
            isFinalized: response.data.is_finalized || false,
          });
        }
      } catch (error) {
        console.error("Failed to fetch ranking details:", error);
      } finally {
        setIsRankingLoading(false);
      }
    },
    [setIsRankingLoading, setRankingData, setActiveConfigDeadline]
  );

  // Auto-refresh when switching to ranking tab or when data version changes
  useEffect(() => {
    // Only refresh when:
    // 1. Current tab is "ranking"
    // 2. Not currently loading
    if (activeTab === "ranking") {
      console.log(
        `[RankingManagementPanel] Auto-refreshing (dataVersion: ${dataVersion})`
      );

      // Refresh rankings list
      fetchRankings();

      // Also refresh applications list (in case application status changed in review tab)
      fetchCollegeApplications(
        selectedAcademicYear,
        selectedSemester,
        activeScholarshipTab
      );

      // If a ranking is selected, also refresh its details
      if (selectedRanking && !isRankingLoading) {
        fetchRankingDetails(selectedRanking);
      }
    }
    // Note: Removed isRankingLoading and fetchRankingDetails from deps to prevent infinite loop
    // The condition check (!isRankingLoading) inside the effect is sufficient
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, dataVersion, fetchRankings, selectedRanking]);

  const createNewRanking = useCallback(async () => {
    try {
      const academicConfig = await getAcademicConfig();
      const scholarshipConfigData = await getScholarshipConfig();

      const currentScholarshipType = availableOptions?.scholarship_types.find(
        type => type.code === activeScholarshipTab
      );

      const configScholarship = scholarshipConfigData.find(
        config => config.name === currentScholarshipType?.name
      );

      const targetScholarshipId =
        configScholarship?.id || scholarshipConfigData[0]?.id;
      const targetSubTypeCode =
        configScholarship?.subTypes[0]?.code ||
        scholarshipConfigData[0]?.subTypes[0]?.code;
      const useYear = selectedAcademicYear || academicConfig.currentYear;
      const useSemester = selectedSemester || academicConfig.currentSemester;

      const semesterName =
        useSemester === Semester.FIRST
          ? "上學期"
          : useSemester === Semester.SECOND
            ? "下學期"
            : "全年";

      const response = await apiClient.college.createRanking({
        scholarship_type_id: targetScholarshipId,
        sub_type_code: targetSubTypeCode,
        academic_year: useYear,
        semester: useSemester === Semester.YEARLY ? null : useSemester,
        ranking_name: `${scholarshipType.name} - ${useYear} ${semesterName}`,
        force_new: true, // Always create a new ranking when user clicks "建立新排名"
      });

      if (response.success && response.data) {
        try {
          // Refresh rankings list
          await fetchRankings();
          // Select the newly created ranking
          setSelectedRanking(response.data.id);
          // Load ranking details
          await fetchRankingDetails(response.data.id);
          // Increment data version
          incrementDataVersion();

          // Show success notification
          toast.success(
            locale === "zh"
              ? `排名「${response.data.ranking_name || "新排名"}」已成功建立`
              : `Ranking "${response.data.ranking_name || "New Ranking"}" has been created successfully`
          );
        } catch (fetchError) {
          console.error("Failed to load ranking after creation:", fetchError);
          toast.error(
            locale === "zh"
              ? "排名已建立，但無法自動載入。請手動重新整理頁面。"
              : "Ranking created but failed to load automatically. Please refresh the page manually."
          );
        }
      } else {
        // API returned success: false
        toast.error(
          response.message ||
            (locale === "zh" ? "無法建立排名" : "Failed to create ranking")
        );
      }
    } catch (error) {
      console.error("Failed to create ranking:", error);
      toast.error(
        error instanceof Error
          ? error.message
          : locale === "zh"
            ? "建立排名時發生錯誤"
            : "An error occurred while creating the ranking"
      );
    }
  }, [
    getAcademicConfig,
    getScholarshipConfig,
    availableOptions,
    activeScholarshipTab,
    scholarshipConfig,
    selectedAcademicYear,
    selectedSemester,
    scholarshipType.name,
    fetchRankings,
    setSelectedRanking,
    fetchRankingDetails,
    toast,
    locale,
    incrementDataVersion,
  ]);

  const handleRankingChange = useCallback(
    // newOrder is the typed `Application[]` from CollegeRankingTable;
    // we narrow to the subset we actually read (ranking_item_id) when building
    // the updateRankingOrder payload below. The application objects are passed
    // straight through to setRankingData, whose .applications field is itself
    // `any[]` in the context type for the same reason.
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    async (newOrder: any[]) => {
      if (!rankingData || !selectedRanking) return;

      setRankingData({
        ...rankingData,
        applications: newOrder,
      });

      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }

      setSaveStatus("idle");

      saveTimeoutRef.current = setTimeout(async () => {
        setSaveStatus("saving");
        try {
          // Use ranking_item_id (CollegeRankingItem.id) not application_id
          const rankingItems = newOrder.map((app, index) => ({
            item_id: app.ranking_item_id,
            position: index + 1,
          }));

          // Use updateRankingOrder API instead of updateRanking
          const response = await apiClient.college.updateRankingOrder(
            selectedRanking,
            rankingItems
          );

          if (response.success) {
            setSaveStatus("saved");
            setTimeout(() => setSaveStatus("idle"), 2000);
          } else {
            setSaveStatus("error");
          }
        } catch (error) {
          console.error("Failed to save ranking:", error);
          setSaveStatus("error");
        }
      }, 500);
    },
    [
      rankingData,
      selectedRanking,
      setRankingData,
      saveTimeoutRef,
      setSaveStatus,
    ]
  );

  const handleReviewApplication = useCallback(
    async (
      applicationId: number,
      action: "approve" | "reject",
      comments?: string
    ) => {
      try {
        const response = await apiClient.college.reviewApplication(
          applicationId,
          {
            recommendation: action,
            review_comments: comments,
          }
        );

        // 檢查是否自動重新執行了分發
        if (response.success && response.data) {
          const redistribution = response.data.redistribution_info;

          if (redistribution?.auto_redistributed) {
            toast.success(
              `審核完成並已自動重新執行分發，分配 ${redistribution.total_allocated} 名學生`,
              { duration: 5000 }
            );
          } else if (redistribution?.reason === "roster_exists") {
            toast.warning(
              `審核完成。此排名已開始造冊 (${redistribution.roster_info?.roster_code})，未重新執行分發`,
              { duration: 6000 }
            );
          } else {
            toast.success(`審核${action === "approve" ? "核准" : "駁回"}完成`);
          }
        }

        // 刷新所有相關資料以確保 UI 同步
        await Promise.all([
          // 刷新當前排名的詳細資訊（包含最新的分配結果）
          selectedRanking
            ? fetchRankingDetails(selectedRanking)
            : Promise.resolve(),
          // 刷新排名列表（更新分配計數等統計資訊）
          fetchRankings(),
          // 刷新申請列表（更新學生狀態）
          fetchCollegeApplications(
            selectedAcademicYear,
            selectedSemester,
            activeScholarshipTab
          ),
        ]);

        // Increment data version to notify other panels to refresh
        incrementDataVersion();
        console.log(
          "[RankingManagementPanel] Data version incremented after review"
        );
      } catch (error) {
        console.error("Failed to review application:", error);
        toast.error("審核提交失敗");
      }
    },
    [
      selectedRanking,
      fetchRankingDetails,
      fetchRankings,
      fetchCollegeApplications,
      selectedAcademicYear,
      selectedSemester,
      activeScholarshipTab,
      incrementDataVersion,
    ]
  );

  const handleFinalizeRanking = useCallback(
    async (targetRankingId?: number) => {
      const rankingId = targetRankingId ?? selectedRanking;
      if (!rankingId) return;

      try {
        const response = await apiClient.college.finalizeRanking(rankingId);
        if (response.success) {
          await fetchRankings();
          if (rankingData && rankingId === selectedRanking) {
            setRankingData({ ...rankingData, isFinalized: true });
          }
          incrementDataVersion();
          toast.success(
            locale === "zh"
              ? "排名已成功鎖定"
              : "Ranking has been locked successfully"
          );
        }
      } catch (error) {
        console.error("Failed to finalize ranking:", error);
      }
    },
    [
      selectedRanking,
      rankingData,
      fetchRankings,
      setRankingData,
      toast,
      locale,
      incrementDataVersion,
    ]
  );

  const handleUnfinalizeRanking = useCallback(
    async (targetRankingId?: number) => {
      const rankingId = targetRankingId ?? selectedRanking;
      if (!rankingId) return;

      try {
        const response = await apiClient.college.unfinalizeRanking(rankingId);
        if (response.success) {
          await fetchRankings();
          if (rankingData && rankingId === selectedRanking) {
            setRankingData({ ...rankingData, isFinalized: false });
          }
          incrementDataVersion();
          toast.success(
            locale === "zh" ? "排名已成功解除鎖定" : "Ranking unlocked"
          );
        }
      } catch (error) {
        console.error("Failed to unfinalize ranking:", error);
      }
    },
    [
      selectedRanking,
      rankingData,
      fetchRankings,
      setRankingData,
      toast,
      locale,
      incrementDataVersion,
    ]
  );

  const handleImportExcel = useCallback(
    async (
      data: Array<{
        student_id: string;
        student_name: string;
        rank_position: number | string;
      }>
    ) => {
      if (!selectedRanking) throw new Error("No ranking selected");

      try {
        // The Excel parser produces rank_position as `number | string` (the
        // "N" sentinel for unranked rows). The api.college.importRankingExcel
        // type declares `number` only, but the backend handler accepts both
        // shapes — cast here to preserve the runtime behavior. Tracked in
        // college-ranking-table.tsx parser at lines 627-645.
        const response = await apiClient.college.importRankingExcel(
          selectedRanking,
          data as Array<{
            student_id: string;
            student_name: string;
            rank_position: number;
          }>
        );
        if (response.success) {
          await fetchRankingDetails(selectedRanking);
          incrementDataVersion();
        } else {
          throw new Error(response.message || "Failed to import");
        }
      } catch (error) {
        console.error("Failed to import Excel:", error);
        throw error;
      }
    },
    [selectedRanking, fetchRankingDetails, incrementDataVersion]
  );

  const handleDeleteRanking = useCallback(async () => {
    if (!rankingToDelete) return;

    try {
      const response = await apiClient.college.deleteRanking(
        rankingToDelete.id
      );
      if (response.success) {
        if (selectedRanking === rankingToDelete.id) {
          setSelectedRanking(null);
          setRankingData(null);
          setActiveConfigDeadline(null);
        }
        await fetchRankings();
        incrementDataVersion();
        setShowDeleteRankingDialog(false);
        setRankingToDelete(null);
      }
    } catch (error) {
      console.error("Failed to delete ranking:", error);
    }
  }, [
    rankingToDelete,
    selectedRanking,
    fetchRankings,
    setSelectedRanking,
    setRankingData,
    setShowDeleteRankingDialog,
    setRankingToDelete,
    incrementDataVersion,
  ]);

  const handleEditRankingName = useCallback(
    (ranking: { id: number; ranking_name: string }) => {
      setEditingRankingId(ranking.id);
      setEditingRankingName(ranking.ranking_name);
    },
    [setEditingRankingId, setEditingRankingName]
  );

  const handleSaveRankingName = useCallback(
    async (rankingId: number) => {
      try {
        const response = await apiClient.college.updateRanking(rankingId, {
          ranking_name: editingRankingName,
        });
        if (response.success) {
          await fetchRankings();
          setEditingRankingId(null);
          setEditingRankingName("");
          toast.success(
            locale === "zh" ? "排名名稱已更新" : "Ranking name has been updated"
          );
        } else {
          toast.error(
            response.message ||
              (locale === "zh"
                ? "無法更新排名名稱"
                : "Failed to update ranking name")
          );
        }
      } catch (error) {
        console.error("Failed to update ranking name:", error);
        toast.error(
          locale === "zh" ? "無法更新排名名稱" : "Failed to update ranking name"
        );
      }
    },
    [
      editingRankingName,
      fetchRankings,
      setEditingRankingId,
      setEditingRankingName,
      toast,
      locale,
    ]
  );

  const handleCancelEditRankingName = useCallback(() => {
    setEditingRankingId(null);
    setEditingRankingName("");
  }, [setEditingRankingId, setEditingRankingName]);

  // #63: deadline state for the currently-selected scholarship configuration.
  // Re-evaluates every minute so the countdown stays close to live without
  // burning render cycles on every state change.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(id);
  }, []);
  // Fetch the deadline directly from the active scholarship configuration
  // matching the current (scholarship_type, year, semester) selection. This
  // is the authoritative source — runs whenever the selection changes, so
  // the banner appears immediately on page entry, with zero rankings, or
  // after switching combinations.
  useEffect(() => {
    const activeConfig = scholarshipConfig.find(
      (c) => c.code === scholarshipType.code
    );
    if (!activeConfig?.id || typeof selectedAcademicYear !== "number") {
      setPanelDeadline(null);
      return;
    }
    const semParam =
      !selectedSemester || selectedSemester === Semester.YEARLY
        ? "yearly"
        : selectedSemester;
    let cancelled = false;
    apiClient
      .request<{ college_review_end: string | null }>(
        "/college-review/active-config",
        {
          method: "GET",
          params: {
            scholarship_type_id: activeConfig.id,
            academic_year: selectedAcademicYear,
            semester: semParam,
          },
        }
      )
      .then(resp => {
        if (cancelled) return;
        setPanelDeadline(
          resp.success && resp.data ? resp.data.college_review_end ?? null : null
        );
      })
      .catch(() => {
        if (!cancelled) setPanelDeadline(null);
      });
    return () => {
      cancelled = true;
    };
  }, [
    scholarshipConfig,
    scholarshipType.code,
    selectedAcademicYear,
    selectedSemester,
  ]);

  // Authoritative deadline = the one matched directly to the active config.
  // Fall back to anything carried on the current rankings, then to a freshly
  // fetched ranking-detail value, while the active-config call is in flight.
  const deadlineISO = useMemo(() => {
    const fromList = filteredRankings.find(
      (r: { college_review_end?: string | null } | null | undefined) =>
        r && r.college_review_end
    )?.college_review_end as string | undefined;
    return panelDeadline ?? fromList ?? activeConfigDeadline ?? null;
  }, [panelDeadline, filteredRankings, activeConfigDeadline]);
  const deadlineInfo = useMemo(
    () => computeDeadlineInfo(deadlineISO),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `now` triggers re-eval
    [deadlineISO, now]
  );
  const isAdmin = user.role === "admin" || user.role === "super_admin";

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            學生排序管理 - {scholarshipType.name}
          </h2>
          <p className="text-muted-foreground">管理獎學金申請的排序和排名</p>
        </div>

        <div className="flex items-center gap-2">
          <ConfigSelector
            selectedCombination={selectedCombination}
            availableYears={availableOptions?.academic_years || []}
            availableSemesters={availableOptions?.semesters || []}
            onCombinationChange={value => {
              setSelectedCombination(value);
              const [year, semester] = value.split("-");
              setSelectedAcademicYear(parseInt(year));
              setSelectedSemester(semester || undefined);
            }}
            locale={locale}
          />

          <Button
            onClick={createNewRanking}
            disabled={deadlineInfo.state === "passed" && !isAdmin}
          >
            <Plus className="h-4 w-4 mr-2" />
            建立新排名
          </Button>
        </div>
      </div>

      {/* #63: deadline banner */}
      {deadlineInfo.state !== "none" && deadlineInfo.deadline && (
        <div
          className={`rounded-md border p-3 text-sm flex items-start gap-2 ${
            deadlineInfo.state === "passed"
              ? "border-rose-300 bg-rose-50 text-rose-900"
              : deadlineInfo.state === "near"
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-emerald-300 bg-emerald-50 text-emerald-900"
          }`}
        >
          {deadlineInfo.state === "passed" ? (
            <Lock className="h-4 w-4 mt-0.5 shrink-0" />
          ) : deadlineInfo.state === "near" ? (
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          ) : (
            <Clock className="h-4 w-4 mt-0.5 shrink-0" />
          )}
          <div className="flex-1 leading-relaxed">
            {deadlineInfo.state === "passed" ? (
              <>
                <strong>已過排名截止時間</strong>(
                {deadlineInfo.deadline.toLocaleString(
                  locale === "zh" ? "zh-TW" : "en-US"
                )}
                )。
                {isAdmin
                  ? locale === "zh"
                    ? "你以管理員身份登入,仍可調整排名。"
                    : "You're signed in as an administrator and can still edit."
                  : locale === "zh"
                  ? "排名匯入 / 修改功能已鎖定,如需修改請聯絡管理員延期。"
                  : "Ranking import / edit is locked. Contact an administrator to extend the deadline."}
              </>
            ) : deadlineInfo.state === "near" ? (
              <>
                <strong>
                  {locale === "zh"
                    ? "排名截止時間將至"
                    : "Ranking deadline approaching"}
                </strong>
                {locale === "zh" ? "  ·  剩餘 " : " · "}
                {formatCountdown(deadlineInfo.msToDeadline ?? 0, locale)}
                {locale === "zh" ? "  ·  截止於 " : " · due "}
                {deadlineInfo.deadline.toLocaleString(
                  locale === "zh" ? "zh-TW" : "en-US"
                )}
                。
              </>
            ) : (
              <>
                {locale === "zh" ? "排名截止時間" : "Ranking deadline"}:
                {" "}
                {deadlineInfo.deadline.toLocaleString(
                  locale === "zh" ? "zh-TW" : "en-US"
                )}
                {locale === "zh" ? "  ·  剩餘 " : " · "}
                {formatCountdown(deadlineInfo.msToDeadline ?? 0, locale)}
              </>
            )}
          </div>
        </div>
      )}

      {/* Ranking Selection */}
      <Card>
        <CardHeader>
          <CardTitle>選擇排名</CardTitle>
          <CardDescription>選擇要管理的排名清單</CardDescription>
        </CardHeader>
        <CardContent>
          {/* #63: when deadline has passed and user isn't admin, hide
              edit/delete/finalize affordances. Backend enforces the same
              constraint via assert_ranking_within_deadline. */}
          <RankingCardList
            rankings={filteredRankings}
            selectedRankingId={selectedRanking}
            onRankingSelect={id => {
              setSelectedRanking(id);
              fetchRankingDetails(id);
            }}
            showActions={true}
            showOnlyDistributed={false}
            emptyStateConfig={{
              title: "暫無符合條件的排名",
              description: `${scholarshipType.name} 目前在選定的學年度與學期沒有排名`,
              actionButton:
                deadlineInfo.state === "passed" && !isAdmin
                  ? undefined
                  : {
                      label: "立即建立排名",
                      onClick: createNewRanking,
                    },
            }}
            editingId={editingRankingId}
            editingName={editingRankingName}
            onEdit={
              deadlineInfo.state === "passed" && !isAdmin
                ? undefined
                : handleEditRankingName
            }
            onEditNameChange={setEditingRankingName}
            onEditNameSave={handleSaveRankingName}
            onEditNameCancel={handleCancelEditRankingName}
            onDelete={
              deadlineInfo.state === "passed" && !isAdmin
                ? undefined
                : ranking => {
                    setRankingToDelete(ranking);
                    setShowDeleteRankingDialog(true);
                  }
            }
            onToggleLock={
              deadlineInfo.state === "passed" && !isAdmin
                ? undefined
                : (id, isLocked) => {
                    if (isLocked) {
                      handleUnfinalizeRanking(id);
                    } else {
                      handleFinalizeRanking(id);
                    }
                  }
            }
            locale={locale}
          />
        </CardContent>
      </Card>

      {/* Ranking Details */}
      {selectedRanking && rankingData && (
        <div className="space-y-6">
          {isRankingLoading ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : (
            <CollegeRankingTable
              applications={rankingData.applications}
              totalQuota={rankingData.totalQuota}
              subTypeCode={rankingData.subTypeCode}
              academicYear={rankingData.academicYear}
              semester={rankingData.semester}
              isFinalized={rankingData.isFinalized}
              lockedByDeadline={
                deadlineInfo.state === "passed" && !isAdmin
              }
              rankingId={selectedRanking}
              onRankingChange={handleRankingChange}
              onReviewApplication={handleReviewApplication}
              onFinalizeRanking={handleFinalizeRanking}
              onImportExcel={handleImportExcel}
              locale={locale}
              subTypeMeta={rankingData.subTypeMetadata}
              saveStatus={saveStatus}
            />
          )}
        </div>
      )}

      {/* Delete Ranking Dialog */}
      <Dialog
        open={showDeleteRankingDialog}
        onOpenChange={setShowDeleteRankingDialog}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>刪除排名</DialogTitle>
            <DialogDescription>
              確定要刪除排名「{rankingToDelete?.ranking_name}
              」嗎？此操作無法復原。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDeleteRankingDialog(false)}
            >
              取消
            </Button>
            <Button variant="destructive" onClick={handleDeleteRanking}>
              刪除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
