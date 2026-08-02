"use client";

import { useState } from "react";
import { Eye, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { apiClient } from "@/lib/api";
import { useStudentHistoryVisibility } from "@/hooks/use-student-history-visibility";
import type { StudentHistoryVisibilityUpdate } from "@/lib/api/modules/student-history";
import { logger } from "@/lib/utils/logger";

type Audience = "student" | "college";

const AUDIENCES: Array<{
  audience: Audience;
  field: keyof StudentHistoryVisibilityUpdate;
  label: string;
  description: string;
}> = [
  {
    audience: "student",
    field: "student_enabled",
    label: "開放學生查詢",
    description: "學生可在「我的申請」看到自己的已領獎學金總月數（不含金額與造冊明細）。",
  },
  {
    audience: "college",
    field: "college_enabled",
    label: "開放學院查詢",
    description: "學院可查詢本學院學生的領獎紀錄；查詢範圍仍由後端限制在該學院。",
  },
];

/**
 * Admin control for who 領獎紀錄查詢 is open to. The two audiences are decided
 * separately — each switch sends only its own field, so toggling one never
 * overwrites the other. Admin access itself is never gated by these switches.
 */
export function HistoryVisibilityCard() {
  const { visibility, isLoaded, error, mutate } = useStudentHistoryVisibility();
  const [pendingAudience, setPendingAudience] = useState<Audience | null>(null);

  const handleToggle = async (
    audience: Audience,
    field: keyof StudentHistoryVisibilityUpdate,
    checked: boolean,
  ) => {
    setPendingAudience(audience);
    try {
      const response = await apiClient.studentHistory.updateVisibility({
        [field]: checked,
      });
      if (response.success && response.data) {
        // Server response is authoritative — it carries BOTH switches back.
        await mutate(response.data, { revalidate: false });
        toast.success(checked ? "已開放查詢" : "已關閉查詢");
      } else {
        toast.error(response.message || "更新開放設定失敗");
        await mutate();
      }
    } catch (err) {
      logger.error("Failed to update student history visibility", { err });
      toast.error(err instanceof Error ? err.message : "更新開放設定失敗");
      // Refetch rather than assume nothing changed: the switches are written
      // one row at a time server-side, so a failure leaves the real state
      // uncertain.
      await mutate();
    } finally {
      setPendingAudience(null);
    }
  };

  return (
    <Card data-testid="history-visibility-card">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Eye className="h-5 w-5 text-muted-foreground" />
          查詢開放設定
        </CardTitle>
        <CardDescription>
          決定學生與學院是否能查詢領獎紀錄，兩者可分別開放；管理者不受此設定限制。
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <p className="text-sm text-destructive">
            無法載入開放設定，請重新整理頁面。
          </p>
        )}
        {AUDIENCES.map(({ audience, field, label, description }) => {
          const switchId = `student-history-visible-${audience}`;
          return (
            <div
              key={audience}
              className="flex items-start justify-between gap-4 rounded-md border p-3"
            >
              <div className="space-y-1">
                <Label htmlFor={switchId} className="text-sm font-medium">
                  {label}
                </Label>
                <p className="text-xs text-muted-foreground">{description}</p>
              </div>
              <div className="flex items-center gap-2 pt-1">
                {pendingAudience === audience && (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                )}
                <Switch
                  id={switchId}
                  checked={visibility[field]}
                  disabled={!isLoaded || pendingAudience !== null}
                  onCheckedChange={(checked) => handleToggle(audience, field, checked)}
                />
              </div>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
