/**
 * Manual Distribution API Module
 *
 * Provides endpoints for admin to manually allocate scholarships to students.
 * Replaces the automated quota/matrix distribution with a UI-driven workflow.
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";
import { fetchBinaryExport } from "./binary-export";

/** One reviewer verdict for one sub-type, shown in the 教授推薦/學院推薦 columns. */
export interface ReviewItemSummary {
  /** Normalized (lowercase/stripped) sub-type code, matching rejected_sub_types. */
  sub_type_code: string;
  /** "approve" | "reject" */
  recommendation: string;
  comments: string | null;
}

export interface DistributionStudent {
  ranking_item_id: number;
  application_id: number;
  rank_position: number;
  applied_sub_types: string[];
  rejected_sub_types: string[];
  /** Per-sub-type professor verdicts (教授推薦 column). */
  professor_review_items: ReviewItemSummary[];
  /** Per-sub-type college review verdicts supplementing the ranking verdict (學院推薦 column); admin reviews excluded. The college's PRIMARY verdict is the finalized ranking: college_rejected below. */
  college_review_items: ReviewItemSummary[];
  /** Config requires a professor recommendation step (renewal-aware) — distinguishes 未推薦 chips (step required, no verdict yet) from "—" (no professor step). */
  requires_professor_recommendation: boolean;
  allocated_sub_type: string | null;
  /** Config whose quota this student's slot consumes. Seed the checked column from (allocated_sub_type, allocation_config_id). */
  allocation_config_id: number | null;
  /** Live funding flag. Cancel (revoke/suspend) sets this false to free the quota slot; restore sets it true. Seed the 核配 checkbox from this, NOT from allocated_sub_type (preserved across cancel). */
  is_allocated: boolean;
  status: string;
  /** Application-level allocation status: "allocated" | "revoked" | "suspended" | "rejected" | null. Drives the row status control + checkbox disabling. */
  quota_allocation_status: string | null;
  /** Holds a funded award — or, once 撤銷/停發'd, gets one back on 復原. Derived server-side so it mirrors restore_allocation (legacy fallback included); drives the status control + dialog copy. NOT the same as is_allocated, which is the ranking item's live funding flag. */
  holds_award: boolean;
  revoke_reason: string | null;
  suspend_reason: string | null;
  college_rejected: boolean;
  college_code: string;
  college_name: string;
  department_name: string;
  term_count: number | null;
  student_name: string;
  nationality: string;
  enrollment_date: string;
  student_id: string;
  application_identity: string;
  is_renewal: boolean;
  renewal_year: number | null;
  renewal_sub_type: string | null;
  received_months: number | null;
  received_months_source: string | null;
  is_supplementary: boolean;
}

export interface CollegeQuota {
  total: number;
  allocated: number;
  /** total − allocated; NOT clamped — negative means the college is over its
   * cell of quotas[sub_type], which the server rejects on allocate/finalize. */
  remaining: number;
}

/** Quota for one distributable config (own or linked source) under a sub_type. */
export interface ConfigQuota {
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  total: number;
  remaining: number;
  /** Per-college grid keyed by college code (""=unknown); null for non-matrix configs. */
  by_college: Record<string, CollegeQuota> | null;
}

export interface SubTypeQuotaStatus {
  display_name: string;
  /** Distributable configs for this sub_type (own config first, then linked sources). */
  by_config: ConfigQuota[];
}

export type QuotaStatus = Record<string, SubTypeQuotaStatus>;

/** Local allocation state for a student: which (sub_type, config) they're assigned to */
export interface LocalAlloc {
  sub_type: string;
  config_id: number;
}

/** Composite key for a (sub_type, config) column: "nstc:42" */
export function makeColKey(sub_type: string, config_id: number): string {
  return `${sub_type}:${config_id}`;
}

/**
 * The student's SERVER-SAVED allocation, or null. `is_allocated` is the live
 * funding flag (`allocated_sub_type` is preserved across cancel), so all three
 * fields must agree. Single source of truth for seeding local allocation state
 * and for the matrix's saved-side delta.
 */
export function getSavedAllocation(s: DistributionStudent): LocalAlloc | null {
  return s.is_allocated && s.allocated_sub_type && s.allocation_config_id != null
    ? { sub_type: s.allocated_sub_type, config_id: s.allocation_config_id }
    : null;
}

