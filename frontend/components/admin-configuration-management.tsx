"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import {
  Plus,
  Edit,
  Copy,
  Trash2,
  AlertCircle,
  Search,
  Calendar,
  DollarSign,
  Eye,
  FileText,
  Clock,
  Info,
} from "lucide-react";
import { format } from "date-fns";
import { zhTW } from "date-fns/locale";
import apiClient, {
  ScholarshipType,
  ScholarshipConfiguration,
  ScholarshipConfigurationFormData,
} from "@/lib/api";
import { WhitelistManagementDialog } from "./whitelist-management-dialog";
import { QuotaManagementMode, getQuotaManagementModeLabel } from "@/lib/enums";
const api = apiClient;

interface AdminConfigurationManagementProps {
  scholarshipTypes: ScholarshipType[];
  onScholarshipTypeUpdate?: (id: number, updates: Partial<ScholarshipType>) => void;
}

export function AdminConfigurationManagement({
  scholarshipTypes,
  onScholarshipTypeUpdate,
}: AdminConfigurationManagementProps) {
  // State for configurations and UI
  const [configurations, setConfigurations] = useState<
    ScholarshipConfiguration[]
  >([]);
  const [filteredConfigurations, setFilteredConfigurations] = useState<
    ScholarshipConfiguration[]
  >([]);
  const [selectedScholarshipType, setSelectedScholarshipType] =
    useState<ScholarshipType | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [academyCodes, setAcademyCodes] = useState<Record<string, string>>({});

  // Calculate current ROC year dynamically
  const currentROCYear = new Date().getFullYear() - 1911;
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error";
  } | null>(null);

  // Dialog states
  const [showViewDialog, setShowViewDialog] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const [showCodeTableDialog, setShowCodeTableDialog] = useState(false);
  const [showWhitelistDialog, setShowWhitelistDialog] = useState(false);
  const [selectedConfig, setSelectedConfig] =
    useState<ScholarshipConfiguration | null>(null);

  // Form state
  const [formData, setFormData] = useState<
    Partial<ScholarshipConfigurationFormData>
  >({});
  const [formLoading, setFormLoading] = useState(false);

  // Toast helper functions
  const showToast = (message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 5000);
  };

  const showSuccessToast = (message: string) => showToast(message, "success");
  const showErrorToast = (message: string) => showToast(message, "error");

  // Academic year options (generate based on current year)
  const currentYear = new Date().getFullYear();
  const taiwanYear = currentYear - 1911;
  const academicYears = Array.from({ length: 5 }, (_, i) => taiwanYear - 2 + i);

  // Load academy codes from database
  useEffect(() => {
    const loadAcademyCodes = async () => {
      try {
        const response = await api.referenceData.getAcademies();
        if (response.success && response.data) {
          const codesMap: Record<string, string> = {};
          response.data.forEach(academy => {
            codesMap[academy.code] = academy.name;
          });
          setAcademyCodes(codesMap);
        }
      } catch (error) {
        console.error("載入學院代碼失敗:", error);
        showErrorToast("載入學院代碼失敗: " + (error as Error).message);
      }
    };

    loadAcademyCodes();
  }, []);

  // Auto-select first scholarship type
  useEffect(() => {
    if (scholarshipTypes.length > 0 && !selectedScholarshipType) {
      setSelectedScholarshipType(scholarshipTypes[0]);
    }
  }, [scholarshipTypes, selectedScholarshipType]);

  // Load configurations when scholarship type changes
  useEffect(() => {
    if (selectedScholarshipType) {
      loadConfigurations(selectedScholarshipType);
    }
  }, [selectedScholarshipType]);

  // Debounce search term
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 400);

    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Memoized filtering
  const filteredAndSortedConfigurations = useMemo(() => {
    let filtered = configurations;

    if (debouncedSearchTerm) {
      const searchLower = debouncedSearchTerm.toLowerCase();
      filtered = filtered.filter(
        config =>
          config.config_name.toLowerCase().includes(searchLower) ||
          (config.config_code &&
            config.config_code.toLowerCase().includes(searchLower)) ||
          (config.description &&
            config.description.toLowerCase().includes(searchLower))
      );
    }

    return filtered.sort((a, b) => {
      if (a.academic_year !== b.academic_year) {
        return (b.academic_year || 0) - (a.academic_year || 0);
      }
      const semesterOrder = {
        second: 0,
        "2": 0,
        first: 1,
        "1": 1,
        null: 2,
        undefined: 2,
      };
      const aOrder =
        semesterOrder[a.semester as keyof typeof semesterOrder] ?? 2;
      const bOrder =
        semesterOrder[b.semester as keyof typeof semesterOrder] ?? 2;
      return aOrder - bOrder;
    });
  }, [configurations, debouncedSearchTerm]);

  // Update filtered configurations when computation changes
  useEffect(() => {
    setFilteredConfigurations(filteredAndSortedConfigurations);
  }, [filteredAndSortedConfigurations]);

  const loadConfigurations = useCallback(
    async (scholarshipType: ScholarshipType) => {
      if (!scholarshipType) return;

      setLoading(true);
      try {
        // 發出兩次請求：一次獲取啟用的配置，一次獲取未啟用的配置
        const [activeResponse, inactiveResponse] = await Promise.all([
          api.admin.getScholarshipConfigurations({
            scholarship_type_id: scholarshipType.id,
            is_active: true,
          }),
          api.admin.getScholarshipConfigurations({
            scholarship_type_id: scholarshipType.id,
            is_active: false,
          }),
        ]);

        const allConfigurations = [
          ...(activeResponse.success ? activeResponse.data || [] : []),
          ...(inactiveResponse.success ? inactiveResponse.data || [] : []),
        ];

        setConfigurations(allConfigurations);
      } catch (error) {
        console.error("載入配置失敗:", error);
        showErrorToast("載入配置失敗: " + (error as Error).message);
        setConfigurations([]);
        setFilteredConfigurations([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleCreateConfig = async () => {
    try {
      setFormLoading(true);

      // 根據 quota_management_mode 自動推導 has_quota_limit 和 has_college_quota
      const quotaMode = formData.quota_management_mode || "none";
      const processedData = {
        ...formData,
        has_quota_limit: quotaMode !== "none",
        has_college_quota: quotaMode === "college_based" || quotaMode === "matrix_based",
      };

      const response = await api.admin.createScholarshipConfiguration(
        processedData as ScholarshipConfigurationFormData
      );
      if (response.success) {
        setShowCreateDialog(false);
        setFormData({});
        await loadConfigurations(selectedScholarshipType!);
        showSuccessToast("配置建立成功");
      }
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        "建立配置失敗";
      showErrorToast("建立配置失敗: " + errorMessage);
    } finally {
      setFormLoading(false);
    }
  };

  const handleUpdateConfig = async () => {
    if (!selectedConfig) return;

    try {
      setFormLoading(true);

      // 根據 quota_management_mode 自動推導 has_quota_limit 和 has_college_quota
      const quotaMode = formData.quota_management_mode || "none";
      const processedData = {
        ...formData,
        has_quota_limit: quotaMode !== "none",
        has_college_quota: quotaMode === "college_based" || quotaMode === "matrix_based",
      };

      const response = await api.admin.updateScholarshipConfiguration(
        selectedConfig.id,
        processedData
      );
      if (response.success) {
        setShowEditDialog(false);
        setSelectedConfig(null);
        setFormData({});
        await loadConfigurations(selectedScholarshipType!);
        showSuccessToast("配置更新成功");
      }
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        "更新配置失敗";
      showErrorToast("更新配置失敗: " + errorMessage);
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteConfig = async () => {
    if (!selectedConfig) return;

    try {
      setFormLoading(true);
      const response = await api.admin.deleteScholarshipConfiguration(
        selectedConfig.id
      );
      if (response.success) {
        setShowDeleteDialog(false);
        setSelectedConfig(null);
        await loadConfigurations(selectedScholarshipType!);
        showSuccessToast("配置刪除成功");
      }
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        "刪除配置失敗";
      showErrorToast("刪除配置失敗: " + errorMessage);
    } finally {
      setFormLoading(false);
    }
  };

  const handleDuplicateConfig = async () => {
    if (!selectedConfig) return;

    try {
      setFormLoading(true);
      const targetData = {
        academic_year: formData.academic_year!,
        semester: formData.semester,
        config_code: formData.config_code!,
        config_name: formData.config_name,
      };
      const response = await api.admin.duplicateScholarshipConfiguration(
        selectedConfig.id,
        targetData
      );
      if (response.success) {
        setShowDuplicateDialog(false);
        setSelectedConfig(null);
        setFormData({});
        await loadConfigurations(selectedScholarshipType!);
        showSuccessToast("配置複製成功");
      }
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        "複製配置失敗";
      showErrorToast("複製配置失敗: " + errorMessage);
    } finally {
      setFormLoading(false);
    }
  };

  const handleToggleWhitelist = async (enabled: boolean) => {
    if (!selectedScholarshipType) return;

    try {
      const response = await api.whitelist.toggleScholarshipWhitelist(
        selectedScholarshipType.id,
        enabled
      );
      if (response.success) {
        // Update local state
        setSelectedScholarshipType(prev =>
          prev ? { ...prev, whitelist_enabled: enabled } : prev
        );
        // Update parent component's scholarshipTypes state
        onScholarshipTypeUpdate?.(selectedScholarshipType.id, { whitelist_enabled: enabled });
        showSuccessToast(`申請白名單已${enabled ? "啟用" : "停用"}`);
      }
    } catch (error: any) {
      const errorMessage = error.message || "切換申請白名單狀態失敗";
      showErrorToast("操作失敗: " + errorMessage);
    }
  };

  const handleCreateConfiguration = () => {
    if (!selectedScholarshipType) return;
    setFormData({
      scholarship_type_id: selectedScholarshipType.id,
      academic_year: taiwanYear,
      semester: "first",
      currency: "TWD",
      is_active: true,
      version: "1.0",
      has_quota_limit: false,
      has_college_quota: false,
      quota_management_mode: "none",
      total_quota: 0,
      quotas: {},
      whitelist_student_ids: {},
    });
    setShowCreateDialog(true);
  };

  const openViewDialog = async (config: ScholarshipConfiguration) => {
    try {
      // Refetch the latest configuration to ensure quotas and other data are up-to-date
      const response = await api.admin.getScholarshipConfiguration(config.id);
      if (response.success && response.data) {
        setSelectedConfig(response.data);
        setShowViewDialog(true);
      } else {
        showErrorToast("無法載入配置詳情");
      }
    } catch (error: any) {
      const errorMessage =
        error.response?.data?.message ||
        error.response?.data?.detail ||
        "載入配置詳情失敗";
      showErrorToast(errorMessage);
    }
  };

  const openEditDialog = (config: ScholarshipConfiguration) => {
    setSelectedConfig(config);
    setFormData({
      config_name: config.config_name,
      config_code: config.config_code,
      description: config.description || "",
      description_en: config.description_en || "",
      amount: config.amount,
      currency: config.currency,
      has_quota_limit: config.has_quota_limit || false,
      has_college_quota: config.has_college_quota || false,
      quota_management_mode: config.quota_management_mode || "none",
      total_quota: config.total_quota,
      quotas: config.quotas,
      whitelist_student_ids: config.whitelist_student_ids,
      renewal_application_start_date: formatDateTimeLocal(
        config.renewal_application_start_date
      ),
      renewal_application_end_date: formatDateTimeLocal(
        config.renewal_application_end_date
      ),
      application_start_date: formatDateTimeLocal(
        config.application_start_date
      ),
      application_end_date: formatDateTimeLocal(config.application_end_date),
      renewal_professor_review_start: formatDateTimeLocal(
        config.renewal_professor_review_start
      ),
      renewal_professor_review_end: formatDateTimeLocal(
        config.renewal_professor_review_end
      ),
      renewal_college_review_start: formatDateTimeLocal(
        config.renewal_college_review_start
      ),
      renewal_college_review_end: formatDateTimeLocal(
        config.renewal_college_review_end
      ),
      requires_professor_recommendation:
        config.requires_professor_recommendation,
      professor_review_start: formatDateTimeLocal(
        config.professor_review_start
      ),
      professor_review_end: formatDateTimeLocal(config.professor_review_end),
      requires_college_review: config.requires_college_review,
      college_review_start: formatDateTimeLocal(config.college_review_start),
      college_review_end: formatDateTimeLocal(config.college_review_end),
      review_deadline: formatDateTimeLocal(config.review_deadline),
      is_active: config.is_active,
      effective_start_date: formatDateTimeLocal(config.effective_start_date),
      effective_end_date: formatDateTimeLocal(config.effective_end_date),
      version: config.version,
    });
    setShowEditDialog(true);
  };

  const openDuplicateDialog = (config: ScholarshipConfiguration) => {
    setSelectedConfig(config);
    const nextYear = (config.academic_year || taiwanYear) + 1;
    setFormData({
      academic_year: nextYear,
      semester: config.semester,
      config_code: `${config.config_code}-${nextYear}`,
      config_name: `${config.config_name} (複製)`,
    });
    setShowDuplicateDialog(true);
  };

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return "-";
    try {
      return format(new Date(dateString), "yyyy/MM/dd", { locale: zhTW });
    } catch {
      return "-";
    }
  };

  const formatDateTime = (dateString: string | null | undefined) => {
    if (!dateString) {
      return "未設定";
    }
    try {
      const date = new Date(dateString);
      return format(date, "yyyy年MM月dd日 HH:mm", { locale: zhTW });
    } catch (error) {
      return "無效日期";
    }
  };

  // 格式化日期時間字符串為 datetime-local 輸入格式 (YYYY-MM-DDTHH:mm)
  const formatDateTimeLocal = (dateString: string | null | undefined) => {
    if (!dateString) return "";
    try {
      const date = new Date(dateString);
      // 檢查日期是否有效
      if (isNaN(date.getTime())) {
        console.warn("Invalid date string:", dateString);
        return "";
      }

      // 使用本地時間
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      const hours = String(date.getHours()).padStart(2, "0");
      const minutes = String(date.getMinutes()).padStart(2, "0");

      return `${year}-${month}-${day}T${hours}:${minutes}`;
    } catch (error) {
      return "";
    }
  };

  const getSemesterDisplay = (semester: string | null | undefined) => {
    if (!semester) return "全學年";
    if (semester === "first" || semester === "1") return "第一學期";
    if (semester === "second" || semester === "2") return "第二學期";
    return semester;
  };

  if (scholarshipTypes.length === 0) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">尚無獎學金類型</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Scholarship Type Tabs */}
      <Tabs
        value={selectedScholarshipType?.id.toString() || ""}
        onValueChange={value => {
          const type = scholarshipTypes.find(t => t.id.toString() === value);
          setSelectedScholarshipType(type || null);
        }}
      >
        <TabsList className="grid w-full grid-cols-3">
          {scholarshipTypes.map(type => (
            <TabsTrigger key={type.id} value={type.id.toString()}>
              {type.name}
            </TabsTrigger>
          ))}
        </TabsList>

        {scholarshipTypes.map(type => (
          <TabsContent key={type.id} value={type.id.toString()}>
            <Card className="p-6">
              {/* Search Filter */}
              <div className="flex flex-col lg:flex-row gap-4 mb-6">
                <div className="flex-1">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="搜尋配置名稱、代碼或描述..."
                      value={searchTerm}
                      onChange={e => setSearchTerm(e.target.value)}
                      className="pl-8"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button
                    onClick={handleCreateConfiguration}
                    className="nycu-gradient text-white"
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    新增配置
                  </Button>
                </div>
              </div>

              {/* Configuration Table */}
              {loading ? (
                <div className="flex justify-center p-8">
                  <div className="text-muted-foreground">載入中...</div>
                </div>
              ) : filteredConfigurations.length === 0 ? (
                <div className="flex items-center justify-center p-8">
                  <div className="text-center">
                    <FileText className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-muted-foreground">
                      {searchTerm ? "找不到符合條件的配置" : "尚無配置資料"}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="border rounded-md">
                  <table className="w-full">
                    <thead className="border-b bg-muted/50">
                      <tr>
                        <th className="text-left p-4 font-semibold">
                          配置名稱
                        </th>
                        <th className="text-left p-4 font-semibold">
                          學年度/學期
                        </th>
                        <th className="text-left p-4 font-semibold">
                          配置代碼
                        </th>
                        <th className="text-left p-4 font-semibold">
                          申請期間
                        </th>
                        <th className="text-left p-4 font-semibold">狀態</th>
                        <th className="text-right p-4 font-semibold">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredConfigurations.map(config => {
                        return (
                          <tr
                            key={config.id}
                            className="border-b hover:bg-muted/25 transition-colors"
                          >
                            <td className="p-4">
                              <div className="space-y-1">
                                <div className="font-medium">
                                  {config.config_name}
                                </div>
                                {config.description && (
                                  <div className="text-xs text-muted-foreground line-clamp-2">
                                    {config.description}
                                  </div>
                                )}
                              </div>
                            </td>
                            <td className="p-4">
                              <div className="flex items-center gap-1">
                                <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                                <span className="text-sm">
                                  {config.academic_year}{" "}
                                  {getSemesterDisplay(config.semester)}
                                </span>
                              </div>
                            </td>
                            <td className="p-4">
                              <Badge
                                variant="outline"
                                className="text-xs whitespace-nowrap"
                              >
                                {config.config_code}
                              </Badge>
                            </td>
                            <td className="p-4">
                              <div className="text-sm space-y-1">
                                {/* 一般申請期間 */}
                                {config.application_start_date &&
                                config.application_end_date ? (
                                  <div>
                                    <div className="font-medium">一般申請</div>
                                    <div className="text-xs text-muted-foreground">
                                      {formatDate(
                                        config.application_start_date
                                      )}{" "}
                                      ~{" "}
                                      {formatDate(config.application_end_date)}
                                    </div>
                                  </div>
                                ) : null}

                                {/* 續領申請期間 */}
                                {config.renewal_application_start_date &&
                                config.renewal_application_end_date ? (
                                  <div>
                                    <div className="font-medium">續領申請</div>
                                    <div className="text-xs text-muted-foreground">
                                      {formatDate(
                                        config.renewal_application_start_date
                                      )}{" "}
                                      ~{" "}
                                      {formatDate(
                                        config.renewal_application_end_date
                                      )}
                                    </div>
                                  </div>
                                ) : null}

                                {/* 如果兩個期間都沒設定 */}
                                {!config.application_start_date &&
                                !config.application_end_date &&
                                !config.renewal_application_start_date &&
                                !config.renewal_application_end_date ? (
                                  <div className="text-muted-foreground">
                                    未設定
                                  </div>
                                ) : null}
                              </div>
                            </td>
                            <td className="p-4">
                              <Badge
                                className={
                                  config.is_active
                                    ? "text-xs bg-green-500 whitespace-nowrap"
                                    : "text-xs whitespace-nowrap"
                                }
                                variant={
                                  config.is_active ? "default" : "secondary"
                                }
                              >
                                {config.is_active ? "已啟用" : "已停用"}
                              </Badge>
                            </td>
                            <td className="p-4">
                              <div className="flex justify-end gap-1">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openViewDialog(config)}
                                  title="檢視詳情"
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openEditDialog(config)}
                                  title="編輯配置"
                                >
                                  <Edit className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openDuplicateDialog(config)}
                                  title="複製配置"
                                  className="text-blue-600 hover:text-blue-700"
                                >
                                  <Copy className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="text-red-600 hover:text-red-700"
                                  onClick={() => {
                                    setSelectedConfig(config);
                                    setShowDeleteDialog(true);
                                  }}
                                  title="刪除配置"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      {/* View Configuration Dialog */}
      <Dialog open={showViewDialog} onOpenChange={setShowViewDialog}>
        <DialogContent
          className="max-w-3xl max-h-[90vh]"
          onInteractOutside={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest('[data-sonner-toast]') || target.closest('[data-radix-toast-viewport]')) {
              e.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>配置詳細資訊</DialogTitle>
            <DialogDescription>{selectedConfig?.config_name}</DialogDescription>
          </DialogHeader>

          <ScrollArea className="max-h-[60vh]">
            <div className="space-y-6 pr-4">
              {/* Basic Information */}
              <div>
                <h3 className="text-sm font-medium mb-3">基本資訊</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">配置代碼：</span>
                    <span className="ml-2 font-medium">
                      {selectedConfig?.config_code}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">學年度學期：</span>
                    <span className="ml-2 font-medium">
                      {selectedConfig?.academic_year}學年度{" "}
                      {getSemesterDisplay(selectedConfig?.semester)}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">獎學金金額：</span>
                    <span className="ml-2 font-medium">
                      NT$ {selectedConfig?.amount?.toLocaleString()}{" "}
                      {selectedConfig?.currency}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">版本：</span>
                    <span className="ml-2 font-medium">
                      v{selectedConfig?.version || "1.0"}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">狀態：</span>
                    <Badge
                      variant={
                        selectedConfig?.is_active ? "default" : "secondary"
                      }
                      className="ml-2"
                    >
                      {selectedConfig?.is_active ? "啟用" : "停用"}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">獎學金類型：</span>
                    <span className="ml-2 font-medium">
                      {selectedConfig?.scholarship_type_name}
                    </span>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Description */}
              <div>
                <h3 className="text-sm font-medium mb-2">說明</h3>
                {selectedConfig?.description ? (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {selectedConfig.description}
                    </p>
                    {selectedConfig?.description_en && (
                      <div>
                        <p className="text-xs text-muted-foreground font-medium">
                          English Description:
                        </p>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {selectedConfig.description_en}
                        </p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">無說明</p>
                )}
              </div>

              <Separator />

              {/* Effective Period */}
              <div>
                <h3 className="text-sm font-medium mb-3">生效期間</h3>
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="text-muted-foreground">生效開始：</span>
                    <span className="ml-2">
                      {selectedConfig?.effective_start_date
                        ? formatDateTime(selectedConfig.effective_start_date)
                        : "未設定"}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">生效結束：</span>
                    <span className="ml-2">
                      {selectedConfig?.effective_end_date
                        ? formatDateTime(selectedConfig.effective_end_date)
                        : "未設定"}
                    </span>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Application Periods */}
              <div>
                <h3 className="text-sm font-medium mb-3">申請時程</h3>
                <div className="space-y-3">
                  {/* 續領申請期間 */}
                  <div className="border rounded-lg p-3 bg-blue-50/50">
                    <h4 className="text-sm font-medium mb-2 text-blue-800">
                      續領申請期間
                    </h4>
                    <div className="space-y-1 text-sm">
                      <div>
                        <span className="text-muted-foreground">
                          申請開始：
                        </span>
                        <span className="ml-2">
                          {selectedConfig?.renewal_application_start_date
                            ? formatDateTime(
                                selectedConfig.renewal_application_start_date
                              )
                            : "未設定"}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">
                          申請截止：
                        </span>
                        <span className="ml-2">
                          {selectedConfig?.renewal_application_end_date
                            ? formatDateTime(
                                selectedConfig.renewal_application_end_date
                              )
                            : "未設定"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* 一般申請期間 */}
                  <div className="border rounded-lg p-3 bg-green-50/50">
                    <h4 className="text-sm font-medium mb-2 text-green-800">
                      一般申請期間
                    </h4>
                    <div className="space-y-1 text-sm">
                      <div>
                        <span className="text-muted-foreground">
                          申請開始：
                        </span>
                        <span className="ml-2">
                          {selectedConfig?.application_start_date
                            ? formatDateTime(
                                selectedConfig.application_start_date
                              )
                            : "未設定"}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">
                          申請截止：
                        </span>
                        <span className="ml-2">
                          {selectedConfig?.application_end_date
                            ? formatDateTime(
                                selectedConfig.application_end_date
                              )
                            : "未設定"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Review Periods */}
              <div>
                <h3 className="text-sm font-medium mb-3">審查時程</h3>
                <div className="space-y-3">
                  {/* 續領審查期間 */}
                  <div className="border rounded-lg p-3 bg-orange-50/50">
                    <h4 className="text-sm font-medium mb-2 text-orange-800">
                      續領審查期間
                    </h4>
                    <div className="space-y-2 text-sm">
                      <div>
                        <span className="text-muted-foreground font-medium">
                          教授審查：
                        </span>
                        <div className="ml-4 space-y-1">
                          <div>
                            <span className="text-muted-foreground">
                              開始：
                            </span>
                            <span className="ml-2">
                              {selectedConfig?.renewal_professor_review_start
                                ? formatDateTime(
                                    selectedConfig.renewal_professor_review_start
                                  )
                                : "未設定"}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">
                              截止：
                            </span>
                            <span className="ml-2">
                              {selectedConfig?.renewal_professor_review_end
                                ? formatDateTime(
                                    selectedConfig.renewal_professor_review_end
                                  )
                                : "未設定"}
                            </span>
                          </div>
                        </div>
                      </div>
                      <div>
                        <span className="text-muted-foreground font-medium">
                          學院審查：
                        </span>
                        <div className="ml-4 space-y-1">
                          <div>
                            <span className="text-muted-foreground">
                              開始：
                            </span>
                            <span className="ml-2">
                              {selectedConfig?.renewal_college_review_start
                                ? formatDateTime(
                                    selectedConfig.renewal_college_review_start
                                  )
                                : "未設定"}
                            </span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">
                              截止：
                            </span>
                            <span className="ml-2">
                              {selectedConfig?.renewal_college_review_end
                                ? formatDateTime(
                                    selectedConfig.renewal_college_review_end
                                  )
                                : "未設定"}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 一般申請審查期間 */}
                  <div className="border rounded-lg p-3 bg-purple-50/50">
                    <h4 className="text-sm font-medium mb-2 text-purple-800">
                      一般申請審查期間
                    </h4>
                    <div className="space-y-2 text-sm">
                      <div className="flex items-center space-x-2">
                        <span className="text-muted-foreground">
                          需要教授審查：
                        </span>
                        <Badge
                          variant={
                            selectedConfig?.requires_professor_recommendation
                              ? "default"
                              : "secondary"
                          }
                          className="text-xs"
                        >
                          {selectedConfig?.requires_professor_recommendation
                            ? "是"
                            : "否"}
                        </Badge>
                      </div>
                      {selectedConfig?.requires_professor_recommendation && (
                        <div>
                          <span className="text-muted-foreground font-medium">
                            教授審查：
                          </span>
                          <div className="ml-4 space-y-1">
                            <div>
                              <span className="text-muted-foreground">
                                開始：
                              </span>
                              <span className="ml-2">
                                {selectedConfig?.professor_review_start
                                  ? formatDateTime(
                                      selectedConfig.professor_review_start
                                    )
                                  : "未設定"}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">
                                截止：
                              </span>
                              <span className="ml-2">
                                {selectedConfig?.professor_review_end
                                  ? formatDateTime(
                                      selectedConfig.professor_review_end
                                    )
                                  : "未設定"}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      <div className="flex items-center space-x-2">
                        <span className="text-muted-foreground">
                          需要學院審查：
                        </span>
                        <Badge
                          variant={
                            selectedConfig?.requires_college_review
                              ? "default"
                              : "secondary"
                          }
                          className="text-xs"
                        >
                          {selectedConfig?.requires_college_review
                            ? "是"
                            : "否"}
                        </Badge>
                      </div>
                      {selectedConfig?.requires_college_review && (
                        <div>
                          <span className="text-muted-foreground font-medium">
                            學院審查：
                          </span>
                          <div className="ml-4 space-y-1">
                            <div>
                              <span className="text-muted-foreground">
                                開始：
                              </span>
                              <span className="ml-2">
                                {selectedConfig?.college_review_start
                                  ? formatDateTime(
                                      selectedConfig.college_review_start
                                    )
                                  : "未設定"}
                              </span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">
                                截止：
                              </span>
                              <span className="ml-2">
                                {selectedConfig?.college_review_end
                                  ? formatDateTime(
                                      selectedConfig.college_review_end
                                    )
                                  : "未設定"}
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      <div>
                        <span className="text-muted-foreground">
                          總審查截止：
                        </span>
                        <span className="ml-2">
                          {selectedConfig?.review_deadline
                            ? formatDateTime(selectedConfig.review_deadline)
                            : "未設定"}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <Separator />

              {/* Quota Management Information */}
              <div>
                <h3 className="text-sm font-medium mb-3">配額管理設定</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">配額限制：</span>
                    <Badge
                      variant={
                        selectedConfig?.has_quota_limit
                          ? "default"
                          : "secondary"
                      }
                      className="ml-2"
                    >
                      {selectedConfig?.has_quota_limit ? "啟用" : "停用"}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">學院配額：</span>
                    <Badge
                      variant={
                        selectedConfig?.has_college_quota
                          ? "default"
                          : "secondary"
                      }
                      className="ml-2"
                    >
                      {selectedConfig?.has_college_quota ? "啟用" : "停用"}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-muted-foreground">
                      配額管理模式：
                    </span>
                    <span className="ml-2 font-medium">
                      {selectedConfig?.quota_management_mode &&
                        getQuotaManagementModeLabel(selectedConfig.quota_management_mode as QuotaManagementMode)}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">總配額：</span>
                    <span className="ml-2 font-medium">
                      {selectedConfig?.total_quota
                        ? selectedConfig.total_quota.toLocaleString()
                        : "無限制"}
                    </span>
                  </div>
                </div>

                {/* Display quotas configuration if exists */}
                {selectedConfig?.quotas &&
                  Object.keys(selectedConfig.quotas).length > 0 && (
                    <div className="mt-4">
                      <h4 className="text-sm font-medium mb-2">配額分配詳情</h4>
                      <div className="bg-gray-50 rounded-lg p-3">
                        <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap">
                          {JSON.stringify(selectedConfig.quotas, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
              </div>

              <Separator />

              {/* Whitelist Information */}
              {selectedConfig?.whitelist_student_ids &&
                Object.keys(selectedConfig.whitelist_student_ids).length >
                  0 && (
                  <>
                    <div>
                      <h3 className="text-sm font-medium mb-3">申請白名單設定</h3>
                      <div className="space-y-2">
                        {Object.entries(
                          selectedConfig.whitelist_student_ids
                        ).map(([subType, studentIds]) => (
                          <div
                            key={subType}
                            className="border rounded-lg p-3 bg-gray-50/50"
                          >
                            <div className="flex justify-between items-center">
                              <span className="text-sm font-medium">
                                {subType}
                              </span>
                              <Badge variant="outline" className="text-xs">
                                {studentIds.length} 人
                              </Badge>
                            </div>
                            {studentIds.length > 0 && (
                              <div className="mt-2 text-xs text-muted-foreground">
                                學生ID: {studentIds.slice(0, 10).join(", ")}
                                {studentIds.length > 10 &&
                                  `... 等 ${studentIds.length} 人`}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                    <Separator />
                  </>
                )}

              {/* System Information */}
              <div>
                <h3 className="text-sm font-medium mb-3">系統資訊</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-muted-foreground">配置ID：</span>
                    <span className="ml-2 font-mono">{selectedConfig?.id}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">
                      獎學金類型ID：
                    </span>
                    <span className="ml-2 font-mono">
                      {selectedConfig?.scholarship_type_id}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">建立時間：</span>
                    <span className="ml-2">
                      {formatDateTime(selectedConfig?.created_at)}
                    </span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">最後更新：</span>
                    <span className="ml-2">
                      {formatDateTime(selectedConfig?.updated_at)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>

          <DialogFooter>
            <Button variant="outline" onClick={() => setShowViewDialog(false)}>
              關閉
            </Button>
            <Button
              onClick={() => {
                setShowViewDialog(false);
                openEditDialog(selectedConfig!);
              }}
            >
              <Edit className="h-4 w-4 mr-1" />
              編輯配置
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Configuration Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent
          className="max-w-2xl max-h-[90vh]"
          onInteractOutside={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest('[data-sonner-toast]') || target.closest('[data-radix-toast-viewport]')) {
              e.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>新增獎學金配置</DialogTitle>
            <DialogDescription>
              為選定的獎學金類型建立新的配置設定
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="max-h-[60vh]">
            <div className="grid gap-4 pl-2 pr-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="config_name">配置名稱 *</Label>
                  <Input
                    id="config_name"
                    value={formData.config_name || ""}
                    onChange={e =>
                      setFormData(prev => ({
                        ...prev,
                        config_name: e.target.value,
                      }))
                    }
                    placeholder="例：113學年度第一學期配置"
                  />
                </div>
                <div>
                  <Label htmlFor="config_code">配置代碼 *</Label>
                  <Input
                    id="config_code"
                    value={formData.config_code || ""}
                    onChange={e =>
                      setFormData(prev => ({
                        ...prev,
                        config_code: e.target.value,
                      }))
                    }
                    placeholder="例：PHD-113-1"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="academic_year">學年度 *</Label>
                  <Select
                    value={formData.academic_year?.toString() || ""}
                    onValueChange={value =>
                      setFormData(prev => ({
                        ...prev,
                        academic_year: parseInt(value),
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇學年度" />
                    </SelectTrigger>
                    <SelectContent>
                      {academicYears.map(year => (
                        <SelectItem key={year} value={year.toString()}>
                          {year}學年度
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="semester">學期</Label>
                  <Select
                    value={formData.semester || "null"}
                    onValueChange={value =>
                      setFormData(prev => ({
                        ...prev,
                        semester: value === "null" ? null : value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇學期" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="null">全學年</SelectItem>
                      <SelectItem value="first">第一學期</SelectItem>
                      <SelectItem value="second">第二學期</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <Label htmlFor="description">中文描述</Label>
                <Textarea
                  id="description"
                  value={formData.description || ""}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      description: e.target.value,
                    }))
                  }
                  placeholder="配置中文描述..."
                  className="min-h-[80px]"
                />
              </div>

              <div>
                <Label htmlFor="description_en">英文描述</Label>
                <Textarea
                  id="description_en"
                  value={formData.description_en || ""}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      description_en: e.target.value,
                    }))
                  }
                  placeholder="Configuration description in English..."
                  className="min-h-[80px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="amount">獎學金金額 *</Label>
                  <Input
                    id="amount"
                    type="number"
                    value={formData.amount || ""}
                    onChange={e =>
                      setFormData(prev => ({
                        ...prev,
                        amount: parseInt(e.target.value) || 0,
                      }))
                    }
                    placeholder="例：50000"
                  />
                </div>
                <div>
                  <Label htmlFor="currency">幣別</Label>
                  <Select
                    value={formData.currency || "TWD"}
                    onValueChange={value =>
                      setFormData(prev => ({ ...prev, currency: value }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="TWD">新台幣 (TWD)</SelectItem>
                      <SelectItem value="USD">美金 (USD)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              {/* Quota Management */}
              <div className="space-y-4">
                <h4 className="font-medium">配額管理設定</h4>

                <div>
                  <Label htmlFor="quota_management_mode">配額管理模式</Label>
                  <Select
                    value={formData.quota_management_mode || "none"}
                    onValueChange={value =>
                      setFormData(prev => ({
                        ...prev,
                        quota_management_mode: value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇配額管理模式" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">無配額管理</SelectItem>
                      <SelectItem value="simple">簡單配額</SelectItem>
                      <SelectItem value="college_based">學院配額</SelectItem>
                      <SelectItem value="matrix_based">矩陣配額</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* 根據配額模式顯示相應欄位 */}
                {formData.quota_management_mode === "simple" && (
                  <div>
                    <Label htmlFor="total_quota">總配額數量</Label>
                    <Input
                      id="total_quota"
                      type="number"
                      min="0"
                      value={formData.total_quota || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          total_quota: parseInt(e.target.value) || 0,
                        }))
                      }
                      placeholder="例：100"
                    />
                  </div>
                )}

                {(formData.quota_management_mode === "college_based" ||
                  formData.quota_management_mode === "matrix_based") && (
                  <div>
                    <Label htmlFor="quotas">配額設定 (JSON 格式)</Label>
                    <div className="mt-1 mb-2 text-sm text-muted-foreground">
                      {formData.quota_management_mode === "matrix_based" && (
                        <p>
                          矩陣格式範例：
                          {`{"nstc": {"C": 5, "E": 4, "I": 3}, "moe_1w": {"M": 6, "S": 5, "O": 4}}`}
                        </p>
                      )}
                      {formData.quota_management_mode === "college_based" && (
                        <p>學院格式範例：{`{"C": 10, "E": 15, "I": 8}`}</p>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowCodeTableDialog(true)}
                        className="mt-1 text-blue-600 hover:text-blue-700"
                      >
                        <Info className="h-3 w-3 mr-1" />
                        查看學院代碼表
                      </Button>
                    </div>
                    <Textarea
                      id="quotas"
                      value={
                        typeof formData.quotas === "object"
                          ? JSON.stringify(formData.quotas, null, 2)
                          : formData.quotas || ""
                      }
                    onChange={e => {
                      try {
                        const parsed = e.target.value
                          ? JSON.parse(e.target.value)
                          : {};
                        setFormData(prev => ({ ...prev, quotas: parsed }));
                      } catch {
                        // 如果 JSON 無效，保持字串狀態讓使用者繼續編輯
                        setFormData(prev => ({
                          ...prev,
                          quotas: e.target.value,
                        }));
                      }
                    }}
                    placeholder='{"sub_type": {"college": quota_number}}'
                    className="min-h-[100px] font-mono text-sm"
                  />
                </div>
                )}

                {/* 申請白名單功能控制 */}
                <div className="space-y-3">
                  <Label>申請白名單功能</Label>
                  <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/30">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">申請白名單功能</span>
                      <Badge variant={selectedScholarshipType?.whitelist_enabled ? "default" : "outline"} className="text-xs">
                        {selectedScholarshipType?.whitelist_enabled ? "已啟用" : "未啟用"}
                      </Badge>
                    </div>
                    <Switch
                      checked={selectedScholarshipType?.whitelist_enabled || false}
                      onCheckedChange={handleToggleWhitelist}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    啟用後，只有申請白名單中的學生才能申請此獎學金
                  </p>
                  {selectedScholarshipType?.whitelist_enabled && selectedConfig && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowWhitelistDialog(true)}
                    >
                      管理申請白名單學生
                    </Button>
                  )}
                </div>

                <div>
                  <Label htmlFor="whitelist_student_ids">
                    申請白名單學生設定 (JSON 格式) - 進階選項
                  </Label>
                  <div className="mt-1 mb-2 text-sm text-muted-foreground">
                    <p>
                      格式範例：
                      {`{"general": [123, 456, 789], "nstc": [111, 222, 333]}`}
                    </p>
                    <p>說明：依子獎學金類型分別設定可申請的學生ID列表</p>
                  </div>
                  <Textarea
                    id="whitelist_student_ids"
                    value={
                      typeof formData.whitelist_student_ids === "object"
                        ? JSON.stringify(
                            formData.whitelist_student_ids,
                            null,
                            2
                          )
                        : formData.whitelist_student_ids || ""
                    }
                    onChange={e => {
                      try {
                        const parsed = e.target.value
                          ? JSON.parse(e.target.value)
                          : {};
                        setFormData(prev => ({
                          ...prev,
                          whitelist_student_ids: parsed,
                        }));
                      } catch {
                        // 如果 JSON 無效，保持字串狀態讓使用者繼續編輯
                        setFormData(prev => ({
                          ...prev,
                          whitelist_student_ids: e.target.value,
                        }));
                      }
                    }}
                    placeholder='{"sub_type": [student_id_1, student_id_2]}'
                    className="min-h-[100px] font-mono text-sm"
                  />
                </div>
              </div>

              <Separator />

              {/* Application Periods */}
              <div className="space-y-4">
                <h4 className="font-medium">申請期間</h4>
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="application_start_date">
                        一般申請開始
                      </Label>
                      <Input
                        id="application_start_date"
                        type="datetime-local"
                        value={formData.application_start_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            application_start_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div>
                      <Label htmlFor="application_end_date">一般申請截止</Label>
                      <Input
                        id="application_end_date"
                        type="datetime-local"
                        value={formData.application_end_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            application_end_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="renewal_application_start_date">
                        續領申請開始
                      </Label>
                      <Input
                        id="renewal_application_start_date"
                        type="datetime-local"
                        value={formData.renewal_application_start_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            renewal_application_start_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div>
                      <Label htmlFor="renewal_application_end_date">
                        續領申請截止
                      </Label>
                      <Input
                        id="renewal_application_end_date"
                        type="datetime-local"
                        value={formData.renewal_application_end_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            renewal_application_end_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>

              <Separator />

              {/* 生效期間設定 */}
              <div className="space-y-4">
                <h4 className="font-medium">生效期間</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="effective_start_date">生效開始日期</Label>
                    <Input
                      id="effective_start_date"
                      type="datetime-local"
                      value={formData.effective_start_date || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          effective_start_date: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <Label htmlFor="effective_end_date">生效結束日期</Label>
                    <Input
                      id="effective_end_date"
                      type="datetime-local"
                      value={formData.effective_end_date || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          effective_end_date: e.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
              </div>
            </div>
          </ScrollArea>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowCreateDialog(false)}
              disabled={formLoading}
            >
              取消
            </Button>
            <Button onClick={handleCreateConfig} disabled={formLoading}>
              {formLoading ? "建立中..." : "建立配置"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Configuration Dialog */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent
          className="max-w-2xl max-h-[90vh]"
          onInteractOutside={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest('[data-sonner-toast]') || target.closest('[data-radix-toast-viewport]')) {
              e.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>編輯獎學金配置</DialogTitle>
            <DialogDescription>修改選定配置的設定</DialogDescription>
          </DialogHeader>

          <ScrollArea className="max-h-[60vh]">
            <div className="grid gap-4 pl-2 pr-4">
              <div>
                <Label htmlFor="edit_config_name">配置名稱 *</Label>
                <Input
                  id="edit_config_name"
                  value={formData.config_name || ""}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      config_name: e.target.value,
                    }))
                  }
                />
              </div>

              <div>
                <Label htmlFor="edit_config_code">配置代碼</Label>
                <Input
                  id="edit_config_code"
                  value={formData.config_code || ""}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      config_code: e.target.value,
                    }))
                  }
                  placeholder="例：PHD-114-1"
                />
              </div>

              <div>
                <Label htmlFor="edit_description">中文描述</Label>
                <Textarea
                  id="edit_description"
                  value={formData.description || ""}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      description: e.target.value,
                    }))
                  }
                  className="min-h-[80px]"
                />
              </div>

              <div>
                <Label htmlFor="edit_description_en">英文描述</Label>
                <Textarea
                  id="edit_description_en"
                  value={formData.description_en || ""}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      description_en: e.target.value,
                    }))
                  }
                  placeholder="Configuration description in English..."
                  className="min-h-[80px]"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="edit_amount">獎學金金額 *</Label>
                  <Input
                    id="edit_amount"
                    type="number"
                    value={formData.amount || ""}
                    onChange={e =>
                      setFormData(prev => ({
                        ...prev,
                        amount: parseInt(e.target.value) || 0,
                      }))
                    }
                  />
                </div>
                <div>
                  <Label htmlFor="edit_currency">幣別</Label>
                  <Select
                    value={formData.currency || "TWD"}
                    onValueChange={value =>
                      setFormData(prev => ({ ...prev, currency: value }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="TWD">新台幣 (TWD)</SelectItem>
                      <SelectItem value="USD">美金 (USD)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />

              {/* Quota Management Edit */}
              <div className="space-y-4">
                <h4 className="font-medium">配額管理設定</h4>

                <div>
                  <Label htmlFor="edit_quota_management_mode">
                    配額管理模式
                  </Label>
                  <Select
                    value={formData.quota_management_mode || "none"}
                    onValueChange={value =>
                      setFormData(prev => ({
                        ...prev,
                        quota_management_mode: value,
                      }))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="選擇配額管理模式" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">無配額管理</SelectItem>
                      <SelectItem value="simple">簡單配額</SelectItem>
                      <SelectItem value="college_based">學院配額</SelectItem>
                      <SelectItem value="matrix_based">矩陣配額</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* 根據配額模式顯示相應欄位 */}
                {formData.quota_management_mode === "simple" && (
                  <div>
                    <Label htmlFor="edit_total_quota">總配額數量</Label>
                    <Input
                      id="edit_total_quota"
                      type="number"
                      min="0"
                      value={formData.total_quota || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          total_quota: parseInt(e.target.value) || 0,
                        }))
                      }
                      placeholder="例：100"
                    />
                  </div>
                )}

                {(formData.quota_management_mode === "college_based" ||
                  formData.quota_management_mode === "matrix_based") && (
                  <div>
                    <Label htmlFor="edit_quotas">配額設定 (JSON 格式)</Label>
                    <div className="mt-1 mb-2 text-sm text-muted-foreground">
                      {formData.quota_management_mode === "matrix_based" && (
                        <p>
                          矩陣格式範例：
                          {`{"nstc": {"C": 5, "E": 4, "I": 3}, "moe_1w": {"M": 6, "S": 5, "O": 4}}`}
                        </p>
                      )}
                      {formData.quota_management_mode === "college_based" && (
                        <p>學院格式範例：{`{"C": 10, "E": 15, "I": 8}`}</p>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowCodeTableDialog(true)}
                        className="mt-1 text-blue-600 hover:text-blue-700"
                      >
                        <Info className="h-3 w-3 mr-1" />
                        查看學院代碼表
                      </Button>
                    </div>
                    <Textarea
                      id="edit_quotas"
                      value={
                        typeof formData.quotas === "object"
                          ? JSON.stringify(formData.quotas, null, 2)
                          : formData.quotas || ""
                      }
                      onChange={e => {
                        try {
                          const parsed = e.target.value
                            ? JSON.parse(e.target.value)
                            : {};
                          setFormData(prev => ({ ...prev, quotas: parsed }));
                        } catch {
                          // 如果 JSON 無效，保持字串狀態讓使用者繼續編輯
                          setFormData(prev => ({
                            ...prev,
                            quotas: e.target.value,
                          }));
                        }
                      }}
                      placeholder='{"sub_type": {"college": quota_number}}'
                      className="min-h-[100px] font-mono text-sm"
                    />
                  </div>
                )}

                {/* 申請白名單功能控制 */}
                <div className="space-y-3">
                  <Label>申請白名單功能</Label>
                  <div className="flex items-center justify-between p-3 border rounded-lg bg-muted/30">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">申請白名單功能</span>
                      <Badge variant={selectedScholarshipType?.whitelist_enabled ? "default" : "outline"} className="text-xs">
                        {selectedScholarshipType?.whitelist_enabled ? "已啟用" : "未啟用"}
                      </Badge>
                    </div>
                    <Switch
                      checked={selectedScholarshipType?.whitelist_enabled || false}
                      onCheckedChange={handleToggleWhitelist}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">
                    啟用後，只有申請白名單中的學生才能申請此獎學金
                  </p>
                  {selectedScholarshipType?.whitelist_enabled && selectedConfig && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setShowWhitelistDialog(true)}
                    >
                      管理申請白名單學生
                    </Button>
                  )}
                </div>

                <div>
                  <Label htmlFor="edit_whitelist_student_ids">
                    申請白名單學生設定 (JSON 格式) - 進階選項
                  </Label>
                  <div className="mt-1 mb-2 text-sm text-muted-foreground">
                    <p>
                      格式範例：
                      {`{"general": [123, 456, 789], "nstc": [111, 222, 333]}`}
                    </p>
                    <p>說明：依子獎學金類型分別設定可申請的學生ID列表</p>
                  </div>
                  <Textarea
                    id="edit_whitelist_student_ids"
                    value={
                      typeof formData.whitelist_student_ids === "object"
                        ? JSON.stringify(
                            formData.whitelist_student_ids,
                            null,
                            2
                          )
                        : formData.whitelist_student_ids || ""
                    }
                    onChange={e => {
                      try {
                        const parsed = e.target.value
                          ? JSON.parse(e.target.value)
                          : {};
                        setFormData(prev => ({
                          ...prev,
                          whitelist_student_ids: parsed,
                        }));
                      } catch {
                        // 如果 JSON 無效，保持字串狀態讓使用者繼續編輯
                        setFormData(prev => ({
                          ...prev,
                          whitelist_student_ids: e.target.value,
                        }));
                      }
                    }}
                    placeholder='{"sub_type": [student_id_1, student_id_2]}'
                    className="min-h-[100px] font-mono text-sm"
                  />
                </div>
              </div>

              <Separator />

              {/* 申請時間區段編輯 */}
              <div className="space-y-4">
                <h4 className="font-medium">申請期間設定</h4>

                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="edit_application_start_date">
                        一般申請開始
                      </Label>
                      <Input
                        id="edit_application_start_date"
                        type="datetime-local"
                        value={formData.application_start_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            application_start_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div>
                      <Label htmlFor="edit_application_end_date">
                        一般申請截止
                      </Label>
                      <Input
                        id="edit_application_end_date"
                        type="datetime-local"
                        value={formData.application_end_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            application_end_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <Label htmlFor="edit_renewal_application_start_date">
                        續領申請開始
                      </Label>
                      <Input
                        id="edit_renewal_application_start_date"
                        type="datetime-local"
                        value={formData.renewal_application_start_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            renewal_application_start_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <div>
                      <Label htmlFor="edit_renewal_application_end_date">
                        續領申請截止
                      </Label>
                      <Input
                        id="edit_renewal_application_end_date"
                        type="datetime-local"
                        value={formData.renewal_application_end_date || ""}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            renewal_application_end_date: e.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>
                </div>
              </div>

              <Separator />

              {/* 審查期間設定 */}
              <div className="space-y-4">
                <h4 className="font-medium">審查期間設定</h4>

                <div className="space-y-4">
                  {/* 續領審查期間 */}
                  <div>
                    <h5 className="text-sm font-medium mb-2">續領審查期間</h5>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label htmlFor="edit_renewal_professor_review_start">
                          續領教授審查開始
                        </Label>
                        <Input
                          id="edit_renewal_professor_review_start"
                          type="datetime-local"
                          value={formData.renewal_professor_review_start || ""}
                          onChange={e =>
                            setFormData(prev => ({
                              ...prev,
                              renewal_professor_review_start: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div>
                        <Label htmlFor="edit_renewal_professor_review_end">
                          續領教授審查截止
                        </Label>
                        <Input
                          id="edit_renewal_professor_review_end"
                          type="datetime-local"
                          value={formData.renewal_professor_review_end || ""}
                          onChange={e =>
                            setFormData(prev => ({
                              ...prev,
                              renewal_professor_review_end: e.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mt-2">
                      <div>
                        <Label htmlFor="edit_renewal_college_review_start">
                          續領學院審查開始
                        </Label>
                        <Input
                          id="edit_renewal_college_review_start"
                          type="datetime-local"
                          value={formData.renewal_college_review_start || ""}
                          onChange={e =>
                            setFormData(prev => ({
                              ...prev,
                              renewal_college_review_start: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div>
                        <Label htmlFor="edit_renewal_college_review_end">
                          續領學院審查截止
                        </Label>
                        <Input
                          id="edit_renewal_college_review_end"
                          type="datetime-local"
                          value={formData.renewal_college_review_end || ""}
                          onChange={e =>
                            setFormData(prev => ({
                              ...prev,
                              renewal_college_review_end: e.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                  </div>

                  {/* 一般申請審查期間 */}
                  <div>
                    <h5 className="text-sm font-medium mb-2">
                      一般申請審查期間
                    </h5>

                    <div className="flex items-center space-x-2 mb-2">
                      <input
                        type="checkbox"
                        id="edit_requires_professor_recommendation"
                        checked={
                          formData.requires_professor_recommendation || false
                        }
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            requires_professor_recommendation: e.target.checked,
                          }))
                        }
                        className="h-4 w-4"
                      />
                      <Label htmlFor="edit_requires_professor_recommendation">
                        需要教授審查
                      </Label>
                    </div>

                    {formData.requires_professor_recommendation && (
                      <div className="grid grid-cols-2 gap-4 mb-2">
                        <div>
                          <Label htmlFor="edit_professor_review_start">
                            教授審查開始
                          </Label>
                          <Input
                            id="edit_professor_review_start"
                            type="datetime-local"
                            value={formData.professor_review_start || ""}
                            onChange={e =>
                              setFormData(prev => ({
                                ...prev,
                                professor_review_start: e.target.value,
                              }))
                            }
                          />
                        </div>
                        <div>
                          <Label htmlFor="edit_professor_review_end">
                            教授審查截止
                          </Label>
                          <Input
                            id="edit_professor_review_end"
                            type="datetime-local"
                            value={formData.professor_review_end || ""}
                            onChange={e =>
                              setFormData(prev => ({
                                ...prev,
                                professor_review_end: e.target.value,
                              }))
                            }
                          />
                        </div>
                      </div>
                    )}

                    <div className="flex items-center space-x-2 mb-2">
                      <input
                        type="checkbox"
                        id="edit_requires_college_review"
                        checked={formData.requires_college_review || false}
                        onChange={e =>
                          setFormData(prev => ({
                            ...prev,
                            requires_college_review: e.target.checked,
                          }))
                        }
                        className="h-4 w-4"
                      />
                      <Label htmlFor="edit_requires_college_review">
                        需要學院審查
                      </Label>
                    </div>

                    {formData.requires_college_review && (
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <Label htmlFor="edit_college_review_start">
                            學院審查開始
                          </Label>
                          <Input
                            id="edit_college_review_start"
                            type="datetime-local"
                            value={formData.college_review_start || ""}
                            onChange={e =>
                              setFormData(prev => ({
                                ...prev,
                                college_review_start: e.target.value,
                              }))
                            }
                          />
                        </div>
                        <div>
                          <Label htmlFor="edit_college_review_end">
                            學院審查截止
                          </Label>
                          <Input
                            id="edit_college_review_end"
                            type="datetime-local"
                            value={formData.college_review_end || ""}
                            onChange={e =>
                              setFormData(prev => ({
                                ...prev,
                                college_review_end: e.target.value,
                              }))
                            }
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 總審查截止日期 */}
                  <div>
                    <Label htmlFor="edit_review_deadline">總審查截止日期</Label>
                    <Input
                      id="edit_review_deadline"
                      type="datetime-local"
                      value={formData.review_deadline || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          review_deadline: e.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
              </div>

              <Separator />

              {/* 生效期間設定 */}
              <div className="space-y-4">
                <h4 className="font-medium">生效期間設定</h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="edit_effective_start_date">
                      生效開始日期
                    </Label>
                    <Input
                      id="edit_effective_start_date"
                      type="datetime-local"
                      value={formData.effective_start_date || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          effective_start_date: e.target.value,
                        }))
                      }
                    />
                  </div>
                  <div>
                    <Label htmlFor="edit_effective_end_date">
                      生效結束日期
                    </Label>
                    <Input
                      id="edit_effective_end_date"
                      type="datetime-local"
                      value={formData.effective_end_date || ""}
                      onChange={e =>
                        setFormData(prev => ({
                          ...prev,
                          effective_end_date: e.target.value,
                        }))
                      }
                    />
                  </div>
                </div>
              </div>

              <Separator />

              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="edit_is_active"
                  checked={formData.is_active || false}
                  onChange={e =>
                    setFormData(prev => ({
                      ...prev,
                      is_active: e.target.checked,
                    }))
                  }
                  className="h-4 w-4"
                />
                <Label htmlFor="edit_is_active">啟用此配置</Label>
              </div>
            </div>
          </ScrollArea>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowEditDialog(false)}
              disabled={formLoading}
            >
              取消
            </Button>
            <Button onClick={handleUpdateConfig} disabled={formLoading}>
              {formLoading ? "更新中..." : "更新配置"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Duplicate Configuration Dialog */}
      <Dialog open={showDuplicateDialog} onOpenChange={setShowDuplicateDialog}>
        <DialogContent
          onInteractOutside={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest('[data-sonner-toast]') || target.closest('[data-radix-toast-viewport]')) {
              e.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>複製獎學金配置</DialogTitle>
            <DialogDescription>複製現有配置到新的學年度/學期</DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label htmlFor="target_academic_year">目標學年度</Label>
                <Select
                  value={formData.academic_year?.toString() || ""}
                  onValueChange={value =>
                    setFormData(prev => ({
                      ...prev,
                      academic_year: parseInt(value),
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {academicYears.map(year => (
                      <SelectItem key={year} value={year.toString()}>
                        {year}學年度
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label htmlFor="target_semester">目標學期</Label>
                <Select
                  value={formData.semester || "null"}
                  onValueChange={value =>
                    setFormData(prev => ({
                      ...prev,
                      semester: value === "null" ? null : value,
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="null">全學年</SelectItem>
                    <SelectItem value="first">第一學期</SelectItem>
                    <SelectItem value="second">第二學期</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div>
              <Label htmlFor="duplicate_config_code">新配置代碼</Label>
              <Input
                id="duplicate_config_code"
                value={formData.config_code || ""}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    config_code: e.target.value,
                  }))
                }
              />
            </div>

            <div>
              <Label htmlFor="duplicate_config_name">新配置名稱</Label>
              <Input
                id="duplicate_config_name"
                value={formData.config_name || ""}
                onChange={e =>
                  setFormData(prev => ({
                    ...prev,
                    config_name: e.target.value,
                  }))
                }
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowDuplicateDialog(false)}
              disabled={formLoading}
            >
              取消
            </Button>
            <Button onClick={handleDuplicateConfig} disabled={formLoading}>
              {formLoading ? "複製中..." : "複製配置"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確認刪除</AlertDialogTitle>
            <AlertDialogDescription>
              您確定要停用配置「{selectedConfig?.config_name}」嗎？
              <br />
              這個操作將會將配置標記為非活躍狀態。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={formLoading}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfig}
              disabled={formLoading}
              className="bg-destructive hover:bg-destructive/90"
            >
              {formLoading ? "刪除中..." : "確定刪除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Academy Code Lookup Table Dialog */}
      <Dialog open={showCodeTableDialog} onOpenChange={setShowCodeTableDialog}>
        <DialogContent
          className="max-w-2xl"
          onInteractOutside={(e) => {
            const target = e.target as HTMLElement;
            if (target.closest('[data-sonner-toast]') || target.closest('[data-radix-toast-viewport]')) {
              e.preventDefault();
            }
          }}
        >
          <DialogHeader>
            <DialogTitle>學院代碼對照表</DialogTitle>
            <DialogDescription>
              配額設定中使用的學院代碼與中文名稱對照表
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="max-h-[60vh]">
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-4 p-3 bg-gray-50 rounded-lg font-medium text-sm">
                <div>代碼</div>
                <div className="col-span-2">學院名稱</div>
              </div>
              {Object.entries(academyCodes).map(([code, name]) => (
                <div
                  key={code}
                  className="grid grid-cols-3 gap-4 p-3 border rounded-lg hover:bg-gray-50/50 transition-colors"
                >
                  <div className="font-mono text-sm font-medium text-blue-600">
                    {code}
                  </div>
                  <div className="col-span-2 text-sm">{name}</div>
                </div>
              ))}
            </div>
          </ScrollArea>

          <div className="mt-4 p-4 bg-blue-50 rounded-lg">
            <h4 className="text-sm font-medium text-blue-800 mb-2">使用說明</h4>
            <div className="text-sm text-blue-700 space-y-1">
              <p>• 在配額設定 JSON 中使用這些代碼來指定各學院的配額</p>
              <p>
                • 矩陣格式範例：
                {`{"nstc": {"C": 5, "E": 4}, "moe_1w": {"I": 3, "M": 2}}`}
              </p>
              <p>• 您也可以使用簡單格式：{`{"nstc": 10, "moe_1w": 30}`}</p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowCodeTableDialog(false)}
            >
              關閉
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Whitelist Management Dialog */}
      {selectedConfig && selectedScholarshipType && (
        <WhitelistManagementDialog
          isOpen={showWhitelistDialog}
          onClose={() => setShowWhitelistDialog(false)}
          configuration={selectedConfig}
          subTypes={
            selectedScholarshipType.sub_type_list?.length > 0
              ? selectedScholarshipType.sub_type_list
              : ["general"]
          }
        />
      )}

      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed top-4 right-4 z-50 p-4 rounded-md shadow-lg transition-all duration-300 ${
            toast.type === "success"
              ? "bg-green-50 border border-green-200 text-green-800"
              : "bg-red-50 border border-red-200 text-red-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {toast.type === "success" ? (
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
            ) : (
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            )}
            <p className="text-sm font-medium">{toast.message}</p>
            <button
              onClick={() => setToast(null)}
              className="ml-2 text-current opacity-70 hover:opacity-100"
            >
              <svg
                className="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
