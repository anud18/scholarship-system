"use client";

/**
 * Compact segmented "sliding bar" that BOTH shows a distributed student's
 * current allocation status (正常 / 撤銷 / 停發) and drives the revoke/suspend
 * actions. The active segment is colour-coded and an animated indicator slides
 * to it, so an admin can tell at a glance who has already been revoked or
 * suspended while scanning a dense table.
 *
 * Transitions are one-way and terminal (no un-revoke / un-suspend in this
 * iteration — the backend 409s on a second action), so once a student is
 * 撤銷 / 停發 the control becomes a read-only status indicator.
 */

export type AllocationStatus = "normal" | "revoked" | "suspended";

interface AllocationStatusControlProps {
  status: AllocationStatus;
  /** Revoke or suspend reason, surfaced as a tooltip once terminal. */
  reason?: string | null;
  onRevoke: () => void;
  onSuspend: () => void;
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

export function AllocationStatusControl({
  status,
  reason,
  onRevoke,
  onSuspend,
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
      // Terminal: inactive segments are inert, just dimmed context.
      return "text-slate-300";
    }
    // Normal state → the two inactive segments are the live actions.
    return seg === "revoked"
      ? "text-red-500 hover:text-red-700"
      : "text-orange-500 hover:text-orange-700";
  };

  const handleSegment = (seg: AllocationStatus) => {
    if (isTerminal || seg === "normal") return; // read-only / no-op
    if (seg === "revoked") onRevoke();
    else onSuspend();
  };

  return (
    <div
      role="group"
      aria-label="分發狀態"
      title={isTerminal && reason ? `原因：${reason}` : undefined}
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
        const actionable = !isTerminal && seg.key !== "normal";
        return (
          <button
            key={seg.key}
            type="button"
            onClick={() => handleSegment(seg.key)}
            disabled={!actionable}
            aria-pressed={isActive}
            title={
              actionable
                ? seg.key === "revoked"
                  ? "撤銷此學生獎學金（違反獎學金要點）"
                  : "停發此學生獎學金（休學/退學/畢業）"
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
