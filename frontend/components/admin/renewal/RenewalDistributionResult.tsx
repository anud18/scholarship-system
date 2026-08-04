"use client";

/**
 * 續領分發結果顯示元件 (Admin)
 *
 * 取得指定 (獎學金類型, 學年度) 下的續領分發結果，依
 * (sub_type, renewal_year) 分組呈現。資料來源：
 *   GET /api/v1/renewals/distribution-result
 *
 * 設計參考：docs/superpowers/plans/2026-05-13-renewal-application.md §14.1
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient } from "@/lib/api";
import type {
  RenewalDistributionResult,
  RenewalDistributionGroup,
} from "@/lib/api/modules/renewal";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Trophy,
  XCircle,
} from "lucide-react";

interface RenewalDistributionResultProps {
  /** 獎學金類型 ID（必填，未指定時顯示空狀態提示） */
  scholarshipTypeId: number | null;
  /** 學年度（必填，未指定時顯示空狀態提示） */
  academicYear: number | null;
  /** 顯示名稱：獎學金類型（供標題使用） */
  scholarshipTypeName?: string;
}

/**
 * 將 sub_type 代碼轉為簡短中文顯示名稱。
 *   nstc          → "國科會"
 *   moe_1w/moe_2w → "教育部"
 *   其他          → 原值
 */
function getSubTypeShortName(subType: string | null): string {
  if (!subType) return "未分類";
  if (subType === "nstc") return "國科會";
  if (/^moe_\d+w$/.test(subType)) return "教育部";
  return subType;
}

/**
 * 將分組依 (sub_type, renewal_year) 穩定排序：
 *   - sub_type 字典序
 *   - renewal_year 由小至大（補發年度先，當年度後）
 */
function sortGroups(
  groups: RenewalDistributionGroup[]
): RenewalDistributionGroup[] {
  return [...groups].sort((a, b) => {
    const subA = a.sub_type ?? "";
    const subB = b.sub_type ?? "";
    if (subA !== subB) return subA.localeCompare(subB);
    const yearA = a.renewal_year ?? 0;
    const yearB = b.renewal_year ?? 0;
    return yearA - yearB;
  });
}