export const UNKNOWN_COLLEGE_LABEL = "未知";

/**
 * college_code → display name, academies (reference data) first, then each
 * student's snapshot college_name for codes the reference table doesn't know.
 * Single source of truth for the distribution panel: the 所屬學院 filter,
 * group headers, per-student cells and the quota matrix must all resolve a
 * code to the SAME name — two codes labelled from different sources is how
 * "two 藥物科學院 options" and "wrong college's quota row moved" happened.
 */
export function buildCollegeNameMap(
  academies: Array<{ code: string; name: string }>,
  students: DistributionStudent[]
): Map<string, string> {
  const names = new Map<string, string>();
  for (const academy of academies) {
    names.set(academy.code, academy.name);
  }
  for (const s of students) {
    if (s.college_code && s.college_name && !names.has(s.college_code)) {
      names.set(s.college_code, s.college_name);
    }
  }
  return names;
}

/** Resolved name, falling back to the raw code; empty code → fallback (未知). */
export function resolveCollegeName(
  names: Map<string, string>,
  code: string,
  emptyCodeFallback?: string
): string {
  if (code) return names.get(code) ?? code;
  return emptyCodeFallback || UNKNOWN_COLLEGE_LABEL;
}

/** A flattened (sub_type × source-config) column descriptor for the distribution table */
export interface SubTypeConfigCol {
  sub_type: string;
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  display_name: string; // e.g., "國科會 · phd_114"
  total: number;
  remaining: number; // live: pool_total − consumers, from /quota-status
  key: string; // composite key: "nstc:42" (sub_type:config_id)
}

export interface AllocationItem {
  ranking_item_id: number;
  sub_type_code: string | null;
  /** The config whose quota this slot consumes (own config or a linked source). Null only for the whole-period sentinel. */
  allocation_config_id: number | null;
}

export interface AllocationSuggestion {
  ranking_item_id: number;
  sub_type_code: string | null;
  allocation_config_id: number | null;
  /** Why nothing could be allocated. Null on a successful suggestion. */
  reason?: UnallocatedReason | null;
}

export interface MergeSuggestionsResult {
  /** A NEW map — callers must not mutate `current`. */
  next: Map<number, LocalAlloc | null>;
  /** How many 未決 rows the suggestions filled. */
  filled: number;
}

/**
 * Merge auto-allocation suggestions into the staged allocation map.
 *
 * Single implementation for the on-load preview and the 預設分發 buttons, so
 * both apply the same rules: only rows in `eligibleItemIds` (in the grid, right
 * college, not 撤銷/停發), and only 未決 rows — a row already carrying an
 * allocation is decided, and is never overwritten.
 *
 * No quota cap here. The suggestions were computed against the same staged map
 * this merges into (see getAutoAllocatePreview's `staged`), so the server has
 * already spent exactly the headroom the screen has left; a second cap applied
 * here could only wrongly drop a row the server deliberately allocated.
 */
export function mergeSuggestions(
  current: Map<number, LocalAlloc | null>,
  suggestions: AllocationSuggestion[],
  eligibleItemIds: Set<number>
): MergeSuggestionsResult {
  const next = new Map(current);
  let filled = 0;
  for (const s of suggestions) {
    if (!s.sub_type_code || s.allocation_config_id == null) continue;
    if (!eligibleItemIds.has(s.ranking_item_id)) continue;
    if (next.get(s.ranking_item_id)) continue;
    next.set(s.ranking_item_id, {
      sub_type: s.sub_type_code,
      config_id: s.allocation_config_id,
    });
    filled++;
  }
  return { next, filled };
}

/** The staged map on the wire — every row the grid renders, 未決 rows included. */
export function toStagedItems(
  allocations: Map<number, LocalAlloc | null>
): AllocationItem[] {
  return Array.from(allocations.entries()).map(([ranking_item_id, alloc]) => ({
    ranking_item_id,
    sub_type_code: alloc?.sub_type ?? null,
    allocation_config_id: alloc?.config_id ?? null,
  }));
}

export interface AllocateRequest {
  scholarship_type_id: number;
  academic_year: number;
  semester: string;
  allocations: AllocationItem[];
}

export interface FinalizeRequest {
  scholarship_type_id: number;
  academic_year: number;
  semester: string;
}

