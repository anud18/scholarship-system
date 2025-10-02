"use client";

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProgressTimeline } from "@/components/progress-timeline";
import SemesterSelector from "@/components/semester-selector";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Calendar,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
  Award,
  GraduationCap,
  UserCheck,
  Filter,
  RefreshCw,
} from "lucide-react";
import { apiClient } from "@/lib/api";
import { User } from "@/types/user";
import { useScholarshipPermissions } from "@/hooks/use-scholarship-permissions";

interface ScholarshipTimelineProps {
  user: User;
}

interface TimelineStep {
  id: string;
  title: string;
  status: "completed" | "current" | "pending" | "rejected";
  date?: string;
  estimatedDate?: string;
}

interface ScholarshipTimelineData {
  id: number;
  code: string;
  name: string;
  nameEn?: string;
  academicYear: number;
  semester: string;
  applicationCycle: "semester" | "yearly"; // 新增申請週期
  currentStage: string;
  timeline: {
    renewal: {
      applicationStart?: string;
      applicationEnd?: string;
      professorReviewStart?: string;
      professorReviewEnd?: string;
      collegeReviewStart?: string;
      collegeReviewEnd?: string;
    };
    general: {
      applicationStart?: string;
      applicationEnd?: string;
      professorReviewStart?: string;
      professorReviewEnd?: string;
      collegeReviewStart?: string;
      collegeReviewEnd?: string;
    };
  };
}