export function RenewalDistributionResult({
  scholarshipTypeId,
  academicYear,
  scholarshipTypeName,
}: RenewalDistributionResultProps) {
  const [result, setResult] = useState<RenewalDistributionResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchResult = useCallback(async () => {
    if (scholarshipTypeId == null || academicYear == null) {
      setResult(null);
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await apiClient.renewal.getDistributionResult(
        scholarshipTypeId,
        academicYear
      );
      if (response.success && response.data) {
        setResult(response.data);
      } else {
        setErrorMessage(response.message || "載入續領分發結果失敗");
        setResult(null);
      }
    } catch (err) {
      const detail = err instanceof Error ? err.message : "未知錯誤";
      setErrorMessage(`網路錯誤：${detail}`);
      setResult(null);
    } finally {
      setIsLoading(false);
    }
  }, [scholarshipTypeId, academicYear]);

  useEffect(() => {
    fetchResult();
  }, [fetchResult]);

  // ---------- 空狀態：未選擇條件 ----------
  if (scholarshipTypeId == null || academicYear == null) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          請於上方選擇獎學金類型與學年度以查看續領分發結果。
        </CardContent>
      </Card>
    );
  }

  // ---------- 載入中 ----------
  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          載入續領分發結果中…
        </CardContent>
      </Card>
    );
  }

  // ---------- 錯誤 ----------
  if (errorMessage) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription className="flex items-center justify-between gap-3">
          <span>{errorMessage}</span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={fetchResult}
            className="shrink-0"
          >
            <RefreshCw className="mr-1 h-3 w-3" />
            重新載入
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!result) {
    return null;
  }

  const sortedGroups = sortGroups(result.groups);
  const headerSubtitle = scholarshipTypeName
    ? `${scholarshipTypeName} · ${academicYear} 學年`
    : `學年 ${academicYear}`;

  return (
    <div className="space-y-6">
      {/* 標題與總結 */}
      <Card className="border-[#003d7a]/20">
        <CardHeader className="border-b border-[#003d7a]/10 bg-[#003d7a]/5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="text-[#003d7a]">
                續領分發結果
              </CardTitle>
              <p className="mt-1 text-sm text-muted-foreground">
                {headerSubtitle}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={fetchResult}
            >
              <RefreshCw className="mr-1 h-3 w-3" />
              重新載入
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <SummaryStat
              label="通過 (approved)"
              value={result.summary.approved}
              tone="success"
            />
            <SummaryStat
              label="拒絕 (rejected)"
              value={result.summary.rejected}
              tone="danger"
            />
            <SummaryStat
              label="分組數"
              value={sortedGroups.length}
              tone="info"
            />
          </div>
        </CardContent>
      </Card>

      {/* 通過名單分組 */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2 text-base">
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
            續領通過名單（依 sub_type × renewal_year 分組）
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {sortedGroups.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              （目前無已核可的續領申請）
            </p>
          ) : (
            <div className="space-y-5">
              {sortedGroups.map(group => (
                <GroupBlock
                  key={`${group.sub_type ?? "none"}-${group.renewal_year ?? "n"}`}
                  group={group}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* 拒絕名單 */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="flex items-center gap-2 text-base">
            <XCircle className="h-4 w-4 text-rose-600" />
            續領被拒名單
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {result.rejected.length === 0 ? (
            <p className="text-sm text-muted-foreground">（無拒絕紀錄）</p>
          ) : (
            <ul className="divide-y rounded-md border">
              {result.rejected.map(item => (
                <li
                  key={item.id}
                  className="flex items-center justify-between px-4 py-2 text-sm"
                >
                  <span>{item.student_name ?? "（未知學生）"}</span>
                  <span className="text-xs text-muted-foreground">
                    App #{item.id}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 子元件
// ---------------------------------------------------------------------------

interface SummaryStatProps {
  label: string;
  value: number;
  tone: "success" | "danger" | "info";
}

function SummaryStat({ label, value, tone }: SummaryStatProps) {
  const toneClasses: Record<SummaryStatProps["tone"], string> = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    danger: "border-rose-200 bg-rose-50 text-rose-700",
    info: "border-[#003d7a]/20 bg-[#003d7a]/5 text-[#003d7a]",
  };
  return (
    <div className={`rounded-md border px-4 py-3 ${toneClasses[tone]}`}>
      <p className="text-xs font-medium uppercase tracking-wide">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </div>
  );
}

interface GroupBlockProps {
  group: RenewalDistributionGroup;
}

function GroupBlock({ group }: GroupBlockProps) {
  const shortName = getSubTypeShortName(group.sub_type);
  const yearLabel =
    group.renewal_year != null ? `計畫年度 ${group.renewal_year}` : "（無年度）";
  const count = group.applications.length;

  return (
    <div className="overflow-hidden rounded-md border">
      <div className="flex items-center justify-between border-b bg-muted/40 px-4 py-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Badge
            variant="outline"
            className="border-[#003d7a]/30 bg-white text-[#003d7a]"
          >
            {shortName}
          </Badge>
          <span className="text-muted-foreground">·</span>
          <span>{yearLabel}</span>
        </div>
        <span className="text-xs text-muted-foreground">
          共 {count} 人
        </span>
      </div>
      {count === 0 ? (
        <p className="px-4 py-3 text-sm text-muted-foreground">
          （此分組目前無人）
        </p>
      ) : (
        <ul className="divide-y">
          {group.applications.map(app => (
            <li
              key={app.id}
              className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium">
                  {app.student_name ?? "（未知學生）"}
                </span>
                <span className="text-xs text-muted-foreground">
                  {app.app_id}
                </span>
                {app.previous_application_id != null && (
                  <span className="text-xs text-muted-foreground">
                    原 App #{app.previous_application_id}
                  </span>
                )}
              </div>
              {app.has_challenge && (
                <Badge
                  variant="outline"
                  className="border-amber-300 bg-amber-50 text-amber-700"
                >
                  <Trophy className="mr-1 h-3 w-3" />
                  同時提交挑戰
                </Badge>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
