"use client";

/**
 * 挑戰申請卡 (Challenge Application Card)
 *
 * 顯示給「已有核可續領申請」的學生 — 允許其挑戰其他 sub_type 以爭取
 * 更高名額；中籤後系統自動釋出其原有保底名額（將原續領申請標記為
 * cancelled_by_challenge）。
 *
 * 資料來源：POST /api/v1/renewals/challenge
 *
 * Props 由父層 (EnhancedStudentPortal) 依當前學生的核可續領申請與所屬
 * scholarshipType 的可用 sub_types 提供。
 *
 * 設計參考：docs/superpowers/plans/2026-05-13-renewal-application.md §9.2
 */

import { useCallback, useMemo, useState } from "react";
import { ChevronRight, Loader2, Swords } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { apiClient } from "@/lib/api";

interface ChallengeApplicationCardProps {
  /** 已核可續領申請的 ID（父層自學生申請清單篩出 is_renewal && approved 取得） */
  approvedRenewalId: number;
  /** 該續領申請的 sub_type — 將從可挑戰選單中排除 */
  approvedRenewalSubType: string;
  /** 獎學金類型 ID（呼叫 createChallenge 不直接用到，但保留供未來追蹤） */
  scholarshipTypeId: number;
  /** 可顯示的獎學金名稱（標題用） */
  scholarshipTypeName?: string;
  /**
   * 可挑戰之 sub_type 清單 — 父層依 scholarshipConfiguration.quotas 鍵清單
   * 過濾掉 approvedRenewalSubType 後傳入。空陣列時整張卡片不渲染。
   */
  availableSubTypes: string[];
  /** 建立成功後通知父層切換至編輯該新建挑戰申請的頁面 */
  onStartEditing?: (applicationId: number) => void;
}

/**
 * 將 sub_type 代碼轉為簡短中文顯示名稱。
 *   nstc          → "國科會"
 *   moe_1w/moe_2w → "教育部+1" / "教育部+2"
 *   其他          → 原值
 */
function getSubTypeShortName(subType: string): string {
  if (subType === "nstc") return "國科會";
  const moeMatch = subType.match(/^moe_(\d+)w$/);
  if (moeMatch) return `教育部+${moeMatch[1]}`;
  return subType;
}

export function ChallengeApplicationCard({
  approvedRenewalId,
  approvedRenewalSubType,
  scholarshipTypeName,
  availableSubTypes,
  onStartEditing,
}: ChallengeApplicationCardProps) {
  // 移除續領 sub_type，避免使用者自己挑戰自己
  const eligibleSubTypes = useMemo(
    () => availableSubTypes.filter(st => st && st !== approvedRenewalSubType),
    [availableSubTypes, approvedRenewalSubType]
  );

  const [targetSubType, setTargetSubType] = useState<string>(
    eligibleSubTypes[0] ?? ""
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = useCallback(async () => {
    if (!targetSubType) {
      setErrorMessage("請選擇要挑戰的 sub_type");
      return;
    }
    setIsSubmitting(true);
    setErrorMessage(null);
    try {
      const response = await apiClient.renewal.createChallenge(
        approvedRenewalId,
        targetSubType
      );
      if (response.success && response.data) {
        onStartEditing?.(response.data.id);
      } else {
        setErrorMessage(response.message || "建立挑戰申請失敗");
      }
    } catch (err) {
      console.error("Failed to create challenge:", err);
      setErrorMessage(
        err instanceof Error ? err.message : "建立挑戰申請失敗"
      );
    } finally {
      setIsSubmitting(false);
    }
  }, [approvedRenewalId, onStartEditing, targetSubType]);

  // 沒有任何可挑戰 sub_type — 整張卡片不顯示
  if (eligibleSubTypes.length === 0) return null;

  return (
    <Card className="border-l-4 border-l-amber-500 bg-amber-50/40">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Swords className="h-5 w-5 text-amber-600" />
          <CardTitle className="text-base text-amber-900">
            挑戰其他 sub_type
            {scholarshipTypeName && (
              <span className="ml-2 text-sm font-normal text-amber-800/80">
                — {scholarshipTypeName}
              </span>
            )}
          </CardTitle>
        </div>
        <CardDescription className="text-amber-900/80">
          您已續領{" "}
          <Badge
            variant="outline"
            className="border-amber-300 bg-amber-100 text-amber-900"
          >
            {getSubTypeShortName(approvedRenewalSubType)}
          </Badge>
          （保底）。可挑戰其他 sub_type；中籤則自動釋出保底名額。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {errorMessage && (
          <Alert variant="destructive">
            <AlertDescription>{errorMessage}</AlertDescription>
          </Alert>
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="flex-1">
            <Select
              value={targetSubType}
              onValueChange={setTargetSubType}
              disabled={isSubmitting}
            >
              <SelectTrigger className="bg-white">
                <SelectValue placeholder="選擇要挑戰的 sub_type" />
              </SelectTrigger>
              <SelectContent>
                {eligibleSubTypes.map(st => (
                  <SelectItem key={st} value={st}>
                    {getSubTypeShortName(st)}
                    <span className="ml-1 text-xs text-gray-500">({st})</span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button
            onClick={handleSubmit}
            disabled={isSubmitting || !targetSubType}
            className="bg-amber-600 hover:bg-amber-700"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                建立中...
              </>
            ) : (
              <>
                提交挑戰申請
                <ChevronRight className="ml-1 h-4 w-4" />
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
