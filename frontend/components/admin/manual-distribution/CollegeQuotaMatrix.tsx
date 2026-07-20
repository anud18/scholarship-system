"use client";

import { useMemo } from "react";
import { Building2 } from "lucide-react";
import type {
  CollegeQuota,
  DistributionStudent,
  LocalAlloc,
  QuotaStatus,
  SubTypeConfigCol,
} from "@/lib/api/modules/manual-distribution";
import {
  buildCollegeNameMap,
  getSavedAllocation,
  makeColKey,
  resolveCollegeName,
} from "@/lib/api/modules/manual-distribution";

interface CollegeQuotaMatrixProps {
  cols: SubTypeConfigCol[];
  quotaStatus: QuotaStatus;
  students: DistributionStudent[];
  /** ranking_item_id → current local allocation (null = unallocated). */
  localAllocations: Map<number, LocalAlloc | null>;
  academies: Array<{ code: string; name: string }>;
}

function cellKey(collegeCode: string, colKey: string) {
  return `${collegeCode}|${colKey}`;
}

/** A cell for a college the matrix has no quota/consumers for (staged-only). */
const ZERO_QUOTA_CELL: CollegeQuota = { total: 0, allocated: 0, remaining: 0 };

/**
 * College × (sub_type × config) remaining-quota matrix (advisory display).
 *
 * liveRemaining = serverRemaining − Δlocal, where Δlocal counts the UNSAVED
 * difference between each student's current local allocation and their
 * server-saved allocation. The delta form avoids double-counting: server
 * `allocated` already includes saved allocations, and `localAllocations` is
 * seeded from them (plus auto-preview suggestions).
 *
 * Renewal students are excluded from the delta: the backend counts a
 * renewal's consumption via its approved Application, not its ranking item,
 * so checkbox changes on a renewal row don't move quota server-side.
 */
export function CollegeQuotaMatrix({
  cols,
  quotaStatus,
  students,
  localAllocations,
  academies,
}: CollegeQuotaMatrixProps) {
  const localDelta = useMemo(() => {
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
  }, [students, localAllocations]);

  // Per visible column: the server's per-college grid (null = non-matrix config).
  const byColKey = useMemo(() => {
    const map: Record<string, Record<string, CollegeQuota> | null> = {};
    for (const col of cols) {
      const cData = (quotaStatus[col.sub_type]?.by_config ?? []).find(
        c => c.config_id === col.config_id
      );
      map[col.key] = cData?.by_college ?? null;
    }
    return map;
  }, [cols, quotaStatus]);

  // Rows: colleges known to the server, plus colleges that only exist as
  // staged (unsaved) allocations into a matrix column — those must surface
  // so over-allocating a zero-quota college warns BEFORE saving.
  const collegeRows = useMemo(() => {
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
    return Array.from(codes).sort((a, b) => a.localeCompare(b));
  }, [cols, byColKey, localDelta]);

  const collegeNames = useMemo(
    () => buildCollegeNameMap(academies, students),
    [academies, students]
  );

  if (cols.length === 0 || collegeRows.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm mb-3">
      <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-[#003d7a]" />
          各學院剩餘名額
        </h3>
        <span className="text-[10px] text-slate-400">
          剩餘/總額；已即時扣除未儲存的勾選；超額僅供參考，鎖定時以全域名額檢查為準
        </span>
      </div>
      <div className="p-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500">
              <th
                scope="col"
                className="text-left font-medium py-1.5 pr-3 whitespace-nowrap"
              >
                學院
              </th>
              {cols.map(col => (
                <th
                  key={col.key}
                  scope="col"
                  className="text-center font-medium py-1.5 px-2 whitespace-nowrap"
                >
                  {col.display_name}
                  {!col.is_own && (
                    <span className="ml-1 text-[9px] bg-amber-100 text-amber-700 px-1 py-0.5 rounded">
                      共用往年
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {collegeRows.map(code => (
              <tr key={code || "__unknown__"} className="border-t border-slate-100">
                <th
                  scope="row"
                  className="text-left py-1.5 pr-3 font-medium text-slate-700 whitespace-nowrap"
                >
                  {resolveCollegeName(collegeNames, code)}
                </th>
                {cols.map(col => {
                  const colColleges = byColKey[col.key];
                  const delta = localDelta[cellKey(code, col.key)] ?? 0;
                  // Synthesize a 0/0 cell when a matrix column only has
                  // staged allocations for this college (no server entry).
                  const entry =
                    colColleges?.[code] ??
                    (colColleges != null && delta !== 0
                      ? ZERO_QUOTA_CELL
                      : undefined);
                  if (!entry) {
                    return (
                      <td key={col.key} className="py-1.5 px-2 text-center text-slate-300">
                        —
                      </td>
                    );
                  }
                  const liveRemaining = entry.remaining - delta;
                  const tone =
                    liveRemaining < 0
                      ? "text-red-600 font-bold"
                      : liveRemaining === 0
                        ? "text-slate-400"
                        : "text-[#003d7a] font-semibold";
                  return (
                    <td
                      key={col.key}
                      className={`py-1.5 px-2 text-center font-mono tabular-nums ${tone}`}
                      title={`總額 ${entry.total}・已儲存核配 ${entry.allocated}`}
                    >
                      {liveRemaining}/{entry.total}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
