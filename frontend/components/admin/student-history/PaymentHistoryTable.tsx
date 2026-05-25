"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PaymentRecord } from "@/lib/api/modules/student-history";

interface PaymentHistoryTableProps {
  records: PaymentRecord[];
}

function formatAmount(amount: string): string {
  const num = Number(amount);
  if (Number.isNaN(num)) return amount;
  return new Intl.NumberFormat("zh-TW").format(num);
}

export function PaymentHistoryTable({ records }: PaymentHistoryTableProps) {
  if (records.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>領取明細</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">尚無領取記錄</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>領取明細 ({records.length} 筆)</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>期間</TableHead>
              <TableHead>獎學金</TableHead>
              <TableHead>子類型</TableHead>
              <TableHead className="text-right">金額 (NT$)</TableHead>
              <TableHead>配額學年</TableHead>
              <TableHead>造冊號</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.map((r, idx) => (
              <TableRow key={`${r.roster_id}-${idx}`}>
                <TableCell className="font-mono">{r.period_label}</TableCell>
                <TableCell>{r.scholarship_name}</TableCell>
                <TableCell>{r.scholarship_subtype ?? "—"}</TableCell>
                <TableCell className="text-right font-mono">
                  {formatAmount(r.scholarship_amount)}
                </TableCell>
                <TableCell>{r.allocation_year ?? "—"}</TableCell>
                <TableCell className="font-mono text-xs">{r.roster_code}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
