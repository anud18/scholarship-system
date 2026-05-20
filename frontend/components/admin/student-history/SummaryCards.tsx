"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { HistorySummary } from "@/lib/api/modules/student-history";

interface SummaryCardsProps {
  summary: HistorySummary;
}

function formatAmount(amount: string): string {
  const num = Number(amount);
  if (Number.isNaN(num)) return amount;
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "TWD",
    maximumFractionDigits: 0,
  }).format(num);
}

export function SummaryCards({ summary }: SummaryCardsProps) {
  const items = [
    { label: "總筆數", value: summary.total_records.toString() },
    { label: "總金額", value: formatAmount(summary.total_amount) },
    { label: "獎學金類型數", value: summary.scholarship_type_count.toString() },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((it) => (
        <Card key={it.label}>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-muted-foreground">{it.label}</p>
            <p className="text-3xl font-semibold mt-1">{it.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
