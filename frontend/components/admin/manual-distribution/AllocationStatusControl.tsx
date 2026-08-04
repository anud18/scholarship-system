"use client";

/**
 * Compact segmented "sliding bar" that BOTH shows a student's current
 * allocation status (正常 / 撤銷 / 停發) and drives the revoke/suspend actions.
 * The active segment is colour-coded and an animated indicator slides to it, so
 * an admin can tell at a glance who has already been revoked or suspended while
 * scanning a dense table.
 *
 * Rendered for EVERY student in the distribution roster, not only the
 * already-allocated ones: a student who 休學/退學/畢業 between 學院排序 and
 * 確認分發 has to be markable up front so 預設分發 stops suggesting them and
 * 確認分發 skips them. `hasAllocation` only tunes the wording — a
 * not-yet-allocated 撤銷/停發 excludes the student from the round rather than
 * pulling them out of a roster.
 *
 * Reversible: from 正常 you can revoke/suspend; from a terminal state the 正常
 * segment restores back to whatever the student was before. To switch directly
 * between 撤銷 and 停發, restore to 正常 first (the other action segment is
 * inert while terminal).
 */

export type AllocationStatus = "normal" | "revoked" | "suspended";

interface AllocationStatusControlProps {
  status: AllocationStatus;
  /** Revoke or suspend reason, surfaced as a tooltip once terminal. */
  reason?: string | null;
  /**
   * Whether the student holds (or held) a quota slot. Drives tooltip wording
   * only — both states are fully actionable.
   */
  hasAllocation?: boolean;
  onRevoke: () => void;
  onSuspend: () => void;
  /** Restore a revoked/suspended student back to 正常. */
  onRestore: () => void;
}

const SEGMENTS: { key: AllocationStatus; label: string }[] = [
  { key: "normal", label: "正常" },
  { key: "revoked", label: "撤銷" },
  { key: "suspended", label: "停發" },
];

const ACTIVE_INDEX: Record<AllocationStatus, number> = {
  normal: 0,
  revoked: 1,
  suspended: 2,
};

// Sliding indicator fill per active status.
const INDICATOR_BG: Record<AllocationStatus, string> = {
  normal: "bg-white shadow-sm ring-1 ring-slate-200",
  revoked: "bg-red-500 shadow-sm",
  suspended: "bg-orange-500 shadow-sm",
};

/**
 * Per-segment tooltip copy. The 已核配 variants are load-bearing for the
 * revoke/suspend e2e spec, which locates the buttons by
 * `title*="撤銷此學生獎學金"` / `title*="停發此學生獎學金"` — the 未核配
 * variants deliberately read 「撤銷此學生的…」 so those selectors keep
 * resolving to an allocated row.
 */
const ACTION_TITLES: Record<
  "revoked" | "suspended",
  { allocated: string; unallocated: string }
> = {
  revoked: {
    allocated: "撤銷此學生獎學金（違反獎學金要點）",
    unallocated: "撤銷此學生的獎學金資格（違反獎學金要點），本次分發將略過",
  },
  suspended: {
    allocated: "停發此學生獎學金（休學/退學/畢業）",
    unallocated: "停發此學生的獎學金（休學/退學/畢業），本次分發將略過",
  },
};

export function AllocationStatusControl({
  status,
  reason,
  hasAllocation = true,
  onRevoke,
  onSuspend,
  onRestore,
}: AllocationStatusControlProps) {
  const isTerminal = status !== "normal";
  const activeIndex = ACTIVE_INDEX[status];

  const segmentClass = (seg: AllocationStatus): string => {
    const isActive = seg === status;
    if (isActive) {
      // Active label sits on top of the coloured indicator.
      return status === "normal"
        ? "text-slate-800 font-semibold"
        : "text-white font-semibold";
    }
    if (isTerminal) {
      // Terminal: only 正常 is live (restore); the other action is inert
      // (switch type by restoring to 正常 first).
      return seg === "normal"
        ? "text-slate-500 hover:text-slate-800"
        : "text-slate-300";
    }
    // Normal state → the two inactive segments are the live actions.
    return seg === "revoked"
      ? "text-red-500 hover:text-red-700"
      : "text-orange-500 hover:text-orange-700";
  };

  // Normal → 撤銷/停發 actionable. Terminal → only 正常 (restore) actionable.
  const isActionable = (seg: AllocationStatus): boolean =>
    isTerminal ? seg === "normal" : seg !== "normal";

  const handleSegment = (seg: AllocationStatus) => {
    if (!isActionable(seg)) return;
    if (seg === "normal") onRestore();
    else if (seg === "revoked") onRevoke();
    else onSuspend();
  };

  return (
    <div
      role="group"
      aria-label="分發狀態"
      title={
        isTerminal && reason
          ? `原因：${reason}`
          : !isTerminal && !hasAllocation
            ? "尚未核配獎學金，仍可預先撤銷／停發以排除於本次分發"
            : undefined
      }
      className="relative inline-grid grid-cols-3 w-[120px] rounded-full bg-slate-100 p-0.5 select-none"
    >
      {/* Sliding indicator */}
      <span
        aria-hidden
        className={`pointer-events-none absolute inset-y-0.5 left-0.5 w-[calc((100%-0.25rem)/3)] rounded-full transition-transform duration-200 ease-out ${INDICATOR_BG[status]}`}
        style={{ transform: `translateX(${activeIndex * 100}%)` }}
      />
      {SEGMENTS.map(seg => {
        const isActive = seg.key === status;
        const actionable = isActionable(seg.key);
        return (
          <button
            key={seg.key}
            type="button"
            onClick={() => handleSegment(seg.key)}
            disabled={!actionable}
            aria-pressed={isActive}
            title={
              actionable
                ? seg.key === "normal"
                  ? hasAllocation
                    ? "恢復為正常分發"
                    : "恢復為正常，重新納入本次分發"
                  : ACTION_TITLES[seg.key][
                      hasAllocation ? "allocated" : "unallocated"
                    ]
                : undefined
            }
            className={`relative z-10 py-1 text-[11px] leading-none rounded-full transition-colors ${
              actionable ? "cursor-pointer" : "cursor-default"
            } ${segmentClass(seg.key)}`}
          >
            {seg.label}
          </button>
        );
      })}
    </div>
  );
}
