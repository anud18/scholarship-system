"use client";

import { useEffect, useState } from "react";
import { Loader2, Download, FileSpreadsheet, FileText } from "lucide-react";
import { toast } from "sonner";
import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import type { DistributionResults } from "@/lib/api/modules/college";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { triggerBlobDownload } from "@/lib/utils/download";

interface DistributionResultPanelProps {
  user: User;
  scholarshipType: { id: number; code: string; name: string };
}

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
    if (typeof selectedAcademicYear !== "number") return;
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
      {data.sub_types.map((group) => (
        <div key={group.code} className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-base font-semibold text-gray-800">{group.label}</h3>

          <Section title="正取" tone="emerald">
            {group.admitted.map((s) => (
              <Row key={`a-${s.student_number}`} order={s.rank_position} name={s.student_name} id={s.student_number} department={s.department} />
            ))}
          </Section>

          <Section title="備取" tone="amber">
            {group.backup.map((s) => (
              <Row key={`b-${s.student_number}`} order={s.backup_position} name={s.student_name} id={s.student_number} department={s.department} />
            ))}
          </Section>

          <Section title="未錄取" tone="gray">
            {group.rejected.map((s) => (
              <Row key={`r-${s.student_number}`} name={s.student_name} id={s.student_number} department={s.department} />
            ))}
          </Section>
        </div>
      ))}
    </div>
  );
}

function Section({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "emerald" | "amber" | "gray";
  children: React.ReactNode;
}) {
  const hasItems = Array.isArray(children) ? children.length > 0 : !!children;
  const toneClass =
    tone === "emerald" ? "text-emerald-700" : tone === "amber" ? "text-amber-700" : "text-gray-500";
  return (
    <div className="mb-3 last:mb-0">
      <p className={`mb-1 text-xs font-semibold ${toneClass}`}>{title}</p>
      {hasItems ? <ul className="space-y-0.5">{children}</ul> : <p className="text-xs text-gray-400">—</p>}
    </div>
  );
}

function Row({
  order,
  name,
  id,
  department,
}: {
  order?: number;
  name: string;
  id: string;
  department: string;
}) {
  return (
    <li className="flex items-center gap-2 text-sm text-gray-700">
      {typeof order === "number" && <span className="tabular-nums text-gray-400">{order}.</span>}
      <span>{name}</span>
      <span className="text-xs text-gray-400">({id})</span>
      {department && <span className="text-xs text-gray-500">{department}</span>}
    </li>
  );
}
