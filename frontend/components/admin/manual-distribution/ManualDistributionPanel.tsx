"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { logger } from "@/lib/utils/logger";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { useReferenceData } from "@/hooks/use-reference-data";
import { apiClient } from "@/lib/api";
import { exportDepartmentSummaryBulk } from "@/lib/api/modules/college";
import type {
  DistributionStudent,
  LocalAlloc,
  QuotaStatus,
  ReviewItemSummary,
  SubTypeConfigCol,
  DistributionHistoryRecord,
  RestoreRequest,
  DistributionSummaryResult,
  AllocationSuggestion,
  DistributionState,
  ReleaseChainItem,
} from "@/lib/api/modules/manual-distribution";
import { DistributionSummaryDialog } from "./DistributionSummaryDialog";
import {
  buildCollegeNameMap,
  getSavedAllocation,
  isCancelledAllocation,
  makeColKey,
  mergeSuggestions,
  reasonsBySuggestion,
  resolveCollegeName,
  summarizeReasons,
  toStagedItems,
  unallocatedReasonLabel,
  type UnallocatedReason,
} from "@/lib/api/modules/manual-distribution";
import { buildCollegeQuotaGrid } from "@/lib/api/modules/college-quota-grid";
import { User } from "@/types/user";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
  AllocationActionDialog,
  type AllocationMode,
} from "@/components/admin/manual-distribution/AllocationActionDialog";
import {
  AllocationStatusControl,
  type AllocationStatus,
} from "@/components/admin/manual-distribution/AllocationStatusControl";
import { CollegeQuotaMatrix } from "@/components/admin/manual-distribution/CollegeQuotaMatrix";
import {
  Loader2,
  Save,
  CheckCircle2,
  AlertCircle,
  Download,
  Clock,
  Eye,
  Shield,
  AlertTriangle,
  ArrowRight,
  RefreshCw,
  Wand2,
} from "lucide-react";

interface ManualDistributionPanelProps {
  user: User;
  scholarshipType: { id: number; code: string; name: string };
}

const ALL_ACADEMIES_SYSTEM = "__all__";

/** In-flight marker for the whole-page 預設分發 run; no college_code collides. */
const ALL_COLLEGES = "__all_colleges__";

/** Refusals when a college is over its own cell of quotas[sub_type] — the
 * offending cells are listed in the banner, so these only say why nothing ran. */
const OVERFLOW_BLOCKED_SAVE = "有學院超過名額上限，無法儲存（詳見上方紅色提示）";
const OVERFLOW_BLOCKED_FINALIZE =
  "有學院超過名額上限，無法確認分發（詳見上方紅色提示）";

/** Seed local allocation state from the server snapshot (null = 未決). */
function seedAllocations(
  students: DistributionStudent[]
): Map<number, LocalAlloc | null> {
  const allocMap = new Map<number, LocalAlloc | null>();
  for (const s of students) {
    allocMap.set(s.ranking_item_id, getSavedAllocation(s));
  }
  return allocMap;
}

/**
 * Derive abbreviated display name from sub_type code and full display_name.
 * nstc           → "國科會"
 * moe_1w/moe_2w  → "教育部"
 * other          → truncated display_name
 */
function getSubTypeShortName(sub_type: string, display_name: string): string {
  if (sub_type === "nstc") return "國科會";
  if (/^moe_\d+w$/.test(sub_type)) return "教育部";
  return display_name.length > 7
    ? display_name.slice(0, 6) + "…"
    : display_name;
}

const VERDICT_CHIP_BASE =
  "inline-flex items-center w-fit px-1 py-0.5 rounded border text-[10px] leading-none whitespace-nowrap";
const VERDICT_CHIP = {
  approve: `${VERDICT_CHIP_BASE} bg-emerald-50 text-emerald-700 border-emerald-300`,
  reject: `${VERDICT_CHIP_BASE} bg-red-50 text-red-600 border-red-300`,
  none: `${VERDICT_CHIP_BASE} bg-slate-50 text-slate-500 border-slate-300`,
};

/**
 * Per-sub-type 推薦/不推薦 chips for the 教授推薦/學院推薦 columns
 * (reviewer comments on hover); renders nothing when there are no verdicts.
 */
function ReviewItemChips({
  items,
  quotaStatus,
}: {
  items: ReviewItemSummary[];
  quotaStatus: QuotaStatus;
}) {
  return (
    <>
      {items.map((item, idx) => {
        const label = getSubTypeShortName(
          item.sub_type_code,
          quotaStatus[item.sub_type_code]?.display_name || item.sub_type_code
        );
        const isApprove = item.recommendation === "approve";
        return (
          <span
            key={`${item.sub_type_code}-${idx}`}
            title={item.comments || undefined}
            className={isApprove ? VERDICT_CHIP.approve : VERDICT_CHIP.reject}
          >
            {label}: {isApprove ? "推薦" : "不推薦"}
          </span>
        );
      })}
    </>
  );
}

/**
 * Per-sub-type verdict chips for the 教授推薦/學院推薦 columns: one chip for
 * EVERY applied sub-type, so a sub-type the reviewer rejected (不推薦) or
 * never gave a verdict on (未推薦) is written out instead of silently
 * omitted. Any reject wins over approve (matches the rejected_sub_types
 * convention); review items on sub-types outside the applied list are still
 * appended so no verdict is lost.
 */
function SubTypeVerdictChips({
  appliedSubTypes,
  items,
  quotaStatus,
  noVerdictTitle,
}: {
  appliedSubTypes: string[];
  items: ReviewItemSummary[];
  quotaStatus: QuotaStatus;
  /** Tooltip on the gray 未推薦 chip — names which reviewer gave no verdict. */
  noVerdictTitle: string;
}) {
  const norm = (code: string) => code.toLowerCase().trim();
  const applied = Array.from(new Set(appliedSubTypes.map(norm)));
  const labelFor = (code: string) =>
    getSubTypeShortName(code, quotaStatus[code]?.display_name || code);
  const extras = items.filter(item => !applied.includes(norm(item.sub_type_code)));
  return (
    <>
      {applied.map(code => {
        const verdicts = items.filter(item => norm(item.sub_type_code) === code);
        const reject = verdicts.find(item => item.recommendation !== "approve");
        const approve = verdicts.find(item => item.recommendation === "approve");
        if (reject) {
          return (
            <span
              key={code}
              title={reject.comments || undefined}
              className={VERDICT_CHIP.reject}
            >
              {labelFor(code)}: 不推薦
            </span>
          );
        }
        if (approve) {
          return (
            <span
              key={code}
              title={approve.comments || undefined}
              className={VERDICT_CHIP.approve}
            >
              {labelFor(code)}: 推薦
            </span>
          );
        }
        return (
          <span
            key={code}
            title={noVerdictTitle}
            className={VERDICT_CHIP.none}
          >
            {labelFor(code)}: 未推薦
          </span>
        );
      })}
      <ReviewItemChips items={extras} quotaStatus={quotaStatus} />
    </>
  );
}

