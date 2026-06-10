"use client";

import { useMemo } from "react";
import { Building2 } from "lucide-react";
import type {
  CollegeQuota,
  DistributionStudent,
  QuotaStatus,
  SubTypeConfigCol,
} from "@/lib/api/modules/manual-distribution";
import { getAcademyName } from "@/hooks/use-reference-data";

interface CollegeQuotaMatrixProps {
  cols: SubTypeConfigCol[];
  quotaStatus: QuotaStatus;
  students: DistributionStudent[];
  /** ranking_item_id → current local allocation (null = unallocated). */
  localAllocations: Map<number, { sub_type: string; config_id: number } | null>;
  academies: Array<{ code: string; name: string }>;
}

const UNKNOWN_COLLEGE_LABEL = "未知";

function cellKey(collegeCode: string, colKey: string) {
  return `${collegeCode}|${colKey}`;
}

/**
 * College × (sub_type × config) remaining-quota matrix (advisory display).
 *
 * liveRemaining = serverRemaining − Δlocal, where Δlocal counts the UNSAVED
 * difference between each student's current local allocation and their
 * server-saved allocation. The delta form avoids double-counting: server
 * `allocated` already includes saved allocations, and `localAllocations` is
 * seeded from them (plus auto-preview suggestions).
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
      const college = s.college_code || "";
      if (s.is_allocated && s.allocated_sub_type && s.allocation_config_id != null) {
        bump(college, `${s.allocated_sub_type}:${s.allocation_config_id}`, -1);
      }
      const local = localAllocations.get(s.ranking_item_id);
      if (local) {
        bump(college, `${local.sub_type}:${local.config_id}`, +1);
      }
    }
    return delta;
  }, [students, localAllocations]);

  const collegeRows = useMemo(() => {
    const codes = new Set<string>();
    for (const stData of Object.values(quotaStatus)) {
      for (const cData of Object.values(stData.by_config)) {
        for (const code of Object.keys(cData.by_college ?? {})) {
          codes.add(code);
        }
      }
    }
    return Array.from(codes).sort((a, b) => a.localeCompare(b));
  }, [quotaStatus]);

  const byColKey = useMemo(() => {
    const map: Record<string, Record<string, CollegeQuota> | null> = {};
    for (const [subType, stData] of Object.entries(quotaStatus)) {
      for (const cData of Object.values(stData.by_config)) {
        map[`${subType}:${cData.config_id}`] = cData.by_college ?? null;
      }
    }
    return map;
  }, [quotaStatus]);

  const resolveCollegeName = (code: string): string => {
    if (!code) return UNKNOWN_COLLEGE_LABEL;
    const fromReference = getAcademyName(code, academies);
    if (fromReference !== code && fromReference !== "-") return fromReference;
    return students.find(s => s.college_code === code)?.college_name || code;
  };

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
              <th className="text-left font-medium py-1.5 pr-3 whitespace-nowrap">
                學院
              </th>
              {cols.map(col => (
                <th
                  key={col.key}
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
                <td className="py-1.5 pr-3 font-medium text-slate-700 whitespace-nowrap">
                  {resolveCollegeName(code)}
                </td>
                {cols.map(col => {
                  const entry = byColKey[col.key]?.[code];
                  if (!entry) {
                    return (
                      <td key={col.key} className="py-1.5 px-2 text-center text-slate-300">
                        —
                      </td>
                    );
                  }
                  const liveRemaining =
                    entry.remaining - (localDelta[cellKey(code, col.key)] ?? 0);
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