export interface AllocateResult {
  updated_count: number;
}

export interface FinalizeResult {
  approved_count: number;
  rejected_count: number;
  total: number;
}

export interface DistributionHistoryRecord {
  id: number;
  operation_type: string;
  change_summary: string | null;
  total_allocated: number | null;
  created_at: string | null;
  created_by: number | null;
}

export interface RestoreRequest {
  history_id: number;
}

export interface RestoreResult {
  restored_count: number;
  /** Snapshot rows NOT restored because the sub-type was rejected (不同意) in review. */
  skipped_rejected: number;
  /** Snapshot rows NOT restored because the application is now 撤銷/停發. */
  skipped_cancelled: number;
}

/** True when the student was pulled out of the distribution (撤銷/停發) and must not be (re)allocated. */
export function isCancelledAllocation(s: DistributionStudent): boolean {
  return (
    s.quota_allocation_status === "revoked" ||
    s.quota_allocation_status === "suspended"
  );
}

/**
 * Why 預設分發 could not place a student. Decided by the backend, which is the
 * only place that knows — a reject from a reviewer role the grid does not
 * render is invisible here, and "the quota ran out" cannot be told apart from
 * "they were never a candidate" by looking at the row.
 *
 * Mirrors the UNALLOCATED_* constants in manual_distribution_service.py.
 */
export type UnallocatedReason =
  | "cancelled"
  | "college_rejected"
  | "not_applied"
  | "review_rejected"
  | "quota_full"
  | "no_college_quota";

export const UNALLOCATED_REASON_LABEL: Record<UnallocatedReason, string> = {
  cancelled: "已撤銷／停發",
  college_rejected: "學院不予推薦",
  not_applied: "未申請可分配的子類型",
  review_rejected: "審核不同意",
  quota_full: "名額不足",
  no_college_quota: "該學院無此類別名額",
};

/**
 * Label for a reason code, surviving one the backend added and this build has
 * not learnt yet. The union is a hand-kept mirror of the UNALLOCATED_*
 * constants and the response is untyped, so an unknown code reaches here with
 * no type error — showing the raw code beats 「未分配: undefined」.
 */
export function unallocatedReasonLabel(reason: UnallocatedReason): string {
  return UNALLOCATED_REASON_LABEL[reason] ?? reason;
}

/**
 * ranking_item_id → why it was left 未決, for the rows the run could not place.
 *
 * 撤銷/停發 rows are dropped: they were never candidates, and the grid already
 * states their status on the row itself. Counting them would report a dozen
 * "failures" for a college where nothing actually went wrong.
 */
export function reasonsBySuggestion(
  suggestions: AllocationSuggestion[]
): Map<number, UnallocatedReason> {
  const reasons = new Map<number, UnallocatedReason>();
  for (const s of suggestions) {
    if (s.sub_type_code || !s.reason || s.reason === "cancelled") continue;
    reasons.set(s.ranking_item_id, s.reason);
  }
  return reasons;
}

/** Reason → count, most common first; zero counts omitted. */
export function summarizeReasons(
  reasons: Map<number, UnallocatedReason>
): Array<{ reason: UnallocatedReason; count: number }> {
  const tally = new Map<UnallocatedReason, number>();
  for (const reason of reasons.values()) {
    tally.set(reason, (tally.get(reason) ?? 0) + 1);
  }
  return [...tally.entries()]
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count);
}

export interface RosterSummary {
  id: number;
  roster_code: string;
  sub_type: string;
  /** Consumed config id (pool key for this roster). */
  allocation_config_id: number | null;
  /** Frozen display snapshot = consumed config's academic_year. */
  allocation_year: number | null;
  project_number: string | null;
  period_label: string;
  status: string;
  qualified_count: number;
  disqualified_count: number;
  total_amount: string;
}

export interface GenerateRostersRequest {
  scholarship_type_id: number;
  academic_year: number;
  semester: string;
  student_verification_enabled?: boolean;
  force_regenerate?: boolean;
}

export interface GenerateRostersResult {
  rosters_created: number;
  rosters: RosterSummary[];
  /** 已存在、未重新產生（force_regenerate=false 時）的造冊 */
  rosters_skipped?: number;
  skipped_rosters?: RosterSummary[];
  /** 已鎖定、force_regenerate 也無法重建的造冊 */
  rosters_locked?: number;
  locked_rosters?: RosterSummary[];
}