export function ManualDistributionPanel({
  user,
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

  const { academies } = useReferenceData();
  const [summaryDept, setSummaryDept] = useState<string>("");

  // The 匯出總表 dropdown lists 學院 (academies), not individual 系所.
  // Admins see every academy; a college user sees only their own.
  const visibleAcademies = useMemo(() => {
    if (!academies) return [];
    if (user.role === "admin" || user.role === "super_admin") return academies;
    return academies.filter(
      (a: { code: string; name: string }) => a.code === user.college_code
    );
  }, [academies, user]);

  const handleDownloadSummary = useCallback(async () => {
    if (!summaryDept || !scholarshipType.id || !selectedAcademicYear) {
      toast.error("缺少必要的篩選條件");
      return;
    }
    try {
      const common = {
        scholarship_type_id: scholarshipType.id,
        academic_year: selectedAcademicYear,
        semester: selectedSemester ?? null,
      };
      let result: { blob: Blob; filename: string };
      if (summaryDept === ALL_ACADEMIES_SYSTEM) {
        result = await exportDepartmentSummaryBulk({ ...common, scope: "all" });
      } else {
        // summaryDept holds an academy code — export that college's departments.
        result = await exportDepartmentSummaryBulk({
          ...common,
          scope: "college",
          academy_code: summaryDept,
        });
      }
      const url = URL.createObjectURL(result.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = result.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(`匯出失敗：${(err as Error).message}`);
    }
  }, [summaryDept, scholarshipType.id, selectedAcademicYear, selectedSemester]);

  const [students, setStudents] = useState<DistributionStudent[]>([]);
  const [quotaStatus, setQuotaStatus] = useState<QuotaStatus>({});
  // Map<ranking_item_id, LocalAlloc | null>
  const [localAllocations, setLocalAllocations] = useState<
    Map<number, LocalAlloc | null>
  >(new Map());
  // Mirror of localAllocations for async handlers: an await'd handler must merge
  // into the CURRENT staged map, not the one captured when it started, or it
  // silently reverts checkbox edits made while its request was in flight.
  const localAllocationsRef = useRef(localAllocations);
  useEffect(() => {
    localAllocationsRef.current = localAllocations;
  }, [localAllocations]);
  // Why the last 預設分發 run left a row 未決, keyed by ranking_item_id. Comes
  // straight from the backend, which is the only place that can tell a review
  // reject from an exhausted quota. Cleared whenever the grid is reseeded.
  const [unallocatedReasons, setUnallocatedReasons] = useState<
    Map<number, UnallocatedReason>
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
      allocation_year: number | null;
      project_number: string | null;
      qualified_count: number;
      total_amount: string;
    }>;
  } | null>(null);
  const [previewApplied, setPreviewApplied] = useState(false);
  // Which 預設分發 run is in flight: a college_code, ALL_COLLEGES, or null (idle).
  const [autoAllocatingCollege, setAutoAllocatingCollege] = useState<
    string | null
  >(null);
  // Renewal-aware panel state (Phase 8.2): approved renewals occupying slots,
  // remaining quota per (sub_type × allocation_year), and ranked candidates
  // with challenge metadata. Independent of `students` / `quotaStatus` —
  // additive, never blocks the existing flow if the call fails.
  const [distributionState, setDistributionState] =
    useState<DistributionState | null>(null);
  const [isLoadingState, setIsLoadingState] = useState(false);
  const [action, setAction] = useState<{
    mode: AllocationMode;
    applicationId: number;
    studentName: string;
    /** Student holds (or held) a quota slot — drives the dialog's copy. */
    hasAllocation: boolean;
  } | null>(null);

  /**
   * Flatten quota status into (sub_type × source-config) columns, ordered by:
   * - sub_type (by appearance order in quotaStatus keys)
   * - own config first, then linked sources by descending academic_year
   */
  const subTypeCols = useMemo<SubTypeConfigCol[]>(() => {
    const cols: SubTypeConfigCol[] = [];
    for (const [sub_type, stData] of Object.entries(quotaStatus)) {
      const configs = [...stData.by_config].sort((a, b) => {
        if (a.is_own !== b.is_own) return a.is_own ? -1 : 1; // own first
        return b.academic_year - a.academic_year; // then descending year
      });
      const isMulti = configs.length > 1;
      const shortName = getSubTypeShortName(sub_type, stData.display_name);
      for (const cData of configs) {
        if (cData.total <= 0) continue;
        // Multi-config sub-types (e.g. nstc borrowing): label with config code → "國科會 · phd_114"
        // Single-config sub-types (e.g. moe_1w): just the short name → "教育部"
        const display_name = isMulti ? `${shortName} · ${cData.config_code}` : shortName;
        cols.push({
          sub_type,
          config_id: cData.config_id,
          config_code: cData.config_code,
          academic_year: cData.academic_year,
          is_own: cData.is_own,
          display_name,
          total: cData.total,
          remaining: cData.remaining,
          key: makeColKey(sub_type, cData.config_id),
        });
      }
    }
    return cols;
  }, [quotaStatus]);

  /** Count how many local allocations are using each (sub_type, config) slot */
  const localAllocCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const col of subTypeCols) counts[col.key] = 0;
    for (const [, alloc] of localAllocations) {
      if (alloc) {
        const k = makeColKey(alloc.sub_type, alloc.config_id);
        counts[k] = (counts[k] ?? 0) + 1;
      }
    }
    return counts;
  }, [localAllocations, subTypeCols]);

  // Academies-first code→name map, shared with the quota matrix so every
  // college label on this screen resolves identically (see buildCollegeNameMap).
  const collegeNames = useMemo(
    () => buildCollegeNameMap(academies, students),
    [academies, students]
  );

  const studentByItemId = useMemo(
    () => new Map(students.map(s => [s.ranking_item_id, s])),
    [students]
  );

  // Each college's cell of quotas[sub_type] is a HARD cap, enforced server-side
  // in _assert_round_not_oversubscribed. This is the SAME live grid the
  // 各學院剩餘名額 matrix renders, so a tick that would overfill a college is
  // refused on the spot (see collegeQuotaRefusal) and 儲存/確認分發 have a
  // backstop for states the ticks can't produce (auto-preview, stale snapshot).
  const collegeQuotaGrid = useMemo(
    () =>
      buildCollegeQuotaGrid({
        cols: subTypeCols,
        quotaStatus,
        students,
        localAllocations,
      }),
    [subTypeCols, quotaStatus, students, localAllocations]
  );

  /**
   * Why assigning `rankingItemId` to `col` must be refused, or null when it fits.
   *
   * Renewal rows are exempt: the backend counts a renewal's consumption via its
   * approved Application, not its ranking item, so it never moves this grid.
   */
  const collegeQuotaRefusal = useCallback(
    (rankingItemId: number, col: SubTypeConfigCol): string | null => {
      const student = studentByItemId.get(rankingItemId);
      if (!student || student.is_renewal) return null;
      // A non-matrix column has no per-college split at all — only the global
      // pool caps it, and that is the `atCapacity` disable on the checkbox.
      if (!collegeQuotaGrid.hasCollegeSplit(col.key)) return null;
      const code = student.college_code || "";
      const cell = collegeQuotaGrid.cell(code, col.key);
      if (!cell || cell.remaining > 0) return null;
      const college = resolveCollegeName(collegeNames, code, student.college_name);
      if (cell.total <= 0) {
        return `${college} 在「${col.display_name}」沒有名額，無法核配`;
      }
      return `${college}「${col.display_name}」名額已用完（${cell.total - cell.remaining}/${cell.total}），無法再核配`;
    },
    [studentByItemId, collegeQuotaGrid, collegeNames]
  );

  const collegeOverflowMessage = useMemo(() => {
    const { overflows } = collegeQuotaGrid;
    if (overflows.length === 0) return null;
    const detail = overflows
      .map(
        o =>
          `${resolveCollegeName(collegeNames, o.collegeCode)}／${o.col.display_name} ${o.used}/${o.total}`
      )
      .join("；");
    return `超過各學院名額（已核配/該學院名額）：${detail}。請調整分發後再儲存。`;
  }, [collegeQuotaGrid, collegeNames]);

  const fetchData = useCallback(async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    setIsLoading(true);
    setSaveMessage(null);
    setPreviewApplied(false);
    setUnallocatedReasons(new Map());
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
        const allocMap = seedAllocations(studentsResp.data);

        // Load preview separately (optional — failure should not break the page)
        let previewSuggestions: AllocationSuggestion[] = [];
        try {
          const previewResp =
            await apiClient.manualDistribution.getAutoAllocatePreview(
              scholarshipTypeId,
              selectedAcademicYear,
              selectedSemester,
              undefined,
              // The overlay a fresh screen would send equals the saved state, so
              // it is omitted: the server's own snapshot IS this screen.
              undefined
            );
          if (previewResp.success && previewResp.data) {
            previewSuggestions = previewResp.data.suggestions;
          }
        } catch {
          // Preview is optional; proceed without it
        }

        // Apply auto-preview suggestions for 未決 students. Eligible = rows the
        // grid actually renders, minus 撤銷/停發 — a suggestion for a row that is
        // not on screen (a duplicate ranking item, or a cancelled student behind
        // a disabled checkbox) would be saved without the admin ever being able
        // to see or untick it.
        //
        // Quota status is the same kind of prerequisite: the 核配 columns are
        // derived from it, so if it failed to load the grid renders NO columns
        // and staged suggestions would be invisible yet still saved.
        const hasQuota =
          quotaResp.success &&
          !!quotaResp.data &&
          Object.keys(quotaResp.data).length > 0;
        const eligibleItemIds = new Set(
          studentsResp.data
            .filter(s => !isCancelledAllocation(s))
            .map(s => s.ranking_item_id)
        );
        const merged = mergeSuggestions(
          allocMap,
          hasQuota ? previewSuggestions : [],
          eligibleItemIds
        );
        // Commit students together with their seeded allocations so no render
        // sees new students against stale local state (the matrix reads both).
        setStudents(studentsResp.data);
        setPreviewApplied(merged.filled > 0);
        setLocalAllocations(merged.next);
        setUnallocatedReasons(
          hasQuota ? reasonsBySuggestion(previewSuggestions) : new Map()
        );
      }
      if (quotaResp.success && quotaResp.data) {
        setQuotaStatus(quotaResp.data);
      }
    } finally {
      setIsLoading(false);
    }
  }, [scholarshipTypeId, selectedAcademicYear, selectedSemester]);

  /**
   * Refetch students + quota status together and reseed local allocations
   * from the server snapshot. Shared by save / finalize / restore so the
   * matrix always sees a consistent server state after a mutation. Unlike
   * fetchData, this does NOT clear saveMessage or apply auto-preview
   * suggestions.
   */
  const reloadServerSnapshot = useCallback(async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
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
      setLocalAllocations(seedAllocations(studentsResp.data));
      // The reseed is server-only, so any auto-preview suggestions are gone
      // (saved or discarded) — clear the "已自動預設分配" notice, and with it
      // the reasons, which described a screen that no longer exists.
      setPreviewApplied(false);
      setUnallocatedReasons(new Map());
    }
    if (quotaResp.success && quotaResp.data) {
      setQuotaStatus(quotaResp.data);
    }
  }, [scholarshipTypeId, selectedAcademicYear, selectedSemester]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Fetch renewal-aware panel state alongside the existing student/quota
  // pipeline. Wrapped in its own effect so a state-endpoint failure cannot
  // break the legacy table render.
  useEffect(() => {
    let cancelled = false;
    const loadState = async () => {
      if (!scholarshipTypeId || !selectedAcademicYear) {
        setDistributionState(null);
        return;
      }
      setIsLoadingState(true);
      try {
        const resp = await apiClient.manualDistribution.getState(
          scholarshipTypeId,
          selectedAcademicYear
        );
        if (cancelled) return;
        if (resp.success && resp.data) {
          setDistributionState(resp.data);
        } else {
          // Soft-fail: keep existing UI working even if state endpoint errors
          setDistributionState(null);
        }
      } catch {
        if (!cancelled) setDistributionState(null);
      } finally {
        if (!cancelled) setIsLoadingState(false);
      }
    };
    loadState();
    return () => {
      cancelled = true;
    };
  }, [scholarshipTypeId, selectedAcademicYear]);

  // Lookup: which `application_id`s are challenge applications. Used to
  // surface the 🛡 marker and amber styling in the candidate table.
  const challengeAppMap = useMemo(() => {
    const map = new Map<
      number,
      {
        applying_sub_type: string | null;
        challenged_renewal: {
          renewal_application_id: number;
          sub_type: string | null;
          renewal_year: number | null;
        } | null;
      }
    >();
    if (!distributionState) return map;
    for (const c of distributionState.candidates) {
      if (c.is_challenge) {
        map.set(c.application_id, {
          applying_sub_type: c.applying_sub_type,
          challenged_renewal: c.challenged_renewal,
        });
      }
    }
    return map;
  }, [distributionState]);

  // Release preview: dry-run the proposed allocations so admins can see
  // which renewals would be cancelled and the auto-fill suggestion. Only
  // POSTs when at least one challenge is currently staged.
  const [releasePreview, setReleasePreview] = useState<ReleaseChainItem[]>([]);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);

  const hasStagedChallenge = useMemo(() => {
    if (challengeAppMap.size === 0) return false;
    // Cross-reference staged allocations with challenge application_ids.
    for (const [rankingItemId, alloc] of localAllocations) {
      if (!alloc) continue;
      const student = students.find(s => s.ranking_item_id === rankingItemId);
      if (student && challengeAppMap.has(student.application_id)) return true;
    }
    return false;
  }, [localAllocations, challengeAppMap, students]);

  useEffect(() => {
    let cancelled = false;
    const runPreview = async () => {
      if (
        !scholarshipTypeId ||
        !selectedAcademicYear ||
        !selectedSemester ||
        !hasStagedChallenge
      ) {
        setReleasePreview([]);
        return;
      }
      const allocations = Array.from(localAllocations.entries())
        .filter(([, alloc]) => alloc !== null)
        .map(([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_config_id: alloc?.config_id ?? null,
        }));
      setIsLoadingPreview(true);
      try {
        const resp = await apiClient.manualDistribution.previewDistribution({
          scholarship_type_id: scholarshipTypeId,
          academic_year: selectedAcademicYear,
          semester: selectedSemester,
          allocations,
        });
        if (cancelled) return;
        if (resp.success && resp.data) {
          setReleasePreview(resp.data.release_chain || []);
        } else {
          setReleasePreview([]);
        }
      } catch {
        if (!cancelled) setReleasePreview([]);
      } finally {
        if (!cancelled) setIsLoadingPreview(false);
      }
    };
    runPreview();
    return () => {
      cancelled = true;
    };
  }, [
    scholarshipTypeId,
    selectedAcademicYear,
    selectedSemester,
    localAllocations,
    hasStagedChallenge,
  ]);

  const handleCheckbox = (rankingItemId: number, col: SubTypeConfigCol) => {
    const { sub_type, config_id } = col;
    const current = localAllocations.get(rankingItemId);
    const isUncheck =
      current?.sub_type === sub_type && current?.config_id === config_id;

    // A tick that would push this student's college past its own cell of
    // quotas[sub_type] is a no-op: the controlled checkbox snaps back to its
    // previous state and the reason surfaces as a toast. Unticking is always
    // allowed — it can only free a slot.
    if (!isUncheck) {
      const refusal = collegeQuotaRefusal(rankingItemId, col);
      if (refusal) {
        toast.error(refusal);
        return;
      }
    }

    // Unticking returns the row to 未決 — nothing else is remembered about it.
    // A 未決 row is open to 預設分發 again and its slot is free for someone
    // else; to keep a student out of the round entirely, use 撤銷/停發.
    setUnallocatedReasons(prev => {
      if (!prev.has(rankingItemId)) return prev;
      const next = new Map(prev);
      next.delete(rankingItemId);
      return next;
    });
    setLocalAllocations(prev => {
      const next = new Map(prev);
      const prevAlloc = next.get(rankingItemId);
      // Radio-like: clicking active → uncheck; clicking other → set exclusively
      if (
        prevAlloc?.sub_type === sub_type &&
        prevAlloc?.config_id === config_id
      ) {
        next.set(rankingItemId, null);
      } else {
        next.set(rankingItemId, { sub_type, config_id });
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    if (collegeOverflowMessage) {
      // The offending cells are already named in the banner above — don't repeat
      // the whole list here, just say why the click did nothing.
      setSaveMessage({ type: "error", text: OVERFLOW_BLOCKED_SAVE });
      return;
    }
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const allocations = Array.from(localAllocations.entries()).map(
        ([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_config_id: alloc?.config_id ?? null,
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
        // Reload students AND quota together (same pattern as finalize/restore)
        // so the matrix sees a consistent server snapshot — refetching quota
        // alone would leave `students` stale and double-count saved allocations.
        await reloadServerSnapshot();
      } else {
        setSaveMessage({ type: "error", text: resp.message || "儲存失敗" });
      }
    } catch (error) {
      logger.error("Save error", { error: error });
      // The quota gates (global pool / per-college cell) come back as a 400 whose
      // detail names the offending config or college — echo it, never bury it.
      setSaveMessage({
        type: "error",
        text: (error as Error)?.message || "儲存時發生錯誤",
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleFinalize = async () => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
      return;
    if (collegeOverflowMessage) {
      setSaveMessage({ type: "error", text: OVERFLOW_BLOCKED_FINALIZE });
      return;
    }
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
        await reloadServerSnapshot();
      } else {
        setSaveMessage({ type: "error", text: resp.message || "確認分發失敗" });
      }
    } catch (error) {
      logger.error("Finalize error", { error: error });
      setSaveMessage({
        type: "error",
        text: (error as Error)?.message || "確認分發時發生錯誤",
      });
    } finally {
      setIsFinalizing(false);
    }
  };

  /**
   * 產生造冊。`forceRegenerate` 為 true 時會重建「已存在」的造冊——不需要人員有
   * 異動也能以最新的分發／學生資料重新生成（已鎖定的造冊仍會被後端擋下）。
   */
  const handleGenerateRosters = async (forceRegenerate = false) => {
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
          force_regenerate: forceRegenerate,
        });
      if (resp.success && resp.data) {
        setRosterResult(resp.data);
        // 後端回傳的 message 會誠實交代「已存在未重新產生 / 已鎖定」的份數；
        // 只印 rosters_created 會讓「0 個」看起來像失敗。
        setSaveMessage({
          type: "success",
          text: resp.message || `已產生 ${resp.data.rosters_created} 個造冊`,
        });
      } else {
        setSaveMessage({ type: "error", text: resp.message || "造冊產生失敗" });
      }
    } catch (error) {
      logger.error("Generate rosters error", { error: error });
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
      logger.error("Load distribution summary error", { error: error });
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
      logger.error("Load history error", { error: error });
      setSaveMessage({ type: "error", text: "載入歷史記錄失敗" });
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const handleRestore = async (historyId: number) => {
    if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester) return;
    setIsRestoring(true);
    try {
      const resp = await apiClient.manualDistribution.restoreFromHistory(
        scholarshipTypeId,
        { history_id: historyId }
      );
      if (resp.success && resp.data) {
        const skipped = resp.data.skipped_rejected ?? 0;
        const skippedCancelled = resp.data.skipped_cancelled ?? 0;
        const notes = [
          skipped > 0 ? `${skipped} 筆因審核不同意已略過` : "",
          skippedCancelled > 0
            ? `${skippedCancelled} 筆因已撤銷／停發已略過`
            : "",
        ].filter(Boolean);
        setSaveMessage({
          type: "success",
          text:
            `成功還原 ${resp.data.restored_count} 筆分配紀錄` +
            (notes.length > 0 ? `（${notes.join("，")}）` : ""),
        });
        setShowHistoryDialog(false);
        await reloadServerSnapshot();
      } else {
        setSaveMessage({ type: "error", text: resp.message || "還原失敗" });
      }
    } catch (error) {
      logger.error("Restore error", { error: error });
      setSaveMessage({ type: "error", text: "還原時發生錯誤" });
    } finally {
      setIsRestoring(false);
    }
  };

  /**
   * Run the default distribution — for ONE college, or for all of them when
   * `collegeCode` is null.
   *
   * The plan is computed against THIS SCREEN: the current staged allocations go
   * up with the request, so a box the admin unticked has genuinely released its
   * slot and a box they ticked by hand has genuinely taken one. Reading the
   * saved distribution instead is what made the button report 「名額已用盡」 next
   * to visibly empty columns.
   *
   * It covers the WHOLE ranking in scope, not just the rows a 搜尋 filter leaves
   * on screen — the suggestions are a rank-ordered plan, and applying half of
   * one would hand a slot to the wrong student.
   *
   * Staged locally only — nothing is persisted until the admin presses 儲存 —
   * and it only fills 未決 rows, so it is safe to press repeatedly and never
   * overwrites a deliberate tick.
   */
  const handleAutoAllocate = useCallback(
    async (collegeCode: string | null, scopeName: string) => {
      if (!scholarshipTypeId || !selectedAcademicYear || !selectedSemester)
        return;
      // No columns means quota status never loaded (or carries no allocatable
      // slot). Without it there is nothing on screen to show what was staged —
      // refuse rather than stage invisible allocations that 儲存 would persist.
      if (subTypeCols.length === 0) {
        setSaveMessage({
          type: "error",
          text: "名額資料尚未載入，無法執行預設分發，請重新整理後再試",
        });
        return;
      }
      setAutoAllocatingCollege(collegeCode ?? ALL_COLLEGES);
      setSaveMessage(null);
      try {
        // Read through the ref, NOT the value captured before the await: the
        // checkboxes stay live during the request, so both the overlay sent up
        // and the map merged into must be the latest committed state.
        const resp = await apiClient.manualDistribution.getAutoAllocatePreview(
          scholarshipTypeId,
          selectedAcademicYear,
          selectedSemester,
          collegeCode ?? undefined,
          toStagedItems(localAllocationsRef.current)
        );
        if (!resp.success || !resp.data) {
          setSaveMessage({
            type: "error",
            text: resp.message || `${scopeName} 預設分發失敗`,
          });
          return;
        }
        const suggestions = resp.data.suggestions;
        // Eligible = the rows in scope (never touch another group), minus
        // 撤銷/停發 students, who keep their state and stay unallocated.
        const eligibleItemIds = new Set(
          students
            .filter(
              s =>
                (collegeCode === null ||
                  (s.college_code || "") === collegeCode) &&
                !isCancelledAllocation(s)
            )
            .map(s => s.ranking_item_id)
        );
        const { next, filled } = mergeSuggestions(
          localAllocationsRef.current,
          suggestions,
          eligibleItemIds
        );
        if (filled > 0) {
          setLocalAllocations(next);
          setPreviewApplied(true);
        }
        // Refresh the explanation for every row this run considered: a row it
        // actually staged loses its old one, an unplaced row takes the
        // backend's verdict. Rows out of scope keep whatever an earlier run
        // said. Keyed on what the merge STAGED, not on what the server
        // suggested — a suggestion the merge dropped as ineligible leaves the
        // row 未決, so clearing its reason would strip the only explanation on
        // screen.
        const runReasons = reasonsBySuggestion(suggestions);
        setUnallocatedReasons(prev => {
          const merged = new Map(prev);
          for (const s of suggestions) {
            if (s.sub_type_code && next.get(s.ranking_item_id)) {
              merged.delete(s.ranking_item_id);
            }
          }
          for (const [itemId, reason] of runReasons) {
            merged.set(itemId, reason);
          }
          return merged;
        });

        const breakdown = summarizeReasons(runReasons)
          .map(
            ({ reason, count }) =>
              `${count} 筆${unallocatedReasonLabel(reason)}`
          )
          .join("、");
        const text =
          filled > 0
            ? `${scopeName}：已預設分配 ${filled} 筆${
                breakdown ? `，另有 ${breakdown}` : ""
              }，請確認後儲存`
            : `${scopeName}：無可預設分配${breakdown ? `（${breakdown}）` : ""}`;
        setSaveMessage({ type: "success", text });
      } catch (error) {
        logger.error("Auto-allocate error", { error: error });
        setSaveMessage({
          type: "error",
          text: `${scopeName} 預設分發時發生錯誤`,
        });
      } finally {
        setAutoAllocatingCollege(null);
      }
    },
    [
      scholarshipTypeId,
      selectedAcademicYear,
      selectedSemester,
      students,
      subTypeCols,
    ]
  );

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
          collegeName: resolveCollegeName(collegeNames, key),
          students: seen.get(key)!,
        });
      }
      seen.get(key)!.push(s);
    }
    return groups;
  }, [filteredStudents, collegeNames]);

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
    <>
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
              <Select value={summaryDept} onValueChange={setSummaryDept}>
                <SelectTrigger className="w-[200px] h-9">
                  <SelectValue placeholder="選擇學院匯出總表" />
                </SelectTrigger>
                <SelectContent>
                  {visibleAcademies.map((a: { code: string; name: string }) => (
                    <SelectItem key={a.code} value={a.code}>
                      {a.name}
                    </SelectItem>
                  ))}
                  {(user.role === "admin" || user.role === "super_admin") && (
                    <SelectItem value={ALL_ACADEMIES_SYSTEM}>
                      全部學院 (ZIP)
                    </SelectItem>
                  )}
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="sm"
                disabled={!summaryDept || !scholarshipType.id || !selectedAcademicYear}
                onClick={handleDownloadSummary}
              >
                <Download className="h-4 w-4 mr-1" />
                匯出申請總表
              </Button>
              {/* 分發名單 (受獎名冊) 的 Excel/PDF 匯出在「查看分發名單」對話框內
                  ——與畫面上的名單同一份資料來源，見 DistributionSummaryDialog。 */}
              <Button
                variant="outline"
                size="sm"
                disabled={
                  subTypeCols.length === 0 ||
                  autoAllocatingCollege !== null ||
                  isLoading ||
                  isSaving ||
                  isFinalizing ||
                  isRestoring
                }
                title={
                  subTypeCols.length === 0
                    ? "名額資料尚未載入，無法執行預設分發"
                    : "依排名與志願序自動預設分配所有學院尚未核配的學生（依目前畫面狀態計算，僅填空白，儲存前可修改）"
                }
                onClick={() => handleAutoAllocate(null, "全部學院")}
              >
                {autoAllocatingCollege === ALL_COLLEGES ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-1" />
                ) : (
                  <Wand2 className="h-4 w-4 mr-1" />
                )}
                全部預設分發
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
                        // Every row explicitly 未決 — NOT an empty map. An empty
                        // map says nothing about these rows, so 儲存 would send
                        // no allocations and clear nothing, and 預設分發 would
                        // send an empty overlay and fall straight back to the
                        // saved distribution the admin just cleared.
                        setLocalAllocations(
                          new Map(students.map(s => [s.ranking_item_id, null]))
                        );
                        setUnallocatedReasons(new Map());
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
                      已存在的造冊會被略過——如需以最新的分發／學生資料重建，請改按「重新生成造冊」。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction onClick={() => handleGenerateRosters()}>
                      確認產生
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={isGeneratingRosters || isLoading}
                    title="重建已存在的造冊名單（不需人員有異動）"
                  >
                    {isGeneratingRosters ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <RefreshCw className="h-4 w-4 mr-1" />
                    )}
                    重新生成造冊
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>確認重新生成造冊？</AlertDialogTitle>
                    <AlertDialogDescription>
                      系統會依<strong>當下</strong>
                      的分發名單與學生資料，重建每個（子類型 ×
                      配額年度）組合的造冊名單——即使人員沒有異動也可以執行，並重新匯出
                      Excel。您先前的人為排除／移除會保留；已鎖定的造冊不會被重建，需先解鎖。
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>取消</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => handleGenerateRosters(true)}
                    >
                      確認重新生成
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
                    {resolveCollegeName(collegeNames, code)}
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

        {/* Per-college quota overflow — 儲存/確認分發 stay blocked until it clears */}
        {collegeOverflowMessage && (
          <div className="px-4 py-2 rounded text-sm bg-red-50 text-red-700 border border-red-200 flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{collegeOverflowMessage}</span>
          </div>
        )}

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
                    {r.sub_type}
                    {r.allocation_year != null ? ` ${r.allocation_year} 年度` : ""}
                  </span>
                  {r.project_number && (
                    <span className="text-blue-500">
                      計畫：{r.project_number}
                    </span>
                  )}
                  <span className="text-blue-600">
                    納入造冊 {r.qualified_count} 人，${r.total_amount}
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

        {/* ===========================================================
            Renewal-aware section (Phase 8.2)
            Three additive blocks:
              1) 續領已佔用（不可改動）
              2) 剩餘可分配配額
              3) 釋出與遞補預覽（即時計算）
            All blocks degrade gracefully when state endpoint is empty.
            =========================================================== */}
        <RenewalOccupiedBlock
          state={distributionState}
          isLoading={isLoadingState}
        />
        <AvailableQuotasBlock
          state={distributionState}
          isLoading={isLoadingState}
        />
        <CollegeQuotaMatrix
          cols={subTypeCols}
          quotaStatus={quotaStatus}
          students={students}
          localAllocations={localAllocations}
          academies={academies}
        />
        <ReleasePreviewSection
          releaseChain={releasePreview}
          isLoading={isLoadingPreview}
          hasStaged={hasStagedChallenge}
        />

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
                style={{ minWidth: `${1140 + subTypeCols.length * 85}px` }}
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
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold w-24 text-[11px]"
                    >
                      教授推薦
                    </th>
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 font-semibold w-24 text-[11px]"
                    >
                      學院推薦
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
                      className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-16 whitespace-nowrap"
                    >
                      在學學期數
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
                    <th
                      rowSpan={2}
                      className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-12"
                    >
                      動作
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
                            className={`font-semibold ${col.academic_year < (selectedAcademicYear ?? 9999) ? "text-orange-600" : "text-slate-700"}`}
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
                        colSpan={14 + subTypeCols.length}
                        className="px-4 py-10 border border-slate-200 text-center text-slate-500"
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
                              colSpan={14 + subTypeCols.length}
                              className="px-4 py-1.5 text-xs font-bold text-slate-600 border border-slate-300"
                            >
                              {/* Left-aligned next to the college name: the row
                                  spans 14+N columns, so a right-aligned button
                                  would sit off-screen until the admin scrolls
                                  the table horizontally. */}
                              <div className="flex items-center gap-3">
                                <span>{collegeName}</span>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  className="h-6 px-2 text-[11px] font-medium"
                                  disabled={
                                    !collegeCode ||
                                    subTypeCols.length === 0 ||
                                    autoAllocatingCollege !== null ||
                                    isLoading ||
                                    isSaving ||
                                    isFinalizing ||
                                    isRestoring
                                  }
                                  title={
                                    !collegeCode
                                      ? "無學院代碼，無法執行預設分發"
                                      : subTypeCols.length === 0
                                        ? "名額資料尚未載入，無法執行預設分發"
                                        : `依排名與志願序自動預設分配 ${collegeName} 尚未核配的學生（依目前畫面狀態計算，僅填空白，儲存前可修改）`
                                  }
                                  onClick={() =>
                                    handleAutoAllocate(collegeCode, collegeName)
                                  }
                                >
                                  {autoAllocatingCollege === collegeCode ? (
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                  ) : (
                                    <Wand2 className="h-3 w-3" />
                                  )}
                                  <span className="ml-1">預設分發</span>
                                </Button>
                              </div>
                            </td>
                          </tr>
                          {collegeStudents.map(student => {
                            const rejectedSubTypes =
                              student.rejected_sub_types || [];
                            const curAlloc = localAllocations.get(
                              student.ranking_item_id
                            );
                            // Only meaningful while the row is still 未決: once
                            // it carries an allocation, whatever stopped an
                            // earlier run no longer describes it.
                            const unallocatedReason = curAlloc
                              ? undefined
                              : unallocatedReasons.get(student.ranking_item_id);
                            // Phase 8.2: surface challenge metadata from the
                            // /state payload (keyed by application_id).
                            const challengeMeta = challengeAppMap.get(
                              student.application_id
                            );
                            const isChallenge = !!challengeMeta;
                            // Application-level allocation status drives the
                            // row status control + disables 核配 checkboxes.
                            // One definition of 撤銷/停發 for the whole screen:
                            // the row-disabling logic and the auto-allocate
                            // guards must never disagree about who is cancelled.
                            const isCancelled = isCancelledAllocation(student);
                            const cancelStatus: AllocationStatus = !isCancelled
                              ? "normal"
                              : (student.quota_allocation_status as
                                  | "revoked"
                                  | "suspended");
                            // Was this student actually FUNDED (post-確認分發)?
                            // Derived server-side (see _holds_award) so it can
                            // mirror restore_allocation exactly — the dialog and
                            // toast must never promise a roster removal or a
                            // 「重新佔用配額」 restore that won't happen.
                            const hasAllocation = student.holds_award;
                            return (
                              <tr
                                key={student.ranking_item_id}
                                className={`transition-colors ${
                                  cancelStatus === "revoked"
                                    ? "bg-red-50/60 hover:bg-red-50"
                                    : cancelStatus === "suspended"
                                      ? "bg-orange-50/50 hover:bg-orange-50"
                                      : isChallenge
                                        ? "bg-amber-50/60 hover:bg-amber-100/60"
                                        : "hover:bg-slate-50"
                                }`}
                              >
                                <td className="px-1.5 py-1.5 border border-slate-200 text-center font-bold text-slate-700 text-[11px]">
                                  {student.college_rejected ? (
                                    <span className="text-red-600">N</span>
                                  ) : (
                                    student.rank_position
                                  )}
                                </td>
                                <td className="px-1.5 py-1.5 border border-slate-200 leading-snug text-[10px]">
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
                                <td className="px-1.5 py-1.5 border border-slate-200 leading-snug">
                                  {(student.professor_review_items || [])
                                    .length > 0 ||
                                  (student.requires_professor_recommendation &&
                                    (student.applied_sub_types || []).length >
                                      0) ? (
                                    <div className="flex flex-col gap-0.5">
                                      {/* Same convention as 學院推薦: a chip
                                          per applied sub-type, and a missing
                                          professor verdict renders as 未推薦
                                          — it no longer blocks allocation,
                                          the admin decides. */}
                                      <SubTypeVerdictChips
                                        appliedSubTypes={
                                          student.applied_sub_types || []
                                        }
                                        items={
                                          student.professor_review_items || []
                                        }
                                        quotaStatus={quotaStatus}
                                        noVerdictTitle="教授未對此子類型作出推薦審核"
                                      />
                                    </div>
                                  ) : student.requires_professor_recommendation ? (
                                    /* Professor step required but the
                                       scholarship has no sub-types and no
                                       verdict yet — chips would be empty, so
                                       write the 未推薦 out explicitly. */
                                    <span
                                      className={VERDICT_CHIP.none}
                                      title="教授未作出推薦審核"
                                    >
                                      未推薦
                                    </span>
                                  ) : (
                                    <span className="text-[11px] text-slate-400">
                                      —
                                    </span>
                                  )}
                                </td>
                                <td className="px-1.5 py-1.5 border border-slate-200 leading-snug">
                                  <div className="flex flex-col gap-0.5">
                                    {/* The ranking IS the college's primary
                                        verdict: rows only exist once the
                                        college finalized its ranking, and
                                        N (college_rejected) means 不推薦.
                                        Review-tab verdicts supplement it. */}
                                    {student.college_rejected ? (
                                      <span
                                        className={VERDICT_CHIP.reject}
                                        title="學院於確認排名將此生標記為 N（不推薦）"
                                      >
                                        排名: 不推薦
                                      </span>
                                    ) : (
                                      <span
                                        className={VERDICT_CHIP.approve}
                                        title="已列入學院確認排名"
                                      >
                                        排名: 推薦
                                      </span>
                                    )}
                                    <SubTypeVerdictChips
                                      appliedSubTypes={
                                        student.applied_sub_types || []
                                      }
                                      items={student.college_review_items || []}
                                      quotaStatus={quotaStatus}
                                      noVerdictTitle="學院未對此子類型作出推薦審核"
                                    />
                                    {/* Why the last 預設分發 left this row
                                        blank, straight from the backend.
                                        撤銷/停發 is omitted — the row's own
                                        status control already says so. */}
                                    {unallocatedReason && (
                                      <span
                                        className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200"
                                        title={`預設分發未分配：${unallocatedReasonLabel(unallocatedReason)}`}
                                      >
                                        未分配:{" "}
                                        {unallocatedReasonLabel(
                                          unallocatedReason
                                        )}
                                      </span>
                                    )}
                                  </div>
                                </td>
                                {subTypeCols.map(col => {
                                  const isApplied =
                                    student.applied_sub_types.includes(
                                      col.sub_type
                                    );
                                  // rejected_sub_types arrive lowercased from
                                  // the backend; normalize the config key so
                                  // case-differing sub-type codes still match.
                                  const isRejected = rejectedSubTypes.includes(
                                    col.sub_type.toLowerCase().trim()
                                  );
                                  const isChecked =
                                    curAlloc?.sub_type === col.sub_type &&
                                    curAlloc?.config_id === col.config_id;
                                  const localUsed =
                                    localAllocCounts[col.key] ?? 0;
                                  const atCapacity =
                                    col.total > 0 &&
                                    localUsed >= col.total &&
                                    !isChecked;
                                  // Per-college cell full (hard cap) — tooltip
                                  // only. The cell is NOT tinted: "exactly
                                  // consumed" is the healthy end state of a
                                  // finished college, and painting it red would
                                  // be indistinguishable from real overflow.
                                  // Kept clickable on purpose too: the click is
                                  // a no-op that toasts the reason, which reads
                                  // better than a silently greyed-out box.
                                  const collegeFull = isChecked
                                    ? null
                                    : collegeQuotaRefusal(
                                        student.ranking_item_id,
                                        col
                                      );
                                  // Phase 8.2: for a challenge candidate the
                                  // sub_type they already hold a renewal in is
                                  // their "safety net" — they must not be
                                  // re-allocated there via the new path.
                                  const isFallbackColumn =
                                    isChallenge &&
                                    challengeMeta?.challenged_renewal
                                      ?.sub_type === col.sub_type;
                                  // Freeze edits while a mutation is in flight:
                                  // its success path reseeds localAllocations
                                  // from the server, which would silently
                                  // revert any tick made mid-request.
                                  //
                                  // 預設分發 counts too. It sends the staged map
                                  // up and merges the reply back into it, so a
                                  // tick landing in between is both lost AND
                                  // uncounted — the server would hand out a slot
                                  // it does not know was just taken. The save
                                  // gate would reject the result rather than
                                  // over-allocate, but only after the fact.
                                  const isMutating =
                                    isSaving ||
                                    isFinalizing ||
                                    isRestoring ||
                                    autoAllocatingCollege !== null;
                                  // A rejected sub-type can't be (re)checked,
                                  // but a cell that is ALREADY checked must
                                  // stay clickable so the admin can uncheck it
                                  // — finalize hard-blocks rejected
                                  // allocations with 「請先取消該勾選」, which
                                  // would deadlock against a disabled cell.
                                  const disabled =
                                    !isApplied ||
                                    (isRejected && !isChecked) ||
                                    atCapacity ||
                                    isFallbackColumn ||
                                    isCancelled ||
                                    isMutating;
                                  return (
                                    <td
                                      key={col.key}
                                      className={`px-0.5 py-1.5 border border-slate-200 text-center ${
                                        isCancelled
                                          ? "opacity-40"
                                          : isRejected
                                            ? "opacity-40 bg-red-50"
                                            : !isApplied
                                              ? "opacity-40"
                                              : isFallbackColumn
                                                ? "opacity-40 bg-amber-100/40"
                                                : ""
                                      }`}
                                    >
                                      <input
                                        type="checkbox"
                                        className="h-5 w-5 cursor-pointer rounded accent-blue-600"
                                        checked={isChecked}
                                        disabled={disabled}
                                        title={
                                          isCancelled
                                            ? "此學生已撤銷／停發，無法核配獎學金類別"
                                            : isFallbackColumn
                                            ? `保底欄位：此考生已持有 ${col.sub_type} 的續領資格，不可改配於此`
                                            : !isApplied
                                              ? `未申請 ${col.display_name}`
                                              : isRejected
                                                ? isChecked
                                                  ? `審核不同意 ${col.display_name}，請取消勾選`
                                                  : `審核不同意（不推薦）${col.display_name}`
                                                : atCapacity
                                                  ? `${col.display_name} 名額已滿`
                                                  : collegeFull
                                                    ? collegeFull
                                                    : isChecked
                                                      ? "點擊取消分配"
                                                      : `分配至 ${col.display_name}`
                                        }
                                        onChange={() =>
                                          handleCheckbox(
                                            student.ranking_item_id,
                                            col
                                          )
                                        }
                                      />
                                    </td>
                                  );
                                })}
                                <td className="px-3 py-2.5 border border-slate-200 whitespace-nowrap">
                                  {resolveCollegeName(
                                    collegeNames,
                                    student.college_code,
                                    student.college_name
                                  )}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 whitespace-nowrap">
                                  {student.department_name}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 text-center whitespace-nowrap">
                                  {student.term_count ?? "-"}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 text-center whitespace-nowrap">
                                  {/* 已領月份數 = 匯入 + 系統. The 匯 marker means an
                                      imported 國科會 baseline contributed to the total;
                                      see docs/received-months-calculation.md. */}
                                  <span className={student.received_months_source?.includes("imported") ? "text-blue-600 font-medium" : ""}>{student.received_months ?? "-"}</span>
                                  {student.received_months_source?.includes("imported") && <span className="ml-0.5 text-[9px] text-blue-400" title="含匯入的國科會已領月份數">匯</span>}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 font-medium whitespace-nowrap">
                                  {student.student_name}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 text-slate-500 whitespace-nowrap">
                                  {student.nationality}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 text-center tabular-nums whitespace-nowrap">
                                  {student.enrollment_date}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 font-mono text-xs whitespace-nowrap">
                                  {student.student_id}
                                </td>
                                <td className="px-3 py-2.5 border border-slate-200 text-xs font-semibold whitespace-nowrap">
                                  {student.is_renewal ? (
                                    <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-300">
                                      {student.renewal_year || ""} 續領
                                      {student.renewal_sub_type || ""}
                                    </span>
                                  ) : isChallenge ? (
                                    // Phase 8.2: challenge applicant — show
                                    // 挑戰 chip + 🛡 fallback annotation
                                    <div className="flex flex-col gap-0.5">
                                      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300 w-fit">
                                        <AlertTriangle className="h-3 w-3" />
                                        挑戰
                                      </span>
                                      {challengeMeta?.challenged_renewal && (
                                        <span className="inline-flex items-center gap-1 text-[10px] text-amber-700">
                                          <Shield className="h-3 w-3" />
                                          保底{" "}
                                          {challengeMeta.challenged_renewal
                                            .sub_type || "-"}
                                          -
                                          {challengeMeta.challenged_renewal
                                            .renewal_year ?? "-"}
                                        </span>
                                      )}
                                    </div>
                                  ) : (
                                    <div className="flex flex-col gap-0.5">
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
                                      {distributionState && (
                                        <span className="text-[10px] text-slate-500 font-normal">
                                          純新
                                        </span>
                                      )}
                                    </div>
                                  )}
                                </td>
                                <td className="px-1.5 py-1.5 border border-slate-200 text-center">
                                  {/* Rendered for EVERY student, allocated or
                                      not — a 休學/退學/畢業 student must be
                                      markable before 確認分發 so the round
                                      skips them. */}
                                  <AllocationStatusControl
                                    status={cancelStatus}
                                    hasAllocation={hasAllocation}
                                    reason={
                                      cancelStatus === "revoked"
                                        ? student.revoke_reason
                                        : cancelStatus === "suspended"
                                          ? student.suspend_reason
                                          : null
                                    }
                                    onRevoke={() =>
                                      setAction({
                                        mode: "revoke",
                                        applicationId: student.application_id,
                                        studentName: student.student_name,
                                        hasAllocation,
                                      })
                                    }
                                    onSuspend={() =>
                                      setAction({
                                        mode: "suspend",
                                        applicationId: student.application_id,
                                        studentName: student.student_name,
                                        hasAllocation,
                                      })
                                    }
                                    onRestore={() =>
                                      setAction({
                                        mode: "restore",
                                        applicationId: student.application_id,
                                        studentName: student.student_name,
                                        hasAllocation,
                                      })
                                    }
                                  />
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
            <li>
              「動作」欄的
              <span className="font-semibold">正常／撤銷／停發</span>
              每位學生皆可操作：分發前撤銷／停發代表將該生排除於本次分發（預設分發不再建議、確認分發會略過）；分發後則會一併從未鎖定造冊移除。點「正常」即可復原。
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
                const isPriorYear = col.academic_year < (selectedAcademicYear ?? 9999);
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

      {/* Distribution Summary Dialog */}
      {showDistributionSummary && (
        <DistributionSummaryDialog
          summary={distributionSummary}
          isLoading={isLoadingSummary}
          collegeNames={collegeNames}
          getSubTypeLabel={code => getSubTypeShortName(code, code)}
          scholarshipTypeId={scholarshipTypeId}
          academicYear={selectedAcademicYear}
          semester={selectedSemester}
          onClose={() => setShowDistributionSummary(false)}
        />
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

    {/* Revoke / Suspend allocation dialog */}
    <AllocationActionDialog
      mode={action?.mode ?? "revoke"}
      target={
        action
          ? {
              applicationId: action.applicationId,
              studentName: action.studentName,
              hasAllocation: action.hasAllocation,
            }
          : null
      }
      onClose={() => setAction(null)}
      onConfirmed={async studentName => {
        // Snapshot mode BEFORE setAction(null) — the success text below
        // depends on it, and the reset would otherwise null it out.
        const mode = action?.mode;
        const hadAllocation = action?.hasAllocation ?? true;
        setAction(null);
        await fetchData();
        // Set success message AFTER fetchData so it isn't cleared by
        // fetchData's own setSaveMessage(null) (preserves the race fix
        // from commit 2dd0f611).
        setSaveMessage({
          type: "success",
          text:
            mode === "restore"
              ? hadAllocation
                ? `已恢復 ${studentName} 為正常分發`
                : `已恢復 ${studentName} 為正常，重新納入本次分發`
              : hadAllocation
                ? `已${mode === "suspend" ? "停發" : "撤銷"} ${studentName} 的獎學金分發`
                : `已${mode === "suspend" ? "停發" : "撤銷"} ${studentName}，本次分發將略過此學生`,
        });
      }}
    />
    </>
  );
}

// ===========================================================================
// Phase 8.2 — Renewal-aware sub-components
//
// Three additive blocks shown above the existing candidate list:
//   1. RenewalOccupiedBlock     — read-only, shows approved renewals per
//                                 (sub_type, renewal_year). Marked with *
//                                 when a downstream challenge exists.
//   2. AvailableQuotasBlock     — remaining quota per (sub_type,
//                                 allocation_year).
//   3. ReleasePreviewSection    — dry-run release_chain when challenges are
//                                 staged. Surfaces who would be displaced
//                                 and the suggested fill-in candidate.
// ===========================================================================

/** Render label like "nstc · 計畫年度 114"; falls back gracefully on nulls. */
function formatSubTypeYear(sub_type: string | null, year: number | null) {
  const sub = sub_type ?? "—";
  const y = year ?? "—";
  return `${sub} · 計畫年度 ${y}`;
}

function RenewalOccupiedBlock({
  state,
  isLoading,
}: {
  state: DistributionState | null;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-blue-200 shadow-sm p-4 mb-3">
        <div className="flex items-center gap-2 text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">載入續領佔用資料中…</span>
        </div>
      </div>
    );
  }
  if (!state) return null;
  const groups = state.renewal_allocations || [];
  const hasChallenge = groups.some(g =>
    g.applications.some(a => a.has_challenge)
  );

  return (
    <div className="bg-white rounded-xl border-2 border-[#003d7a]/30 shadow-sm mb-3">
      <div className="flex items-center justify-between px-4 py-2 bg-[#003d7a] text-white rounded-t-lg">
        <h3 className="font-bold text-sm flex items-center gap-2">
          <Shield className="h-4 w-4" />
          續領已佔用（不可改動）
        </h3>
        <span className="text-[10px] bg-white/20 px-2 py-0.5 rounded-full">
          唯讀
        </span>
      </div>
      <div className="p-3 space-y-1.5">
        {groups.length === 0 ? (
          <p className="text-xs text-slate-400 py-2 text-center">
            尚無已核定的續領申請
          </p>
        ) : (
          groups.map(g => {
            const total = g.applications.length;
            const names = g.applications.map(a => (
              <span key={a.application_id} className="whitespace-nowrap">
                {a.student_name || `#${a.application_id}`}
                {a.has_challenge && (
                  <span
                    className="text-amber-600 font-bold"
                    title="此續領已被挑戰申請"
                  >
                    *
                  </span>
                )}
              </span>
            ));
            return (
              <div
                key={`${g.sub_type}-${g.renewal_year}`}
                className="text-xs text-slate-700 px-3 py-2 rounded-md bg-blue-50/40 border border-blue-100"
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-semibold text-[#003d7a]">
                    {formatSubTypeYear(g.sub_type, g.renewal_year)}
                  </span>
                  <span className="text-[11px] font-mono text-slate-500">
                    {total}/{total}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-slate-600">
                  {names.length > 0 ? (
                    names.reduce<React.ReactNode[]>((acc, el, i) => {
                      if (i > 0)
                        acc.push(
                          <span key={`sep-${i}`} className="text-slate-300">
                            、
                          </span>
                        );
                      acc.push(el);
                      return acc;
                    }, [])
                  ) : (
                    <span className="text-slate-400">—</span>
                  )}
                </div>
              </div>
            );
          })
        )}
        {hasChallenge && (
          <p className="text-[11px] text-amber-700 px-1 pt-1">
            <span className="font-bold">*</span> 標記者已被挑戰申請
          </p>
        )}
      </div>
    </div>
  );
}

function AvailableQuotasBlock({
  state,
  isLoading,
}: {
  state: DistributionState | null;
  isLoading: boolean;
}) {
  if (isLoading || !state) return null;
  const quotas = state.available_quotas || [];

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm mb-3">
      <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2">
          <RefreshCw className="h-4 w-4 text-[#003d7a]" />
          剩餘可分配配額
        </h3>
        <span className="text-[10px] text-slate-400">
          扣除續領後可用於一般 / 挑戰分配
        </span>
      </div>
      <div className="p-3">
        {quotas.length === 0 ? (
          <p className="text-xs text-slate-400 py-2 text-center">
            尚無配額設定
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {quotas.map(q => {
              const isFull = q.remaining <= 0 && q.total > 0;
              return (
                <div
                  key={`${q.sub_type}-${q.config_id}`}
                  className={`px-3 py-2 rounded-md border text-xs ${
                    isFull
                      ? "bg-slate-100 border-slate-200 text-slate-500"
                      : "bg-slate-50 border-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-slate-700">
                      {formatSubTypeYear(q.sub_type, q.academic_year)}
                    </span>
                    <span
                      className={`font-mono text-sm tabular-nums font-bold ${
                        isFull ? "text-slate-400" : "text-[#003d7a]"
                      }`}
                    >
                      {q.used}/{q.total}
                    </span>
                  </div>
                  {q.remaining > 0 && (
                    <div className="mt-0.5 text-[10px] text-slate-500">
                      剩餘 {q.remaining} 個名額
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function ReleasePreviewSection({
  releaseChain,
  isLoading,
  hasStaged,
}: {
  releaseChain: ReleaseChainItem[];
  isLoading: boolean;
  hasStaged: boolean;
}) {
  // Only render if there's something challenge-related staged or in flight
  if (!hasStaged && !isLoading && releaseChain.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border-2 border-amber-200 shadow-sm mb-3">
      <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 flex items-center justify-between">
        <h3 className="font-bold text-sm text-amber-800 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          釋出與遞補預覽（即時計算）
        </h3>
        {isLoading && (
          <span className="text-[11px] text-amber-700 flex items-center gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            計算中…
          </span>
        )}
      </div>
      <div className="p-3 space-y-2">
        {releaseChain.length === 0 ? (
          <p className="text-xs text-slate-500 py-1">
            目前的勾選不會觸發任何續領被釋出。
          </p>
        ) : (
          releaseChain.map((item, idx) => (
            <div
              key={`${item.cancelled_application_id}-${idx}`}
              className="rounded-md border border-amber-200 bg-amber-50/40 px-3 py-2 text-xs text-slate-700"
            >
              <div className="flex items-center gap-1 font-semibold text-amber-800">
                <AlertTriangle className="h-3.5 w-3.5" />
                挑戰申請 #
                {item.challenge_application_id ?? "—"} 成功
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-slate-600 pl-4">
                <ArrowRight className="h-3 w-3 text-amber-600" />
                釋出{" "}
                <span className="font-mono text-[#003d7a]">
                  {item.freed_slot.sub_type ?? "—"} · 配額池 #{item.freed_slot.allocation_config_id ?? "—"}
                </span>{" "}
                slot（取消續領 #{item.cancelled_application_id}）
              </div>
              <div className="mt-1 flex items-center gap-1.5 text-slate-600 pl-4">
                <ArrowRight className="h-3 w-3 text-amber-600" />
                自動遞補：
                {item.suggested_fill_id ? (
                  <>
                    <span className="font-medium text-slate-800">
                      {item.suggested_fill_name ||
                        `#${item.suggested_fill_id}`}
                    </span>
                    <span className="text-slate-500">（純新申請）</span>
                    <ArrowRight className="h-3 w-3 text-amber-600" />
                    分配至{" "}
                    <span className="font-mono text-[#003d7a]">
                      {item.freed_slot.sub_type ?? "—"} · 配額池 #{item.freed_slot.allocation_config_id ?? "—"}
                    </span>
                  </>
                ) : (
                  <span className="text-slate-500">
                    無可用候補者（waitlist 為空）
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
