"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { DistributionResultsPanel } from "@/components/distribution-results-panel";

interface DistributionPanelProps {
  user: User;
  scholarshipType: { code: string; name: string };
}

export function DistributionPanel({
  user,
  scholarshipType,
}: DistributionPanelProps) {
  const {
    locale,
    selectedRanking,
    rankingData,
  } = useCollegeManagement();

  return (
    <>
      <div>
        <h2 className="text-3xl font-bold tracking-tight">
          獎學金分發管理 - {scholarshipType.name}
        </h2>
        <p className="text-muted-foreground">
          查看與管理獎學金分發結果
        </p>
      </div>

      {selectedRanking ? (
        <DistributionResultsPanel
          rankingId={selectedRanking}
          applications={rankingData?.applications}
          locale={locale}
          subTypeQuotaBreakdown={rankingData?.collegeQuotaBreakdown}
        />
      ) : (
        <div className="text-center py-12">
          <p className="text-lg text-gray-600">
            {locale === "zh"
              ? "請先在「學生排序」標籤中選擇一個排名"
              : "Please select a ranking in the Student Ranking tab"}
          </p>
        </div>
      )}
    </>
  );
}