export interface DistributionSummaryStudent {
  ranking_item_id: number;
  application_id: number;
  student_name: string;
  student_id: string;
  college_code: string;
  college_name: string;
  department_name: string;
  rank_position: number;
  college_rejected?: boolean;
  is_supplementary?: boolean;
}

export interface DistributionSummaryGroup {
  sub_type: string;
  allocation_config_id: number | null;
  /** Consumed config's academic_year, for the "XXX 年度" group label. */
  allocation_year: number | null;
  count: number;
  students: DistributionSummaryStudent[];
}

export interface DistributionSummaryResult {
  groups: DistributionSummaryGroup[];
  total_allocated: number;
}

export interface AvailableCombinations {
  scholarship_types: Array<{
    id: number;
    code: string;
    name: string;
    name_en?: string;
  }>;
  academic_years: number[];
  semesters: string[];
}

// ---------------------------------------------------------------------------
// Renewal + challenge: distribution state and release-chain preview
//
// Backed by:
//   GET  /api/v1/manual-distribution/state
//   POST /api/v1/manual-distribution/preview-distribution
// ---------------------------------------------------------------------------

/** Approved renewal that is currently occupying a (sub_type × renewal_year) slot. */
export interface DistributionStateRenewalApp {
  application_id: number;
  student_name: string | null;
  /** True when a challenge application points at this renewal (Application_C). */
  has_challenge: boolean;
}

/** Group of approved renewals sharing the same (sub_type, renewal_year). */
export interface DistributionStateRenewalGroup {
  sub_type: string | null;
  renewal_year: number;
  applications: DistributionStateRenewalApp[];
}

/** Available pool per (sub_type, config): total / used / remaining. */
export interface DistributionStateAvailableQuota {
  sub_type: string;
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  total: number;
  used: number;
  remaining: number;
}

/** Minimal info about the renewal a challenge candidate is targeting. */
export interface DistributionStateChallengedRenewal {
  renewal_application_id: number;
  sub_type: string | null;
  renewal_year: number | null;
}

/** Ranked non-renewal candidate (pure-new or challenge). */
export interface DistributionStateCandidate {
  rank: number;
  application_id: number;
  student_name: string | null;
  is_challenge: boolean;
  challenged_renewal: DistributionStateChallengedRenewal | null;
  applying_sub_type: string | null;
}

/** Combined panel-state payload returned by GET /state. */
export interface DistributionState {
  renewal_allocations: DistributionStateRenewalGroup[];
  available_quotas: DistributionStateAvailableQuota[];
  candidates: DistributionStateCandidate[];
}

/** Single entry in the release_chain returned by /preview-distribution. */
export interface ReleaseChainItem {
  /** The challenge application that would win and trigger the release. */
  challenge_application_id?: number;
  /** The renewal application that would be cancelled. */
  cancelled_application_id: number;
  /** The slot that would be freed. */
  freed_slot: {
    sub_type: string | null;
    allocation_config_id: number | null;
  };
  /** Suggested waitlist candidate (pure-new) to fill the freed slot. */
  suggested_fill_id: number | null;
  suggested_fill_name: string | null;
}

export interface PreviewDistributionResult {
  release_chain: ReleaseChainItem[];
}

