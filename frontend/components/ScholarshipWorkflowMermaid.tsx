"use client";

import { useEffect, useState } from "react";
import { format } from "date-fns";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Download,
  Info,
  Calendar,
  Users,
  Clock,
  RefreshCw,
  ChevronRight,
} from "lucide-react";
import apiClient, { ScholarshipConfiguration } from "@/lib/api";

interface ScholarshipWorkflowMermaidProps {
  configurations: ScholarshipConfiguration[];
  selectedConfigId?: number;
  onConfigChange?: (configId: number) => void;
}

interface WorkflowStats {
  totalApplications: number;
  pendingReviews: number;
  currentStage: string;
  nextDeadline?: Date;
}

export function ScholarshipWorkflowMermaid({
  configurations,
  selectedConfigId,
  onConfigChange,
}: ScholarshipWorkflowMermaidProps) {
  const [selectedConfig, setSelectedConfig] =
    useState<ScholarshipConfiguration | null>(null);
  const [stats, setStats] = useState<WorkflowStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [stageApplications, setStageApplications] = useState<any[]>([]);
  const [showStageDetails, setShowStageDetails] = useState(false);

  // Tab 功能相關狀態
  const [activeTab, setActiveTab] = useState<string>("");
  const [scholarshipGroups, setScholarshipGroups] = useState<
    Record<string, ScholarshipConfiguration[]>
  >({});

  // 組件已載入標記
  const [componentLoaded, setComponentLoaded] = useState(false);

  // 組件載入完成
  useEffect(() => {
    setComponentLoaded(true);
  }, []);

  // 當配置列表變化時，重新分組
  useEffect(() => {
    if (configurations.length > 0) {
      const groups: Record<string, ScholarshipConfiguration[]> = {};

      configurations.forEach(config => {
        const typeName = config.scholarship_type_name || "其他獎學金";
        if (!groups[typeName]) {
          groups[typeName] = [];
        }
        groups[typeName].push(config);
      });

      // 排序每個組內的配置（按學年和學期排序）
      Object.keys(groups).forEach(typeName => {
        groups[typeName].sort((a, b) => {
          if (a.academic_year !== b.academic_year) {
            return b.academic_year - a.academic_year; // 新學年在前
          }
          // 如果學年相同，按學期排序（第二學期在前）
          if (a.semester && b.semester) {
            return b.semester.localeCompare(a.semester);
          }
          return 0;
        });
      });

      setScholarshipGroups(groups);

      // 設置默認的活動tab
      const typeNames = Object.keys(groups);
      if (typeNames.length > 0 && !activeTab) {
        setActiveTab(typeNames[0]);

        // 如果沒有選中的配置，選擇第一個
        if (!selectedConfig && groups[typeNames[0]].length > 0) {
          const firstConfig = groups[typeNames[0]][0];
          setSelectedConfig(firstConfig);
          onConfigChange?.(firstConfig.id);
          loadWorkflowStats(firstConfig.id);
        }
      }
    }
  }, [configurations, activeTab, selectedConfig, onConfigChange]);

  // 當切換tab時，自動選擇該類型的第一個配置
  useEffect(() => {
    if (
      activeTab &&
      scholarshipGroups[activeTab] &&
      scholarshipGroups[activeTab].length > 0
    ) {
      const groupConfigs = scholarshipGroups[activeTab];
      // 如果當前選中的配置不在這個組中，切換到該組的第一個配置
      if (
        !selectedConfig ||
        !groupConfigs.find(c => c.id === selectedConfig.id)
      ) {
        const firstConfig = groupConfigs[0];
        setSelectedConfig(firstConfig);
        onConfigChange?.(firstConfig.id);
        loadWorkflowStats(firstConfig.id);
      }
    }
  }, [activeTab, scholarshipGroups, selectedConfig, onConfigChange]);

  // 當選中的配置改變時更新
  useEffect(() => {
    if (selectedConfigId && configurations.length > 0) {
      const config = configurations.find(c => c.id === selectedConfigId);
      if (config) {
        setSelectedConfig(config);
        loadWorkflowStats(config.id);
      }
    } else if (configurations.length > 0 && !selectedConfig) {
      // 預設選擇第一個配置
      setSelectedConfig(configurations[0]);
      loadWorkflowStats(configurations[0].id);
      onConfigChange?.(configurations[0].id);
    }
  }, [selectedConfigId, configurations]);

  // 載入工作流程統計資料
  const loadWorkflowStats = async (configId: number) => {
    setLoading(true);
    try {
      const config = configurations.find(c => c.id === configId);
      if (!config) {
        console.warn("Configuration not found for id:", configId);
        setStats(null);
        return;
      }

      // 使用 scholarship_type_code 獲取申請資料
      const response = await apiClient.admin.getApplicationsByScholarship(
        config.scholarship_type_code
      );

      if (response.success && response.data) {
        const applications = response.data;

        // 計算統計資料
        const totalApplications = applications.length;

        // 計算待審核數量 (pending_review, under_review 狀態)
        const pendingReviews = applications.filter(
          app =>
            app.status === "pending_review" ||
            app.status === "under_review" ||
            app.status === "professor_review_pending" ||
            app.status === "college_review_pending"
        ).length;

        // 判斷當前階段
        const now = new Date();
        let currentStage = "未開始";
        let nextDeadline: Date | undefined;

        // 判斷目前處於哪個階段
        if (
          config.renewal_application_start_date &&
          config.renewal_application_end_date
        ) {
          const renewalStart = new Date(config.renewal_application_start_date);
          const renewalEnd = new Date(config.renewal_application_end_date);
          if (now >= renewalStart && now <= renewalEnd) {
            currentStage = "續領申請期";
            nextDeadline = renewalEnd;
          }
        }

        if (config.application_start_date && config.application_end_date) {
          const appStart = new Date(config.application_start_date);
          const appEnd = new Date(config.application_end_date);
          if (now >= appStart && now <= appEnd) {
            currentStage = "一般申請期";
            nextDeadline = appEnd;
          }
        }

        if (config.professor_review_start && config.professor_review_end) {
          const profStart = new Date(config.professor_review_start);
          const profEnd = new Date(config.professor_review_end);
          if (now >= profStart && now <= profEnd) {
            currentStage = "教授審查階段";
            nextDeadline = profEnd;
          }
        }

        if (config.college_review_start && config.college_review_end) {
          const collegeStart = new Date(config.college_review_start);
          const collegeEnd = new Date(config.college_review_end);
          if (now >= collegeStart && now <= collegeEnd) {
            currentStage = "學院審查階段";
            nextDeadline = collegeEnd;
          }
        }

        if (config.review_deadline) {
          const reviewDeadline = new Date(config.review_deadline);
          if (now <= reviewDeadline && currentStage === "未開始") {
            currentStage = "最終審查階段";
            nextDeadline = reviewDeadline;
          }
        }

        setStats({
          totalApplications,
          pendingReviews,
          currentStage,
          nextDeadline,
        });
      } else {
        console.warn("Failed to load applications:", response.message);
        setStats({
          totalApplications: 0,
          pendingReviews: 0,
          currentStage: "資料載入失敗",
          nextDeadline: undefined,
        });
      }
    } catch (error) {
      console.error("Failed to load workflow stats:", error);
      setStats({
        totalApplications: 0,
        pendingReviews: 0,
        currentStage: "載入錯誤",
        nextDeadline: undefined,
      });
    } finally {
      setLoading(false);
    }
  };

  // 輔助函數
  const getStageStatus = (
    startDate?: string | null,
    endDate?: string | null
  ): "completed" | "active" | "pending" | "expired" => {
    if (!startDate || !endDate) return "pending";
    const start = new Date(startDate);
    const end = new Date(endDate);
    const now = new Date();

    if (now < start) return "pending";
    if (now >= start && now <= end) return "active";
    if (now > end) return "expired";
    return "completed";
  };

  const formatDate = (date?: string | null) => {
    if (!date) return "未設定";
    return format(new Date(date), "MM/dd");
  };

  // 準備工作流程階段數據
  const getWorkflowStages = (config: ScholarshipConfiguration) => {
    interface WorkflowStage {
      name: string;
      type: string;
      status: "completed" | "active" | "pending" | "expired";
      period?: string;
    }

    const stages: WorkflowStage[] = [
      {
        name: "開始",
        type: "start",
        status: "completed",
      },
    ];

    // 續領申請階段
    if (config.renewal_application_start_date) {
      stages.push({
        name: "續領申請期",
        type: "renewal_application",
        status: getStageStatus(
          config.renewal_application_start_date,
          config.renewal_application_end_date
        ),
        period: `${formatDate(config.renewal_application_start_date)} - ${formatDate(config.renewal_application_end_date)}`,
      });
    }

    // 一般申請階段
    if (config.application_start_date) {
      stages.push({
        name: "一般申請期",
        type: "application",
        status: getStageStatus(
          config.application_start_date,
          config.application_end_date
        ),
        period: `${formatDate(config.application_start_date)} - ${formatDate(config.application_end_date)}`,
      });
    }

    // 教授審查階段
    if (
      config.requires_professor_recommendation &&
      config.professor_review_start
    ) {
      stages.push({
        name: "教授審查",
        type: "professor_review",
        status: getStageStatus(
          config.professor_review_start,
          config.professor_review_end
        ),
        period: `${formatDate(config.professor_review_start)} - ${formatDate(config.professor_review_end)}`,
      });
    }

    // 學院審查階段
    if (config.requires_college_review && config.college_review_start) {
      stages.push({
        name: "學院審查",
        type: "college_review",
        status: getStageStatus(
          config.college_review_start,
          config.college_review_end
        ),
        period: `${formatDate(config.college_review_start)} - ${formatDate(config.college_review_end)}`,
      });
    }

    // 最終審查
    stages.push({
      name: "最終審查",
      type: "final_review",
      status: "pending",
      period: config.review_deadline
        ? `截止: ${formatDate(config.review_deadline)}`
        : "",
    });

    // 結果公告
    stages.push({
      name: "結果公告",
      type: "result",
      status: "pending",
    });

    return stages;
  };

  // 重新載入數據
  const refreshData = async () => {
    if (selectedConfig) {
      await loadWorkflowStats(selectedConfig.id);
    }
  };

  // 查看特定階段的詳細資料
  const viewStageDetails = async (stageName: string) => {
    if (!selectedConfig) return;

    setSelectedStage(stageName);
    setLoading(true);

    try {
      const response = await apiClient.admin.getApplicationsByScholarship(
        selectedConfig.scholarship_type_code
      );
      if (response.success && response.data) {
        // 根據階段篩選申請
        let filteredApplications = response.data;

        // 可以根據 stageName 和當前時間來篩選相關的申請
        if (stageName.includes("申請")) {
          filteredApplications = response.data.filter(
            app => app.status === "submitted" || app.status === "under_review"
          );
        } else if (stageName.includes("教授")) {
          filteredApplications = response.data.filter(
            app =>
              app.status === "professor_review_pending" ||
              app.status === "professor_reviewed"
          );
        } else if (stageName.includes("學院")) {
          filteredApplications = response.data.filter(
            app =>
              app.status === "college_review_pending" ||
              app.status === "college_reviewed"
          );
        }

        setStageApplications(filteredApplications);
        setShowStageDetails(true);
      }
    } catch (error) {
      console.error("Failed to load stage details:", error);
    } finally {
      setLoading(false);
    }
  };

  // 匯出流程圖 (匯出為 JSON 數據)
  const exportDiagram = async () => {
    if (!selectedConfig) return;

    const workflowData = {
      configName: selectedConfig.config_name,
      academicYear: selectedConfig.academic_year,
      semester: selectedConfig.semester,
      stages: getWorkflowStages(selectedConfig),
      statistics: stats,
      exportDate: new Date().toISOString(),
    };

    // 創建 JSON 下載
    const jsonData = JSON.stringify(workflowData, null, 2);
    const blob = new Blob([jsonData], { type: "application/json" });
    const url = URL.createObjectURL(blob);

    const downloadLink = document.createElement("a");
    downloadLink.href = url;
    downloadLink.download = `${selectedConfig.config_name || "workflow"}-流程資料.json`;
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
    URL.revokeObjectURL(url);
  };

  if (configurations.length === 0) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <div className="text-center text-gray-500">
            <Calendar className="h-16 w-16 mx-auto mb-4 text-gray-300" />
            <p className="text-lg font-medium">暫無可用的獎學金配置</p>
            <p className="text-sm mt-2">請先建立獎學金配置以查看工作流程</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* 標題區域 */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Calendar className="h-5 w-5" />
                獎學金工作流程
              </CardTitle>
              <CardDescription>按獎學金類型查看流程圖與進度</CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={refreshData}
                disabled={loading}
              >
                <RefreshCw
                  className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`}
                />
                重新載入
              </Button>
              <Button variant="outline" size="sm" onClick={exportDiagram}>
                <Download className="h-4 w-4 mr-2" />
                匯出流程圖
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Tab區域 */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="flex w-full">
          {Object.keys(scholarshipGroups).map(typeName => (
            <TabsTrigger
              key={typeName}
              value={typeName}
              className="flex-1 flex items-center justify-center gap-2"
            >
              <span>{typeName}</span>
              <Badge variant="secondary" className="text-xs">
                {scholarshipGroups[typeName].length}
              </Badge>
            </TabsTrigger>
          ))}
        </TabsList>

        {Object.keys(scholarshipGroups).map(typeName => (
          <TabsContent
            key={typeName}
            value={typeName}
            className="space-y-4 mt-6"
          >
            <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
              <h3 className="text-lg font-semibold text-blue-900 mb-2">
                {typeName}
              </h3>
              <p className="text-sm text-blue-700">
                此類型共有 {scholarshipGroups[typeName].length} 個配置
              </p>
            </div>

            <Card>
              <CardContent className="pt-6">
                <div className="flex items-center gap-4 mb-4">
                  <label className="text-sm font-medium text-gray-700">
                    選擇配置：
                  </label>
                  <Select
                    value={selectedConfig?.id.toString() || ""}
                    onValueChange={value => {
                      const configId = parseInt(value);
                      const config = scholarshipGroups[typeName].find(
                        c => c.id === configId
                      );
                      if (config) {
                        setSelectedConfig(config);
                        loadWorkflowStats(configId);
                        onConfigChange?.(configId);
                      }
                    }}
                  >
                    <SelectTrigger className="w-80">
                      <SelectValue placeholder="請選擇獎學金配置" />
                    </SelectTrigger>
                    <SelectContent>
                      {scholarshipGroups[typeName].map(config => (
                        <SelectItem
                          key={config.id}
                          value={config.id.toString()}
                        >
                          {config.config_name} ({config.academic_year}
                          {config.semester && `-${config.semester}`})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* 統計資訊 */}
                {stats && (
                  <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
                    <div
                      className="bg-blue-50 p-3 rounded-lg border border-blue-200 cursor-pointer hover:bg-blue-100 transition-colors"
                      onClick={() => viewStageDetails("所有申請")}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Users className="h-4 w-4 text-blue-600" />
                          <span className="text-sm font-medium text-blue-800">
                            總申請數
                          </span>
                        </div>
                        <ChevronRight className="h-3 w-3 text-blue-600" />
                      </div>
                      <p className="text-2xl font-bold text-blue-900">
                        {stats.totalApplications}
                      </p>
                    </div>
                    <div
                      className="bg-orange-50 p-3 rounded-lg border border-orange-200 cursor-pointer hover:bg-orange-100 transition-colors"
                      onClick={() => viewStageDetails("待審核申請")}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Clock className="h-4 w-4 text-orange-600" />
                          <span className="text-sm font-medium text-orange-800">
                            待審核
                          </span>
                        </div>
                        <ChevronRight className="h-3 w-3 text-orange-600" />
                      </div>
                      <p className="text-2xl font-bold text-orange-900">
                        {stats.pendingReviews}
                      </p>
                    </div>
                    <div className="bg-green-50 p-3 rounded-lg border border-green-200">
                      <div className="flex items-center gap-2">
                        <Info className="h-4 w-4 text-green-600" />
                        <span className="text-sm font-medium text-green-800">
                          當前階段
                        </span>
                      </div>
                      <p className="text-sm font-medium text-green-900">
                        {stats.currentStage}
                      </p>
                    </div>
                    <div className="bg-purple-50 p-3 rounded-lg border border-purple-200">
                      <div className="flex items-center gap-2">
                        <Calendar className="h-4 w-4 text-purple-600" />
                        <span className="text-sm font-medium text-purple-800">
                          下次截止
                        </span>
                      </div>
                      <p className="text-sm font-medium text-purple-900">
                        {stats.nextDeadline
                          ? format(stats.nextDeadline, "MM/dd")
                          : "無"}
                      </p>
                    </div>
                  </div>
                )}

                {/* 流程圖區域 */}
                {selectedConfig && (
                  <Card>
                    <CardHeader>
                      <CardTitle>
                        {selectedConfig?.config_name} - 流程圖
                      </CardTitle>
                      <CardDescription>
                        {selectedConfig?.academic_year}學年度
                        {selectedConfig?.semester &&
                          ` ${selectedConfig.semester}學期`}
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      {loading ? (
                        <div className="flex items-center justify-center py-12">
                          <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent"></div>
                        </div>
                      ) : selectedConfig ? (
                        <div className="w-full overflow-x-auto">
                          <div className="bg-gray-50 p-6 rounded-lg border">
                            <div className="text-center mb-6">
                              <h3 className="text-lg font-semibold text-gray-700">
                                {selectedConfig.config_name} 工作流程
                              </h3>
                              <p className="text-sm text-gray-500">
                                顯示獎學金申請與審查流程
                              </p>
                            </div>

                            <div className="space-y-4">
                              {getWorkflowStages(selectedConfig).map(
                                (stage: any, index: number, array: any[]) => (
                                  <div
                                    key={index}
                                    className="flex items-center"
                                  >
                                    <div
                                      className={`
                        min-w-0 flex-1 p-4 rounded-lg border-l-4
                        ${stage.status === "completed" ? "bg-green-50 border-green-500" : ""}
                        ${stage.status === "active" ? "bg-blue-50 border-blue-500" : ""}
                        ${stage.status === "pending" ? "bg-gray-50 border-gray-300" : ""}
                        ${stage.status === "expired" ? "bg-red-50 border-red-500" : ""}
                      `}
                                    >
                                      <div className="flex items-center justify-between">
                                        <div>
                                          <h4 className="font-medium text-gray-900">
                                            {stage.name}
                                          </h4>
                                          {stage.period && (
                                            <p className="text-sm text-gray-600 mt-1">
                                              {stage.period}
                                            </p>
                                          )}
                                        </div>
                                        <div
                                          className={`
                            px-2 py-1 rounded text-xs font-medium
                            ${stage.status === "completed" ? "bg-green-100 text-green-800" : ""}
                            ${stage.status === "active" ? "bg-blue-100 text-blue-800" : ""}
                            ${stage.status === "pending" ? "bg-gray-100 text-gray-600" : ""}
                            ${stage.status === "expired" ? "bg-red-100 text-red-800" : ""}
                          `}
                                        >
                                          {stage.status === "completed" &&
                                            "已完成"}
                                          {stage.status === "active" &&
                                            "進行中"}
                                          {stage.status === "pending" &&
                                            "未開始"}
                                          {stage.status === "expired" &&
                                            "已過期"}
                                        </div>
                                      </div>
                                    </div>

                                    {index < array.length - 1 && (
                                      <div className="flex flex-col items-center mx-4">
                                        <div className="w-0.5 h-8 bg-gray-300"></div>
                                        <ChevronRight className="h-4 w-4 text-gray-400" />
                                        <div className="w-0.5 h-8 bg-gray-300"></div>
                                      </div>
                                    )}
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-center justify-center py-12 text-gray-500">
                          <p>請選擇獎學金配置以查看工作流程</p>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                )}

                {/* 圖例說明 */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">圖例說明</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="flex flex-wrap gap-4 text-sm">
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-green-500 rounded"></div>
                        <span>已完成階段</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-blue-500 rounded"></div>
                        <span>進行中階段</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-gray-500 rounded"></div>
                        <span>未開始階段</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-red-500 rounded"></div>
                        <span>已過期階段</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-yellow-500 rounded"></div>
                        <span>決策節點</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      {/* 階段詳細資料對話框 */}
      <Dialog open={showStageDetails} onOpenChange={setShowStageDetails}>
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Info className="h-5 w-5" />
              {selectedStage} - 詳細資料
            </DialogTitle>
            <DialogDescription>
              {selectedConfig?.config_name} 中的 {selectedStage} 申請列表
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <Badge variant="outline">
                共 {stageApplications.length} 筆申請
              </Badge>
            </div>

            {stageApplications.length > 0 ? (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>申請編號</TableHead>
                    <TableHead>學生姓名</TableHead>
                    <TableHead>學號</TableHead>
                    <TableHead>狀態</TableHead>
                    <TableHead>申請時間</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stageApplications.map((app: any) => (
                    <TableRow key={app.id}>
                      <TableCell className="font-medium">#{app.id}</TableCell>
                      <TableCell>{app.student?.name || "N/A"}</TableCell>
                      <TableCell>{app.student?.nycu_id || "N/A"}</TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            app.status === "approved"
                              ? "default"
                              : app.status === "rejected"
                                ? "destructive"
                                : app.status === "under_review"
                                  ? "secondary"
                                  : "outline"
                          }
                        >
                          {app.status === "submitted" && "已提交"}
                          {app.status === "under_review" && "審核中"}
                          {app.status === "professor_review_pending" &&
                            "教授審核中"}
                          {app.status === "college_review_pending" &&
                            "學院審核中"}
                          {app.status === "approved" && "已核准"}
                          {app.status === "rejected" && "已拒絕"}
                          {![
                            "submitted",
                            "under_review",
                            "professor_review_pending",
                            "college_review_pending",
                            "approved",
                            "rejected",
                          ].includes(app.status) && app.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {app.created_at
                          ? format(new Date(app.created_at), "yyyy/MM/dd HH:mm")
                          : "N/A"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <Users className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                <p className="text-lg font-medium">此階段暫無申請資料</p>
                <p className="text-sm mt-2">可能還沒有申請進入此階段</p>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
