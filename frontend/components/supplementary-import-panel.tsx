"use client";

import { useCallback, useEffect, useId, useState } from "react";
import {
  AlertCircle,
  Download,
  FileSpreadsheet,
  Loader2,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { apiClient } from "@/lib/api";
import { logger } from "@/lib/utils/logger";

const MAX_BYTES = 10 * 1024 * 1024; // 10 MB
// Backend uses openpyxl which only parses .xlsx (Office Open XML).
// Keep client + server in sync — surface a clear extension error if user picks .xls.
const ACCEPT = ".xlsx";

interface Scholarship {
  id: number;
  name: string;
  name_en?: string;
  code: string;
}

interface PeriodOption {
  value: string;
  label: string;
  label_en?: string;
  academic_year: number;
  semester: string | null;
  is_current?: boolean;
}

interface Availability {
  allowed: boolean;
  configuration_id: number | null;
}

interface SupplementaryImportPanelProps {
  locale?: "zh" | "en";
}

/**
 * 補充匯入 — a college submits applications on behalf of new students.
 *
 * It replaced 批次匯入 for colleges, so the template it offers and the file it
 * accepts are the admin batch-import workbook (one shared generator + parser).
 *
 * The imported rows become ordinary submitted applications: no rank, and no
 * ranking entry. The students go through professor review and college ranking
 * exactly like self-submitting applicants.
 */
export function SupplementaryImportPanel({
  locale = "zh",
}: SupplementaryImportPanelProps) {
  const [scholarships, setScholarships] = useState<Scholarship[]>([]);
  const [selectedScholarship, setSelectedScholarship] =
    useState<Scholarship | null>(null);
  const [periods, setPeriods] = useState<PeriodOption[]>([]);
  const [selectedPeriod, setSelectedPeriod] = useState<string>("");
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [isLoadingScholarships, setIsLoadingScholarships] = useState(false);
  const [isLoadingPeriods, setIsLoadingPeriods] = useState(false);
  const [isCheckingAvailability, setIsCheckingAvailability] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [downloadingTemplate, setDownloadingTemplate] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<{
    imported: number;
    unresolvedProfessors: string[];
  } | null>(null);

  const inputId = useId();
  const isZh = locale === "zh";

  useEffect(() => {
    const fetchScholarships = async () => {
      setIsLoadingScholarships(true);
      try {
        const response = await apiClient.admin.getMyScholarships();
        if (response.success && response.data) {
          setScholarships(response.data as Scholarship[]);
        }
      } catch (error) {
        logger.error("Failed to fetch scholarships", { error });
        setLastError(
          isZh ? "無法載入獎學金列表" : "Failed to load scholarships"
        );
      } finally {
        setIsLoadingScholarships(false);
      }
    };
    void fetchScholarships();
  }, [isZh]);

  useEffect(() => {
    if (!selectedScholarship) {
      setPeriods([]);
      setSelectedPeriod("");
      return;
    }
    const fetchPeriods = async () => {
      setIsLoadingPeriods(true);
      try {
        const response = await apiClient.referenceData.getScholarshipPeriods({
          scholarship_code: selectedScholarship.code,
        });
        if (response.success && response.data) {
          setPeriods(response.data.periods);
          const current = response.data.periods.find(p => p.is_current);
          setSelectedPeriod(current ? current.value : "");
        }
      } catch (error) {
        logger.error("Failed to fetch periods", { error });
        setLastError(
          isZh ? "無法載入學年學期選項" : "Failed to load period options"
        );
      } finally {
        setIsLoadingPeriods(false);
      }
    };
    void fetchPeriods();
  }, [selectedScholarship, isZh]);

  const period = periods.find(p => p.value === selectedPeriod) ?? null;

  useEffect(() => {
    if (!selectedScholarship || !period) {
      setAvailability(null);
      return;
    }
    let cancelled = false;
    const checkAvailability = async () => {
      // Drop the previous period's verdict before asking about this one, so the
      // drop zone can never stay enabled on a stale "open" answer.
      setAvailability(null);
      setIsCheckingAvailability(true);
      try {
        const response =
          await apiClient.college.getSupplementaryImportAvailability(
            selectedScholarship.code,
            period.academic_year,
            period.semester ?? "yearly"
          );
        if (cancelled) return;
        if (response.success && response.data) {
          setAvailability(response.data);
        } else {
          // A 200 that isn't a usable answer is still a failure to answer —
          // don't leave the drop zone disabled pointing at an absent message.
          setAvailability(null);
          setLastError(
            response.message ||
              (isZh
                ? "無法確認補充匯入開放狀態"
                : "Could not check supplementary import availability")
          );
        }
      } catch (error) {
        logger.error("Failed to check supplementary import availability", {
          error,
        });
        if (!cancelled) {
          setAvailability(null);
          // This request is the gate for the panel's only action — swallowing a
          // failure would leave a disabled drop zone with no explanation.
          setLastError(
            error instanceof Error
              ? error.message
              : isZh
                ? "無法確認補充匯入開放狀態"
                : "Could not check supplementary import availability"
          );
        }
      } finally {
        if (!cancelled) setIsCheckingAvailability(false);
      }
    };
    void checkAvailability();
    return () => {
      cancelled = true;
    };
    // `period` is derived from (periods, selectedPeriod); depending on those two
    // keeps the effect from re-firing on every render via a fresh object identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedScholarship, periods, selectedPeriod, isZh]);

  // Why the drop zone is disabled — never claim "pick a scholarship" once one
  // is picked, or the user has no idea what to do next.
  const dropZoneHint = !selectedScholarship || !period
    ? isZh
      ? "請先選擇獎學金與學年學期"
      : "Select a scholarship and period first"
    : isCheckingAvailability
      ? isZh
        ? "確認開放狀態中…"
        : "Checking availability…"
      : availability?.allowed === false
        ? isZh
          ? "此學年學期尚未開放補充匯入"
          : "Supplementary import is not open for this period"
        : isZh
          ? "無法確認開放狀態，請見下方錯誤訊息"
          : "Availability unknown — see the error below";

  const canUpload = Boolean(
    selectedScholarship && period && availability?.allowed && !uploading
  );

  const handleFile = useCallback(
    async (file: File) => {
      if (!canUpload || !selectedScholarship || !period) return;
      setLastError(null);
      setLastResult(null);

      if (!file.name.toLowerCase().endsWith(".xlsx")) {
        const msg = isZh ? "僅接受 .xlsx 檔案" : "Only .xlsx files are accepted";
        setLastError(msg);
        toast.error(msg);
        return;
      }
      if (file.size > MAX_BYTES) {
        const msg = isZh
          ? `檔案過大（${(file.size / 1024 / 1024).toFixed(1)} MB），上限 10 MB`
          : `File too large (${(file.size / 1024 / 1024).toFixed(1)} MB), limit is 10 MB`;
        setLastError(msg);
        toast.error(msg);
        return;
      }

      setUploading(true);
      try {
        const result = await apiClient.college.uploadSupplementaryImport(
          selectedScholarship.code,
          period.academic_year,
          period.semester ?? "yearly",
          file
        );
        if (result.success && result.data) {
          const unresolved = result.data.unresolved_professors ?? [];
          setLastResult({
            imported: result.data.imported_count,
            unresolvedProfessors: unresolved,
          });
          toast.success(
            isZh
              ? `已匯入 ${result.data.imported_count} 位學生，名次將於排名階段決定`
              : `Imported ${result.data.imported_count} students; ranking is decided later`
          );
        }
      } catch (err) {
        const detail =
          err instanceof Error ? err.message : isZh ? "匯入失敗" : "Import failed";
        setLastError(detail);
        // Toast preview (first line only) — full detail rendered in the inline Alert
        const firstLine = detail.split("\n")[0].slice(0, 120);
        toast.error(firstLine, {
          description:
            detail.length > firstLine.length
              ? isZh
                ? "詳細原因見下方提示"
                : "See details below"
              : undefined,
          duration: 8000,
        });
      } finally {
        setUploading(false);
      }
    },
    [canUpload, selectedScholarship, period, isZh]
  );

  const handleDownloadTemplate = useCallback(async () => {
    if (!selectedScholarship || downloadingTemplate) return;
    setDownloadingTemplate(true);
    try {
      const { blob, filename } =
        await apiClient.college.downloadSupplementaryImportTemplate(
          selectedScholarship.code
        );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      const detail =
        err instanceof Error
          ? err.message
          : isZh
            ? "下載範本失敗"
            : "Failed to download template";
      setLastError(detail);
      toast.error(detail);
    } finally {
      setDownloadingTemplate(false);
    }
  }, [selectedScholarship, downloadingTemplate, isZh]);

  return (
    <Card className="overflow-hidden border-emerald-200/70">
      <CardHeader className="border-b border-emerald-100 bg-gradient-to-br from-emerald-50/60 via-background to-background">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-emerald-100 p-2 text-emerald-700 ring-1 ring-emerald-200">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="space-y-1">
            <CardTitle className="text-base">
              {isZh ? "補充匯入" : "Supplementary Import"}
            </CardTitle>
            <CardDescription>
              {isZh
                ? "上傳新申請學生 Excel（格式與管理員的批次匯入相同）。匯入的學生會以一般申請身分進入審查與排名流程，名次由學院於排名階段決定。"
                : "Upload an Excel of new applying students (same format as the admin batch import). They enter the normal review and ranking flow as ordinary applicants."}
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4 md:p-5">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-1.5">
            <label
              htmlFor={`${inputId}-scholarship`}
              className="text-sm font-medium"
            >
              {isZh ? "獎學金類型" : "Scholarship Type"}
            </label>
            <select
              id={`${inputId}-scholarship`}
              value={selectedScholarship?.id ?? ""}
              disabled={isLoadingScholarships || uploading}
              onChange={e => {
                const found = scholarships.find(
                  s => String(s.id) === e.target.value
                );
                setSelectedScholarship(found ?? null);
                setLastError(null);
                setLastResult(null);
              }}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="">
                {isZh ? "請選擇獎學金" : "Select Scholarship"}
              </option>
              {scholarships.map(s => (
                <option key={s.id} value={s.id}>
                  {isZh ? s.name : s.name_en || s.name}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <label htmlFor={`${inputId}-period`} className="text-sm font-medium">
              {isZh ? "學年學期" : "Academic Period"}
            </label>
            <select
              id={`${inputId}-period`}
              value={selectedPeriod}
              disabled={!selectedScholarship || isLoadingPeriods || uploading}
              onChange={e => {
                setSelectedPeriod(e.target.value);
                setLastError(null);
                setLastResult(null);
              }}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="">{isZh ? "請選擇" : "Select"}</option>
              {periods.map(p => (
                <option key={p.value} value={p.value}>
                  {isZh ? p.label : p.label_en || p.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {scholarships.length === 0 && !isLoadingScholarships && (
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              {isZh
                ? "尚未被指派任何獎學金，請聯絡管理員設定權限。"
                : "No scholarships assigned to your account. Contact an administrator."}
            </AlertDescription>
          </Alert>
        )}

        {/* Template download is deliberately NOT gated on availability — the
            college can prepare the sheet before admin opens the period. */}
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-dashed border-muted-foreground/30 p-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!selectedScholarship || downloadingTemplate}
            onClick={() => void handleDownloadTemplate()}
          >
            {downloadingTemplate ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {isZh ? "下載範本" : "Download template"}
          </Button>
          <p className="text-xs text-muted-foreground">
            {isZh
              ? "申請類別欄填 1 表示有申請該獎學金。"
              : "A 1 in a category column means the student applied for that scholarship."}
          </p>
        </div>

        {selectedScholarship && period && !isCheckingAvailability && (
          <>
            {availability?.allowed === false && (
              <Alert className="border-amber-300 bg-amber-50/80">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle className="text-sm font-semibold">
                  {isZh ? "尚未開放" : "Not open"}
                </AlertTitle>
                <AlertDescription className="text-xs">
                  {isZh
                    ? "此學年學期尚未開放補充匯入，請聯絡管理員於獎學金配置中開啟。"
                    : "Supplementary import is not open for this period. Ask an administrator to enable it."}
                </AlertDescription>
              </Alert>
            )}
          </>
        )}

        <label
          htmlFor={`${inputId}-file`}
          onDragOver={e => {
            e.preventDefault();
            if (canUpload) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) void handleFile(file);
          }}
          className={[
            "group relative flex items-center gap-3 rounded-lg border-2 border-dashed px-4 py-6 text-sm transition-all",
            !canUpload
              ? "cursor-not-allowed border-muted bg-muted/30 opacity-60"
              : uploading
                ? "cursor-wait border-emerald-300 bg-emerald-50/70"
                : dragging
                  ? "border-emerald-500 bg-emerald-50 ring-4 ring-emerald-100"
                  : "cursor-pointer border-emerald-300 bg-white/60 hover:border-emerald-500 hover:bg-emerald-50/80",
          ].join(" ")}
          aria-disabled={!canUpload}
        >
          <input
            id={`${inputId}-file`}
            type="file"
            accept={ACCEPT}
            disabled={!canUpload}
            className="sr-only"
            onChange={async e => {
              const file = e.target.files?.[0];
              if (file) await handleFile(file);
              e.target.value = "";
            }}
          />
          {uploading ? (
            <>
              <Loader2 className="h-5 w-5 shrink-0 animate-spin text-emerald-600" />
              <div className="leading-tight">
                <div className="font-medium text-emerald-800">
                  {isZh ? "上傳中…" : "Uploading…"}
                </div>
                <div className="text-[11px] text-emerald-700/70">
                  {isZh ? "正在解析並比對學籍資料" : "Parsing and matching SIS data"}
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="relative shrink-0">
                <FileSpreadsheet className="h-5 w-5 text-emerald-700" />
                <Upload className="absolute -bottom-1 -right-1 h-3 w-3 rounded-full bg-white p-0.5 text-emerald-600 ring-1 ring-emerald-200" />
              </div>
              <div className="leading-tight">
                <div className="font-medium text-foreground group-hover:text-emerald-800">
                  {canUpload
                    ? isZh
                      ? "點擊或拖曳 Excel"
                      : "Click or drag an Excel file"
                    : dropZoneHint}
                </div>
                <div className="text-[11px] text-muted-foreground">
                  {isZh
                    ? "僅接受 .xlsx · 上限 10 MB"
                    : ".xlsx only · 10 MB limit"}
                </div>
              </div>
            </>
          )}
        </label>

        {lastResult && (
          <Alert className="border-emerald-300 bg-emerald-50/80">
            <AlertTitle className="text-sm font-semibold text-emerald-900">
              {isZh
                ? `已匯入 ${lastResult.imported} 位學生`
                : `Imported ${lastResult.imported} students`}
            </AlertTitle>
            <AlertDescription className="mt-1 text-xs leading-relaxed text-emerald-900/90">
              {isZh
                ? "學生已建立申請，名次將於學院排名階段一併決定。"
                : "Applications created. Ranking is decided in the college ranking step."}
              {lastResult.unresolvedProfessors.length > 0 && (
                <div className="mt-2 text-amber-800">
                  {isZh
                    ? `以下學號未能對應到指導教授帳號，將不會出現在教授待審清單：${lastResult.unresolvedProfessors.join("、")}`
                    : `No advisor account matched for: ${lastResult.unresolvedProfessors.join(", ")}`}
                </div>
              )}
            </AlertDescription>
          </Alert>
        )}

        {lastError && (
          <Alert variant="destructive" className="border-red-300 bg-red-50/80">
            <AlertCircle className="h-4 w-4" />
            <button
              type="button"
              aria-label={isZh ? "關閉錯誤提示" : "Dismiss error"}
              onClick={() => setLastError(null)}
              className="absolute right-3 top-3 rounded p-0.5 text-red-500/70 hover:bg-red-100 hover:text-red-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
            <AlertTitle className="pr-6 text-sm font-semibold">
              {isZh ? "匯入失敗" : "Import failed"}
            </AlertTitle>
            <AlertDescription className="mt-1 whitespace-pre-line text-xs leading-relaxed text-red-900/90">
              {lastError}
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}
