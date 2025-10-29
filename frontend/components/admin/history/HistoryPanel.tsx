"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApplicationReviewDialog } from "@/components/common/ApplicationReviewDialog";
import apiClient, {
  HistoricalApplication,
  HistoricalApplicationFilters,
} from "@/lib/api";
import {
  ApplicationStatus,
  getApplicationStatusLabel,
} from "@/lib/enums";
import {
  getDisplayStatusInfo,
} from "@/lib/utils/application-helpers";
import { Locale } from "@/lib/validators";
import { AlertCircle, Eye, FileText, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

interface User {
  id: string;
  nycu_id: string;
  name: string;
  email: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
}

interface HistoryPanelProps {
  user: User;
}

export function HistoryPanel({ user }: HistoryPanelProps) {
  // Locale for translations (admin panel uses Chinese by default)
  const locale: Locale = "zh";

  // 歷史申請相關狀態
  const [historicalApplications, setHistoricalApplications] = useState<
    HistoricalApplication[]
  >([]);
  const [historicalApplicationsGroups, setHistoricalApplicationsGroups] =
    useState<Record<string, HistoricalApplication[]>>({});
  const [activeHistoricalTab, setActiveHistoricalTab] = useState<string>("all");
  const [loadingHistoricalApplications, setLoadingHistoricalApplications] =
    useState(false);
  const [historicalApplicationsError, setHistoricalApplicationsError] =
    useState<string | null>(null);
  const [
    historicalApplicationsPagination,
    setHistoricalApplicationsPagination,
  ] = useState({
    page: 1,
    size: 20,
    total: 0,
    pages: 0,
  });
  const [historicalApplicationsFilters, setHistoricalApplicationsFilters] =
    useState<HistoricalApplicationFilters>({
      page: 1,
      size: 20,
      status: "",
      scholarship_type: "",
      academic_year: undefined,
      semester: "",
      search: "",
    });

  // Selected application for viewing details
  const [selectedApplication, setSelectedApplication] = useState<HistoricalApplication | null>(null);

  // 獲取歷史申請資料
  const fetchHistoricalApplications = useCallback(async () => {
    // 檢查用戶認證狀態
    if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
      setHistoricalApplicationsError("用戶未認證或不具有管理員權限");
      setLoadingHistoricalApplications(false);
      return;
    }

    setLoadingHistoricalApplications(true);
    setHistoricalApplicationsError(null);

    try {
      // 構建篩選條件，如果選中的是特定獎學金類型，則添加該篩選
      const filters = {
        ...historicalApplicationsFilters,
        scholarship_type:
          activeHistoricalTab === "all" ? "" : activeHistoricalTab,
      };

      const response = await apiClient.admin.getHistoricalApplications(filters);

      if (response.success && response.data) {
        const applications = response.data.items || [];
        setHistoricalApplications(applications);

        setHistoricalApplicationsPagination({
          page: response.data.page,
          size: response.data.size,
          total: response.data.total,
          pages: response.data.pages,
        });
        setHistoricalApplicationsError(null);
      } else {
        const errorMsg = response.message || "獲取歷史申請失敗";
        setHistoricalApplicationsError(errorMsg);
      }
    } catch (error: any) {
      console.error("獲取歷史申請資料失敗:", error);
      const errorMsg =
        error?.message ||
        error?.response?.data?.message ||
        "網路錯誤或伺服器未回應";
      setHistoricalApplicationsError(errorMsg);
    } finally {
      setLoadingHistoricalApplications(false);
    }
  }, [historicalApplicationsFilters, activeHistoricalTab, user]);

  // 獲取所有歷史申請以建立 tab 列表
  const fetchAllHistoricalApplicationsForTabs = useCallback(async () => {
    if (!user || (user.role !== "admin" && user.role !== "super_admin")) {
      return;
    }

    try {
      // 分頁獲取所有申請來建立 tab 列表，遵守 API 的 size <= 100 限制
      let allApplications: HistoricalApplication[] = [];
      let currentPage = 1;
      let hasMore = true;

      while (hasMore) {
        const response = await apiClient.admin.getHistoricalApplications({
          page: currentPage,
          size: 100, // 使用 API 允許的最大值
          status: "",
          scholarship_type: "",
          academic_year: undefined,
          semester: "",
          search: "",
        });

        if (response.success && response.data) {
          const pageApplications = response.data.items || [];
          allApplications = [...allApplications, ...pageApplications];

          // 檢查是否還有更多數據
          hasMore =
            pageApplications.length === 100 &&
            currentPage < response.data.pages;
          currentPage++;
        } else {
          hasMore = false;
        }
      }

      // 根據 scholarship_name 分組
      const groups: Record<string, HistoricalApplication[]> = {};
      allApplications.forEach(app => {
        const scholarshipType = app.scholarship_name || "未分類";
        if (!groups[scholarshipType]) {
          groups[scholarshipType] = [];
        }
        groups[scholarshipType].push(app);
      });
      setHistoricalApplicationsGroups(groups);

      // 設置第一個 tab 為默認
      const tabKeys = Object.keys(groups);
      if (tabKeys.length > 0 && activeHistoricalTab === "all") {
        setActiveHistoricalTab("all"); // 保持全部為默認
      }
    } catch (error) {
      console.error("獲取歷史申請 tab 資料失敗:", error);
    }
  }, [user, activeHistoricalTab]);

  // 歷史申請資料載入
  useEffect(() => {
    // 只在用戶已認證且具有管理員權限時載入歷史申請
    if (user && (user.role === "admin" || user.role === "super_admin")) {
      fetchHistoricalApplications();
    }
  }, [fetchHistoricalApplications, user]);

  // 初始載入時獲取所有歷史申請以建立 tab
  useEffect(() => {
    if (user && (user.role === "admin" || user.role === "super_admin")) {
      fetchAllHistoricalApplicationsForTabs();
    }
  }, [fetchAllHistoricalApplicationsForTabs, user]);

  return (
    <Card className="academic-card border-nycu-blue-200">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-nycu-navy-800">
          <FileText className="h-5 w-5 text-nycu-blue-600" />
          歷史申請
        </CardTitle>
        <CardDescription>
          查看所有歷史申請記錄及其狀態，按獎學金類型分類
        </CardDescription>
      </CardHeader>
      <CardContent>
        {/* 獎學金類型 Tab 區域 */}
        <Tabs
          value={activeHistoricalTab}
          onValueChange={setActiveHistoricalTab}
          className="w-full"
        >
          <TabsList className="flex w-full mb-6">
            <TabsTrigger
              key="all"
              value="all"
              className="flex-1 flex items-center justify-center gap-2"
            >
              <span>全部申請</span>
              <Badge variant="secondary" className="text-xs">
                {Object.values(historicalApplicationsGroups).reduce(
                  (total, apps) => total + apps.length,
                  0
                )}
              </Badge>
            </TabsTrigger>
            {Object.keys(historicalApplicationsGroups).map(scholarshipType => (
              <TabsTrigger
                key={scholarshipType}
                value={scholarshipType}
                className="flex-1 flex items-center justify-center gap-2"
              >
                <span>{scholarshipType}</span>
                <Badge variant="secondary" className="text-xs">
                  {historicalApplicationsGroups[scholarshipType].length}
                </Badge>
              </TabsTrigger>
            ))}
          </TabsList>

          {/* 全部申請 Tab */}
          <TabsContent key="all" value="all" className="space-y-4 mt-6">
            <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
              <h3 className="text-lg font-semibold text-blue-900 mb-2">
                全部歷史申請
              </h3>
              <p className="text-sm text-blue-700">
                顯示所有類型的歷史申請記錄，共 {historicalApplications.length} 筆
              </p>
            </div>
            <div className="space-y-4">
              {/* 篩選控制區 */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <Label htmlFor="status-filter">狀態篩選</Label>
                  <Select
                    value={historicalApplicationsFilters.status || "all"}
                    onValueChange={value =>
                      setHistoricalApplicationsFilters(prev => ({
                        ...prev,
                        status: value === "all" ? "" : value,
                        page: 1,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇狀態" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部狀態</SelectItem>
                      <SelectItem value="draft">草稿</SelectItem>
                      <SelectItem value="submitted">已提交</SelectItem>
                      <SelectItem value="under_review">審核中</SelectItem>
                      <SelectItem value="approved">已通過</SelectItem>
                      <SelectItem value="rejected">已拒絕</SelectItem>
                      <SelectItem value="returned">已退回</SelectItem>
                      <SelectItem value="withdrawn">已撤回</SelectItem>
                      <SelectItem value="cancelled">已取消</SelectItem>
                      <SelectItem value="deleted">已刪除</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="year-filter">學年度</Label>
                  <Select
                    value={
                      historicalApplicationsFilters.academic_year?.toString() ||
                      "all"
                    }
                    onValueChange={value =>
                      setHistoricalApplicationsFilters(prev => ({
                        ...prev,
                        academic_year:
                          value && value !== "all" ? parseInt(value) : undefined,
                        page: 1,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇學年度" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部學年度</SelectItem>
                      <SelectItem value="114">114學年度</SelectItem>
                      <SelectItem value="113">113學年度</SelectItem>
                      <SelectItem value="112">112學年度</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="semester-filter">學期</Label>
                  <Select
                    value={historicalApplicationsFilters.semester || "all"}
                    onValueChange={value =>
                      setHistoricalApplicationsFilters(prev => ({
                        ...prev,
                        semester: value === "all" ? "" : value,
                        page: 1,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇學期" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部學期</SelectItem>
                      <SelectItem value="first">第一學期</SelectItem>
                      <SelectItem value="second">第二學期</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label htmlFor="search-input">搜尋</Label>
                  <Input
                    id="search-input"
                    placeholder="搜尋學生姓名、學號或申請編號"
                    value={historicalApplicationsFilters.search}
                    onChange={e =>
                      setHistoricalApplicationsFilters(prev => ({
                        ...prev,
                        search: e.target.value,
                        page: 1,
                      }))
                    }
                  />
                </div>
              </div>

              {/* 操作按鈕 */}
              <div className="flex justify-between items-center">
                <div className="text-sm text-gray-600">
                  共 {historicalApplicationsPagination.total} 筆申請記錄
                </div>
                <Button
                  onClick={fetchHistoricalApplications}
                  disabled={loadingHistoricalApplications}
                  variant="outline"
                  size="sm"
                >
                  <RefreshCw
                    className={`h-4 w-4 mr-2 ${loadingHistoricalApplications ? "animate-spin" : ""}`}
                  />
                  刷新
                </Button>
              </div>

              {/* 錯誤顯示 */}
              {historicalApplicationsError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex items-center gap-2 text-red-700">
                    <AlertCircle className="h-4 w-4" />
                    <span className="font-medium">載入失敗</span>
                  </div>
                  <p className="text-red-600 text-sm mt-1">
                    {historicalApplicationsError}
                  </p>
                </div>
              )}

              {/* 載入狀態 */}
              {loadingHistoricalApplications && (
                <div className="flex items-center justify-center py-8">
                  <div className="flex items-center gap-3">
                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
                    <span className="text-nycu-navy-600">
                      載入歷史申請中...
                    </span>
                  </div>
                </div>
              )}

              {/* 申請列表 */}
              {!loadingHistoricalApplications &&
                !historicalApplicationsError && (
                  <div className="border rounded-lg overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>申請編號</TableHead>
                          <TableHead>學生資訊</TableHead>
                          <TableHead>獎學金類型</TableHead>
                          <TableHead>學年度/學期</TableHead>
                          <TableHead>狀態</TableHead>
                          <TableHead>申請時間</TableHead>
                          <TableHead>金額</TableHead>
                          <TableHead>操作</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {historicalApplications.length === 0 ? (
                          <TableRow>
                            <TableCell
                              colSpan={8}
                              className="text-center py-8 text-gray-500"
                            >
                              沒有找到符合條件的申請記錄
                            </TableCell>
                          </TableRow>
                        ) : (
                          historicalApplications.map(application => (
                            <TableRow key={application.id}>
                              <TableCell className="font-medium">
                                {application.app_id}
                              </TableCell>
                              <TableCell>
                                <div>
                                  <div className="font-medium">
                                    {application.student_name}
                                  </div>
                                  <div className="text-sm text-gray-500">
                                    {application.student_id}
                                  </div>
                                  {application.student_department && (
                                    <div className="text-xs text-gray-400">
                                      {application.student_department}
                                    </div>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div>
                                  <div className="font-medium">
                                    {application.scholarship_name}
                                  </div>
                                  {application.sub_scholarship_type &&
                                    application.sub_scholarship_type !==
                                      "GENERAL" && (
                                      <div className="text-sm text-gray-500">
                                        {application.sub_scholarship_type}
                                      </div>
                                    )}
                                  {application.is_renewal && (
                                    <Badge
                                      variant="outline"
                                      className="text-xs mt-1"
                                    >
                                      續領
                                    </Badge>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div className="text-sm">
                                  {application.academic_year}學年度
                                  {application.semester && (
                                    <div className="text-xs text-gray-500">
                                      {application.semester === "first"
                                        ? "第一學期"
                                        : "第二學期"}
                                    </div>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div className="flex gap-2">
                                  {(() => {
                                    const statusInfo = getDisplayStatusInfo(application, locale);
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
                              </TableCell>
                              <TableCell>
                                <div className="text-sm">
                                  {new Date(
                                    application.created_at
                                  ).toLocaleDateString("zh-TW")}
                                </div>
                                {application.submitted_at && (
                                  <div className="text-xs text-gray-500">
                                    提交：
                                    {new Date(
                                      application.submitted_at
                                    ).toLocaleDateString("zh-TW")}
                                  </div>
                                )}
                              </TableCell>
                              <TableCell>
                                {application.amount ? (
                                  <div className="font-medium">
                                    NT${" "}
                                    {Number(application.amount).toLocaleString()}
                                  </div>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </TableCell>
                              <TableCell>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setSelectedApplication(application)}
                                >
                                  <Eye className="h-4 w-4 mr-1" />
                                  查看詳情
                                </Button>
                              </TableCell>
                            </TableRow>
                          ))
                        )}
                      </TableBody>
                    </Table>
                  </div>
                )}

              {/* 分頁控制 */}
              {historicalApplicationsPagination.total > 0 && (
                <div className="flex items-center justify-between">
                  <div className="text-sm text-gray-600">
                    第{" "}
                    {(historicalApplicationsPagination.page - 1) *
                      historicalApplicationsPagination.size +
                      1}{" "}
                    -{" "}
                    {Math.min(
                      historicalApplicationsPagination.page *
                        historicalApplicationsPagination.size,
                      historicalApplicationsPagination.total
                    )}{" "}
                    筆，共 {historicalApplicationsPagination.total} 筆
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setHistoricalApplicationsFilters(prev => ({
                          ...prev,
                          page: (prev.page ?? 2) - 1,
                        }));
                      }}
                      disabled={historicalApplicationsPagination.page <= 1}
                    >
                      上一頁
                    </Button>
                    <span className="text-sm">
                      第 {historicalApplicationsPagination.page} /{" "}
                      {historicalApplicationsPagination.pages} 頁
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setHistoricalApplicationsFilters(prev => ({
                          ...prev,
                          page: (prev.page ?? 0) + 1,
                        }));
                      }}
                      disabled={
                        historicalApplicationsPagination.page >=
                        historicalApplicationsPagination.pages
                      }
                    >
                      下一頁
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </TabsContent>

          {/* 各獎學金類型的 Tab */}
          {Object.keys(historicalApplicationsGroups).map(scholarshipType => (
            <TabsContent
              key={scholarshipType}
              value={scholarshipType}
              className="space-y-4 mt-6"
            >
              <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
                <h3 className="text-lg font-semibold text-blue-900 mb-2">
                  {scholarshipType}
                </h3>
                <p className="text-sm text-blue-700">
                  此類型共有{" "}
                  {historicalApplicationsGroups[scholarshipType].length} 筆申請記錄
                </p>
              </div>

              <div className="space-y-4">
                {/* 篩選控制區 */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4 bg-gray-50 rounded-lg">
                  <div>
                    <Label htmlFor="status-filter">狀態篩選</Label>
                    <Select
                      value={historicalApplicationsFilters.status || "all"}
                      onValueChange={value =>
                        setHistoricalApplicationsFilters(prev => ({
                          ...prev,
                          status: value === "all" ? "" : value,
                          page: 1,
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="選擇狀態" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">全部狀態</SelectItem>
                        <SelectItem value="draft">草稿</SelectItem>
                        <SelectItem value="submitted">已提交</SelectItem>
                        <SelectItem value="under_review">審核中</SelectItem>
                        <SelectItem value="approved">已通過</SelectItem>
                        <SelectItem value="rejected">已拒絕</SelectItem>
                        <SelectItem value="returned">已退回</SelectItem>
                        <SelectItem value="withdrawn">已撤回</SelectItem>
                        <SelectItem value="cancelled">已取消</SelectItem>
                        <SelectItem value="deleted">已刪除</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label htmlFor="year-filter">學年度</Label>
                    <Select
                      value={
                        historicalApplicationsFilters.academic_year?.toString() ||
                        "all"
                      }
                      onValueChange={value =>
                        setHistoricalApplicationsFilters(prev => ({
                          ...prev,
                          academic_year:
                            value && value !== "all"
                              ? parseInt(value)
                              : undefined,
                          page: 1,
                        }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="選擇學年度" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">全部學年度</SelectItem>
                        <SelectItem value="114">114學年度</SelectItem>
                        <SelectItem value="113">113學年度</SelectItem>
                        <SelectItem value="112">112學年度</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div>
                    <Label htmlFor="search-input">搜尋</Label>
                    <Input
                      id="search-input"
                      placeholder="搜尋學生姓名、學號或申請編號"
                      value={historicalApplicationsFilters.search}
                      onChange={e =>
                        setHistoricalApplicationsFilters(prev => ({
                          ...prev,
                          search: e.target.value,
                          page: 1,
                        }))
                      }
                    />
                  </div>
                </div>

                {/* 操作按鈕 */}
                <div className="flex justify-between items-center">
                  <div className="text-sm text-gray-600">
                    {scholarshipType} 共{" "}
                    {historicalApplicationsGroups[scholarshipType].length}{" "}
                    筆申請記錄
                  </div>
                  <Button
                    onClick={fetchHistoricalApplications}
                    disabled={loadingHistoricalApplications}
                    variant="outline"
                    size="sm"
                  >
                    <RefreshCw
                      className={`h-4 w-4 mr-2 ${loadingHistoricalApplications ? "animate-spin" : ""}`}
                    />
                    刷新
                  </Button>
                </div>

                {/* 申請列表 - 只顯示當前類型的申請 */}
                <div className="border rounded-lg overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>申請編號</TableHead>
                        <TableHead>學生資訊</TableHead>
                        <TableHead>學年度/學期</TableHead>
                        <TableHead>狀態</TableHead>
                        <TableHead>申請時間</TableHead>
                        <TableHead>金額</TableHead>
                        <TableHead>操作</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {historicalApplicationsGroups[scholarshipType].length ===
                      0 ? (
                        <TableRow>
                          <TableCell
                            colSpan={7}
                            className="text-center py-8 text-gray-500"
                          >
                            沒有找到 {scholarshipType} 的申請記錄
                          </TableCell>
                        </TableRow>
                      ) : (
                        historicalApplicationsGroups[scholarshipType].map(
                          application => (
                            <TableRow key={application.id}>
                              <TableCell className="font-medium">
                                {application.app_id}
                              </TableCell>
                              <TableCell>
                                <div>
                                  <div className="font-medium">
                                    {application.student_name}
                                  </div>
                                  <div className="text-sm text-gray-500">
                                    {application.student_id}
                                  </div>
                                  {application.student_department && (
                                    <div className="text-xs text-gray-400">
                                      {application.student_department}
                                    </div>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div className="text-sm">
                                  {application.academic_year}學年度
                                  {application.semester && (
                                    <div className="text-xs text-gray-500">
                                      {application.semester === "first"
                                        ? "第一學期"
                                        : "第二學期"}
                                    </div>
                                  )}
                                </div>
                              </TableCell>
                              <TableCell>
                                <div className="flex gap-2">
                                  {(() => {
                                    const statusInfo = getDisplayStatusInfo(application, locale);
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
                              </TableCell>
                              <TableCell>
                                <div className="text-sm">
                                  {new Date(
                                    application.created_at
                                  ).toLocaleDateString("zh-TW")}
                                </div>
                                {application.submitted_at && (
                                  <div className="text-xs text-gray-500">
                                    提交：
                                    {new Date(
                                      application.submitted_at
                                    ).toLocaleDateString("zh-TW")}
                                  </div>
                                )}
                              </TableCell>
                              <TableCell>
                                {application.amount ? (
                                  <div className="font-medium">
                                    NT${" "}
                                    {Number(application.amount).toLocaleString()}
                                  </div>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </TableCell>
                              <TableCell>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setSelectedApplication(application)}
                                >
                                  <Eye className="h-4 w-4 mr-1" />
                                  查看詳情
                                </Button>
                              </TableCell>
                            </TableRow>
                          )
                        )
                      )}
                    </TableBody>
                  </Table>
                </div>
              </div>
            </TabsContent>
          ))}
        </Tabs>

        {/* Application Review Dialog */}
        <ApplicationReviewDialog
          application={selectedApplication}
          role="admin"
          open={!!selectedApplication}
          onOpenChange={(open) => !open && setSelectedApplication(null)}
          locale={locale}
          academicYear={selectedApplication?.academic_year}
          user={user}
        />
      </CardContent>
    </Card>
  );
}
