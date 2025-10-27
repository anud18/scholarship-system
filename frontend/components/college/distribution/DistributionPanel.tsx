"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { useCallback, useEffect, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { DistributionResultsPanel } from "@/components/distribution-results-panel";
import { ConfigSelector } from "../shared/ConfigSelector";
import { RankingCardList } from "../shared/RankingCardList";
import { Loader2, PackageCheck, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { apiClient } from "@/lib/api";

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
    setSelectedRanking,
    rankingData,
    setRankingData,
    isRankingLoading,
    setIsRankingLoading,
    filteredRankings,
    selectedCombination,
    setSelectedCombination,
    selectedAcademicYear,
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    availableOptions,
  } = useCollegeManagement();

  // State for roster status
  const [rosterStatus, setRosterStatus] = useState<{
    has_roster: boolean;
    can_redistribute: boolean;
    roster_info?: {
      roster_code: string;
      status: string;
      period_label: string;
      created_at: string;
      completed_at?: string;
    };
  } | null>(null);

  // Fetch ranking details when a ranking is selected
  const fetchRankingDetails = useCallback(
    async (rankingId: number) => {
      try {
        setIsRankingLoading(true);
        console.log("Fetching ranking details for:", rankingId);
        const response = await apiClient.college.getRanking(rankingId);

        if (response.success && response.data) {
          console.log("Ranking details:", response.data);

          // Transform the API response (items -> applications)
          const transformedApplications = (response.data.items || []).map(
            (item: any) => ({
              id: item.application?.id || item.id,
              ranking_item_id: item.id,
              app_id: item.application?.app_id || `APP-${item.application?.id || item.id}`,
              student_name: item.student_name || item.application?.student_info?.display_name || "未提供姓名",
              student_id: item.student_id || item.application?.student_info?.student_id || "N/A",
              academy_name: item.application?.academy_name,
              academy_code: item.application?.academy_code,
              department_name: item.application?.department_name,
              department_code: item.application?.department_code,
              scholarship_type: item.application?.scholarship_type,
              sub_type: item.sub_type,
              eligible_subtypes: item.application?.eligible_subtypes || [],
              rank_position: item.rank_position,
              is_allocated: item.is_allocated || false,
              status: item.application?.status || "pending",
              review_status: item.application?.review_status,
              student_termcount: item.application?.student_info?.term_count,
            })
          );

          setRankingData({
            applications: transformedApplications,
            totalQuota: response.data.total_quota || 0,
            subTypeCode: response.data.sub_type_code,
            academicYear: response.data.academic_year,
            semester: response.data.semester,
            isFinalized: response.data.is_finalized || false,
            subTypeMetadata: response.data.sub_type_metadata,
            collegeQuotaBreakdown: response.data.college_quota_breakdown,
          });
        }
      } catch (error) {
        console.error("Failed to fetch ranking details:", error);
      } finally {
        setIsRankingLoading(false);
      }
    },
    [setIsRankingLoading, setRankingData]
  );

  // Fetch roster status when ranking is selected
  useEffect(() => {
    const fetchRosterStatus = async () => {
      if (!selectedRanking) {
        setRosterStatus(null);
        return;
      }

      try {
        const response = await apiClient.college.getRankingRosterStatus(selectedRanking);
        if (response.success && response.data) {
          setRosterStatus(response.data);
        }
      } catch (error) {
        console.error("Failed to fetch roster status:", error);
        setRosterStatus(null);
      }
    };

    fetchRosterStatus();
  }, [selectedRanking]);

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            獎學金分發管理 - {scholarshipType.name}
          </h2>
          <p className="text-muted-foreground">
            查看與管理獎學金分發結果
          </p>
        </div>

        <ConfigSelector
          selectedCombination={selectedCombination}
          availableYears={availableOptions?.academic_years || []}
          availableSemesters={availableOptions?.semesters || []}
          onCombinationChange={(value) => {
            setSelectedCombination(value);
            const [year, semester] = value.split("-");
            setSelectedAcademicYear(parseInt(year));
            setSelectedSemester(semester || undefined);
          }}
          locale={locale}
        />
      </div>

      {/* Ranking Selection - Only show distributed rankings */}
      <Card>
        <CardHeader>
          <CardTitle>選擇已分發的排名</CardTitle>
          <CardDescription>選擇一個已執行分發的排名以查看分發結果</CardDescription>
        </CardHeader>
        <CardContent>
          <RankingCardList
            rankings={filteredRankings}
            selectedRankingId={selectedRanking}
            onRankingSelect={(id) => {
              setSelectedRanking(id);
              fetchRankingDetails(id);
            }}
            showActions={false}
            showOnlyDistributed={true}
            emptyStateConfig={{
              icon: <PackageCheck className="h-12 w-12 mx-auto mb-4 text-slate-300" />,
              title: "暫無已分發的排名",
              description: `${scholarshipType.name} 在選定的學年度與學期尚未有已執行分發的排名`,
            }}
            locale={locale}
          />
        </CardContent>
      </Card>

      {/* Distribution Results */}
      {selectedRanking && (
        <div className="space-y-6">
          {isRankingLoading ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : rankingData ? (
            <>
              {/* Roster Status Display */}
              {rosterStatus && rosterStatus.has_roster && (
                <Alert
                  variant={
                    rosterStatus.roster_info?.status === "completed" ||
                    rosterStatus.roster_info?.status === "locked"
                      ? "default"
                      : rosterStatus.roster_info?.status === "processing"
                      ? "default"
                      : "destructive"
                  }
                  className={
                    rosterStatus.roster_info?.status === "completed" ||
                    rosterStatus.roster_info?.status === "locked"
                      ? "border-green-500 bg-green-50"
                      : rosterStatus.roster_info?.status === "processing"
                      ? "border-blue-500 bg-blue-50"
                      : ""
                  }
                >
                  {rosterStatus.roster_info?.status === "completed" ||
                  rosterStatus.roster_info?.status === "locked" ? (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  ) : rosterStatus.roster_info?.status === "processing" ? (
                    <Clock className="h-4 w-4 text-blue-600" />
                  ) : (
                    <AlertCircle className="h-4 w-4" />
                  )}
                  <AlertTitle className="font-semibold">
                    造冊狀態：
                    {rosterStatus.roster_info?.status === "draft" && "草稿"}
                    {rosterStatus.roster_info?.status === "processing" && "處理中"}
                    {rosterStatus.roster_info?.status === "completed" && "已完成"}
                    {rosterStatus.roster_info?.status === "locked" && "已鎖定"}
                    {rosterStatus.roster_info?.status === "failed" && "失敗"}
                  </AlertTitle>
                  <AlertDescription className="mt-2 space-y-1">
                    <div>
                      <strong>造冊代碼：</strong>
                      {rosterStatus.roster_info?.roster_code}
                    </div>
                    <div>
                      <strong>期間：</strong>
                      {rosterStatus.roster_info?.period_label}
                    </div>
                    <div>
                      <strong>建立時間：</strong>
                      {new Date(
                        rosterStatus.roster_info?.created_at || ""
                      ).toLocaleString("zh-TW")}
                    </div>
                    {rosterStatus.roster_info?.completed_at && (
                      <div>
                        <strong>完成時間：</strong>
                        {new Date(
                          rosterStatus.roster_info.completed_at
                        ).toLocaleString("zh-TW")}
                      </div>
                    )}
                    {!rosterStatus.can_redistribute && (
                      <div className="mt-2 text-sm font-medium text-amber-700">
                        ⚠️ 此排名已開始造冊，無法自動重新執行分發
                      </div>
                    )}
                  </AlertDescription>
                </Alert>
              )}

              <DistributionResultsPanel
                rankingId={selectedRanking}
                applications={rankingData.applications}
                locale={locale}
                subTypeQuotaBreakdown={rankingData.collegeQuotaBreakdown}
              />
            </>
          ) : null}
        </div>
      )}
    </>
  );
}
