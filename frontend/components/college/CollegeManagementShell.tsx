"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CollegeManagementProvider, useCollegeManagement } from "@/contexts/college-management-context";
import { Award, GraduationCap, Trophy, Loader2 } from "lucide-react";
import { User } from "@/types/user";

// Lazy load heavy panel components
const ApplicationReviewPanel = dynamic(
  () => import("./review/ApplicationReviewPanel").then(mod => ({ default: mod.ApplicationReviewPanel })),
  {
    loading: () => (
      <div className="flex items-center justify-center py-8">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
          <span className="text-gray-600">載入審核面板中...</span>
        </div>
      </div>
    )
  }
);

const RankingManagementPanel = dynamic(
  () => import("./ranking/RankingManagementPanel").then(mod => ({ default: mod.RankingManagementPanel })),
  {
    loading: () => (
      <div className="flex items-center justify-center py-8">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
          <span className="text-gray-600">載入排名面板中...</span>
        </div>
      </div>
    )
  }
);

const DistributionPanel = dynamic(
  () => import("./distribution/DistributionPanel").then(mod => ({ default: mod.DistributionPanel })),
  {
    loading: () => (
      <div className="flex items-center justify-center py-8">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
          <span className="text-gray-600">載入分發面板中...</span>
        </div>
      </div>
    )
  }
);

interface CollegeDashboardProps {
  user: User;
  locale?: "zh" | "en";
}

