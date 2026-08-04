"use client";

/**
 * /admin/renewal — 續領分發結果管理頁
 *
 * 提供：
 *   1. 獎學金類型選擇器（資料源：GET /api/v1/manual-distribution/available-combinations）
 *   2. 學年度選擇器
 *   3. 續領分發結果顯示（RenewalDistributionResult 元件）
 *
 * 此頁面僅讀取，不修改後端狀態。
 */

import { useEffect, useMemo, useState } from "react";
import { apiClient } from "@/lib/api";
import type { AvailableCombinations } from "@/lib/api/modules/manual-distribution";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { AlertCircle, Loader2 } from "lucide-react";
import { RenewalDistributionResult } from "@/components/admin/renewal/RenewalDistributionResult";

interface ScholarshipTypeOption {
  id: number;
  code: string;
  name: string;
  name_en?: string;
}

export default function AdminRenewalPage() {
  const [scholarshipTypes, setScholarshipTypes] = useState<
    ScholarshipTypeOption[]
  >([]);
  const [academicYears, setAcademicYears] = useState<number[]>([]);
  const [selectedTypeId, setSelectedTypeId] = useState<number | null>(null);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [isLoadingOptions, setIsLoadingOptions] = useState(true);
  const [optionsError, setOptionsError] = useState<string | null>(null);

  // 初次載入：從 manual-distribution 端點取得可用獎學金類型與學年度。
  // （續領分發複用相同的後端設定，因此不需另開端點。）
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIsLoadingOptions(true);
      setOptionsError(null);
      try {
        const response =
          await apiClient.manualDistribution.getAvailableCombinations();
        if (cancelled) return;
        if (response.success && response.data) {
          const data = response.data as AvailableCombinations;
          setScholarshipTypes(data.scholarship_types ?? []);
          // 學年度由新到舊排序：方便預設選最新年度
          const years = [...(data.academic_years ?? [])].sort(
            (a, b) => b - a
          );
          setAcademicYears(years);
          // 預設選第一項（若有）
          if (
            data.scholarship_types &&
            data.scholarship_types.length > 0 &&
            selectedTypeId == null
          ) {
            setSelectedTypeId(data.scholarship_types[0].id);
          }
          if (years.length > 0 && selectedYear == null) {
            setSelectedYear(years[0]);
          }
        } else {
          setOptionsError(response.message || "無法載入獎學金類型清單");
        }
      } catch (err) {
        if (cancelled) return;
        const detail = err instanceof Error ? err.message : "未知錯誤";
        setOptionsError(`網路錯誤：${detail}`);
      } finally {
        if (!cancelled) setIsLoadingOptions(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // 僅在掛載時取資料；後續選擇變更不需重新請求 options。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedTypeName = useMemo(() => {
    const found = scholarshipTypes.find(t => t.id === selectedTypeId);
    return found?.name;
  }, [scholarshipTypes, selectedTypeId]);

  return (
    <div className="container mx-auto space-y-6 p-6">
      <header>
        <h1 className="text-2xl font-bold text-[#003d7a]">續領分發結果</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          管理員專用：檢視特定獎學金類型 / 學年度的續領分發結果，包含通過、拒絕與是否同時提交挑戰申請。
        </p>
      </header>

      {/* 篩選列 */}
      <Card>
        <CardHeader className="border-b">
          <CardTitle className="text-base">查詢條件</CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {optionsError ? (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{optionsError}</AlertDescription>
            </Alert>
          ) : isLoadingOptions ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              載入篩選選項中…
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">
                  獎學金類型
                </label>
                <Select
                  value={selectedTypeId != null ? String(selectedTypeId) : ""}
                  onValueChange={value => setSelectedTypeId(Number(value))}
                  disabled={scholarshipTypes.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="請選擇獎學金類型" />
                  </SelectTrigger>
                  <SelectContent>
                    {scholarshipTypes.map(type => (
                      <SelectItem key={type.id} value={String(type.id)}>
                        {type.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">
                  學年度
                </label>
                <Select
                  value={selectedYear != null ? String(selectedYear) : ""}
                  onValueChange={value => setSelectedYear(Number(value))}
                  disabled={academicYears.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="請選擇學年度" />
                  </SelectTrigger>
                  <SelectContent>
                    {academicYears.map(year => (
                      <SelectItem key={year} value={String(year)}>
                        {year} 學年
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* 結果顯示 */}
      <RenewalDistributionResult
        scholarshipTypeId={selectedTypeId}
        academicYear={selectedYear}
        scholarshipTypeName={selectedTypeName}
      />
    </div>
  );
}
