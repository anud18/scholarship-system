"use client";

import { useState } from "react";
import { Download, Eye, FileSpreadsheet, FileText, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  exportDistributionSummary,
  resolveCollegeName,
  type DistributionSummaryResult,
} from "@/lib/api/modules/manual-distribution";
import { triggerBlobDownload } from "@/lib/utils/download";

interface DistributionSummaryDialogProps {
  summary: DistributionSummaryResult | null;
  isLoading: boolean;
  /** Academies-first code→name map shared with the panel (buildCollegeNameMap). */
  collegeNames: Map<string, string>;
  /** Short display label for a sub-type code (panel's getSubTypeShortName). */
  getSubTypeLabel: (subType: string) => string;
  scholarshipTypeId: number;
  academicYear: number | undefined;
  semester: string | undefined;
  onClose: () => void;
}

/**
 * The 分發結果名單 modal: allocated students grouped by sub-type × 年度配額,
 * with 匯出 Excel / PDF backed by GET /manual-distribution/distribution-summary/export
 * (the backend export reads through the same loader as the list shown here).
 */
export function DistributionSummaryDialog({
  summary,
  isLoading,
  collegeNames,
  getSubTypeLabel,
  scholarshipTypeId,
  academicYear,
  semester,
  onClose,
}: DistributionSummaryDialogProps) {
  const [exporting, setExporting] = useState(false);

  const hasRows = !!summary && summary.groups.length > 0;

  const handleExport = async (format: "xlsx" | "pdf") => {
    // The modal only opens after a load with valid selections, but the guard
    // keeps a stale/cleared selection from sending academic_year=undefined.
    // Say so rather than no-opping — a dead button reads as a broken export.
    if (typeof academicYear !== "number" || !Number.isFinite(academicYear) || !semester) {
      toast.error("請先選擇學年度與學期");
      return;
    }
    setExporting(true);
    try {
      // Statically imported: this module is already in the initial chunk via
      // resolveCollegeName above, so a dynamic import would split nothing. The
      // lazy-import rule in frontend/CLAUDE.md targets heavy libs (xlsx,
      // react-pdf); rendering happens server-side here.
      const result = await exportDistributionSummary({
        scholarshipTypeId,
        academicYear,
        semester,
        format,
      });
      triggerBlobDownload(result);
      toast.success("匯出成功");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "匯出失敗");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg shadow-lg max-w-4xl w-full max-h-[85vh] flex flex-col">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Eye className="h-5 w-5" />
            分發結果名單
          </h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 text-2xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {isLoading ? (
            <div className="flex justify-center py-12">
              <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
            </div>
          ) : !hasRows ? (
            <p className="text-center text-slate-500 py-8">
              尚未完成分發，或無已分配的學生
            </p>
          ) : (
            <div className="space-y-6">
              <div className="text-sm text-slate-600">
                共 {summary.total_allocated} 位學生已分發到{" "}
                {summary.groups.length} 個獎學金類別
              </div>
              {summary.groups.map(group => (
                <div
                  // Groups are keyed server-side by (sub_type, allocation_config_id),
                  // and two configs can share an academic_year — so the year alone
                  // is not unique. Include the config id.
                  key={`${group.sub_type}-${group.allocation_config_id}-${group.allocation_year}`}
                  className="border border-slate-200 rounded-lg overflow-hidden"
                >
                  <div className="bg-slate-50 px-4 py-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-800">
                        {getSubTypeLabel(group.sub_type)}
                      </span>
                      <span className="text-xs text-slate-500 font-mono">
                        ({group.sub_type})
                      </span>
                      <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                        {group.allocation_year} 年度配額
                      </span>
                    </div>
                    <span className="text-sm font-medium text-slate-700">
                      {group.count} 人
                    </span>
                  </div>
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-slate-100 text-xs text-slate-500">
                        <th className="text-left px-4 py-2">排名</th>
                        <th className="text-left px-4 py-2">學號</th>
                        <th className="text-left px-4 py-2">姓名</th>
                        <th className="text-left px-4 py-2">學院</th>
                        <th className="text-left px-4 py-2">系所</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...group.students]
                        // Same order the export numbers 序號 by: 學院 then 名次.
                        // rank_position is scoped to ONE college's ranking, so
                        // sorting on it alone interleaves colleges and 序號 N in
                        // the file would point at a different row than the Nth
                        // row here.
                        .sort(
                          (a, b) =>
                            (a.college_code || "").localeCompare(
                              b.college_code || ""
                            ) || a.rank_position - b.rank_position
                        )
                        .map(student => (
                          <tr
                            key={student.ranking_item_id}
                            className="border-b border-slate-50 hover:bg-slate-50"
                          >
                            <td className="px-4 py-1.5 text-slate-400">
                              {student.college_rejected ? (
                                <span className="text-red-600">N</span>
                              ) : (
                                student.rank_position
                              )}
                            </td>
                            <td className="px-4 py-1.5 font-mono text-xs">
                              {student.student_id}
                            </td>
                            <td className="px-4 py-1.5 font-medium">
                              {student.student_name}
                            </td>
                            <td className="px-4 py-1.5">
                              {resolveCollegeName(
                                collegeNames,
                                student.college_code,
                                student.college_name
                              )}
                            </td>
                            <td className="px-4 py-1.5 text-slate-600">
                              {student.department_name}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="p-4 border-t border-slate-200 flex justify-between items-center">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" disabled={exporting || !hasRows}>
                {exporting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                匯出
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuItem onClick={() => handleExport("xlsx")}>
                <FileSpreadsheet className="mr-2 h-4 w-4" />
                匯出 Excel
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleExport("pdf")}>
                <FileText className="mr-2 h-4 w-4" />
                匯出 PDF
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="outline" onClick={onClose}>
            關閉
          </Button>
        </div>
      </div>
    </div>
  );
}
