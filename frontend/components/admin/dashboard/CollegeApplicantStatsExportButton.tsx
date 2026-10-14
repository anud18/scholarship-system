"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { triggerBlobDownload } from "@/lib/utils/download";

interface CollegeApplicantStatsExportButtonProps {
  scholarshipCode: string;
  academicYear?: number;
  semester?: string;
}

/**
 * 審核管理「匯出學院申請人數」— downloads 統計各學院學生申請人數 for the
 * scholarship tab and 學年 currently selected on the page.
 */
export function CollegeApplicantStatsExportButton({
  scholarshipCode,
  academicYear,
  semester,
}: CollegeApplicantStatsExportButtonProps) {
  const [isExporting, setIsExporting] = useState(false);
  const isDisabled = isExporting || !scholarshipCode || !academicYear;

  const handleExport = async () => {
    if (!scholarshipCode || !academicYear) return;
    setIsExporting(true);
    try {
      const result = await apiClient.admin.exportCollegeApplicantStats({
        scholarshipCode,
        academicYear,
        semester,
      });
      triggerBlobDownload(result);
    } catch (err) {
      toast.error(`匯出失敗：${(err as Error).message}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <Button
      onClick={handleExport}
      variant="outline"
      disabled={isDisabled}
      title={academicYear ? undefined : "請先選擇學年度"}
    >
      {isExporting ? (
        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
      ) : (
        <Download className="h-4 w-4 mr-2" />
      )}
      匯出學院申請人數
    </Button>
  );
}
