"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiClient } from "@/lib/api";
import type {
  CollegeRankingOverview,
  CollegeRankingOverviewRanking,
  CollegeRankingStatus,
} from "@/lib/api/modules/admin";
import { triggerBlobDownload } from "@/lib/utils/download";
import { logger } from "@/lib/utils/logger";

interface PeriodOption {
  key: string;
  label: string;
  scholarshipCode: string;
  academicYear: number;
  semester?: string;
}

interface ConfigurationRow {
  scholarship_type_code?: string | null;
  scholarship_type_name?: string | null;
  academic_year?: number | null;
  semester?: string | null;
}

type ExportFormat = "xlsx" | "pdf";

const SEMESTER_LABELS: Record<string, string> = {
  first: "第一學期",
  second: "第二學期",
};

const STATUS_META: Record<CollegeRankingStatus, { label: string; className: string }> = {
  not_created: { label: "尚未建立排名", className: "bg-red-100 text-red-800 border-red-200" },
  draft: { label: "草稿（未匯入）", className: "bg-slate-100 text-slate-700 border-slate-200" },
  draft_imported: { label: "草稿已匯入", className: "bg-amber-100 text-amber-800 border-amber-200" },
  finalized: { label: "已確認", className: "bg-green-100 text-green-800 border-green-200" },
};

const STATUS_ORDER: CollegeRankingStatus[] = ["not_created", "draft", "draft_imported", "finalized"];

/** One option per scholarship period; several configurations may share a period. */
export function buildPeriodOptions(configurations: ConfigurationRow[]): PeriodOption[] {
  const options = new Map<string, PeriodOption>();
  for (const config of configurations) {
    if (!config.scholarship_type_code || !config.academic_year) continue;
    const semester =
      config.semester && config.semester !== "yearly" ? config.semester : undefined;
    const key = `${config.scholarship_type_code}|${config.academic_year}|${semester ?? "yearly"}`;
    if (options.has(key)) continue;
    const semesterLabel = semester ? ` ${SEMESTER_LABELS[semester] ?? semester}` : "";
    options.set(key, {
      key,
      label: `${config.academic_year} 學年度${semesterLabel}｜${config.scholarship_type_name ?? config.scholarship_type_code}`,
      scholarshipCode: config.scholarship_type_code,
      academicYear: config.academic_year,
      semester,
    });
  }
  return [...options.values()];
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-TW", { hour12: false });
}

function StatusBadge({ status }: { status: CollegeRankingStatus }) {
  const meta = STATUS_META[status];
  return (
    <Badge variant="outline" className={meta.className}>
      {meta.label}
    </Badge>
  );
}

