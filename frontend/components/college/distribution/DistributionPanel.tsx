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
import { Badge } from "@/components/ui/badge";
import { DistributionResultsPanel } from "@/components/distribution-results-panel";
import { ConfigSelector } from "../shared/ConfigSelector";
import { RankingCardList } from "../shared/RankingCardList";
import { Loader2, PackageCheck, CheckCircle2, Clock, AlertCircle, Lock, FileText } from "lucide-react";
import { apiClient } from "@/lib/api";
import { Progress } from "@/components/ui/progress";

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
      roster_cycle: 'monthly' | 'semi_yearly' | 'yearly';
      period_label: string;
      created_at: string;
      completed_at?: string;
    };
    roster_statistics?: {
      total_periods_completed: number;
      expected_total_periods: number;
      completion_rate: number;
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

  // 輔助函數：週期標籤轉換
  const getCycleLabel = (cycle: string) => {
    const labels = {
      'monthly': locale === 'zh' ? '按月造冊' : 'Monthly',
      'semi_yearly': locale === 'zh' ? '按半年造冊' : 'Semi-yearly',
      'yearly': locale === 'zh' ? '按年造冊' : 'Yearly',
    };
    return labels[cycle as keyof typeof labels] || cycle;
  };

  // 輔助函數：狀態標籤轉換
  const getStatusLabel = (status: string) => {
    const labels = {
      'draft': locale === 'zh' ? '草稿' : 'Draft',
      'processing': locale === 'zh' ? '處理中' : 'Processing',
      'completed': locale === 'zh' ? '已完成' : 'Completed',
      'locked': locale === 'zh' ? '已鎖定' : 'Locked',
      'failed': locale === 'zh' ? '失敗' : 'Failed',
    };
    return labels[status as keyof typeof labels] || status;
  };

  // 輔助函數：狀態圖標
  const getStatusIcon = (status: string) => {
    const icons = {
      'completed': <CheckCircle2 className="h-5 w-5 text-green-600" />,
      'locked': <Lock className="h-5 w-5 text-green-700" />,
      'processing': <Clock className="h-5 w-5 text-blue-600" />,
      'draft': <FileText className="h-5 w-5 text-amber-600" />,
      'failed': <AlertCircle className="h-5 w-5 text-red-600" />,
    };
    return icons[status as keyof typeof icons] || <AlertCircle className="h-5 w-5 text-slate-600" />;
  };

  // 輔助函數：格式化日期
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString(locale === 'zh' ? 'zh-TW' : 'en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  };

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
              {rosterStatus && rosterStatus.has_roster && rosterStatus.roster_info && (
                <Card className="border-l-4 border-l-blue-500">
                  <CardContent className="py-4">
                    <div className="space-y-3">
                      {/* 標題行：狀態 + 週期 */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {getStatusIcon(rosterStatus.roster_info.status)}
                          <span className="font-medium text-slate-900">
                            {locale === 'zh' ? '造冊狀態：' : 'Roster Status: '}
                            {getStatusLabel(rosterStatus.roster_info.status)}
                          </span>
                        </div>
                        <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-300">
                          {getCycleLabel(rosterStatus.roster_info.roster_cycle)}
                        </Badge>
                      </div>

                      {/* 進度條 (僅按月造冊顯示) */}
                      {rosterStatus.roster_info.roster_cycle === 'monthly' && rosterStatus.roster_statistics && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between text-sm text-slate-600">
                            <span>{locale === 'zh' ? '已完成期數' : 'Completed Periods'}</span>
                            <span className="font-mono font-bold text-slate-900">
                              {rosterStatus.roster_statistics.total_periods_completed}/
                              {rosterStatus.roster_statistics.expected_total_periods} {locale === 'zh' ? '個月' : 'months'}
                            </span>
                          </div>
                          <Progress
                            value={rosterStatus.roster_statistics.completion_rate}
                            className="h-2"
                            indicatorClassName="bg-green-500"
                          />
                        </div>
                      )}

                      {/* 半年造冊顯示統計 */}
                      {rosterStatus.roster_info.roster_cycle === 'semi_yearly' && rosterStatus.roster_statistics && (
                        <div className="text-sm text-slate-600">
                          <span>{locale === 'zh' ? '已完成期數：' : 'Completed Periods: '}</span>
                          <span className="font-mono font-bold text-slate-900">
                            {rosterStatus.roster_statistics.total_periods_completed}/
                            {rosterStatus.roster_statistics.expected_total_periods} {locale === 'zh' ? '期' : 'periods'}
                          </span>
                        </div>
                      )}

                      {/* 最新造冊資訊 */}
                      <div className="text-xs text-slate-500">
                        {locale === 'zh' ? '最新造冊：' : 'Latest Roster: '}
                        {rosterStatus.roster_info.period_label}
                        （{formatDate(rosterStatus.roster_info.created_at)}）
                      </div>

                      {/* 警告訊息 */}
                      {!rosterStatus.can_redistribute && (
                        <div className="flex items-center gap-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1.5">
                          <AlertCircle className="h-3 w-3 flex-shrink-0" />
                          <span>
                            {locale === 'zh'
                              ? '此排名已開始造冊，無法自動重新執行分發'
                              : 'Roster has been initiated. Cannot auto-redistribute.'}
                          </span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
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