export function createManualDistributionApi() {
  return {
    /**
     * Get all active scholarship types and configurations for admin distribution.
     */
    getAvailableCombinations: async (): Promise<
      ApiResponse<AvailableCombinations>
    > => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/available-combinations",
        {}
      );
      return toApiResponse(response) as ApiResponse<AvailableCombinations>;
    },

    /**
     * Get ranked students with allocation status for manual distribution.
     */
    getStudents: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string,
      college_code?: string
    ): Promise<ApiResponse<DistributionStudent[]>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/students",
        {
          params: {
            query: {
              scholarship_type_id,
              academic_year,
              semester,
              ...(college_code ? { college_code } : {}),
            },
          },
        }
      );
      return toApiResponse(response) as ApiResponse<DistributionStudent[]>;
    },

    /**
     * Get the full distribution-panel state for a scholarship_type + academic_year:
     *   - renewal_allocations (approved renewals grouped by sub_type × renewal_year)
     *   - available_quotas (per (sub_type, allocation_year))
     *   - candidates (ranked non-renewal applicants, including challenges)
     *
     * Used by the admin Manual Distribution panel to render the renewal-aware UI.
     * Read-only: never mutates state.
     */
    getState: async (
      scholarship_type_id: number,
      academic_year: number
    ): Promise<ApiResponse<DistributionState>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/state" as any,
        {
          params: {
            query: { scholarship_type_id, academic_year } as any,
          },
        }
      );
      return toApiResponse(response) as ApiResponse<DistributionState>;
    },

    /**
     * Dry-run: compute the release_chain for the proposed allocations.
     *
     * For each proposed allocation whose application is a challenge, returns
     * the renewal that would be cancelled and the next pure-new waitlist
     * candidate who would inherit the freed slot. Nothing is persisted.
     */
    previewDistribution: async (
      request: AllocateRequest
    ): Promise<ApiResponse<PreviewDistributionResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/preview-distribution" as any,
        { body: request as any }
      );
      return toApiResponse(response) as ApiResponse<PreviewDistributionResult>;
    },

    /**
     * Get real-time quota status per sub-type per college.
     */
    getQuotaStatus: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string
    ): Promise<ApiResponse<QuotaStatus>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/quota-status",
        {
          params: {
            query: { scholarship_type_id, academic_year, semester },
          },
        }
      );
      return toApiResponse(response) as ApiResponse<QuotaStatus>;
    },

    /**
     * Save manual allocation selections.
     */
    allocate: async (
      request: AllocateRequest
    ): Promise<ApiResponse<AllocateResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/allocate",
        { body: request }
      );
      return toApiResponse(response) as ApiResponse<AllocateResult>;
    },

    /**
     * Finalize distribution - lock and update application statuses.
     */
    finalize: async (
      request: FinalizeRequest
    ): Promise<ApiResponse<FinalizeResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/finalize",
        { body: request }
      );
      return toApiResponse(response) as ApiResponse<FinalizeResult>;
    },

    /**
     * Get allocation history for a scholarship/year/semester combination.
     */
    getHistory: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string
    ): Promise<ApiResponse<DistributionHistoryRecord[]>> => {
      const response = await typedClient.raw.GET(
        `/api/v1/manual-distribution/{scholarship_type_id}/history`,
        {
          params: {
            path: { scholarship_type_id },
            query: { academic_year, semester },
          },
        }
      );
      return toApiResponse(response) as ApiResponse<
        DistributionHistoryRecord[]
      >;
    },

    /**
     * Restore allocations from a specific history record.
     */
    restoreFromHistory: async (
      scholarship_type_id: number,
      request: RestoreRequest
    ): Promise<ApiResponse<RestoreResult>> => {
      const response = await typedClient.raw.POST(
        `/api/v1/manual-distribution/{scholarship_type_id}/restore`,
        {
          params: { path: { scholarship_type_id } },
          body: request,
        }
      );
      return toApiResponse(response) as ApiResponse<RestoreResult>;
    },

    /**
     * Get distribution summary: all allocated students grouped by sub_type × allocation_year.
     */
    getDistributionSummary: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string
    ): Promise<ApiResponse<DistributionSummaryResult>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/manual-distribution/distribution-summary",
        {
          params: {
            query: { scholarship_type_id, academic_year, semester },
          },
        }
      );
      return toApiResponse(response) as ApiResponse<DistributionSummaryResult>;
    },

    /**
     * Get auto-allocation preview suggestions. Writes nothing.
     *
     * Pass `college_code` to run the distribution for a single college — the
     * backend still evaluates quotas globally, so the suggestions match what a
     * whole-scholarship run would produce for that college.
     *
     * Pass `staged` — the grid's CURRENT allocations for every row it renders,
     * every college — to have the plan computed against the screen instead of
     * the saved distribution. Omit it only on a screen that has staged nothing.
     */
    getAutoAllocatePreview: async (
      scholarship_type_id: number,
      academic_year: number,
      semester: string,
      college_code?: string,
      staged?: AllocationItem[]
    ): Promise<ApiResponse<{ suggestions: AllocationSuggestion[] }>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/auto-allocate-preview",
        {
          body: {
            scholarship_type_id,
            academic_year,
            semester,
            ...(college_code ? { college_code } : {}),
            // `staged !== undefined`, not a truthiness test: an EMPTY overlay is
            // a real answer ("this screen renders no rows") and JS and Python
            // disagree about `[]`, so a truthiness test here would ship one
            // meaning and have the server read another.
            ...(staged !== undefined ? { staged } : {}),
          } as never,
        }
      );
      return toApiResponse(response) as ApiResponse<{
        suggestions: AllocationSuggestion[];
      }>;
    },

    /**
     * Generate payment rosters from a finalized+distributed ranking.
     * Creates one roster per (allocation_year, sub_type) combination.
     */
    generateRostersFromDistribution: async (
      request: GenerateRostersRequest
    ): Promise<ApiResponse<GenerateRostersResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/generate-rosters-from-distribution",
        { body: request as never }
      );
      return toApiResponse(response) as ApiResponse<GenerateRostersResult>;
    },

    /**
     * Revoke an allocated student's scholarship distribution.
     * Removes from unlocked rosters and marks application as cancelled/revoked.
     */
    revokeAllocation: async (
      application_id: number,
      reason: string
    ): Promise<ApiResponse<unknown>> => {
      const token = typedClient.getToken();
      const response = await fetch(
        `/api/v1/manual-distribution/applications/${application_id}/revoke`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ reason }),
        }
      );
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        // ignore parse error
      }
      if (!response.ok) {
        const b = body as { detail?: string; message?: string } | null;
        return {
          success: false,
          message: b?.detail || b?.message || "撤銷失敗",
          data: undefined,
        };
      }
      return body as ApiResponse<unknown>;
    },

    /**
     * Suspend an allocated student's scholarship distribution.
     * Removes from unlocked rosters and marks application as cancelled/suspended.
     */
    suspendAllocation: async (
      application_id: number,
      reason: string
    ): Promise<ApiResponse<unknown>> => {
      const token = typedClient.getToken();
      const response = await fetch(
        `/api/v1/manual-distribution/applications/${application_id}/suspend`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ reason }),
        }
      );
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        // ignore parse error
      }
      if (!response.ok) {
        const b = body as { detail?: string; message?: string } | null;
        return {
          success: false,
          message: b?.detail || b?.message || "停發失敗",
          data: undefined,
        };
      }
      return body as ApiResponse<unknown>;
    },

    /**
     * Restore a revoked/suspended student back to the allocated state.
     * Does not touch rosters — regenerate rosters to re-include the student.
     */
    restoreAllocation: async (
      application_id: number
    ): Promise<ApiResponse<unknown>> => {
      const token = typedClient.getToken();
      const response = await fetch(
        `/api/v1/manual-distribution/applications/${application_id}/restore`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        }
      );
      let body: unknown = null;
      try {
        body = await response.json();
      } catch {
        // ignore parse error
      }
      if (!response.ok) {
        const b = body as { detail?: string; message?: string } | null;
        return {
          success: false,
          message: b?.detail || b?.message || "恢復失敗",
          data: undefined,
        };
      }
      return body as ApiResponse<unknown>;
    },
  };
}

/**
 * Download the 分發結果名單 (受獎名冊) as Excel (default) or PDF.
 *
 * Endpoint: GET /api/v1/manual-distribution/distribution-summary/export
 *   `format` is an OPTIONAL query param: "pdf" appends `?format=pdf`; the
 *   default "xlsx" is omitted entirely, so the xlsx request URL is unchanged.
 *
 * Binary exports bypass typedClient.raw (openapi-fetch cannot stream blobs) —
 * see lib/api/modules/binary-export.ts.
 */
export async function exportDistributionSummary(params: {
  scholarshipTypeId: number;
  academicYear: number;
  semester: string;
  format?: "xlsx" | "pdf";
}): Promise<{ blob: Blob; filename: string }> {
  const format = params.format ?? "xlsx";
  const search = new URLSearchParams();
  search.set("scholarship_type_id", String(params.scholarshipTypeId));
  search.set("academic_year", String(params.academicYear));
  search.set("semester", params.semester);
  if (format !== "xlsx") search.set("format", format);
  return fetchBinaryExport(
    "/api/v1/manual-distribution/distribution-summary/export",
    search,
    `分發名單_${params.academicYear}.${format}`,
    "無法匯出分發名單"
  );
}
