/**
 * 增強版管理儀表板 - 包含學期選擇器功能
 * 展示如何將學期選擇器整合到現有的管理介面中
 */

"use client";

import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  FileText,
  TrendingUp,
  Clock,
  CheckCircle,
  AlertCircle,
  Award,
  Loader2,
  RefreshCw,
  Filter,
} from "lucide-react";
import { api } from "@/lib/api";
import SemesterSelector from "./semester-selector";
import { getDisplayStatusInfo } from "@/lib/utils/application-helpers";

interface EnhancedAdminDashboardProps {
  stats: any;
  recentApplications: any[];
  systemAnnouncements: any[];
  isStatsLoading: boolean;
  isRecentLoading: boolean;
  isAnnouncementsLoading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  user: any;
  login: (token: string, userData: any) => void;
  logout: () => void;
  fetchRecentApplications: () => void;
  fetchDashboardStats: () => void;
  onTabChange?: (tab: string) => void;
}

export function EnhancedAdminDashboard({
  stats,
  recentApplications,
  systemAnnouncements,
  isStatsLoading,
  isRecentLoading,
  isAnnouncementsLoading,
  error,
  isAuthenticated,
  user,
  login,
  logout,
  fetchRecentApplications,
  fetchDashboardStats,
  onTabChange,
}: EnhancedAdminDashboardProps) {
  // 學期選擇狀態
  const [selectedCombination, setSelectedCombination] = useState<string>();
  const [currentAcademicYear, setCurrentAcademicYear] = useState<number>();
  const [currentSemester, setCurrentSemester] = useState<string>();
  const [filteredStats, setFilteredStats] = useState<any>(null);
  const [filteredApplications, setFilteredApplications] = useState<any[]>([]);

  // 處理學期選擇變更
  const handleSemesterChange = async (
    combination: string,
    academicYear: number,
    semester: string | null
  ) => {
    setSelectedCombination(combination);
    setCurrentAcademicYear(academicYear);
    setCurrentSemester(semester ?? undefined);

    // 重新載入該學期的統計資料
    await fetchFilteredData(academicYear, semester);
  };

  // 載入篩選後的資料
  const fetchFilteredData = async (
    academicYear: number,
    semester: string | null
  ) => {
    try {
      const statsResponse = await api.request<any>("/admin/dashboard/stats", {
        method: "GET",
        params: {
          academic_year: academicYear,
          semester: semester ?? undefined,
        },
      });
      if (statsResponse.success) {
        setFilteredStats(statsResponse.data);
      }

      const applicationsResponse = await api.request<any>(
        "/admin/recent-applications",
        {
          method: "GET",
          params: {
            academic_year: academicYear,
            semester: semester ?? undefined,
            limit: 10,
          },
        }
      );
      if (
        applicationsResponse.success &&
        Array.isArray(applicationsResponse.data)
      ) {
        setFilteredApplications(applicationsResponse.data);
      }
    } catch (error) {
      console.error("Error fetching filtered data:", error);
      // 如果API不支援篩選，使用原始資料
      setFilteredStats(stats);
      setFilteredApplications(recentApplications);
    }
  };

  // 重置篩選
  const resetFilter = () => {
    setSelectedCombination(undefined);
    setCurrentAcademicYear(undefined);
    setCurrentSemester(undefined);
    setFilteredStats(null);
    setFilteredApplications([]);
  };

  // 取得顯示用的資料
  const displayStats = filteredStats || stats;
  const displayApplications =
    filteredApplications.length > 0 ? filteredApplications : recentApplications;

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-600">
              <AlertCircle className="h-5 w-5" />
              載入錯誤
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-600 mb-4">{error}</p>
            <Button onClick={fetchDashboardStats} className="w-full">
              重新載入
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 學期選擇器和篩選控制 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            學期篩選
          </CardTitle>
          <CardDescription>選擇特定學年學期查看相關統計資料</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            <SemesterSelector
              mode="combined"
              showStatistics={true}
              selectedCombination={selectedCombination}
              onCombinationChange={handleSemesterChange}
              className="flex-1"
            />

            <div className="flex gap-2">
              {selectedCombination && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={resetFilter}
                  className="flex items-center gap-1"
                >
                  <RefreshCw className="h-4 w-4" />
                  重置
                </Button>
              )}
            </div>
          </div>

          {selectedCombination && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg">
              <p className="text-sm text-blue-800">
                <strong>當前篩選：</strong> {currentAcademicYear}學年
                {currentSemester === "first" ? "第一學期" : "第二學期"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      <Separator />

      {/* 統計卡片 */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">總申請數</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isStatsLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                displayStats?.total_applications || 0
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {selectedCombination ? "該學期申請數" : "總申請數"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">處理中</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isStatsLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                displayStats?.pending_applications || 0
              )}
            </div>
            <p className="text-xs text-muted-foreground">待審核申請</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">已核准</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isStatsLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                displayStats?.approved_applications || 0
              )}
            </div>
            <p className="text-xs text-muted-foreground">核准申請數</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">核准率</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {isStatsLoading ? (
                <Loader2 className="h-6 w-6 animate-spin" />
              ) : (
                `${displayStats?.approval_rate || 0}%`
              )}
            </div>
            <p className="text-xs text-muted-foreground">申請核准比例</p>
          </CardContent>
        </Card>
      </div>

      {/* 最近申請 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              最近申請
              {selectedCombination && (
                <Badge variant="secondary" className="ml-2">
                  {currentAcademicYear}學年
                  {currentSemester === "first" ? "第一學期" : "第二學期"}
                </Badge>
              )}
            </CardTitle>
            <CardDescription>最新的申請記錄</CardDescription>
          </CardHeader>
          <CardContent>
            {isRecentLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : displayApplications.length > 0 ? (
              <div className="space-y-4">
                {displayApplications.slice(0, 5).map((application: any) => (
                  <div
                    key={application.id}
                    className="flex items-center justify-between p-3 border rounded-lg"
                  >
                    <div className="flex-1">
                      <div className="font-medium">
                        {application.scholarship_name}
                      </div>
                      <div className="text-sm text-gray-500">
                        申請人: {application.user_name || "未知"}
                      </div>
                      <div className="text-xs text-gray-400">
                        {new Date(application.created_at).toLocaleString(
                          "zh-TW"
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                      {(() => {
                        const statusInfo = getDisplayStatusInfo(application, "zh");
                        return (
                          <>
                            <Badge variant={statusInfo.statusVariant}>
                              {statusInfo.statusLabel}
                            </Badge>
                            {statusInfo.showStage && statusInfo.stageLabel && (
                              <Badge variant={statusInfo.stageVariant}>
                                {statusInfo.stageLabel}
                              </Badge>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-4 text-gray-500">
                {selectedCombination ? "該學期暫無申請記錄" : "暫無申請記錄"}
              </div>
            )}
          </CardContent>
        </Card>

        {/* 系統公告 */}
        <Card className="col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5" />
              系統公告
            </CardTitle>
            <CardDescription>重要系統訊息</CardDescription>
          </CardHeader>
          <CardContent>
            {isAnnouncementsLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : systemAnnouncements.length > 0 ? (
              <div className="space-y-4">
                {systemAnnouncements.slice(0, 5).map((announcement: any) => (
                  <div key={announcement.id} className="p-3 border rounded-lg">
                    <div className="font-medium">{announcement.title}</div>
                    <div className="text-sm text-gray-600 mt-1">
                      {announcement.content}
                    </div>
                    <div className="text-xs text-gray-400 mt-2">
                      {new Date(announcement.created_at).toLocaleString(
                        "zh-TW"
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-4 text-gray-500">暫無系統公告</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export default EnhancedAdminDashboard;
