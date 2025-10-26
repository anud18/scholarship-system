/**
 * Main quota management component for admin interface
 */

import { MatrixQuotaTable } from "@/components/quota/matrix-quota-table";
import {
  QuotaStatsCard,
  QuotaStatsGroup,
} from "@/components/quota/quota-stats-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { useAuth } from "@/hooks/use-auth";
import { useQuotaData } from "@/hooks/use-quota-data";
import apiClient from "@/lib/api";
import { calculateUsagePercentage, quotaApi } from "@/services/api/quotaApi";
import {
  AvailablePeriod,
  getWarningLevel,
  MatrixQuotaData,
} from "@/types/quota";
import {
  AlertCircle,
  BookOpen,
  Calendar,
  Download,
  Info,
  RefreshCw,
  TrendingUp,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

export function QuotaManagement() {  const { user } = useAuth();
  // State management
  const [availablePeriods, setAvailablePeriods] = useState<AvailablePeriod[]>(
    []
  );
  const [selectedPeriod, setSelectedPeriod] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [hasPermission, setHasPermission] = useState(false);
  const [checkingPermission, setCheckingPermission] = useState(true);
  const [forceUpdateCounter, setForceUpdateCounter] = useState(0);

  // Use SWR for quota data fetching with automatic refresh
  const {
    data: matrixData,
    isLoading: loading,
    isRefreshing: refreshing,
    error: swrError,
    refresh,
  } = useQuotaData(selectedPeriod);

  // Track last update time
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  // Check permissions on mount
  useEffect(() => {
    checkUserPermission();
  }, []);

  // Fetch available periods on mount (only if user has permission)
  useEffect(() => {
    if (hasPermission) {
      fetchAvailablePeriods();
    }
  }, [hasPermission]);

  // Update last update time when data changes
  useEffect(() => {
    if (matrixData) {
      setLastUpdate(new Date());
      setForceUpdateCounter(prev => prev + 1);
    }
  }, [matrixData]);

  // Sync SWR error with component error state
  useEffect(() => {
    if (swrError) {
      setError(swrError instanceof Error ? swrError.message : "載入配額資料時發生錯誤");
    } else if (matrixData) {
      setError(null);
    }
  }, [swrError, matrixData]);

  const checkUserPermission = async () => {
    setCheckingPermission(true);
    console.log("🔍 Checking quota management permissions for user:", user);

    try {
      // First check if user is super_admin - they always have access
      if (user?.role === "super_admin") {
        console.log("✅ User is super_admin, granting access");
        setHasPermission(true);
        setCheckingPermission(false);
        return;
      }

      // For admin users, check their scholarship permissions
      if (user?.role === "admin") {
        console.log(
          "🔍 Checking admin permissions via scholarship permissions API"
        );
        try {
          const response =
            await apiClient.admin.getCurrentUserScholarshipPermissions();
          console.log("📊 Scholarship permissions response:", response);

          if (response.success && response.data) {
            const hasPerms = response.data.length > 0;
            console.log(
              hasPerms
                ? "✅ Admin has scholarship permissions"
                : "❌ Admin has no scholarship permissions"
            );
            setHasPermission(hasPerms);
          } else {
            console.log("❌ Admin permission check failed:", response.message);
            setHasPermission(false);
          }
        } catch (permError) {
          console.error("❌ Admin permission check error:", permError);
          setHasPermission(false);
        }
      } else {
        // Other roles don't have access
        console.log(
          "❌ User role not authorized for quota management:",
          user?.role
        );
        setHasPermission(false);
      }
    } catch (error) {
      console.error("❌ Overall permission check failed:", error);
      setHasPermission(false);
    } finally {
      setCheckingPermission(false);
    }
  };

  const fetchAvailablePeriods = async () => {
    try {
      const response = await quotaApi.getAvailableSemesters("matrix_based");
      if (response.success && response.data) {
        setAvailablePeriods(response.data);
        // Select the most recent period by default
        if (response.data.length > 0) {
          setSelectedPeriod(response.data[0]);
        }
      } else {
        throw new Error(response.message || "無法載入可用學期");
      }
    } catch (error) {
      console.error("Error fetching available periods:", error);
      setError("無法載入可用學期資料");
      toast.error("無法載入可用學期資料");
    }
  };

  const handleRefresh = useCallback(async () => {
    if (!selectedPeriod || refreshing) return;

    try {
      await refresh();
      toast.success("配額資料已更新");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "無法更新配額資料");
    }
  }, [selectedPeriod, refreshing, refresh, toast]);

  const handleExport = async () => {
    if (!selectedPeriod) return;

    try {
      const blob = await quotaApi.exportQuotaData(selectedPeriod, "csv");
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `quota-data-${selectedPeriod}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast.success("配額資料已匯出");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "無法匯出配額資料");
    }
  };

  const handleDataUpdate = (_newData: MatrixQuotaData) => {
    // SWR will automatically update the data after the API call completes
    // We just need to update the timestamp and force recalculation
    setLastUpdate(new Date());
    setForceUpdateCounter(prev => prev + 1);

    // Trigger SWR revalidation to sync with server
    refresh();
  };

  // Calculate statistics
  const calculateStats = () => {
    if (!matrixData) {
      return {
        totalQuota: 0,
        totalUsed: 0,
        totalAvailable: 0,
        usagePercentage: 0,
        warningLevel: "normal" as const,
      };
    }

    const { total_quota, total_used, total_available } = matrixData.grand_total;
    const usagePercentage = calculateUsagePercentage(total_used, total_quota);
    const warningLevel = getWarningLevel(usagePercentage);

    return {
      totalQuota: total_quota,
      totalUsed: total_used,
      totalAvailable: total_available,
      usagePercentage,
      warningLevel,
    };
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const stats = useMemo(
    () => calculateStats(),
    [matrixData, forceUpdateCounter]
  );

  // Show loading while checking permissions
  if (checkingPermission) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center space-y-4">
          <RefreshCw className="h-8 w-8 animate-spin mx-auto text-gray-400" />
          <p className="text-gray-500">檢查權限中...</p>
        </div>
      </div>
    );
  }

  // Show access denied if no permission
  if (!hasPermission) {
    return (
      <div className="flex items-center justify-center py-12">
        <Card className="max-w-md">
          <CardHeader className="text-center">
            <AlertCircle className="h-12 w-12 mx-auto text-red-500 mb-4" />
            <CardTitle className="text-red-600">存取被拒絕</CardTitle>
            <CardDescription>
              您沒有權限存取名額管理功能。請聯繫系統管理員為您分配相關獎學金的管理權限。
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-2xl">博士獎學金配額管理</CardTitle>
              <CardDescription>
                管理各學院博士獎學金配額分配（矩陣式配額）
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="text-xs">
                <Calendar className="h-3 w-3 mr-1" />
                最後更新: {lastUpdate.toLocaleTimeString("zh-TW")}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col sm:flex-row gap-4">
            <Select value={selectedPeriod} onValueChange={setSelectedPeriod}>
              <SelectTrigger className="w-full sm:w-[200px]">
                <SelectValue placeholder="選擇學年度" />
              </SelectTrigger>
              <SelectContent>
                {availablePeriods.map(period => (
                  <SelectItem key={period} value={period}>
                    {period.includes("-")
                      ? `${period} 學期`
                      : `${period} 學年度`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRefresh}
                disabled={refreshing || !selectedPeriod}
              >
                <RefreshCw
                  className={cn("h-4 w-4 mr-2", refreshing && "animate-spin")}
                />
                重新整理
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={handleExport}
                disabled={!matrixData || !selectedPeriod}
              >
                <Download className="h-4 w-4 mr-2" />
                匯出 CSV
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>錯誤</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Info Alert */}
      {selectedPeriod && !loading && !error && (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>操作提示</AlertTitle>
          <AlertDescription>
            點擊表格中的配額數字可直接編輯。系統會自動計算總計並即時儲存變更。
          </AlertDescription>
        </Alert>
      )}

      {/* Statistics Cards */}
      {loading ? (
        <QuotaStatsGroup>
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
          <Skeleton className="h-32" />
        </QuotaStatsGroup>
      ) : (
        <QuotaStatsGroup>
          <QuotaStatsCard
            title="總配額"
            value={stats.totalQuota}
            subtitle="所有子類型與學院總和"
            icon={<BookOpen className="h-4 w-4 text-blue-600" />}
          />
          <QuotaStatsCard
            title="已使用"
            value={stats.totalUsed}
            subtitle={`佔總配額 ${stats.usagePercentage}%`}
            percentage={stats.usagePercentage}
            status={stats.warningLevel}
            icon={<Users className="h-4 w-4 text-orange-600" />}
          />
          <QuotaStatsCard
            title="剩餘配額"
            value={stats.totalAvailable}
            subtitle="可供分配名額"
            trend={stats.totalAvailable > 10 ? "up" : "down"}
            icon={<TrendingUp className="h-4 w-4 text-green-600" />}
          />
          <QuotaStatsCard
            title="使用率"
            value={`${stats.usagePercentage}%`}
            subtitle="配額使用狀況"
            percentage={stats.usagePercentage}
            status={stats.warningLevel}
          />
        </QuotaStatsGroup>
      )}

      {/* Matrix Quota Table */}
      <Card>
        <CardHeader>
          <CardTitle>配額分配矩陣</CardTitle>
          <CardDescription>
            各子類型（國科會、教育部）與學院的配額分配表
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <MatrixQuotaTable
            data={matrixData}
            loading={loading}
            onDataUpdate={handleDataUpdate}
            readOnly={false}
            currentPeriod={selectedPeriod}
          />
        </CardContent>
      </Card>
    </div>
  );
}

// Helper function for className concatenation
function cn(...classes: (string | boolean | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}
