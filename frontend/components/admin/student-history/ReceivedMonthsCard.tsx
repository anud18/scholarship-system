"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ReceivedMonthsBreakdown } from "@/lib/api/modules/student-history";

interface ReceivedMonthsCardProps {
  breakdowns: ReceivedMonthsBreakdown[];
}

function formatImportedAt(value: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

/**
 * The stored source row, exactly as the imported file had it. Column order
 * follows the file's own headers, so it reads like the original spreadsheet.
 */
function RawRowDetail({ breakdown }: { breakdown: ReceivedMonthsBreakdown }) {
  const entries = Object.entries(breakdown.raw_row ?? {});
  const importedAt = formatImportedAt(breakdown.imported_at);

  return (
    <div className="mt-2 rounded-md border bg-muted/40 p-3">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
        {entries.map(([header, value]) => (
          <div key={header} className="flex gap-2 text-sm">
            <dt className="min-w-[8rem] shrink-0 text-muted-foreground">
              {header}
            </dt>
            <dd className="break-all">{value || "—"}</dd>
          </div>
        ))}
      </dl>
      {(breakdown.file_name || importedAt) && (
        <p className="mt-3 border-t pt-2 text-xs text-muted-foreground">
          來源檔案 <span className="font-mono">{breakdown.file_name ?? "—"}</span>
          {importedAt && <> · 匯入於 {importedAt}</>}
        </p>
      )}
    </div>
  );
}

export function ReceivedMonthsCard({ breakdowns }: ReceivedMonthsCardProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (breakdowns.length === 0) return null;

  const toggle = (key: string) => {
    // Rebuild the set rather than mutating it, so React sees a new value.
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>已領月份數</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {breakdowns.map((breakdown, index) => {
          const key = `${breakdown.scholarship_type_id ?? "unknown"}-${index}`;
          const isOpen = expanded.has(key);
          const hasImport = breakdown.imported_months > 0;

          return (
            <div key={key} className="rounded-md border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{breakdown.scholarship_name}</span>
                  {hasImport && (
                    <Badge variant="secondary" className="text-xs">
                      含匯入
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-lg font-semibold tabular-nums">
                    {breakdown.total_months}
                  </span>
                  <span className="text-sm text-muted-foreground">個月</span>
                  {breakdown.raw_row && (
                    <button
                      type="button"
                      onClick={() => toggle(key)}
                      aria-expanded={isOpen}
                      className="inline-flex items-center gap-1 text-sm text-primary hover:underline"
                    >
                      {isOpen ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                      檔案明細
                    </button>
                  )}
                </div>
              </div>

              <p className="mt-1 text-sm text-muted-foreground">
                {hasImport && (
                  <>
                    匯入 {breakdown.imported_months}
                    {breakdown.award_start_month && breakdown.award_current_month && (
                      <>
                        {" "}
                        ({breakdown.award_start_month}–{breakdown.award_current_month})
                      </>
                    )}
                    {" · "}
                  </>
                )}
                系統 {breakdown.system_months}
              </p>

              {isOpen && breakdown.raw_row && <RawRowDetail breakdown={breakdown} />}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
