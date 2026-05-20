"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Loader2 } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api";

import { AcademicInfoCard } from "./AcademicInfoCard";
import { SummaryCards } from "./SummaryCards";
import { PaymentHistoryTable } from "./PaymentHistoryTable";

const STUDENT_NUMBER_REGEX = /^[A-Za-z0-9]{4,15}$/;

export function StudentHistoryPanel() {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "student-history", submitted],
    enabled: submitted !== null,
    queryFn: async () => {
      const response = await apiClient.studentHistory.getByNumber(submitted!);
      if (!response.success) {
        throw new Error(response.message || "查詢失敗");
      }
      return response.data!;
    },
    retry: false,
  });

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!STUDENT_NUMBER_REGEX.test(trimmed)) {
      setInputError("請輸入有效的學號 (4-15 位英數字)");
      return;
    }
    setInputError(null);
    setSubmitted(trimmed);
  };

  const notFound =
    query.isError && /404|查無/.test((query.error as Error)?.message ?? "");

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>學生領取歷史查詢</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <Label htmlFor="student-number-input">學號</Label>
              <Input
                id="student-number-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSubmit();
                }}
                placeholder="例: 310460031"
                autoFocus
              />
              {inputError && (
                <p className="text-sm text-destructive mt-1">{inputError}</p>
              )}
            </div>
            <Button onClick={handleSubmit} disabled={query.isFetching}>
              {query.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Search className="h-4 w-4 mr-2" />
              )}
              查詢
            </Button>
          </div>
        </CardContent>
      </Card>

      {query.isFetching && (
        <Card>
          <CardContent className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">查詢中...</span>
          </CardContent>
        </Card>
      )}

      {notFound && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="font-medium text-destructive">查無此學生資料</p>
            <p className="text-sm text-muted-foreground mt-1">
              學號 <span className="font-mono">{submitted}</span> 既無學籍資料也無領取記錄。
            </p>
          </CardContent>
        </Card>
      )}

      {query.data && (
        <>
          <AcademicInfoCard
            academicInfo={query.data.academic_info}
            snapshotName={query.data.summary.snapshot_name}
          />
          <SummaryCards summary={query.data.summary} />
          <PaymentHistoryTable records={query.data.payment_records} />
        </>
      )}
    </div>
  );
}
