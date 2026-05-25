"use client";

import { useEffect, useState } from "react";
import { Search, Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api";
import type { StudentScholarshipHistoryData } from "@/lib/api/modules/student-history";

import { AcademicInfoCard } from "./AcademicInfoCard";
import { SummaryCards } from "./SummaryCards";
import { PaymentHistoryTable } from "./PaymentHistoryTable";

const STUDENT_NUMBER_REGEX = /^[A-Za-z0-9]{4,15}$/;

export function StudentHistoryPanel() {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  const [data, setData] = useState<StudentScholarshipHistoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (submitted === null) return;

    let cancelled = false;
    setLoading(true);
    setData(null);
    setNotFound(false);
    setError(null);

    apiClient.studentHistory
      .getByNumber(submitted)
      .then((response) => {
        if (cancelled) return;
        if (response.success && response.data) {
          setData(response.data);
        } else {
          const msg = response.message ?? "查詢失敗";
          if (/404|查無/.test(msg)) {
            setNotFound(true);
          } else {
            setError(msg);
          }
        }
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : "網路錯誤";
        if (/404|查無/.test(msg)) {
          setNotFound(true);
        } else {
          setError(msg);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [submitted]);

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!STUDENT_NUMBER_REGEX.test(trimmed)) {
      setInputError("請輸入有效的學號 (4-15 位英數字)");
      return;
    }
    setInputError(null);
    setSubmitted(trimmed);
  };

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
              {inputError && <p className="text-sm text-destructive mt-1">{inputError}</p>}
            </div>
            <Button onClick={handleSubmit} disabled={loading}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Search className="h-4 w-4 mr-2" />
              )}
              查詢
            </Button>
          </div>
        </CardContent>
      </Card>

      {loading && (
        <Card>
          <CardContent className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">查詢中...</span>
          </CardContent>
        </Card>
      )}

      {!loading && notFound && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="font-medium text-destructive">查無此學生資料</p>
            <p className="text-sm text-muted-foreground mt-1">
              學號 <span className="font-mono">{submitted}</span> 既無學籍資料也無領取記錄。
            </p>
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="font-medium text-destructive">查詢失敗</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading && data && (
        <>
          <AcademicInfoCard
            academicInfo={data.academic_info}
            snapshotName={data.summary.snapshot_name}
          />
          <SummaryCards summary={data.summary} />
          <PaymentHistoryTable records={data.payment_records} />
        </>
      )}
    </div>
  );
}
