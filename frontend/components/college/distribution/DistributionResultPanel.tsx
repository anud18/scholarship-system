"use client";

import { useEffect, useState } from "react";
import { Loader2, Download, FileSpreadsheet, FileText } from "lucide-react";
import { toast } from "sonner";
import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import type { DistributionResults, DistributionStudent } from "@/lib/api/modules/college";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { triggerBlobDownload } from "@/lib/utils/download";

interface DistributionResultPanelProps {
  user: User;
  scholarshipType: { id: number; code: string; name: string };
}

type DistributionStatus = "admitted" | "backup" | "rejected";

interface PendingRow extends DistributionStudent {
  status: "backup" | "rejected";
  groupLabel: string;
}

const STATUS_CONFIG: Record<
  DistributionStatus,
  { label: string; badgeClass: string; dotClass: string }
> = {
  admitted: {
    label: "正取",
    badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700",
    dotClass: "bg-emerald-500",
  },
  backup: {
    label: "備取",
    badgeClass: "border-amber-200 bg-amber-50 text-amber-700",
    dotClass: "bg-amber-500",
  },
  rejected: {
    label: "未錄取",
    badgeClass: "border-gray-200 bg-gray-100 text-gray-500",
    dotClass: "bg-gray-400",
  },
};

export function DistributionResultPanel({ scholarshipType }: DistributionResultPanelProps) {
  const { selectedAcademicYear, selectedSemester } = useCollegeManagement();
  const [data, setData] = useState<DistributionResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (typeof selectedAcademicYear !== "number" || !Number.isFinite(selectedAcademicYear)) {
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const { apiClient } = await import("@/lib/api");
        const resp = await apiClient.college.getDistributionResults({
          scholarshipTypeId: scholarshipType.id,
          academicYear: selectedAcademicYear,
          semester: selectedSemester,
        });
        if (!cancelled) {
          if (resp.success && resp.data) {
            setData(resp.data);
          } else {
            setError(resp.message || "無法載入分發結果");
          }
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "無法載入分發結果");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [scholarshipType.id, selectedAcademicYear, selectedSemester]);

  const handleExport = async (format: "xlsx" | "pdf") => {
    // Mirror the loader's guard exactly: typeof alone admits NaN/Infinity, which would
    // send academic_year=NaN and earn a 422. Unreachable today (a non-finite year makes
    // the loader bail, so the 尚未分發 branch renders and this dropdown never mounts) —
    // but that safety is an accident of render order, so don't depend on it.
    if (typeof selectedAcademicYear !== "number" || !Number.isFinite(selectedAcademicYear)) return;
    setExporting(true);
    try {
      const { exportDistributionResults } = await import("@/lib/api/modules/college");
      const result = await exportDistributionResults({
        scholarshipTypeId: scholarshipType.id,
        academicYear: selectedAcademicYear,
        semester: selectedSemester,
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

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-600">
        <Loader2 className="h-6 w-6 animate-spin text-blue-600 mr-2" />
        載入分發結果中...
      </div>
    );
  }

  if (error) {
    return <div className="py-12 text-center text-sm text-gray-500">{error}</div>;
  }

  if (!data || !data.distribution_executed || data.sub_types.length === 0) {
    return <div className="py-12 text-center text-sm text-gray-500">尚未分發，暫無結果</div>;
  }

  // Rejected students come back under the RANKING's sub-type code (e.g. a literal
  // "default" group), which is meaningless to the college — so render one card per
  // sub-type that actually admitted students, and pool every 備取/未錄取 row into a
  // single combined table.
  const admittedGroups = data.sub_types.filter((g) => g.admitted.length > 0);
  const byPosition = (a?: number, b?: number) =>
    (a === undefined ? Number.MAX_SAFE_INTEGER : a) - (b === undefined ? Number.MAX_SAFE_INTEGER : b);
  const pendingRows: PendingRow[] = [
    ...data.sub_types
      .flatMap((g) => g.backup.map((s) => ({ ...s, status: "backup" as const, groupLabel: g.label })))
      .sort((a, b) => byPosition(a.backup_position, b.backup_position)),
    ...data.sub_types
      .flatMap((g) => g.rejected.map((s) => ({ ...s, status: "rejected" as const, groupLabel: g.label })))
      .sort((a, b) => byPosition(a.rank_position, b.rank_position)),
  ];
  const backupCount = pendingRows.filter((r) => r.status === "backup").length;

  if (admittedGroups.length === 0 && pendingRows.length === 0) {
    return <div className="py-12 text-center text-sm text-gray-500">尚未分發，暫無結果</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={exporting}>
              {exporting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              匯出
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
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
      </div>
      {admittedGroups.map((group) => (
        <div key={group.code} className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50/80 px-4 py-3">
            <h3 className="text-base font-semibold text-gray-800">{group.label}</h3>
            <StatusCount status="admitted" count={group.admitted.length} />
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-10 w-20 text-center">順位</TableHead>
                <TableHead className="h-10">姓名</TableHead>
                <TableHead className="h-10">學號</TableHead>
                <TableHead className="h-10">系所</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {group.admitted.map((s) => (
                <TableRow key={s.student_number} className="text-gray-700">
                  <TableCell className="py-2.5 text-center tabular-nums">
                    {typeof s.rank_position === "number" ? s.rank_position : "—"}
                  </TableCell>
                  <TableCell className="py-2.5 font-medium">{s.student_name}</TableCell>
                  <TableCell className="py-2.5 tabular-nums">{s.student_number}</TableCell>
                  <TableCell className="py-2.5">{s.department || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}

      {pendingRows.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 bg-gray-50/80 px-4 py-3">
            <h3 className="text-base font-semibold text-gray-800">備取／未錄取</h3>
            <div className="flex items-center gap-4">
              <StatusCount status="backup" count={backupCount} />
              <StatusCount status="rejected" count={pendingRows.length - backupCount} />
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-10 w-24">狀態</TableHead>
                <TableHead className="h-10 w-24 text-center">備取序</TableHead>
                {backupCount > 0 && <TableHead className="h-10">申請類別</TableHead>}
                <TableHead className="h-10">姓名</TableHead>
                <TableHead className="h-10">學號</TableHead>
                <TableHead className="h-10">系所</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pendingRows.map((row) => (
                <TableRow
                  key={`${row.status}-${row.groupLabel}-${row.student_number}`}
                  className={row.status === "rejected" ? "text-gray-400" : "text-gray-700"}
                >
                  <TableCell className="py-2.5">
                    <Badge variant="outline" className={STATUS_CONFIG[row.status].badgeClass}>
                      {STATUS_CONFIG[row.status].label}
                    </Badge>
                  </TableCell>
                  <TableCell className="py-2.5 text-center tabular-nums">
                    {row.status === "backup" && typeof row.backup_position === "number"
                      ? row.backup_position
                      : "—"}
                  </TableCell>
                  {backupCount > 0 && (
                    <TableCell className="py-2.5">
                      {row.status === "backup" ? row.groupLabel : "—"}
                    </TableCell>
                  )}
                  <TableCell className="py-2.5 font-medium">{row.student_name}</TableCell>
                  <TableCell className="py-2.5 tabular-nums">{row.student_number}</TableCell>
                  <TableCell className="py-2.5">{row.department || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function StatusCount({ status, count }: { status: DistributionStatus; count: number }) {
  const config = STATUS_CONFIG[status];
  return (
    <span className="flex items-center gap-1.5 text-xs text-gray-600">
      <span className={`h-2 w-2 rounded-full ${config.dotClass}`} aria-hidden />
      {config.label}
      <span className="font-semibold tabular-nums text-gray-800">{count}</span>
    </span>
  );
}
