"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
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
import { Plus, RefreshCw, Loader2, Clock, AlertTriangle, Lock } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api";
import { logger } from "@/lib/utils/logger";
import { formatDeadline } from "@/lib/utils/format-deadline";
import {
  buildDefaultRankingName,
  findBlockingRanking,
  findScopeSiblings,
  pickDefaultRankingId,
  resolveRankingTarget,
} from "./ranking-scope";
import { FinalizeRankingDialog, type FinalizeCandidate } from "./FinalizeRankingDialog";
import { RankingDriftBanner } from "./RankingDriftBanner";

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
  // "建立排名" for the first time).
  const [panelDeadline, setPanelDeadline] = useState<string | null>(null);

  // Only the latest detail request may write rankingData: a slower response
  // for a card the user has already left must not land under the new one.
  const latestDetailRequestRef = useRef(0);

  const fetchRankingDetails = useCallback(
    async (rankingId: number) => {
      const requestId = ++latestDetailRequestRef.current;
      const isLatestRequest = () => requestId === latestDetailRequestRef.current;
      setIsRankingLoading(true);
      try {
        const response = await apiClient.college.getRanking(rankingId);
        if (!isLatestRequest()) return;
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
              // Objects (not plain codes): backend returns per-subtype review
              // status, consumed as-is by CollegeRankingTable.
              eligible_subtypes?: Array<{
                code: string;
                is_rejected: boolean;
                rejected_by?: {
                  role: string;
                  name: string;
                  reviewed_at: string;
                };
                rejection_reason?: string;
              }>;
              is_renewal?: boolean;
              renewal_year?: number | null;
              status?: string;
              review_status?: string;
              student_info?: { display_name?: string; student_id?: string };
              // #68: nationality/identity snapshot keys for the 國籍/身分 column
              student_data?: {
                std_nation?: string | null;
                std_identity?: number | string | null;
              };
            };
          }
          const rankingPayload = response.data as {
            items?: RankingItemPayload[];
            total_quota?: number;
            college_quota?: number;
            college_quota_breakdown?: Record<string, unknown>;
            sub_type_metadata?: Array<{ code?: string; [key: string]: unknown }>;
            sub_type_code?: string;
            academic_year?: number;
            semester?: string | null;
            is_finalized?: boolean;
            distribution_executed?: boolean;
            pending_application_count?: number;
            stale_application_count?: number;
            college_review_end?: string | null;
          };
          const transformedApplications = (rankingPayload.items || []).map(
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
              student_data: item.application?.student_data,
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
          setActiveConfigDeadline(rankingPayload.college_review_end ?? null);

          setRankingData({
            applications: transformedApplications,
            totalQuota: rankingPayload.total_quota || 0,
            collegeQuota: rankingPayload.college_quota,
            collegeQuotaBreakdown: rankingPayload.college_quota_breakdown as
              | Record<string, { quota?: number; label?: string; label_en?: string }>
              | undefined,
            subTypeMetadata: Array.isArray(rankingPayload.sub_type_metadata)
              ? (rankingPayload.sub_type_metadata.reduce(
                  (
                    acc: Record<string, { code: string; label: string; label_en: string }>,
                    meta: { code?: string; [key: string]: unknown }
                  ) => {
                    if (meta.code) {
                      acc[meta.code] = meta as {
                        code: string;
                        label: string;
                        label_en: string;
                      };
                    }
                    return acc;
                  },
                  {}
                ) as Record<string, { code: string; label: string; label_en: string }>)
              : (rankingPayload.sub_type_metadata as Record<string, { code: string; label: string; label_en: string }> | undefined) || {},
            subTypeCode: rankingPayload.sub_type_code || "default",
            academicYear: rankingPayload.academic_year || 0,
            semester: rankingPayload.semester,
            isFinalized: rankingPayload.is_finalized || false,
            distributionExecuted: rankingPayload.distribution_executed || false,
            pendingApplicationCount: rankingPayload.pending_application_count ?? 0,
            staleApplicationCount: rankingPayload.stale_application_count ?? 0,
          });
        }
      } catch (error) {
        logger.error("Failed to fetch ranking details", { error: error });
      } finally {
        if (isLatestRequest()) setIsRankingLoading(false);
      }
    },
    [setIsRankingLoading, setRankingData, setActiveConfigDeadline]
  );

  // Latest selection, readable from the auto-refresh effect without listing
  // `selectedRanking` as a dependency. Having it as a dependency made every
  // ranking-card click re-fetch the rankings list AND the whole applications
  // list (per-student SIS lookups on the backend) on top of the detail
  // request the click handler already fires — that fan-out is what made
  // 點擊排名 slow to render.
  const selectedRankingRef = useRef(selectedRanking);
  useEffect(() => {
    selectedRankingRef.current = selectedRanking;
  }, [selectedRanking]);
  // After an awaited action on a ranking: is that ranking still the open one,
  // or did the user pick another card while the request was in flight?
  const isStillSelected = useCallback(
    (rankingId: number) => selectedRankingRef.current === rankingId,
    []
  );

  // Open a ranking as soon as the list is known instead of leaving the detail
  // area empty: the finalized one if the period has it (after a lock it is the
  // only ranking left in its scope), else the newest draft. Re-runs when the
  // selection no longer matches the filter (period switched, or the selected
  // draft was deleted by another ranking's lock).
  useEffect(() => {
    const isSelectionValid = filteredRankings.some(
      ranking => ranking.id === selectedRanking
    );
    if (isSelectionValid) return;
    const targetId = pickDefaultRankingId(filteredRankings);
    if (targetId === null) return;
    setSelectedRanking(targetId);
    fetchRankingDetails(targetId);
  }, [filteredRankings, selectedRanking, setSelectedRanking, fetchRankingDetails]);

  // Auto-refresh when switching to ranking tab or when data version changes
  useEffect(() => {
    // Only refresh when:
    // 1. Current tab is "ranking"
    // 2. Not currently loading
    if (activeTab === "ranking") {
      logger.debug(
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
      const currentRanking = selectedRankingRef.current;
      if (currentRanking && !isRankingLoading) {
        fetchRankingDetails(currentRanking);
      }
    }
    // Note: isRankingLoading and fetchRankingDetails are deliberately not deps
    // (infinite loop); the condition check (!isRankingLoading) inside the
    // effect is sufficient. selectedRanking is read via ref (see above).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, dataVersion, fetchRankings]);

  const createNewRanking = useCallback(async () => {
    try {
      const academicConfig = await getAcademicConfig();
      const scholarshipConfigData = await getScholarshipConfig();

      const { scholarshipTypeId, subTypeCode } = resolveRankingTarget(
        availableOptions?.scholarship_types,
        scholarshipConfigData,
        activeScholarshipTab
      );
      if (!scholarshipTypeId || !subTypeCode) {
        toast.error(
          locale === "zh"
            ? "無法判斷要建立排名的獎學金類型，請重新整理頁面"
            : "Could not determine the scholarship for the new ranking. Please refresh the page."
        );
        return;
      }
      const useYear = selectedAcademicYear || academicConfig.currentYear;
      const useSemester = selectedSemester || academicConfig.currentSemester;

      const semesterName =
        useSemester === Semester.FIRST
          ? "上學期"
          : useSemester === Semester.SECOND
            ? "下學期"
            : "全年";

      // Always creates a NEW draft; a college may keep several per period and
      // picks one with 確認排名. The backend answers 409 (shown below as
      // response.message) while a locked or distributed ranking exists in the
      // scope. The name carries a timestamp so the drafts are distinguishable.
      const response = await apiClient.college.createRanking({
        scholarship_type_id: scholarshipTypeId,
        sub_type_code: subTypeCode,
        academic_year: useYear,
        semester: useSemester === Semester.YEARLY ? null : useSemester,
        ranking_name: buildDefaultRankingName({
          scholarshipName: scholarshipType.name,
          academicYear: useYear,
          semesterLabel: semesterName,
          existingNames: rankings.map(ranking => ranking.ranking_name),
        }),
      });

      if (response.success && response.data) {
        try {
          // Refresh rankings list
          await fetchRankings();
          // Select the new ranking
          const newRanking = response.data as {
            id: number;
            ranking_name?: string;
          };
          setSelectedRanking(newRanking.id);
          // Load ranking details
          await fetchRankingDetails(newRanking.id);
          // Increment data version
          incrementDataVersion();

          toast.success(
            locale === "zh"
              ? `排名「${newRanking.ranking_name || "新排名"}」已成功建立`
              : `Ranking "${newRanking.ranking_name || "New Ranking"}" has been created successfully`
          );
        } catch (fetchError) {
          logger.error("Failed to load ranking after creation", { fetchError: fetchError });
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
      logger.error("Failed to create ranking", { error: error });
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
    rankings,
    fetchRankings,
    setSelectedRanking,
    fetchRankingDetails,
    toast,
    locale,
    incrementDataVersion,
  ]);

  const handleRankingChange = useCallback(
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
          logger.error("Failed to save ranking", { error: error });
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

  // 確認排名 confirmation, open while the target has drafts beside it that the
  // lock will delete. Holds a snapshot so the dialog text cannot shift if the
  // list refreshes underneath it.
  const [finalizeCandidate, setFinalizeCandidate] =
    useState<FinalizeCandidate | null>(null);
  const [isFinalizing, setIsFinalizing] = useState(false);

  const finalizeRanking = useCallback(
    async (rankingId: number) => {
      setIsFinalizing(true);
      try {
        const response = await apiClient.college.finalizeRanking(rankingId);
        if (!response.success) {
          toast.error(
            response.message ||
              (locale === "zh" ? "無法鎖定排名" : "Failed to lock the ranking")
          );
          return;
        }
        const deletedCount = response.data?.deleted_ranking_count ?? 0;
        // The lock deletes the scope's other rankings — possibly the one that
        // was open (finalizing via another card's lock toggle). Select the
        // confirmed ranking BEFORE the list refresh so the auto-select effect
        // never reopens a deleted id, and re-read its details first so the
        // table never shows a deleted ranking's rows under the new selection
        // (the backend also recomputes the pending / stale counts on lock).
        setSelectedRanking(rankingId);
        await fetchRankingDetails(rankingId);
        await fetchRankings();
        incrementDataVersion();
        toast.success(
          locale === "zh"
            ? `排名已鎖定${deletedCount > 0 ? `，已刪除其他 ${deletedCount} 份排名` : ""}`
            : `Ranking locked${deletedCount > 0 ? `; ${deletedCount} other ranking(s) deleted` : ""}`
        );
      } catch (error) {
        logger.error("Failed to finalize ranking", { error: error });
        toast.error(
          locale === "zh" ? "鎖定排名時發生錯誤" : "An error occurred while locking the ranking"
        );
      } finally {
        setIsFinalizing(false);
      }
    },
    [
      fetchRankings,
      fetchRankingDetails,
      setSelectedRanking,
      locale,
      incrementDataVersion,
    ]
  );

  // Both 確認排名 entry points (card lock toggle and the table button) land
  // here. Without siblings in the scope there is nothing to delete, so lock
  // directly; otherwise ask first — the deletion cannot be undone.
  const handleFinalizeRanking = useCallback(
    (targetRankingId?: number) => {
      const rankingId = targetRankingId ?? selectedRanking;
      if (!rankingId) return;

      const target = rankings.find(ranking => ranking.id === rankingId);
      const siblings = target ? findScopeSiblings(rankings, target) : [];
      if (!target || siblings.length === 0) {
        void finalizeRanking(rankingId);
        return;
      }
      setFinalizeCandidate({ id: rankingId, name: target.ranking_name, siblings });
    },
    [selectedRanking, rankings, finalizeRanking]
  );

  const handleConfirmFinalize = useCallback(async () => {
    if (!finalizeCandidate) return;
    await finalizeRanking(finalizeCandidate.id);
    setFinalizeCandidate(null);
  }, [finalizeCandidate, finalizeRanking]);

  const handleUnfinalizeRanking = useCallback(
    async (targetRankingId?: number) => {
      const rankingId = targetRankingId ?? selectedRanking;
      if (!rankingId) return;

      try {
        const response = await apiClient.college.unfinalizeRanking(rankingId);
        if (response.success) {
          await fetchRankings();
          if (rankingData && isStillSelected(rankingId)) {
            setRankingData({ ...rankingData, isFinalized: false });
            // Unlocking re-enables syncing; re-read so the pending / stale
            // counts and the sync button reflect the draft state.
            await fetchRankingDetails(rankingId);
          }
          incrementDataVersion();
          toast.success(
            locale === "zh" ? "排名已解除鎖定" : "Ranking unlocked"
          );
        } else {
          toast.error(
            response.message ||
              (locale === "zh" ? "無法解除鎖定" : "Failed to unlock the ranking")
          );
        }
      } catch (error) {
        logger.error("Failed to unfinalize ranking", { error: error });
        toast.error(
          locale === "zh" ? "解除鎖定時發生錯誤" : "An error occurred while unlocking the ranking"
        );
      }
    },
    [
      selectedRanking,
      rankingData,
      isStillSelected,
      fetchRankings,
      fetchRankingDetails,
      setRankingData,
      toast,
      locale,
      incrementDataVersion,
    ]
  );

  // 同步申請名單: update the selected draft in place — newly eligible
  // applications are added, ones no longer eligible removed (a distributed
  // ranking only gains rows). Never POST /rankings here: that always creates
  // another draft.
  const [isSyncing, setIsSyncing] = useState(false);
  const handleSyncRanking = useCallback(async () => {
    const rankingId = selectedRanking;
    if (!rankingId) return;

    setIsSyncing(true);
    try {
      const response = await apiClient.college.syncRanking(rankingId);
      if (!response.success) {
        toast.error(
          response.message ||
            (locale === "zh" ? "無法同步申請名單" : "Failed to sync the application list")
        );
        return;
      }
      const added = response.data?.added_application_count ?? 0;
      const removed = response.data?.removed_application_count ?? 0;
      if (isStillSelected(rankingId)) await fetchRankingDetails(rankingId);
      await fetchRankings();
      incrementDataVersion();

      if (added === 0 && removed === 0) {
        toast.info(
          locale === "zh"
            ? "排名已與申請名單一致"
            : "The ranking already matches the application list"
        );
        return;
      }
      const zhParts = [
        added > 0 ? `加入 ${added} 位新申請者` : null,
        removed > 0 ? `移除 ${removed} 筆已不符合的申請` : null,
      ].filter(Boolean);
      const enParts = [
        added > 0 ? `added ${added} new applicant(s)` : null,
        removed > 0 ? `removed ${removed} application(s) no longer eligible` : null,
      ].filter(Boolean);
      toast.success(
        locale === "zh" ? `已${zhParts.join("、")}` : `Synced: ${enParts.join(", ")}`
      );
    } catch (error) {
      logger.error("Failed to sync ranking", { error: error });
      toast.error(
        locale === "zh"
          ? "同步申請名單時發生錯誤"
          : "An error occurred while syncing the application list"
      );
    } finally {
      setIsSyncing(false);
    }
  }, [
    selectedRanking,
    isStillSelected,
    fetchRankingDetails,
    fetchRankings,
    incrementDataVersion,
    locale,
  ]);

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
        logger.error("Failed to import Excel", { error: error });
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
        // Refresh the list BEFORE clearing the selection, otherwise the
        // auto-select effect would re-open the just-deleted ranking from the
        // stale list and hit a 404.
        await fetchRankings();
        if (selectedRanking === rankingToDelete.id) {
          setSelectedRanking(null);
          setRankingData(null);
          setActiveConfigDeadline(null);
        }
        incrementDataVersion();
        setShowDeleteRankingDialog(false);
        setRankingToDelete(null);
      } else {
        // e.g. 409: a distributed or roster-referenced ranking cannot be deleted.
        toast.error(
          response.message ||
            (locale === "zh" ? "無法刪除排名" : "Failed to delete the ranking")
        );
        setShowDeleteRankingDialog(false);
      }
    } catch (error) {
      logger.error("Failed to delete ranking", { error: error });
      toast.error(
        locale === "zh" ? "刪除排名時發生錯誤" : "An error occurred while deleting the ranking"
      );
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
    locale,
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
        logger.error("Failed to update ranking name", { error: error });
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
      r => r && r.college_review_end
    )?.college_review_end as string | undefined;
    return panelDeadline ?? fromList ?? activeConfigDeadline ?? null;
  }, [panelDeadline, filteredRankings, activeConfigDeadline]);
  const deadlineInfo = useMemo(
    () => computeDeadlineInfo(deadlineISO),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `now` triggers re-eval
    [deadlineISO, now]
  );
  const isAdmin = user.role === "admin" || user.role === "super_admin";
  const isLockedByDeadline = deadlineInfo.state === "passed" && !isAdmin;

  // 建立新排名 is refused (409) while the scope it creates into holds a locked
  // or distributed ranking; resolve that scope exactly like createNewRanking
  // (full scope against every ranking, not the period filter's view) so the
  // button can be disabled with the reason up front. Until a period is picked
  // the scope is unknown and the backend's 409 is the only guard.
  const blockingRanking = useMemo(() => {
    const { scholarshipTypeId, subTypeCode } = resolveRankingTarget(
      availableOptions?.scholarship_types,
      scholarshipConfig,
      activeScholarshipTab
    );
    if (
      !scholarshipTypeId ||
      !subTypeCode ||
      typeof selectedAcademicYear !== "number" ||
      !selectedSemester
    ) {
      return undefined;
    }
    return findBlockingRanking(rankings, {
      scholarship_type_id: scholarshipTypeId,
      sub_type_code: subTypeCode,
      academic_year: selectedAcademicYear,
      semester: selectedSemester === Semester.YEARLY ? null : selectedSemester,
      college_code: user.college_code ?? null,
    });
  }, [
    availableOptions,
    scholarshipConfig,
    activeScholarshipTab,
    selectedAcademicYear,
    selectedSemester,
    rankings,
    user.college_code,
  ]);
  const createBlockedReason = blockingRanking
    ? blockingRanking.is_finalized
      ? locale === "zh"
        ? "已有鎖定的排名，解除鎖定後才能新增排名"
        : "A locked ranking exists; unlock it to create another"
      : locale === "zh"
        ? "已有執行分發的排名，無法再新增排名"
        : "A distributed ranking exists; no new ranking can be created"
    : null;

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

          {/* 同步申請名單 updates the selected draft in place (POST
              /rankings/{id}/sync); a locked ranking must be unlocked first. */}
          {filteredRankings.length > 0 &&
            rankingData &&
            !rankingData.isFinalized && (
              <Button
                variant="outline"
                onClick={handleSyncRanking}
                disabled={isSyncing || isLockedByDeadline}
              >
                <RefreshCw
                  className={`h-4 w-4 mr-2 ${isSyncing ? "animate-spin" : ""}`}
                />
                同步申請名單
              </Button>
            )}

          {/* Each click creates another draft to compare; blocked while the
              scope holds a locked / distributed ranking (backend 409s too). */}
          <div className="flex flex-col items-end gap-1">
            <Button
              onClick={createNewRanking}
              disabled={isLockedByDeadline || Boolean(blockingRanking)}
              title={
                blockingRanking
                  ? `${createBlockedReason}（${blockingRanking.ranking_name}）`
                  : undefined
              }
            >
              <Plus className="h-4 w-4 mr-2" />
              建立新排名
            </Button>
            {createBlockedReason && (
              <p className="text-xs text-muted-foreground">
                {createBlockedReason}
              </p>
            )}
          </div>
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
                {formatDeadline(deadlineInfo.deadline)}
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
                {formatDeadline(deadlineInfo.deadline)}
                。
              </>
            ) : (
              <>
                {locale === "zh" ? "排名截止時間" : "Ranking deadline"}:
                {" "}
                {formatDeadline(deadlineInfo.deadline)}
                {locale === "zh" ? "  ·  剩餘 " : " · "}
                {formatCountdown(deadlineInfo.msToDeadline ?? 0, locale)}
              </>
            )}
          </div>
        </div>
      )}

      {rankingData && (
        <RankingDriftBanner
          locale={locale}
          pendingCount={rankingData.pendingApplicationCount}
          staleCount={rankingData.staleApplicationCount}
          isFinalized={rankingData.isFinalized}
          distributionExecuted={rankingData.distributionExecuted}
          isLockedByDeadline={isLockedByDeadline}
        />
      )}

      {/* Ranking Selection */}
      <Card>
        <CardHeader>
          <CardTitle>學院排名</CardTitle>
          <CardDescription>
            可建立多份排名比較；按「確認排名」鎖定後，其他排名會被刪除、只保留這一份，鎖定期間無法再新增排名（解除鎖定後可再新增）
          </CardDescription>
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
              title: "尚未建立排名",
              description: `${scholarshipType.name} 目前在選定的學年度與學期尚未建立排名`,
              actionButton:
                deadlineInfo.state === "passed" && !isAdmin
                  ? undefined
                  : {
                      label: "建立排名",
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
                    // The card hands back its view model; keep the full list row.
                    const target = filteredRankings.find(r => r.id === ranking.id);
                    if (!target) return;
                    setRankingToDelete(target);
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
            <>
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
              onFinalizeRanking={handleFinalizeRanking}
              onImportExcel={handleImportExcel}
              locale={locale}
              subTypeMeta={rankingData.subTypeMetadata}
              saveStatus={saveStatus}
            />
            </>
          )}
        </div>
      )}

      <FinalizeRankingDialog
        locale={locale}
        candidate={finalizeCandidate}
        isFinalizing={isFinalizing}
        onCancel={() => setFinalizeCandidate(null)}
        onConfirm={handleConfirmFinalize}
      />

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