function CollegeManagementContent({ user }: { user: User }) {
  const {
    locale,
    activeTab,
    setActiveTab,
    activeScholarshipTab,
    setActiveScholarshipTab,
    availableOptions,
    selectedAcademicYear,
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    setSelectedCombination,
    fetchCollegeApplications,
    setSelectedRanking,
    setRankingData,
    academicConfig,
    getAcademicConfig,
    fetchAvailableOptions,
    getScholarshipConfig,
    setManagedCollege,
    scholarshipConfigError,
    refreshPermissions,
  } = useCollegeManagement();

  // Fetch managed college information on component mount
  useEffect(() => {
    const fetchManagedCollege = async () => {
      try {
        const { apiClient } = await import("@/lib/api");
        const response = await apiClient.college.getManagedCollege();
        if (response.success && response.data) {
          setManagedCollege(response.data);
        }
      } catch (error) {
        console.error("Failed to fetch managed college:", error);
      }
    };
    fetchManagedCollege();
  }, [setManagedCollege]);

  // Fetch rankings on component mount
  useEffect(() => {
    const initializeData = async () => {
      await getAcademicConfig();
      await fetchAvailableOptions();
      await getScholarshipConfig();
    };
    initializeData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount to avoid infinite loop

  // Auto-select first scholarship type and appropriate semester on initial load
  useEffect(() => {
    if (availableOptions && academicConfig && !activeScholarshipTab) {
      // Auto-select first scholarship type
      if (availableOptions.scholarship_types.length > 0) {
        const firstScholarshipType = availableOptions.scholarship_types[0].code;
        setActiveScholarshipTab(firstScholarshipType);

        // Auto-select current academic year
        const currentYear = academicConfig.currentYear;
        setSelectedAcademicYear(currentYear);

        // FIXED: Select semester from available options (not blindly from current time)
        // Priority:
        // 1. Current time-based semester (if available in availableOptions.semesters)
        // 2. Otherwise, first semester from availableOptions.semesters
        let selectedSemester: string;

        if (availableOptions.semesters && availableOptions.semesters.length > 0) {
          const currentTimeSemester = academicConfig.currentSemester; // "FIRST" or "SECOND"

          // Check if current semester is supported by this scholarship
          if (availableOptions.semesters.includes(currentTimeSemester)) {
            // Use current semester (e.g., undergraduate scholarships support FIRST/SECOND)
            selectedSemester = currentTimeSemester;
          } else {
            // Use first available semester (e.g., doctoral "YEARLY" when current is "FIRST")
            selectedSemester = availableOptions.semesters[0];
          }
        } else {
          // Fallback (shouldn't happen)
          selectedSemester = academicConfig.currentSemester;
        }

        const combination = `${currentYear}-${selectedSemester}`;

        setSelectedSemester(selectedSemester);
        setSelectedCombination(combination);

        // Fetch data for the auto-selected combination
        fetchCollegeApplications(
          currentYear,
          selectedSemester,
          firstScholarshipType
        );
      }
    }
  }, [
    availableOptions,
    academicConfig,
    activeScholarshipTab,
    setActiveScholarshipTab,
    setSelectedAcademicYear,
    setSelectedSemester,
    setSelectedCombination,
    fetchCollegeApplications,
  ]);

  if (scholarshipConfigError) {
    return (
      <div className="flex items-center justify-center py-12 px-4">
        <div className="w-full max-w-md bg-white rounded-lg border border-red-200 shadow-lg overflow-hidden">
          {/* Header */}
          <div className="bg-red-50 px-6 py-4 border-b border-red-200">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0">
                <svg className="h-6 w-6 text-red-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4v.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div>
                <p className="text-lg font-semibold text-red-800">
                  {locale === "zh" ? "權限設置問題" : "Permission Issue"}
                </p>
                <p className="text-sm text-red-700 mt-1">
                  {locale === "zh" ? "無法存取獎學金資訊" : "Unable to access scholarship information"}
                </p>
              </div>
            </div>
          </div>

          {/* Content */}
          <div className="px-6 py-6 space-y-4">
            <p className="text-gray-700 text-sm leading-relaxed">
              {scholarshipConfigError}
            </p>

            {/* Suggestions */}
            <div className="bg-blue-50 border border-blue-200 rounded p-4">
              <p className="text-sm font-semibold text-blue-900 mb-2">
                {locale === "zh" ? "可能的解決方案：" : "Possible solutions:"}
              </p>
              <ul className="text-sm text-blue-800 space-y-1 ml-4 list-disc">
                <li>
                  {locale === "zh"
                    ? "請確認您已被指派至正確的學院"
                    : "Verify that you are assigned to the correct college"}
                </li>
                <li>
                  {locale === "zh"
                    ? "確認已獲得至少一個獎學金的管理權限"
                    : "Ensure you have management permission for at least one scholarship"}
                </li>
                <li>
                  {locale === "zh"
                    ? "重新登入以重整權限設置"
                    : "Log in again to refresh your permissions"}
                </li>
              </ul>
            </div>

            <div className="pt-2 border-t border-gray-200">
              <p className="text-xs text-gray-500">
                {locale === "zh"
                  ? "如問題持續，請聯絡系統管理員。"
                  : "If the issue persists, please contact your system administrator."}
              </p>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex gap-2">
            <button
              onClick={() => refreshPermissions()}
              className="flex-1 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 transition"
            >
              {locale === "zh" ? "重新整理權限" : "Refresh Permissions"}
            </button>
            <button
              onClick={() => window.location.href = "/"}
              className="flex-1 px-4 py-2 bg-gray-200 text-gray-800 text-sm font-medium rounded hover:bg-gray-300 transition"
            >
              {locale === "zh" ? "回首頁" : "Home"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!availableOptions?.scholarship_types || availableOptions.scholarship_types.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <Loader2 className="h-12 w-12 animate-spin text-blue-600 mx-auto mb-4" />
          <p className="text-lg text-gray-600">
            {locale === "zh" ? "載入獎學金資訊中..." : "Loading scholarship information..."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 獎學金類型選擇 - 最上層 Tab */}
      <Tabs
        value={activeScholarshipTab || ""}
        onValueChange={scholarshipType => {
          setActiveScholarshipTab(scholarshipType);
          // 重置排名選擇
          setSelectedRanking(null);
          setRankingData(null);
          // 切換獎學金類型時重新載入資料
          fetchCollegeApplications(
            selectedAcademicYear,
            selectedSemester,
            scholarshipType
          );
        }}
        className="w-full"
      >
        <TabsList
          className={`grid w-full grid-cols-${Math.min(availableOptions.scholarship_types.length, 5)}`}
        >
          {availableOptions.scholarship_types.map(type => (
            <TabsTrigger
              key={type.code}
              value={type.code}
              className="flex items-center gap-2"
            >
              <Award className="h-4 w-4" />
              {type.name}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* 每個獎學金類型的內容 */}
        {availableOptions.scholarship_types.map(scholarshipType => (
          <TabsContent
            key={scholarshipType.code}
            value={scholarshipType.code}
            className="space-y-6"
          >
            {/* 子 Tab - 申請審核、學生排序、獎學金分發 */}
            <Tabs
              value={activeTab}
              onValueChange={setActiveTab}
              className="w-full"
            >
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="review" className="flex items-center gap-2">
                  <GraduationCap className="h-4 w-4" />
                  {locale === "zh" ? "申請審核" : "Application Review"}
                </TabsTrigger>
                <TabsTrigger
                  value="ranking"
                  className="flex items-center gap-2"
                >
                  <Trophy className="h-4 w-4" />
                  {locale === "zh" ? "學生排序" : "Student Ranking"}
                </TabsTrigger>
                <TabsTrigger
                  value="distribution"
                  className="flex items-center gap-2"
                >
                  <Award className="h-4 w-4" />
                  {locale === "zh" ? "獎學金分發" : "Distribution"}
                </TabsTrigger>
              </TabsList>

              {/* 申請審核標籤頁 */}
              <TabsContent value="review" className="space-y-6">
                <ApplicationReviewPanel
                  user={user}
                  scholarshipType={scholarshipType}
                />
              </TabsContent>

              {/* 學生排序標籤頁 */}
              <TabsContent value="ranking" className="space-y-6">
                <RankingManagementPanel
                  user={user}
                  scholarshipType={scholarshipType}
                />
              </TabsContent>

              {/* 獎學金分發標籤頁 */}
              <TabsContent value="distribution" className="space-y-6">
                <DistributionPanel
                  user={user}
                  scholarshipType={scholarshipType}
                />
              </TabsContent>
            </Tabs>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

export function CollegeManagementShell({ user, locale = "zh" }: CollegeDashboardProps) {
  return (
    <CollegeManagementProvider locale={locale}>
      <CollegeManagementContent user={user} />
    </CollegeManagementProvider>
  );
}

// Export as CollegeDashboard for backward compatibility
export { CollegeManagementShell as CollegeDashboard };
