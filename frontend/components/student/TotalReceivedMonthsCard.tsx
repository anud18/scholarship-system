"use client";

import { useEffect, useState } from "react";
import { CalendarClock } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { apiClient } from "@/lib/api";
import { useStudentHistoryVisibility } from "@/hooks/use-student-history-visibility";
import { logger } from "@/lib/utils/logger";

interface TotalReceivedMonthsCardProps {
  locale?: "zh" | "en";
}

/**
 * Student self-service view of their 已領獎學金總月數 (匯入 + 系統, all
 * scholarship types combined). Students see the months total only — never
 * amounts or per-roster payment details. Renders nothing while loading or
 * when the lookup fails, so it can't block the surrounding page.
 *
 * The whole card is admin-gated: when 開放學生查詢 is off the months request is
 * never made (the endpoint would 403 anyway) and nothing renders.
 */
export function TotalReceivedMonthsCard({ locale = "zh" }: TotalReceivedMonthsCardProps) {
  const [totalMonths, setTotalMonths] = useState<number | null>(null);
  const { visibility } = useStudentHistoryVisibility();
  const isEnabled = visibility.student_enabled;

  useEffect(() => {
    if (!isEnabled) {
      // Drop a previously fetched total if the admin closes the feature.
      setTotalMonths(null);
      return;
    }

    let cancelled = false;
    apiClient.studentHistory
      .getMyMonths()
      .then((response) => {
        if (cancelled) return;
        if (response.success && response.data) {
          setTotalMonths(response.data.total_received_months);
        } else {
          logger.error("Failed to fetch my received months", {
            message: response.message,
          });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          logger.error("Failed to fetch my received months", { error });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [isEnabled]);

  if (!isEnabled || totalMonths === null) return null;

  return (
    <Card data-testid="total-received-months-card">
      <CardContent className="flex items-center gap-4 py-4">
        <div className="rounded-full bg-nycu-blue-50 p-3">
          <CalendarClock className="h-6 w-6 text-nycu-blue-600" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">
            {locale === "zh" ? "已領獎學金總月數" : "Total Scholarship Months Received"}
          </p>
          <p className="text-2xl font-bold">
            {totalMonths}
            <span className="ml-1 text-base font-normal text-muted-foreground">
              {locale === "zh" ? "個月" : "months"}
            </span>
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
