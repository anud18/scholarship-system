"use client";

import { useState } from "react";
import { BarChart3, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { triggerBlobDownload } from "@/lib/utils/download";

interface RosterCollegeAwardStatsButtonProps {
  rosterId: number;
  size?: "sm" | "default";
}

/**
 * 下載該份造冊的「統計各學院學生獲獎人數」— counts the students included in
 * this roster, per college × funding agency.
 */
export function RosterCollegeAwardStatsButton({
  rosterId,
  size = "sm",
}: RosterCollegeAwardStatsButtonProps) {
  const [isExporting, setIsExporting] = useState(false);

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const result =
        await apiClient.paymentRosters.exportCollegeAwardStats(rosterId);
      triggerBlobDownload(result);
    } catch (err) {
      toast.error(`匯出失敗：${(err as Error).message}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Button
      size={size}
      variant="outline"
      onClick={handleExport}
      disabled={isExporting}
      title="下載此造冊的統計各學院學生獲獎人數"
    >
      {isExporting ? (
        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
      ) : (
        <BarChart3 className="mr-1 h-4 w-4" />
      )}
      獲獎人數統計
    </Button>
  );
}