export function ScholarshipTimeline({ user }: ScholarshipTimelineProps) {
  const [scholarships, setScholarships] = useState<ScholarshipTimelineData[]>(
    []
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("");

  // 學期選擇狀態 - 使用 Record 為每個獎學金儲存獨立的選擇
  const [selectedCombinations, setSelectedCombinations] = useState<Record<string, {
    combination: string;
    academicYear: number;
    semester: string | null;
  }>>({});

  // Get user's scholarship permissions
  const { filterScholarshipsByPermission, isLoading: permissionsLoading } =
    useScholarshipPermissions();

  // 處理學期選擇變更
  const handleSemesterChange = async (
    scholarshipCode: string,
    combination: string,
    academicYear: number,
    semester: string | null
  ) => {
    // 更新該獎學金的選擇
    setSelectedCombinations(prev => ({
      ...prev,
      [scholarshipCode]: { combination, academicYear, semester: semester || "first" }
    }));

    // 重新載入該學期的獎學金時間軸資料
    // 對於學年制獎學金，不傳遞學期參數
    await fetchScholarshipTimelines(academicYear, semester ?? undefined);
  };

  // 重置特定獎學金的篩選
  const resetFilter = (scholarshipCode: string) => {
    setSelectedCombinations(prev => {
      const newState = { ...prev };
      delete newState[scholarshipCode];
      return newState;
    });
    fetchScholarshipTimelines();
  };

  // 獲取獎學金時間軸數據
  const fetchScholarshipTimelines = async (
    academicYear?: number,
    semester?: string
  ) => {
    try {
      setIsLoading(true);
      setError(null);

      console.log(
        "ScholarshipTimeline: Starting fetch for user:",
        user.role,
        user.id
      );

      // 建構查詢參數
      const queryParams = new URLSearchParams();
      if (academicYear)
        queryParams.append("academic_year", academicYear.toString());
      if (semester && semester !== "null")
        queryParams.append("semester", semester);

      // 根據用戶角色獲取不同的獎學金列表
      let response;
      if (user.role === "super_admin") {
        // Super admin 可以看到所有獎學金
        console.log(
          "ScholarshipTimeline: Fetching all scholarships for super_admin",
          { academicYear, semester }
        );

        // 構建帶參數的 URL
        const url = queryParams.toString()
          ? `/scholarships?${queryParams.toString()}`
          : "/scholarships";
        response = await apiClient.request(url);
      } else if (user.role === "admin" || user.role === "college") {
        // Admin 和 College 可以看到他們有權限的獎學金
        console.log(
          "ScholarshipTimeline: Fetching scholarships for admin/college user",
          { academicYear, semester }
        );

        // 構建帶參數的 URL
        const url = queryParams.toString()
          ? `/scholarships?${queryParams.toString()}`
          : "/scholarships";
        response = await apiClient.request(url);
      } else {
        // 其他角色不顯示此功能
        console.log(
          "ScholarshipTimeline: User role not eligible for timeline:",
          user.role
        );
        setScholarships([]);
        setIsLoading(false);
        return;
      }

      if (response.success && response.data) {
        console.log(
          "ScholarshipTimeline: Raw scholarships data:",
          response.data
        );

        // Use the filterScholarshipsByPermission function to filter scholarships
        const filteredScholarships = filterScholarshipsByPermission(
          response.data
        );
        console.log(
          "ScholarshipTimeline: Filtered scholarships based on permissions:",
          filteredScholarships
        );

        const timelineData: ScholarshipTimelineData[] =
          filteredScholarships.map((scholarship: any) => {
            console.log(
              `ScholarshipTimeline: Processing ${scholarship.name}, application_cycle:`,
              scholarship.application_cycle
            );

            return {
              id: scholarship.id,
              code: scholarship.code,
              name: scholarship.name,
              nameEn: scholarship.name_en,
              academicYear: scholarship.academic_year || 113,
              semester: scholarship.semester || "first",
              applicationCycle: scholarship.application_cycle || "semester", // 從API獲取申請週期
              currentStage: getCurrentStage(scholarship),
              timeline: {
                renewal: {
                  applicationStart: scholarship.renewal_application_start_date,
                  applicationEnd: scholarship.renewal_application_end_date,
                  professorReviewStart:
                    scholarship.renewal_professor_review_start,
                  professorReviewEnd: scholarship.renewal_professor_review_end,
                  collegeReviewStart: scholarship.renewal_college_review_start,
                  collegeReviewEnd: scholarship.renewal_college_review_end,
                },
                general: {
                  applicationStart: scholarship.application_start_date,
                  applicationEnd: scholarship.application_end_date,
                  professorReviewStart: scholarship.professor_review_start,
                  professorReviewEnd: scholarship.professor_review_end,
                  collegeReviewStart: scholarship.college_review_start,
                  collegeReviewEnd: scholarship.college_review_end,
                },
              },
            };
          });

        setScholarships(timelineData);
        if (timelineData.length > 0 && !activeTab) {
          setActiveTab(timelineData[0].code);
        }
      }
    } catch (err) {
      console.error("Failed to fetch scholarship timelines:", err);
      setError("載入獎學金時間軸失敗");
    } finally {
      setIsLoading(false);
    }
  };

  // 獲取當前階段
  const getCurrentStage = (scholarship: any): string => {
    const now = new Date();

    // 檢查續領申請期間
    if (
      scholarship.renewal_application_start_date &&
      scholarship.renewal_application_end_date
    ) {
      const renewalStart = new Date(scholarship.renewal_application_start_date);
      const renewalEnd = new Date(scholarship.renewal_application_end_date);
      if (now >= renewalStart && now <= renewalEnd) {
        return "續領申請期間";
      }
    }

    // 檢查續領教授審查期間
    if (
      scholarship.renewal_professor_review_start &&
      scholarship.renewal_professor_review_end
    ) {
      const profStart = new Date(scholarship.renewal_professor_review_start);
      const profEnd = new Date(scholarship.renewal_professor_review_end);
      if (now >= profStart && now <= profEnd) {
        return "續領教授審查期間";
      }
    }

    // 檢查續領學院審查期間
    if (
      scholarship.renewal_college_review_start &&
      scholarship.renewal_college_review_end
    ) {
      const collegeStart = new Date(scholarship.renewal_college_review_start);
      const collegeEnd = new Date(scholarship.renewal_college_review_end);
      if (now >= collegeStart && now <= collegeEnd) {
        return "續領學院審查期間";
      }
    }

    // 檢查一般申請期間
    if (
      scholarship.application_start_date &&
      scholarship.application_end_date
    ) {
      const appStart = new Date(scholarship.application_start_date);
      const appEnd = new Date(scholarship.application_end_date);
      if (now >= appStart && now <= appEnd) {
        return "一般申請期間";
      }
    }

    // 檢查一般教授審查期間
    if (
      scholarship.professor_review_start &&
      scholarship.professor_review_end
    ) {
      const profStart = new Date(scholarship.professor_review_start);
      const profEnd = new Date(scholarship.professor_review_end);
      if (now >= profStart && now <= profEnd) {
        return "一般教授審查期間";
      }
    }

    // 檢查一般學院審查期間
    if (scholarship.college_review_start && scholarship.college_review_end) {
      const collegeStart = new Date(scholarship.college_review_start);
      const collegeEnd = new Date(scholarship.college_review_end);
      if (now >= collegeStart && now <= collegeEnd) {
        return "一般學院審查期間";
      }
    }

    return "非申請期間";
  };

  // 生成時間軸步驟
  const generateTimelineSteps = (
    scholarship: ScholarshipTimelineData
  ): TimelineStep[] => {
    const steps: TimelineStep[] = [];
    const now = new Date();

    // 如果有選擇特定學期，需要根據該學期的資料來生成時間軸
    // 這裡可以根據 currentAcademicYear 和 currentSemester 來過濾或調整時間軸

    // 續領申請階段
    if (
      scholarship.timeline.renewal.applicationStart &&
      scholarship.timeline.renewal.applicationEnd
    ) {
      const renewalStart = new Date(
        scholarship.timeline.renewal.applicationStart
      );
      const renewalEnd = new Date(scholarship.timeline.renewal.applicationEnd);

      steps.push({
        id: "renewal-application",
        title: "續領申請期間",
        status:
          now >= renewalStart && now <= renewalEnd
            ? "current"
            : now > renewalEnd
              ? "completed"
              : "pending",
        date:
          now >= renewalStart && now <= renewalEnd
            ? `進行中 (${formatDateOnly(scholarship.timeline.renewal.applicationEnd)})`
            : formatDateOnly(scholarship.timeline.renewal.applicationEnd),
        estimatedDate:
          now < renewalStart
            ? formatDateOnly(scholarship.timeline.renewal.applicationStart)
            : undefined,
      });
    }

    // 續領教授審查階段
    if (
      scholarship.timeline.renewal.professorReviewStart &&
      scholarship.timeline.renewal.professorReviewEnd
    ) {
      const profStart = new Date(
        scholarship.timeline.renewal.professorReviewStart
      );
      const profEnd = new Date(scholarship.timeline.renewal.professorReviewEnd);

      steps.push({
        id: "renewal-professor",
        title: "續領教授審查",
        status:
          now >= profStart && now <= profEnd
            ? "current"
            : now > profEnd
              ? "completed"
              : "pending",
        date:
          now >= profStart && now <= profEnd
            ? `進行中 (${formatDateOnly(scholarship.timeline.renewal.professorReviewEnd)})`
            : formatDateOnly(scholarship.timeline.renewal.professorReviewEnd),
        estimatedDate:
          now < profStart
            ? formatDateOnly(scholarship.timeline.renewal.professorReviewStart)
            : undefined,
      });
    }

    // 續領學院審查階段
    if (
      scholarship.timeline.renewal.collegeReviewStart &&
      scholarship.timeline.renewal.collegeReviewEnd
    ) {
      const collegeStart = new Date(
        scholarship.timeline.renewal.collegeReviewStart
      );
      const collegeEnd = new Date(
        scholarship.timeline.renewal.collegeReviewEnd
      );

      steps.push({
        id: "renewal-college",
        title: "續領學院審查",
        status:
          now >= collegeStart && now <= collegeEnd
            ? "current"
            : now > collegeEnd
              ? "completed"
              : "pending",
        date:
          now >= collegeStart && now <= collegeEnd
            ? `進行中 (${formatDateOnly(scholarship.timeline.renewal.collegeReviewEnd)})`
            : formatDateOnly(scholarship.timeline.renewal.collegeReviewEnd),
        estimatedDate:
          now < collegeStart
            ? formatDateOnly(scholarship.timeline.renewal.collegeReviewStart)
            : undefined,
      });
    }

    // 一般申請階段
    if (
      scholarship.timeline.general.applicationStart &&
      scholarship.timeline.general.applicationEnd
    ) {
      const appStart = new Date(scholarship.timeline.general.applicationStart);
      const appEnd = new Date(scholarship.timeline.general.applicationEnd);

      steps.push({
        id: "general-application",
        title: "一般申請期間",
        status:
          now >= appStart && now <= appEnd
            ? "current"
            : now > appEnd
              ? "completed"
              : "pending",
        date:
          now >= appStart && now <= appEnd
            ? `進行中 (${formatDateOnly(scholarship.timeline.general.applicationEnd)})`
            : formatDateOnly(scholarship.timeline.general.applicationEnd),
        estimatedDate:
          now < appStart
            ? formatDateOnly(scholarship.timeline.general.applicationStart)
            : undefined,
      });
    }

    // 一般教授審查階段
    if (
      scholarship.timeline.general.professorReviewStart &&
      scholarship.timeline.general.professorReviewEnd
    ) {
      const profStart = new Date(
        scholarship.timeline.general.professorReviewStart
      );
      const profEnd = new Date(scholarship.timeline.general.professorReviewEnd);

      steps.push({
        id: "general-professor",
        title: "一般教授審查",
        status:
          now >= profStart && now <= profEnd
            ? "current"
            : now > profEnd
              ? "completed"
              : "pending",
        date:
          now >= profStart && now <= profEnd
            ? `進行中 (${formatDateOnly(scholarship.timeline.general.professorReviewEnd)})`
            : formatDateOnly(scholarship.timeline.general.professorReviewEnd),
        estimatedDate:
          now < profStart
            ? formatDateOnly(scholarship.timeline.general.professorReviewStart)
            : undefined,
      });
    }

    // 一般學院審查階段
    if (
      scholarship.timeline.general.collegeReviewStart &&
      scholarship.timeline.general.collegeReviewEnd
    ) {
      const collegeStart = new Date(
        scholarship.timeline.general.collegeReviewStart
      );
      const collegeEnd = new Date(
        scholarship.timeline.general.collegeReviewEnd
      );

      steps.push({
        id: "general-college",
        title: "一般學院審查",
        status:
          now >= collegeStart && now <= collegeEnd
            ? "current"
            : now > collegeEnd
              ? "completed"
              : "pending",
        date:
          now >= collegeStart && now <= collegeEnd
            ? `進行中 (${formatDateOnly(scholarship.timeline.general.collegeReviewEnd)})`
            : formatDateOnly(scholarship.timeline.general.collegeReviewEnd),
        estimatedDate:
          now < collegeStart
            ? formatDateOnly(scholarship.timeline.general.collegeReviewStart)
            : undefined,
      });
    }

    return steps;
  };

  // 格式化日期 - 只顯示日期（用於時間軸）
  const formatDateOnly = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
  };

  // 格式化日期和時間 - 使用24小時制（用於詳細時間表）
  const formatDateTime = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  };

  // 獲取階段狀態顏色
  const getStageStatusColor = (stage: string) => {
    if (stage.includes("進行中") || stage.includes("期間")) {
      return "bg-blue-100 text-blue-800 border-blue-200";
    }
    if (stage === "非申請期間") {
      return "bg-gray-100 text-gray-800 border-gray-200";
    }
    return "bg-green-100 text-green-800 border-green-200";
  };

  useEffect(() => {
    // Only fetch if permissions are not loading
    if (!permissionsLoading) {
      fetchScholarshipTimelines();
    }
  }, [user.role, permissionsLoading]);

  // 如果用戶沒有權限查看，不顯示組件
  if (!["super_admin", "admin", "college"].includes(user.role)) {
    return null;
  }

  if (isLoading || permissionsLoading) {
    return (
      <Card className="academic-card border-nycu-blue-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
            <Calendar className="h-5 w-5 text-nycu-blue-600" />
            獎學金時間軸
          </CardTitle>
          <CardDescription>載入中...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-nycu-blue-600" />
            <span className="ml-2 text-nycu-navy-600">
              載入獎學金時間軸中...
            </span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="academic-card border-red-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-red-800">
            <AlertCircle className="h-5 w-5 text-red-600" />
            獎學金時間軸
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-4">
            <p className="text-red-600">{error}</p>
            <button
              onClick={() => fetchScholarshipTimelines()}
              className="mt-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700"
            >
              重試
            </button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (scholarships.length === 0) {
    return (
      <Card className="academic-card border-nycu-blue-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
            <Calendar className="h-5 w-5 text-nycu-blue-600" />
            獎學金時間軸
          </CardTitle>
          <CardDescription>
            {["admin", "college"].includes(user.role)
              ? "您沒有獎學金權限"
              : "暫無獎學金資料"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-nycu-navy-600">
            <Award className="h-12 w-12 mx-auto mb-2 text-nycu-blue-300" />
            <p>
              {["admin", "college"].includes(user.role)
                ? "您目前沒有被分配任何獎學金權限，請聯繫管理員"
                : "暫無獎學金時間軸資料"}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="academic-card border-nycu-blue-200">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
          <Calendar className="h-5 w-5 text-nycu-blue-600" />
          獎學金時間軸
        </CardTitle>
        <CardDescription>查看各獎學金申請與審查進度</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList
            className="grid w-full"
            style={{
              gridTemplateColumns: `repeat(${scholarships.length}, 1fr)`,
            }}
          >
            {scholarships.map(scholarship => (
              <TabsTrigger
                key={scholarship.code}
                value={scholarship.code}
                className="text-sm"
              >
                {scholarship.name}
              </TabsTrigger>
            ))}
          </TabsList>

          {scholarships.map(scholarship => (
            <TabsContent
              key={scholarship.code}
              value={scholarship.code}
              className="space-y-4"
            >
              {/* 學期選擇器 */}
              <Card className="bg-gradient-to-r from-green-50 to-blue-50 border-green-200">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="flex items-center gap-2 text-lg font-semibold">
                        <Filter className="h-5 w-5 text-nycu-blue-600" />
                        時間篩選
                      </CardTitle>
                      <CardDescription className="text-sm text-nycu-navy-600 mt-1">
                        選擇要查看的學年學期時間軸
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                      <SemesterSelector
                        mode="combined"
                        scholarshipCode={scholarship.code}
                        selectedCombination={selectedCombinations[scholarship.code]?.combination}
                        onCombinationChange={(combination, academicYear, semester) =>
                          handleSemesterChange(scholarship.code, combination, academicYear, semester)
                        }
                      />
                      {selectedCombinations[scholarship.code] && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => resetFilter(scholarship.code)}
                          className="text-nycu-navy-600 hover:text-nycu-navy-800"
                        >
                          <RefreshCw className="h-4 w-4 mr-2" />
                          清除篩選
                        </Button>
                      )}
                    </div>
                  </div>
                </CardHeader>
              </Card>

              {/* 獎學金基本信息 */}
              <div className="flex items-center justify-between p-4 bg-nycu-blue-50 rounded-lg">
                <div>
                  <h3 className="font-semibold text-nycu-navy-800">
                    {scholarship.name}
                  </h3>
                  <p className="text-sm text-nycu-navy-600">
                    {selectedCombinations[scholarship.code]
                      ? `${selectedCombinations[scholarship.code].academicYear}學年度${
                          scholarship.applicationCycle === "semester" &&
                          selectedCombinations[scholarship.code].semester &&
                          selectedCombinations[scholarship.code].semester !== "null"
                            ? selectedCombinations[scholarship.code].semester === "first"
                              ? " 第一學期"
                              : " 第二學期"
                            : ""
                        }`
                      : `${scholarship.academicYear}學年度${
                          scholarship.applicationCycle === "semester"
                            ? scholarship.semester === "first"
                              ? " 第一學期"
                              : " 第二學期"
                            : ""
                        }`}
                  </p>
                </div>
                <Badge
                  className={getStageStatusColor(scholarship.currentStage)}
                >
                  {scholarship.currentStage}
                </Badge>
              </div>

              {/* 時間軸 */}
              <div className="mt-6">
                <h4 className="text-sm font-medium text-nycu-navy-700 mb-3">
                  申請與審查流程
                </h4>
                <ProgressTimeline
                  steps={generateTimelineSteps(scholarship)}
                  orientation="horizontal"
                  className="mb-4"
                  isLoading={isLoading || permissionsLoading}
                />
              </div>

              {/* 詳細時間表 */}
              <div className="grid gap-4 md:grid-cols-2">
                {/* 續領流程 */}
                {(scholarship.timeline.renewal.applicationStart ||
                  scholarship.timeline.renewal.applicationEnd) && (
                  <Card className="border-nycu-orange-200">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm flex items-center gap-2 text-nycu-navy-800">
                        <UserCheck className="h-4 w-4 text-nycu-orange-600" />
                        續領流程
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      {scholarship.timeline.renewal.applicationStart && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">申請開始：</span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.renewal.applicationStart
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.renewal.applicationEnd && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">申請截止：</span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.renewal.applicationEnd
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.renewal.professorReviewStart && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            教授審查開始：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.renewal.professorReviewStart
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.renewal.professorReviewEnd && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            教授審查截止：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.renewal.professorReviewEnd
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.renewal.collegeReviewStart && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            學院審查開始：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.renewal.collegeReviewStart
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.renewal.collegeReviewEnd && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            學院審查截止：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.renewal.collegeReviewEnd
                            )}
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* 一般申請流程 */}
                {(scholarship.timeline.general.applicationStart ||
                  scholarship.timeline.general.applicationEnd) && (
                  <Card className="border-nycu-blue-200">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm flex items-center gap-2 text-nycu-navy-800">
                        <GraduationCap className="h-4 w-4 text-nycu-blue-600" />
                        一般申請流程
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      {scholarship.timeline.general.applicationStart && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">申請開始：</span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.general.applicationStart
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.general.applicationEnd && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">申請截止：</span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.general.applicationEnd
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.general.professorReviewStart && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            教授審查開始：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.general.professorReviewStart
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.general.professorReviewEnd && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            教授審查截止：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.general.professorReviewEnd
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.general.collegeReviewStart && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            學院審查開始：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.general.collegeReviewStart
                            )}
                          </span>
                        </div>
                      )}
                      {scholarship.timeline.general.collegeReviewEnd && (
                        <div className="flex justify-between">
                          <span className="text-nycu-navy-600">
                            學院審查截止：
                          </span>
                          <span className="font-mono">
                            {formatDateTime(
                              scholarship.timeline.general.collegeReviewEnd
                            )}
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      </CardContent>
    </Card>
  );
}
