"use client";

import { useEffect, useState } from "react";
import { Search, Loader2, Upload, User as UserIcon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api";
import type { StudentHistoryBatchResult } from "@/lib/api/modules/student-history";

import { AcademicInfoCard } from "./AcademicInfoCard";
import { SummaryCards } from "./SummaryCards";
import { PaymentHistoryTable } from "./PaymentHistoryTable";
import { ReceivedMonthsCard } from "./ReceivedMonthsCard";
import { ImportReceivedMonthsDialog } from "./ImportReceivedMonthsDialog";
import { HistoryVisibilityCard } from "./HistoryVisibilityCard";
import { MAX_BATCH_SIZE, parseStudentNumbers } from "./parse-student-numbers";

interface StudentHistoryPanelProps {
  /**
   * "admin" (default) shows the 匯入已領月份數 action; "college" hides it —
   * the import endpoint is admin-only, and the backend scopes college
   * queries to the user's own college.
   */
  variant?: "admin" | "college";
}

function StudentHistoryResult({ result }: { result: StudentHistoryBatchResult }) {
  if (!result.success || !result.data) {
    const isNotFound = /查無/.test(result.error ?? "");
    return (
      <Card className="border-destructive">
        <CardContent className="pt-6">
          <p className="font-medium text-destructive">
            {isNotFound ? "查無此學生資料" : "查詢失敗"}
          </p>
          <p className="text-sm text-muted-foreground mt-1">
            學號 <span className="font-mono">{result.student_number}</span>
            {isNotFound ? " 既無學籍資料也無領取記錄。" : `：${result.error}`}
          </p>
        </CardContent>
      </Card>
    );
  }

  const data = result.data;
  return (
    <div className="space-y-4">
      <AcademicInfoCard
        academicInfo={data.academic_info}
        snapshotName={data.summary.snapshot_name}
      />
      <SummaryCards summary={data.summary} />
      <ReceivedMonthsCard breakdowns={data.received_months} />
      <PaymentHistoryTable records={data.payment_records} />
    </div>
  );
}

export function StudentHistoryPanel({ variant = "admin" }: StudentHistoryPanelProps) {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<string[] | null>(null);
  const [fetchToken, setFetchToken] = useState(0);
  const [inputError, setInputError] = useState<string | null>(null);
  const [results, setResults] = useState<StudentHistoryBatchResult[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    if (submitted === null) return;

    let cancelled = false;
    setLoading(true);
    setResults(null);
    setError(null);

    apiClient.studentHistory
      .getBatch(submitted)
      .then((response) => {
        if (cancelled) return;
        if (response.success && response.data) {
          setResults(response.data.results);
        } else {
          setError(response.message ?? "查詢失敗");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "網路錯誤");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // fetchToken forces refetch when the user retries with the same student numbers
  }, [submitted, fetchToken]);

  const handleSubmit = () => {
    const { valid, invalid } = parseStudentNumbers(input);
    let validationError: string | null = null;
    if (invalid.length > 0) {
      validationError = `請輸入有效的學號 (4-15 位英數字)：${invalid.join("、")}`;
    } else if (valid.length === 0) {
      validationError = "請輸入有效的學號 (4-15 位英數字)";
    } else if (valid.length > MAX_BATCH_SIZE) {
      validationError = `一次最多查詢 ${MAX_BATCH_SIZE} 位學生`;
    }

    if (validationError) {
      setInputError(validationError);
      // Clear previous result so it doesn't render under the validation error.
      // loading must be reset here too: setting `submitted` to null makes the
      // effect early-return, so an in-flight request's .finally (cancelled)
      // would otherwise leave the spinner stranded on.
      setSubmitted(null);
      setResults(null);
      setError(null);
      setLoading(false);
      return;
    }
    setInputError(null);
    setSubmitted(valid);
    setFetchToken((n) => n + 1);
  };

  return (
    <div className="space-y-4">
      {variant === "admin" && <HistoryVisibilityCard />}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle>學生領獎紀錄查詢</CardTitle>
          {variant === "admin" && (
            <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
              <Upload className="h-4 w-4 mr-2" />
              匯入已領月份數
            </Button>
          )}
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
                  // Same gate as the 查詢 button's disabled={loading}.
                  if (e.key === "Enter" && !loading) handleSubmit();
                }}
                placeholder="例: 310460031, 310460032 (可一次查詢多位，以逗號或空白分隔)"
                autoFocus
              />
              {inputError && <p className="text-sm text-destructive mt-1">{inputError}</p>}
              {variant === "college" && (
                <p className="text-xs text-muted-foreground mt-1">
                  僅能查詢本學院學生的領獎紀錄。
                </p>
              )}
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

      {!loading && error && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="font-medium text-destructive">查詢失敗</p>
            <p className="text-sm text-muted-foreground mt-1">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading &&
        results &&
        (results.length === 1 ? (
          <StudentHistoryResult result={results[0]} />
        ) : (
          results.map((result) => (
            <section key={result.student_number} className="space-y-4">
              <h3 className="flex items-center gap-2 text-lg font-semibold border-b pb-2">
                <UserIcon className="h-5 w-5 text-muted-foreground" />
                <span className="font-mono">{result.student_number}</span>
                {result.data?.summary.snapshot_name && (
                  <span className="text-muted-foreground font-normal">
                    {result.data.summary.snapshot_name}
                  </span>
                )}
              </h3>
              <StudentHistoryResult result={result} />
            </section>
          ))
        ))}

      {variant === "admin" && (
        <ImportReceivedMonthsDialog
          open={importOpen}
          onOpenChange={setImportOpen}
          onImported={() => {
            // Re-run the current lookup so a just-imported baseline shows up.
            if (submitted !== null) setFetchToken((n) => n + 1);
          }}
        />
      )}
    </div>
  );
}
