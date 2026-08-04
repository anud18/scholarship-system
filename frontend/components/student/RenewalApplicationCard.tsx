"use client";

/**
 * 續領申請卡 (Renewal Application Card)
 *
 * 顯示給學生 — 列出當前可續領的獎學金紀錄（學生上一年度核可的申請，
 * 對應獎學金類型在當前學年度的續領申請窗口為開啟狀態）。
 *
 * 資料來源：GET /api/v1/renewals/eligible
 * 建立續領：POST /api/v1/renewals/
 *
 * 設計參考：docs/superpowers/plans/2026-05-13-renewal-application.md §9.1
 *
 * 注意：
 *   - 無可續領紀錄時整張卡片不渲染（return null）。
 *   - 建立成功後切回「我的申請」列表並啟動編輯模式 — 由父層 onStartEditing 處理導頁。
 */

import { useCallback, useEffect, useState } from "react";
import { Award, ChevronRight, Loader2 } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { apiClient } from "@/lib/api";
import type { EligibleRenewal } from "@/lib/api/modules/renewal";

interface RenewalApplicationCardProps {
  /**
   * 建立成功後通知父層切換至編輯該新建續領申請的頁面（即「新申請」分頁）。
   * 對應 EnhancedStudentPortal 的 onStartEditing prop。
   */
  onStartEditing?: (applicationId: number) => void;
  /** 顯示語系（目前僅實作 zh-TW，保留英文鉤子） */
  locale?: "zh" | "en";
}

export function RenewalApplicationCard({
  onStartEditing,
}: RenewalApplicationCardProps) {
  const [eligible, setEligible] = useState<EligibleRenewal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [creatingId, setCreatingId] = useState<number | null>(null);

  const fetchEligible = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const response = await apiClient.renewal.listEligible();
      if (response.success && Array.isArray(response.data)) {
        setEligible(response.data);
      } else {
        setEligible([]);
        if (!response.success) {
          setErrorMessage(response.message || "無法載入可續領清單");
        }
      }
    } catch (err) {
      console.error("Failed to load eligible renewals:", err);
      setEligible([]);
      setErrorMessage(
        err instanceof Error ? err.message : "載入可續領清單時發生錯誤"
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEligible();
  }, [fetchEligible]);

  const handleCreate = useCallback(
    async (item: EligibleRenewal) => {
      setCreatingId(item.previous_application_id);
      try {
        const response = await apiClient.renewal.createRenewal(
          item.previous_application_id
        );
        if (response.success && response.data) {
          // 移除這一筆，避免再次建立
          setEligible(prev =>
            prev.filter(
              x => x.previous_application_id !== item.previous_application_id
            )
          );
          onStartEditing?.(response.data.id);
        } else {
          alert(response.message || "建立續領申請失敗");
        }
      } catch (err) {
        console.error("Failed to create renewal:", err);
        alert(err instanceof Error ? err.message : "建立續領申請失敗");
      } finally {
        setCreatingId(null);
      }
    },
    [onStartEditing]
  );

  // 載入中、錯誤、空清單 — 整張卡片不顯示，避免污染學生主畫面
  if (isLoading) return null;
  if (errorMessage) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{errorMessage}</AlertDescription>
      </Alert>
    );
  }
  if (eligible.length === 0) return null;

  return (
    <Card className="border-l-4 border-l-emerald-500 bg-emerald-50/40">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Award className="h-5 w-5 text-emerald-600" />
          <CardTitle className="text-base text-emerald-900">
            可續領的獎學金
          </CardTitle>
        </div>
        <CardDescription className="text-emerald-800/80">
          以下為您上學年度通過的獎學金，目前處於續領申請期間，
          建立後將自動帶入原核可之 sub_type 與基本資料。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {eligible.map(item => (
          <div
            key={item.previous_application_id}
            className="flex flex-col gap-3 rounded-lg border border-emerald-100 bg-white p-3 md:flex-row md:items-center md:justify-between"
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2 font-medium text-gray-900">
                {item.scholarship_type_name || "未知獎學金"}
                {item.sub_scholarship_type && (
                  <Badge
                    variant="outline"
                    className="border-emerald-200 bg-emerald-50 text-emerald-700"
                  >
                    上期 sub_type：{item.sub_scholarship_type}
                  </Badge>
                )}
              </div>
              <div className="text-sm text-gray-600">
                目標學年：{item.target_academic_year} 學年度
                {item.renewal_year &&
                  item.renewal_year !== item.target_academic_year && (
                    <span className="ml-2 text-amber-600">
                      （補發年度：{item.renewal_year}）
                    </span>
                  )}
              </div>
              {item.renewal_deadline && (
                <div className="text-xs text-gray-500">
                  申請截止：
                  {new Date(item.renewal_deadline).toLocaleString("zh-TW", {
                    year: "numeric",
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
              )}
            </div>
            <Button
              onClick={() => handleCreate(item)}
              disabled={creatingId === item.previous_application_id}
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {creatingId === item.previous_application_id ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  建立中...
                </>
              ) : (
                <>
                  建立續領申請
                  <ChevronRight className="ml-1 h-4 w-4" />
                </>
              )}
            </Button>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