function RankingRow({
  ranking,
  exportingKey,
  onExport,
}: {
  ranking: CollegeRankingOverviewRanking;
  exportingKey: string | null;
  onExport: (rankingId: number, format: ExportFormat) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 py-1">
      <span className="font-medium">{ranking.ranking_name || `排名 #${ranking.id}`}</span>
      <Badge variant="outline" className={ranking.is_finalized ? STATUS_META.finalized.className : ""}>
        {ranking.is_finalized ? "已確認" : "草稿"}
      </Badge>
      <span className="text-xs text-muted-foreground">
        {ranking.total_applications} 人
        {ranking.is_finalized && ranking.finalized_at
          ? `｜${formatDateTime(ranking.finalized_at)} ${ranking.finalized_by ?? ""} 確認`
          : ""}
        {ranking.last_import_at
          ? `｜${formatDateTime(ranking.last_import_at)} ${ranking.last_import_by ?? ""} 匯入`
          : ""}
      </span>
      {(["xlsx", "pdf"] as const).map(format => {
        const key = `${ranking.id}:${format}`;
        return (
          <Button
            key={format}
            size="sm"
            variant="outline"
            disabled={exportingKey !== null}
            onClick={() => onExport(ranking.id, format)}
            aria-label={`匯出 ${ranking.ranking_name || `排名 #${ranking.id}`} ${format === "xlsx" ? "Excel" : "PDF"}`}
          >
            {exportingKey === key ? (
              <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            ) : (
              <Download className="h-3 w-3 mr-1" />
            )}
            {format === "xlsx" ? "Excel" : "PDF"}
          </Button>
        );
      })}
    </div>
  );
}

/**
 * 系統管理「學院排名繳交」— which colleges have handed in their ranking for a
 * scholarship period, with each ranking downloadable as the 學生資料彙整表.
 */
export function CollegeRankingOverviewPanel() {
  const [periods, setPeriods] = useState<PeriodOption[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [overview, setOverview] = useState<CollegeRankingOverview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportingKey, setExportingKey] = useState<string | null>(null);
  // Drops the response of a period the admin has already switched away from.
  const latestRequestRef = useRef(0);

  const selectedPeriod = periods.find(period => period.key === selectedKey);

  useEffect(() => {
    let isCancelled = false;
    const loadPeriods = async () => {
      try {
        const response = await apiClient.admin.getScholarshipConfigurations();
        if (isCancelled) return;
        if (!response.success || !response.data) {
          setError(response.message || "載入獎學金期別失敗");
          return;
        }
        const options = buildPeriodOptions(response.data as ConfigurationRow[]);
        setPeriods(options);
        setSelectedKey(current => current || options[0]?.key || "");
      } catch (err: unknown) {
        logger.error("載入獎學金期別失敗", { error: err });
        if (!isCancelled) setError("載入獎學金期別失敗");
      }
    };
    loadPeriods();
    return () => {
      isCancelled = true;
    };
  }, []);

  const loadOverview = useCallback(async (period: PeriodOption) => {
    const requestId = ++latestRequestRef.current;
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.admin.getCollegeRankingOverview({
        scholarshipCode: period.scholarshipCode,
        academicYear: period.academicYear,
        semester: period.semester,
      });
      if (requestId !== latestRequestRef.current) return;
      if (response.success && response.data) {
        setOverview(response.data);
      } else {
        setOverview(null);
        setError(response.message || "載入學院排名繳交狀態失敗");
      }
    } catch (err: unknown) {
      logger.error("載入學院排名繳交狀態失敗", { error: err });
      if (requestId !== latestRequestRef.current) return;
      setOverview(null);
      setError("網路錯誤或伺服器未回應");
    } finally {
      if (requestId === latestRequestRef.current) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedPeriod) loadOverview(selectedPeriod);
  }, [selectedPeriod, loadOverview]);

  const handleExport = async (rankingId: number, format: ExportFormat) => {
    setExportingKey(`${rankingId}:${format}`);
    try {
      triggerBlobDownload(await apiClient.college.exportRankingExcel(rankingId, format));
    } catch (err) {
      toast.error(`匯出失敗：${(err as Error).message}`);
    } finally {
      setExportingKey(null);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>學院排名繳交</CardTitle>
        <p className="text-sm text-muted-foreground">
          查看各學院是否已建立、匯入並確認學生排序名單，並可匯出各學院的排名（學生資料彙整表）。
          系統不保存學院上傳的原始 Excel 檔，匯出內容為系統內目前的排序。
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={selectedKey} onValueChange={setSelectedKey}>
            <SelectTrigger className="w-[360px]" aria-label="獎學金期別">
              <SelectValue placeholder="請選擇獎學金期別" />
            </SelectTrigger>
            <SelectContent>
              {periods.map(period => (
                <SelectItem key={period.key} value={period.key}>
                  {period.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            disabled={!selectedPeriod || isLoading}
            onClick={() => selectedPeriod && loadOverview(selectedPeriod)}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            重新整理
          </Button>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        {overview && (
          <>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span>共 {overview.summary.total} 個學院</span>
              {STATUS_ORDER.map(status => (
                <span key={status} className="flex items-center gap-1">
                  <StatusBadge status={status} />
                  {overview.summary[status]}
                </span>
              ))}
            </div>

            {overview.colleges.length === 0 ? (
              <p className="text-sm text-muted-foreground py-6 text-center">
                此期別尚無可排名的申請，也沒有任何學院建立排名。
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>學院</TableHead>
                    <TableHead className="text-right">可排名申請數</TableHead>
                    <TableHead>狀態</TableHead>
                    <TableHead>最後匯入 Excel</TableHead>
                    <TableHead>排名／匯出</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {overview.colleges.map(college => (
                    <TableRow key={college.college_code || "__global__"}>
                      <TableCell className="font-medium">
                        {college.college_name}
                        {college.college_code && (
                          <span className="ml-1 text-xs text-muted-foreground">
                            ({college.college_code})
                          </span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">{college.applicant_count}</TableCell>
                      <TableCell>
                        <StatusBadge status={college.status} />
                      </TableCell>
                      <TableCell>
                        {college.last_import_at ? (
                          <>
                            <div>{formatDateTime(college.last_import_at)}</div>
                            <div className="text-xs text-muted-foreground">
                              {college.last_import_by ?? "—"}
                            </div>
                          </>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell>
                        {college.rankings.length === 0
                          ? "—"
                          : college.rankings.map(ranking => (
                              <RankingRow
                                key={ranking.id}
                                ranking={ranking}
                                exportingKey={exportingKey}
                                onExport={handleExport}
                              />
                            ))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
