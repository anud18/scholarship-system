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
