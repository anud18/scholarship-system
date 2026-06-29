"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import type { DistributionResults } from "@/lib/api/modules/college";

interface DistributionResultPanelProps {
  user: User;
  scholarshipType: { id: number; code: string; name: string };
}

export function DistributionResultPanel({ scholarshipType }: DistributionResultPanelProps) {
  const { selectedAcademicYear, selectedSemester } = useCollegeManagement();
  const [data, setData] = useState<DistributionResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      if (typeof selectedAcademicYear !== "number") {
        return;
      }
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
      {data.sub_types.map((group) => (
        <div key={group.code} className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-base font-semibold text-gray-800">{group.label}</h3>

          <Section title="正取" tone="emerald">
            {group.admitted.map((s) => (
              <Row key={`a-${s.student_number}`} order={s.rank_position} name={s.student_name} id={s.student_number} />
            ))}
          </Section>

          <Section title="備取" tone="amber">
            {group.backup.map((s) => (
              <Row key={`b-${s.student_number}`} order={s.backup_position} name={s.student_name} id={s.student_number} />
            ))}
          </Section>

          <Section title="未錄取" tone="gray">
            {group.rejected.map((s) => (
              <Row key={`r-${s.student_number}`} name={s.student_name} id={s.student_number} />
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

function Row({ order, name, id }: { order?: number; name: string; id: string }) {
  return (
    <li className="flex items-center gap-2 text-sm text-gray-700">
      {typeof order === "number" && <span className="tabular-nums text-gray-400">{order}.</span>}
      <span>{name}</span>
      <span className="text-xs text-gray-400">({id})</span>
    </li>
  );
}
