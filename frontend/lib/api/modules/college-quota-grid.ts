/**
 * Live college × (sub_type × config) quota grid for manual distribution.
 *
 * Pure — no React, no API. Shared by the 各學院剩餘名額 matrix (which renders it)
 * and the distribution panel (which blocks 儲存/確認分發 on overflow), so the
 * numbers an admin sees and the numbers the save gate applies can never drift.
 *
 * The server enforces the same rule authoritatively in
 * `_assert_round_not_oversubscribed` (per-college cell of `quotas[sub_type]` is a
 * hard cap, not a hint); this module only stops the round-trip early and points
 * at the offending cells.
 */

import type {
  CollegeQuota,
  DistributionStudent,
  LocalAlloc,
  QuotaStatus,
  SubTypeConfigCol,
} from "./manual-distribution";
import { getSavedAllocation, makeColKey } from "./manual-distribution";

export interface CollegeQuotaCell {
  /** The college's cell of `quotas[sub_type]` for this column. */
  total: number;
  /** Server `allocated` for this cell (saved allocations + approved renewals). */
  allocated: number;
  /** total − allocated − unsaved staged delta. NOT clamped: < 0 = over-allocated. */
  remaining: number;
}

export interface CollegeQuotaOverflow {
  collegeCode: string;
  col: SubTypeConfigCol;
  total: number;
  /** Allocated once the staged changes are saved (total − remaining). */
  used: number;
}

export interface CollegeQuotaGrid {
  /** Colleges with a quota cell or a (saved or staged) consumer, sorted by code. */
  collegeCodes: string[];
  /**
   * Whether this column is quota'd per college at all. False for a non-matrix
   * config, whose only ceiling is the global pool — the caller MUST check this
   * before reading a null `cell` as "no cap": a matrix column with no cell for a
   * college means that college has NO quota there, which is the opposite.
   */
  hasCollegeSplit(colKey: string): boolean;
  /** The cell, or null when the college has no cell in this column. */
  cell(collegeCode: string, colKey: string): CollegeQuotaCell | null;
  /** Every cell the staged state would push past its per-college quota. */
  overflows: CollegeQuotaOverflow[];
}

interface BuildArgs {
  cols: SubTypeConfigCol[];
  quotaStatus: QuotaStatus;
  students: DistributionStudent[];
  /** ranking_item_id → current local allocation (null = unallocated). */
  localAllocations: Map<number, LocalAlloc | null>;
}

function cellKey(collegeCode: string, colKey: string): string {
  return `${collegeCode}|${colKey}`;
}

/** A college the grid has no server quota/consumers for (staged-only). */
const ZERO_QUOTA_CELL = { total: 0, allocated: 0, remaining: 0 } as const;

/**
 * Unsaved delta per (college, column): +1 for each student's current local
 * allocation, −1 for their server-saved one. The delta form avoids double
 * counting — the server's `allocated` already includes saved allocations, and
 * `localAllocations` is seeded from them (plus auto-preview suggestions).
 *
 * Renewal students are excluded: the backend counts a renewal's consumption via
 * its approved Application, not its ranking item, so checkbox changes on a
 * renewal row don't move quota server-side.
 */
function buildLocalDelta(
  students: DistributionStudent[],
  localAllocations: Map<number, LocalAlloc | null>
): Record<string, number> {
  const delta: Record<string, number> = {};
  const bump = (college: string, colKey: string, amount: number) => {
    const k = cellKey(college, colKey);
    delta[k] = (delta[k] ?? 0) + amount;
  };
  for (const s of students) {
    if (s.is_renewal) continue;
    const college = s.college_code || "";
    const saved = getSavedAllocation(s);
    if (saved) {
      bump(college, makeColKey(saved.sub_type, saved.config_id), -1);
    }
    const local = localAllocations.get(s.ranking_item_id);
    if (local) {
      bump(college, makeColKey(local.sub_type, local.config_id), +1);
    }
  }
  return delta;
}

export function buildCollegeQuotaGrid({
  cols,
  quotaStatus,
  students,
  localAllocations,
}: BuildArgs): CollegeQuotaGrid {
  const localDelta = buildLocalDelta(students, localAllocations);

  // Per visible column: the server's per-college grid (null = non-matrix config).
  const byColKey: Record<string, Record<string, CollegeQuota> | null> = {};
  for (const col of cols) {
    const cData = (quotaStatus[col.sub_type]?.by_config ?? []).find(
      c => c.config_id === col.config_id
    );
    byColKey[col.key] = cData?.by_college ?? null;
  }

  // Rows: colleges known to the server, plus colleges that only exist as staged
  // (unsaved) allocations into a matrix column — those must surface so
  // over-allocating a zero-quota college warns BEFORE saving.
  const codes = new Set<string>();
  for (const col of cols) {
    for (const code of Object.keys(byColKey[col.key] ?? {})) {
      codes.add(code);
    }
  }
  for (const [key, delta] of Object.entries(localDelta)) {
    if (delta === 0) continue;
    const sep = key.indexOf("|");
    const college = key.slice(0, sep);
    const colKey = key.slice(sep + 1);
    if (byColKey[colKey] != null) {
      codes.add(college);
    }
  }
  const collegeCodes = Array.from(codes).sort((a, b) => a.localeCompare(b));

  const hasCollegeSplit = (colKey: string): boolean => byColKey[colKey] != null;

  const cell = (collegeCode: string, colKey: string): CollegeQuotaCell | null => {
    const colColleges = byColKey[colKey];
    if (colColleges == null) return null;
    const entry = colColleges[collegeCode];
    // _college_breakdown omits a college with neither quota nor consumers, so a
    // missing entry in a MATRIX column means a cell of 0 — not "unconstrained".
    // Reading it as 0/0 is what makes the very first tick into a zero-quota
    // college refusable; treating it as absent let one slip through.
    const delta = localDelta[cellKey(collegeCode, colKey)] ?? 0;
    const base = entry ?? ZERO_QUOTA_CELL;
    return {
      total: base.total,
      allocated: base.allocated,
      remaining: base.remaining - delta,
    };
  };

  const overflows: CollegeQuotaOverflow[] = [];
  for (const collegeCode of collegeCodes) {
    for (const col of cols) {
      const entry = cell(collegeCode, col.key);
      if (!entry || entry.remaining >= 0) continue;
      overflows.push({
        collegeCode,
        col,
        total: entry.total,
        used: entry.total - entry.remaining,
      });
    }
  }

  return { collegeCodes, hasCollegeSplit, cell, overflows };
}
