"use client";

import { useMemo } from "react";
import { Building2 } from "lucide-react";
import type {
  DistributionStudent,
  LocalAlloc,
  QuotaStatus,
  SubTypeConfigCol,
} from "@/lib/api/modules/manual-distribution";
import {
  buildCollegeNameMap,
  resolveCollegeName,
} from "@/lib/api/modules/manual-distribution";
import { buildCollegeQuotaGrid } from "@/lib/api/modules/college-quota-grid";

interface CollegeQuotaMatrixProps {
  cols: SubTypeConfigCol[];
  quotaStatus: QuotaStatus;
  students: DistributionStudent[];
  /** ranking_item_id → current local allocation (null = unallocated). */
  localAllocations: Map<number, LocalAlloc | null>;
  academies: Array<{ code: string; name: string }>;
}

/**
 * College × (sub_type × config) remaining-quota matrix.
 *
 * Each cell is `liveRemaining/total`, where liveRemaining already nets out the
 * UNSAVED checkbox changes (see buildCollegeQuotaGrid). A red (negative) cell is
 * not a warning to weigh — it blocks 儲存/確認分發, both on this screen and in the
 * server's own quota gate.
 */
export function CollegeQuotaMatrix({
  cols,
  quotaStatus,
  students,
  localAllocations,
  academies,
}: CollegeQuotaMatrixProps) {
  const grid = useMemo(
    () => buildCollegeQuotaGrid({ cols, quotaStatus, students, localAllocations }),
    [cols, quotaStatus, students, localAllocations]
  );

  const collegeNames = useMemo(
    () => buildCollegeNameMap(academies, students),
    [academies, students]
  );

  if (cols.length === 0 || grid.collegeCodes.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm mb-3">
      <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-[#003d7a]" />
          各學院剩餘名額
        </h3>
        <span className="text-[10px] text-slate-400">
          剩餘/總額；已即時扣除未儲存的勾選；紅字表示超過該學院名額，須調整後才能儲存
        </span>
      </div>
      <div className="p-3 overflow-x-auto">
        <table className="w-full text-xs border-collapse border border-slate-300">
          <thead>
            <tr className="text-slate-500 bg-slate-50">
              <th
                scope="col"
                className="text-left font-medium py-1.5 px-2 whitespace-nowrap border border-slate-300"
              >
                學院
              </th>
              {cols.map(col => (
                <th
                  key={col.key}
                  scope="col"
                  className="text-center font-medium py-1.5 px-2 whitespace-nowrap border border-slate-300"
                >
                  {col.display_name}
                  {!col.is_own && (
                    <span className="ml-1 text-[9px] bg-amber-100 text-amber-700 px-1 py-0.5 rounded">
                      共用往年
                    </span>
                  )}
                </th>
              ))}
              <th
                scope="col"
                className="text-center font-medium py-1.5 px-2 whitespace-nowrap border border-slate-300 bg-slate-100 text-slate-600"
              >
                總名額
              </th>
            </tr>
          </thead>
          <tbody>
            {grid.collegeCodes.map(code => {
              const rowCells = cols.map(col => ({
                col,
                entry: grid.cell(code, col.key),
              }));
              const rowTotal = rowCells.reduce(
                (acc, { entry }) => acc + (entry?.total ?? 0),
                0
              );
              const rowRemaining = rowCells.reduce(
                (acc, { entry }) => acc + (entry?.remaining ?? 0),
                0
              );
              return (
                <tr key={code || "__unknown__"}>
                  <th
                    scope="row"
                    className="text-left py-1.5 px-2 font-medium text-slate-700 whitespace-nowrap border border-slate-300"
                  >
                    {resolveCollegeName(collegeNames, code)}
                  </th>
                  {rowCells.map(({ col, entry }) => {
                    if (!entry) {
                      return (
                        <td
                          key={col.key}
                          className="py-1.5 px-2 text-center text-slate-300 border border-slate-300"
                        >
                          —
                        </td>
                      );
                    }
                    const tone =
                      entry.remaining < 0
                        ? "text-red-600 font-bold"
                        : entry.remaining === 0
                          ? "text-slate-400"
                          : "text-[#003d7a] font-semibold";
                    return (
                      <td
                        key={col.key}
                        className={`py-1.5 px-2 text-center font-mono tabular-nums border border-slate-300 ${tone}`}
                        title={`總額 ${entry.total}・已儲存核配 ${entry.allocated}`}
                      >
                        {entry.remaining}/{entry.total}
                      </td>
                    );
                  })}
                  <td
                    className={`py-1.5 px-2 text-center font-mono tabular-nums border border-slate-300 bg-slate-50 ${
                      rowRemaining < 0
                        ? "text-red-600 font-bold"
                        : rowRemaining === 0
                          ? "text-slate-400"
                          : "text-[#003d7a] font-bold"
                    }`}
                    title={`本學院各欄位加總：剩餘 ${rowRemaining}・總額 ${rowTotal}`}
                  >
                    {rowRemaining}/{rowTotal}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
