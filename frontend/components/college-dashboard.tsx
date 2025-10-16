"use client";

import { useState, useEffect, useMemo } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
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
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { NationalityFlag } from "@/components/nationality-flag";
import { CollegeRankingTable } from "@/components/college-ranking-table";
import { DistributionResultsPanel } from "@/components/distribution-results-panel";
import { SemesterSelector } from "@/components/semester-selector";
import { ScholarshipTypeSelector } from "@/components/ui/scholarship-type-selector";
import { ApplicationAuditTrail } from "@/components/application-audit-trail";
import { DeleteApplicationDialog } from "@/components/delete-application-dialog";
import { DocumentRequestForm } from "@/components/document-request-form";
import { getTranslation } from "@/lib/i18n";
import {
  getStatusColor,
  getStatusName,
  ApplicationStatus,
} from "@/lib/utils/application-helpers";
import {
  Search,
  Eye,
  CheckCircle,
  XCircle,
  Grid,
  List,
  Download,
  GraduationCap,
  Clock,
  Calendar,
  School,
  AlertCircle,
  Loader2,
  Trophy,
  Users,
  Award,
  Building,
  Send,
  Plus,
  RefreshCw,
  Trash2,
  FileText,
  Pencil,
  Check,
  X,
  Lock,
  LockOpen,
} from "lucide-react";
import { useCollegeApplications } from "@/hooks/use-admin";
import { User } from "@/types/user";
import { apiClient } from "@/lib/api";

interface CollegeDashboardProps {
  user: User;
  locale?: "zh" | "en";
}

interface ScholarshipConfig {
  id: number;
  name: string;
  code?: string;
  subTypes: { code: string; name: string }[];
}

interface AcademicConfig {
  currentYear: number;
  currentSemester: "FIRST" | "SECOND";
  availableYears: number[];
}

type SubTypeQuotaBreakdown = Record<string, { quota?: number; label?: string; label_en?: string }>;

interface RankingData {
  applications: any[];
  totalQuota: number;
  collegeQuota?: number;  // College-specific quota
  collegeQuotaBreakdown?: SubTypeQuotaBreakdown;
  subTypeMetadata?: Record<string, { code: string; label: string; label_en: string }>;
  subTypeCode: string;
  academicYear: number;
  semester?: string | null;
  isFinalized: boolean;
}

interface DistributionQuotaSummaryProps {
  locale: "zh" | "en";
  totalQuota?: number;
  collegeQuota?: number;
  applications?: Array<{ is_allocated?: boolean }>;
  breakdown?: SubTypeQuotaBreakdown;
  subTypeMeta?: Record<string, { code: string; label: string; label_en: string }>;
}

function DistributionQuotaSummary({
  locale,
  totalQuota: _totalQuota,
  collegeQuota,
  applications,
  breakdown,
  subTypeMeta,
}: DistributionQuotaSummaryProps) {
  const hasCollegeQuota =
    typeof collegeQuota === "number" && !Number.isNaN(collegeQuota);
  const effectiveQuota = hasCollegeQuota
    ? (collegeQuota as number)
    : typeof _totalQuota === "number" && !Number.isNaN(_totalQuota)
      ? (_totalQuota as number)
      : 0;

  const allocatedCount = Array.isArray(applications)
    ? applications.filter((app) => app?.is_allocated).length
    : 0;
  const remainingQuota = Math.max(0, effectiveQuota - allocatedCount);

  const breakdownItems = useMemo(() => {
    if (!breakdown) {
      return [] as Array<{
        code: string;
        quota: number;
        label: string;
        labelEn: string;
      }>;
    }

    return Object.entries(breakdown)
      .map(([code, raw]) => {
        let quota = 0;
        let label = subTypeMeta?.[code]?.label || code;
        let labelEn = subTypeMeta?.[code]?.label_en || label;

        if (raw && typeof raw === "object") {
          const maybeQuota = (raw as any).quota;
          if (typeof maybeQuota === "number" && !Number.isNaN(maybeQuota)) {
            quota = maybeQuota;
          } else if (maybeQuota !== undefined) {
            const parsed = Number(maybeQuota);
            quota = Number.isNaN(parsed) ? 0 : parsed;
          }

          if ((raw as any).label) {
            label = String((raw as any).label);
          }

          if ((raw as any).label_en) {
            labelEn = String((raw as any).label_en);
          }
        } else if (raw !== undefined) {
          const parsed = Number(raw);
          quota = Number.isNaN(parsed) ? 0 : parsed;
        }

        return {
          code,
          quota,
          label,
          labelEn,
        };
      })
      .filter((item) => Number.isFinite(item.quota));
  }, [breakdown, subTypeMeta]);

  const eligibleCounts = useMemo(() => {
    if (!Array.isArray(applications)) {
      return {};
    }

    return applications.reduce<Record<string, number>>((acc, app: any) => {
      const rawEligible = app?.eligible_subtypes;
      if (!rawEligible) {
        return acc;
      }

      const list = Array.isArray(rawEligible)
        ? rawEligible
        : typeof rawEligible === "string"
          ? rawEligible.split(",")
          : [];

      list.forEach((item) => {
        let key: string | undefined;

        if (typeof item === "string") {
          key = item;
        } else if (item && typeof item === "object") {
          key =
            item.code ||
            item.sub_type ||
            item.subType ||
            item.name ||
            item.label ||
            item.value;
        }

        if (!key) {
          return;
        }

        const normalized = String(key).trim();
        if (!normalized) {
          return;
        }

        acc[normalized] = (acc[normalized] || 0) + 1;
      });

      return acc;
    }, {});
  }, [applications]);

  const formatValue = (value: number | undefined) =>
    typeof value === "number" && !Number.isNaN(value)
      ? value.toLocaleString()
      : "-";

  const allocationRate =
    effectiveQuota > 0
      ? Math.min(100, Math.round((allocatedCount / effectiveQuota) * 100))
      : 0;

  const demandCount = Array.isArray(applications) ? applications.length : 0;

  const getSubtypeLabel = (subtype: string) => {
    if (!subtype) {
      return locale === "zh" ? "未命名子項目" : "Unnamed";
    }

    return subtype
      .replace(/_/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toUpperCase();
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card className="border-blue-100 bg-blue-50/50">
          <CardContent className="p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-blue-600">
                <School className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-blue-700">
                  {locale === "zh" ? "學院配額" : "College Quota"}
                </p>
                <p className="text-2xl font-semibold text-blue-900">
                  {formatValue(effectiveQuota)}
                </p>
                {!hasCollegeQuota && (
                  <p className="mt-1 text-xs text-blue-700/80">
                    {locale === "zh"
                      ? "尚未設定學院配額，暫以總配額估算"
                      : "Using global quota until college values are configured"}
                  </p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                <CheckCircle className="h-5 w-5" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-medium text-emerald-700">
                  {locale === "zh" ? "已分配" : "Allocated"}
                </p>
                <p className="text-2xl font-semibold text-emerald-700">
                  {allocatedCount.toLocaleString()}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  {locale === "zh"
                    ? `總申請 ${demandCount.toLocaleString()} 名`
                    : `${demandCount.toLocaleString()} total applicants`}
                </p>
                <div className="mt-3">
                  <Progress
                    value={allocationRate}
                    className="h-2"
                    indicatorClassName="bg-emerald-500"
                    aria-label={locale === "zh" ? "分配進度" : "Allocation progress"}
                  />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-orange-100 text-orange-600">
                <AlertCircle className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-orange-700">
                  {locale === "zh" ? "剩餘名額" : "Seats Remaining"}
                </p>
                <p className="text-2xl font-semibold text-orange-700">
                  {formatValue(remainingQuota)}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  {locale === "zh"
                    ? "若名額不足，請檢視備取或調整排序"
                    : "Review backups or ranking if seats are exhausted"}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>


      {breakdownItems.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">
              {locale === "zh" ? "子項目配額概況" : "Sub-scholarship Overview"}
            </CardTitle>
            <CardDescription>
              {locale === "zh"
                ? "比較學院配額與申請需求，協助掌握壓力點"
                : "Compare college quota with demand to spot pressure points"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {breakdownItems.map(({ code, quota, label, labelEn }) => {
                const quotaNumber =
                  typeof quota === "number" && !Number.isNaN(quota) ? quota : 0;
                const eligible = eligibleCounts[code] || 0;
                const delta = quotaNumber ? quotaNumber - eligible : 0;
                const ratio =
                  quotaNumber > 0
                    ? Math.min(100, Math.round((eligible / quotaNumber) * 100))
                    : eligible > 0
                      ? 100
                      : 0;
                const progressColor =
                  quotaNumber > 0 && eligible > quotaNumber
                    ? "bg-orange-500"
                    : "bg-blue-500";
                const displayLabel = locale === "zh" ? label : labelEn || label;

                const demandLabel =
                  quotaNumber > 0
                    ? delta >= 0
                      ? {
                          text:
                            locale === "zh"
                              ? `尚餘 ${delta}`
                              : `${delta} remaining`,
                          className: "text-emerald-600",
                        }
                      : {
                          text:
                            locale === "zh"
                              ? `超出 ${Math.abs(delta)}`
                              : `${Math.abs(delta)} over`,
                          className: "text-orange-600",
                        }
                    : {
                        text:
                          locale === "zh"
                            ? `需求 ${eligible}`
                            : `${eligible} applicants`,
                        className: "text-slate-500",
                      };

                return (
                  <Card key={code} className="border border-slate-200">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-medium text-slate-700">
                            {displayLabel}
                          </p>
                          <p className={`text-xs ${demandLabel.className}`}>
                            {demandLabel.text}
                          </p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-muted-foreground">
                            {locale === "zh" ? "配額" : "Quota"}
                          </p>
                          <p className="text-lg font-semibold text-slate-800">
                            {formatValue(quotaNumber)}
                          </p>
                        </div>
                      </div>

                      <div className="mt-3">
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            {locale === "zh"
                              ? `需求 ${eligible}`
                              : `Demand ${eligible}`}
                          </span>
                          <span>{ratio}%</span>
                        </div>
                        <Progress
                          value={ratio}
                          className="mt-1 h-2"
                          indicatorClassName={progressColor}
                          aria-label={
                            locale === "zh"
                              ? `${displayLabel} 需求與配額比`
                              : `Quota usage for ${displayLabel}`
                          }
                        />
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export function CollegeDashboard({
  user,
  locale = "zh",
}: CollegeDashboardProps) {
  const t = (key: string) => getTranslation(locale, key);
  const {
    applications,
    isLoading,
    error,
    updateApplicationStatus,
    fetchCollegeApplications,
  } = useCollegeApplications();

  // Configuration fetch functions
  const getAcademicConfig = async (): Promise<AcademicConfig> => {
    if (academicConfig) return academicConfig;

    // Calculate current academic year (ROC system)
    const currentDate = new Date();
    const currentYear = currentDate.getFullYear() - 1911;
    const currentMonth = currentDate.getMonth() + 1;

    // Determine semester based on month (Aug-Jan = FIRST, Feb-July = SECOND)
    const currentSemester: "FIRST" | "SECOND" =
      currentMonth >= 8 || currentMonth <= 1 ? "FIRST" : "SECOND";

    const config: AcademicConfig = {
      currentYear,
      currentSemester,
      availableYears: [currentYear - 1, currentYear, currentYear + 1],
    };

    setAcademicConfig(config);
    return config;
  };

  const getScholarshipConfig = async (): Promise<ScholarshipConfig[]> => {
    if (scholarshipConfig.length > 0) return scholarshipConfig;

    try {
      // Ensure availableOptions is loaded first
      let currentAvailableOptions = availableOptions;
      if (!currentAvailableOptions) {
        console.log("Available options not loaded yet, fetching now...");
        const response = await apiClient.college.getAvailableCombinations();
        console.log("Available combinations API response:", response);

        if (response.success && response.data) {
          currentAvailableOptions = response.data;
        } else {
          console.error("API returned unsuccessful response:", response);
        }
      }

      // If still not available after fetching, throw error
      if (!currentAvailableOptions?.scholarship_types) {
        console.error("No scholarship types available:", currentAvailableOptions);
        throw new Error(
          "Unable to load available scholarship options from college API"
        );
      }

      // Check if scholarship_types is empty
      if (currentAvailableOptions.scholarship_types.length === 0) {
        console.error("Scholarship types array is empty");
        throw new Error(
          "No active scholarships available. Please contact administrator."
        );
      }

      // Fetch all scholarships to get the actual IDs that we need for creating rankings
      console.log("Fetching all scholarships to get IDs...");
      const allScholarshipsResponse = await apiClient.scholarships.getAll();

      if (allScholarshipsResponse.success && allScholarshipsResponse.data) {
        console.log("All scholarships:", allScholarshipsResponse.data);
        console.log(
          "Available scholarship types from college:",
          currentAvailableOptions.scholarship_types
        );

        // Map college scholarship types to full scholarship data with IDs
        const configs: ScholarshipConfig[] = [];

        for (const collegeType of currentAvailableOptions.scholarship_types) {
          // Find the matching scholarship by code
          const fullScholarship = allScholarshipsResponse.data.find(
            (scholarship: any) =>
              scholarship.code === collegeType.code ||
              scholarship.name === collegeType.name ||
              scholarship.name_en === collegeType.name
          );

          if (fullScholarship) {
            configs.push({
              id: fullScholarship.id,
              name: collegeType.name,
              code: collegeType.code,
              subTypes: [{ code: "default", name: "Default" }], // Use default sub-type
            });
          } else {
            console.warn(
              `Could not find full scholarship data for college type: ${collegeType.code} - ${collegeType.name}`
            );
          }
        }

        console.log("Mapped scholarship configs:", configs);
        setScholarshipConfig(configs);
        return configs;
      }

      // If no data available, throw error instead of using fallback data
      throw new Error("Failed to retrieve scholarship data from API");
    } catch (error) {
      console.error("Failed to fetch scholarship configuration:", error);
      throw new Error(
        `Failed to retrieve scholarship configuration: ${error instanceof Error ? error.message : "Unknown error"}`
      );
    }
  };

  const [viewMode, setViewMode] = useState<"card" | "table">("card");
  const [selectedApplication, setSelectedApplication] = useState<any>(null);
  const [activeTab, setActiveTab] = useState("review");
  const [activeScholarshipTab, setActiveScholarshipTab] = useState<string>(); // 獎學金類型選擇 tab
  const [rankingData, setRankingData] = useState<RankingData | null>(null);
  const [rankings, setRankings] = useState<any[]>([]);
  const [selectedRanking, setSelectedRanking] = useState<number | null>(null);
  const [isRankingLoading, setIsRankingLoading] = useState(false);
  const [scholarshipConfig, setScholarshipConfig] = useState<
    ScholarshipConfig[]
  >([]);
  const [academicConfig, setAcademicConfig] = useState<AcademicConfig | null>(
    null
  );
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [applicationToDelete, setApplicationToDelete] = useState<any>(null);
  const [showDocumentRequestDialog, setShowDocumentRequestDialog] = useState(false);
  const [applicationToRequestDocs, setApplicationToRequestDocs] = useState<any>(null);
  const [showDeleteRankingDialog, setShowDeleteRankingDialog] = useState(false);
  const [rankingToDelete, setRankingToDelete] = useState<any>(null);

  // Ranking name editing state
  const [editingRankingId, setEditingRankingId] = useState<number | null>(null);
  const [editingRankingName, setEditingRankingName] = useState<string>("");

  // 學期選擇相關狀態
  const [selectedAcademicYear, setSelectedAcademicYear] = useState<number>();
  const [selectedSemester, setSelectedSemester] = useState<string>();
  const [selectedCombination, setSelectedCombination] = useState<string>();
  const [selectedScholarshipType, setSelectedScholarshipType] =
    useState<string>();

  // 可用選項狀態
  const [availableOptions, setAvailableOptions] = useState<{
    scholarship_types: Array<{ code: string; name: string; name_en?: string }>;
    academic_years: number[];
    semesters: string[];
  } | null>(null);

  const filteredRankings = useMemo(() => {
    const activeConfig = scholarshipConfig.find(
      config => config.code === activeScholarshipTab
    );

    const desiredSemester = selectedSemester
      ? selectedSemester === "YEARLY"
        ? null
        : selectedSemester.toLowerCase()
      : undefined;

    return rankings.filter(ranking => {
      const matchesScholarship = activeConfig
        ? ranking.scholarship_type_id === activeConfig.id
        : true;

      const matchesYear =
        typeof selectedAcademicYear === "number"
          ? ranking.academic_year === selectedAcademicYear
          : true;

      const rankingSemesterRaw =
        ranking.semester !== undefined && ranking.semester !== null
          ? String(ranking.semester).toLowerCase()
          : null;
      const rankingSemester =
        rankingSemesterRaw && rankingSemesterRaw !== "yearly"
          ? rankingSemesterRaw
          : null;

      const matchesSemester =
        desiredSemester === undefined
          ? true
          : desiredSemester === null
            ? rankingSemester === null
            : rankingSemester === desiredSemester;

      return matchesScholarship && matchesYear && matchesSemester;
    });
  }, [
    rankings,
    scholarshipConfig,
    activeScholarshipTab,
    selectedAcademicYear,
    selectedSemester,
  ]);

  useEffect(() => {
    if (!selectedRanking) return;
    const exists = filteredRankings.some(
      ranking => ranking.id === selectedRanking
    );

    if (!exists) {
      setSelectedRanking(null);
      setRankingData(null);
    }
  }, [filteredRankings, selectedRanking]);

  const collegeDisplayName = useMemo(() => {
    // Format: 學院名稱(代號) e.g., "資訊學院(CS)"
    if (user?.college_name && user?.college_code) {
      return `${user.college_name}(${user.college_code})`;
    }
    // If only code is available, show just the code
    if (user?.college_code) {
      return user.college_code;
    }
    return locale === "zh" ? "未指定" : "Unspecified";
  }, [user, locale]);

  // Fetch rankings and configuration on component mount
  useEffect(() => {
    const initializeData = async () => {
      await getAcademicConfig();
      await fetchAvailableOptions();
      await fetchRankings();
      await getScholarshipConfig();
    };
    initializeData();
  }, []);

  const fetchAvailableOptions = async () => {
    try {
      console.log("Fetching available combinations...");
      const response = await apiClient.college.getAvailableCombinations();
      console.log("fetchAvailableOptions response:", response);

      if (response.success && response.data) {
        console.log("Setting availableOptions:", response.data);
        setAvailableOptions(response.data);

        // 取得當前學期資訊
        const currentConfig = await getAcademicConfig();
        const currentCombination = `${currentConfig.currentYear}-${currentConfig.currentSemester}`;

        // 檢查當前學期組合是否存在於可用選項中
        const hasCurrentCombination =
          response.data.academic_years?.includes(currentConfig.currentYear) &&
          response.data.semesters?.includes(currentConfig.currentSemester);

        // 檢查是否有學年制獎學金（YEARLY 選項）
        const hasYearlyOption = response.data.semesters?.includes("YEARLY");

        // 設定預設學期組合
        if (hasCurrentCombination && !selectedCombination) {
          setSelectedCombination(currentCombination);
          setSelectedAcademicYear(currentConfig.currentYear);
          setSelectedSemester(currentConfig.currentSemester);
        } else if (
          hasYearlyOption &&
          !selectedCombination &&
          response.data.academic_years?.length > 0
        ) {
          // 如果有學年制獎學金，優先選擇當前年度的全年選項
          const yearlyYear = response.data.academic_years.includes(
            currentConfig.currentYear
          )
            ? currentConfig.currentYear
            : response.data.academic_years[0];
          const yearlyCombination = `${yearlyYear}-YEARLY`;
          setSelectedCombination(yearlyCombination);
          setSelectedAcademicYear(yearlyYear);
          setSelectedSemester("YEARLY");
        } else if (
          !selectedCombination &&
          response.data.academic_years?.length > 0 &&
          response.data.semesters?.length > 0
        ) {
          // 否則設定第一個可用的學期
          const firstYear = response.data.academic_years[0];
          const firstSemester = response.data.semesters[0];
          const fallbackCombination = `${firstYear}-${firstSemester}`;
          setSelectedCombination(fallbackCombination);
          setSelectedAcademicYear(firstYear);
          setSelectedSemester(firstSemester);
        }

        // 設定第一個獎學金類型為預設 tab
        if (
          response.data.scholarship_types &&
          response.data.scholarship_types.length > 0 &&
          !activeScholarshipTab
        ) {
          const firstType = response.data.scholarship_types[0].code;
          setActiveScholarshipTab(firstType);

          // 使用已設定的學期載入申請資料
          let useYear, useSemester;
          if (hasCurrentCombination) {
            useYear = currentConfig.currentYear;
            useSemester = currentConfig.currentSemester;
          } else if (hasYearlyOption) {
            useYear = response.data.academic_years.includes(
              currentConfig.currentYear
            )
              ? currentConfig.currentYear
              : response.data.academic_years[0];
            useSemester = "YEARLY";
          } else {
            useYear = response.data.academic_years?.[0] || undefined;
            useSemester = response.data.semesters?.[0] || undefined;
          }

          fetchCollegeApplications(useYear, useSemester, firstType);
        }
      } else {
        console.error("Failed to fetch available options:", response.message);
        throw new Error(
          `Failed to retrieve available options: ${response.message}`
        );
      }
    } catch (error) {
      console.error("Failed to fetch available options:", error);
      throw new Error(
        `Failed to retrieve available options from database: ${error instanceof Error ? error.message : "Unknown error"}`
      );
    }
  };

  const fetchRankings = async () => {
    try {
      console.log("Fetching rankings...");
      const response = await apiClient.college.getRankings();
      if (response.success && response.data) {
        console.log(`Fetched ${response.data.length} rankings:`, response.data);
        const normalizedRankings = response.data.map((ranking: any) => {
          const rawSemester =
            typeof ranking.semester === "string" && ranking.semester.length > 0
              ? ranking.semester.toLowerCase()
              : null;
          const safeSemester =
            rawSemester && rawSemester !== "yearly"
              ? rawSemester
              : null;
          return { ...ranking, semester: safeSemester };
        });
        setRankings(normalizedRankings);
      } else {
        console.warn("No rankings found or error:", response.message);
        setRankings([]);
      }
    } catch (error) {
      console.error("Failed to fetch rankings:", error);
      setRankings([]);
    }
  };

  const fetchRankingDetails = async (rankingId: number) => {
    setIsRankingLoading(true);
    try {
      const response = await apiClient.college.getRanking(rankingId);
      if (response.success && response.data) {
        // Transform the API response to match the expected format for CollegeRankingTable
        const transformedApplications = (response.data.items || []).map(
          (item: any) => {
            const fallbackStudentName =
              item.student_name ||
              item.application?.student_info?.display_name ||
              "未提供姓名";
            const fallbackStudentId =
              item.student_id ||
              item.application?.student_info?.student_id ||
              item.application?.student_info?.student_id_masked ||
              "N/A";

            return {
              id: item.application?.id || item.id,
              app_id: item.application?.app_id || `APP-${item.id}`,
              student_name: fallbackStudentName,
              student_id: fallbackStudentId,
              student_termcount:
                item.application?.student_info?.term_count ??
                item.application?.student_info?.study_terms ??
                item.student_term_count ??
                item.student_termcount ??
                null,
            scholarship_type:
              item.application?.scholarship_type || item.scholarship_type || "",
            sub_type: item.application?.sub_type || item.sub_type || "",
            eligible_subtypes: item.application?.eligible_subtypes || [],  // Eligible sub-types for badges
            total_score: item.total_score || 0,
            rank_position: item.rank_position || 0,
            is_allocated: item.is_allocated || false,
            status: item.status || "pending",
            review_status: item.application?.status || "pending",
            };
          }
        );

        const rawSemester =
          typeof response.data.semester === "string"
            ? response.data.semester
            : null;
        const normalizedSemester =
          rawSemester && rawSemester.length > 0
            ? rawSemester.toLowerCase()
            : null;
        const safeSemester =
          normalizedSemester && normalizedSemester !== "yearly"
            ? normalizedSemester
            : null;

        const subTypeMetaArray = Array.isArray(response.data.sub_type_metadata)
          ? response.data.sub_type_metadata
          : [];
        const subTypeMetaMap = subTypeMetaArray.reduce(
          (acc: Record<string, { code: string; label: string; label_en: string }>, item: any) => {
            if (item && item.code) {
              acc[item.code] = {
                code: item.code,
                label: item.label || item.code,
                label_en: item.label_en || item.label || item.code,
              };
            }
            return acc;
          },
          {}
        );

        if (response.data.sub_type_code && !subTypeMetaMap[response.data.sub_type_code]) {
          subTypeMetaMap[response.data.sub_type_code] = {
            code: response.data.sub_type_code,
            label: response.data.sub_type_code,
            label_en: response.data.sub_type_code,
          };
        }

        const normalizedBreakdown = Object.entries(
          response.data.college_quota_breakdown || {}
        ).reduce(
          (acc: Record<string, { quota: number; label: string; label_en: string }>, [code, raw]) => {
            const meta = subTypeMetaMap[code] || { code, label: code, label_en: code };
            let quotaValue = 0;

            if (raw && typeof raw === "object") {
              const maybeQuota = (raw as any).quota;
              if (typeof maybeQuota === "number" && !Number.isNaN(maybeQuota)) {
                quotaValue = maybeQuota;
              } else if (maybeQuota !== undefined) {
                const parsed = Number(maybeQuota);
                quotaValue = Number.isNaN(parsed) ? 0 : parsed;
              }

              const rawLabel = (raw as any).label;
              const rawLabelEn = (raw as any).label_en;
              acc[code] = {
                quota: quotaValue,
                label: rawLabel || meta.label,
                label_en: rawLabelEn || rawLabel || meta.label_en,
              };
            } else {
              const parsed = Number(raw);
              quotaValue = Number.isNaN(parsed) ? 0 : parsed;
              acc[code] = {
                quota: quotaValue,
                label: meta.label,
                label_en: meta.label_en,
              };
            }
            return acc;
          },
          {} as Record<string, { quota: number; label: string; label_en: string }>
        );

        setRankingData({
          applications: transformedApplications,
          totalQuota: response.data.total_quota,
          collegeQuota: response.data.college_quota,  // College-specific quota from backend
          collegeQuotaBreakdown: normalizedBreakdown,
          subTypeMetadata: subTypeMetaMap,
          subTypeCode: response.data.sub_type_code,
          academicYear: response.data.academic_year,
          semester: safeSemester,
          isFinalized: response.data.is_finalized,
        });

        console.log(
          `Loaded ranking ${rankingId} with ${transformedApplications.length} applications`
        );
      } else {
        console.error("Failed to load ranking details:", response.message);
        // Clear ranking data on failure
        setRankingData(null);
      }
    } catch (error) {
      console.error("Failed to fetch ranking details:", error);
      // Clear ranking data on error
      setRankingData(null);
    } finally {
      setIsRankingLoading(false);
    }
  };

  const handleRankingChange = (newOrder: any[]) => {
    if (rankingData) {
      setRankingData({
        ...rankingData,
        applications: newOrder,
      });
    }
  };

  const handleReviewApplication = async (
    applicationId: number,
    action: 'approve' | 'reject',
    comments?: string
  ) => {
    try {
      // Call API to submit review
      const response = await apiClient.college.reviewApplication(applicationId, {
        recommendation: action,
        review_comments: comments,
      });

      if (response.success) {
        alert(`${action === 'approve' ? '核准' : '駁回'}成功：申請 #${applicationId} 已${action === 'approve' ? '核准' : '駁回'}`);

        // Refresh ranking data to show updated review status
        if (selectedRanking) {
          await fetchRankingDetails(selectedRanking);
        }
      } else {
        throw new Error(response.message || '操作失敗');
      }
    } catch (error) {
      console.error('Review submission error:', error);
      alert(`提交失敗：${error instanceof Error ? error.message : '無法提交審查意見'}`);
    }
  };

  const handleExecuteDistribution = async () => {
    if (selectedRanking) {
      try {
        // Use matrix distribution endpoint
        const response = await apiClient.college.executeMatrixDistribution(
          selectedRanking
        );
        if (response.success) {
          console.log("Matrix distribution executed successfully:", response.data);
          // Refresh ranking data to show updated allocation status
          await fetchRankingDetails(selectedRanking);
          // Switch to distribution tab to show results
          setActiveTab("distribution");
        } else {
          console.error("Failed to execute distribution:", response.message);
          alert(`分配執行失敗：${response.message}`);
        }
      } catch (error) {
        console.error("Failed to execute distribution:", error);
        alert(`分配執行時發生錯誤：${error instanceof Error ? error.message : "未知錯誤"}`);
      }
    }
  };

  const handleFinalizeRanking = async (targetRankingId?: number) => {
    const rankingId = targetRankingId ?? selectedRanking;
    if (!rankingId) {
      return;
    }

    try {
      const response = await apiClient.college.finalizeRanking(rankingId);
      if (response.success) {
        // Refresh rankings list
        await fetchRankings();
        // Update current ranking data if it matches the locked ranking
        if (rankingData && rankingId === selectedRanking) {
          setRankingData({
            ...rankingData,
            isFinalized: true,
          });
        }
      } else {
        console.error("Failed to finalize ranking:", response.message);
      }
    } catch (error) {
      console.error("Failed to finalize ranking:", error);
    }
  };

  const handleImportExcel = async (data: any[]) => {
    if (!selectedRanking) {
      throw new Error("No ranking selected");
    }

    try {
      const response = await apiClient.college.importRankingExcel(
        selectedRanking,
        data
      );

      if (response.success) {
        // Refresh ranking details to show updated data
        await fetchRankingDetails(selectedRanking);
        console.log("Excel import successful:", response.data);
      } else {
        throw new Error(response.message || "Failed to import ranking data");
      }
    } catch (error) {
      console.error("Failed to import Excel:", error);
      throw error;
    }
  };

  const handleDeleteRanking = async () => {
    if (!rankingToDelete) return;

    try {
      const response = await apiClient.college.deleteRanking(rankingToDelete.id);
      if (response.success) {
        // Clear selection if deleted ranking was selected
        if (selectedRanking === rankingToDelete.id) {
          setSelectedRanking(null);
          setRankingData(null);
        }
        // Refresh rankings list
        await fetchRankings();
        // Close dialog
        setShowDeleteRankingDialog(false);
        setRankingToDelete(null);
      } else {
        alert(`刪除排名失敗：${response.message}`);
      }
    } catch (error) {
      console.error("Failed to delete ranking:", error);
      alert(`刪除排名失敗：${error instanceof Error ? error.message : "未知錯誤"}`);
    }
  };

  const handleEditRankingName = (ranking: any) => {
    setEditingRankingId(ranking.id);
    setEditingRankingName(ranking.ranking_name);
  };

  const handleSaveRankingName = async (rankingId: number) => {
    try {
      const response = await apiClient.college.updateRanking(rankingId, {
        ranking_name: editingRankingName,
      });
      if (response.success) {
        // Refresh rankings list
        await fetchRankings();
        // Clear editing state
        setEditingRankingId(null);
        setEditingRankingName("");
      } else {
        alert(`更新排名名稱失敗：${response.message}`);
      }
    } catch (error) {
      console.error("Failed to update ranking name:", error);
      alert(`更新排名名稱失敗：${error instanceof Error ? error.message : "未知錯誤"}`);
    }
  };

  const handleCancelEditRankingName = () => {
    setEditingRankingId(null);
    setEditingRankingName("");
  };

  const createNewRanking = async (
    scholarshipTypeId?: number,
    subTypeCode?: string
  ) => {
    try {
      // Get academic configuration from API or system settings
      const academicConfig = await getAcademicConfig();
      const scholarshipConfig = await getScholarshipConfig();

      if (!scholarshipTypeId && scholarshipConfig.length === 0) {
        throw new Error("No scholarship types available");
      }

      // Determine the scholarship type to use
      let targetScholarshipId = scholarshipTypeId;
      let targetSubTypeCode = subTypeCode;

      // If no specific scholarship type provided, find the one matching current tab
      if (
        !targetScholarshipId &&
        activeScholarshipTab &&
        availableOptions?.scholarship_types
      ) {
        const currentScholarshipType = availableOptions.scholarship_types.find(
          type => type.code === activeScholarshipTab
        );
        if (currentScholarshipType) {
          // Get the scholarship ID from the scholarship config
          const configScholarship = scholarshipConfig.find(
            config => config.name === currentScholarshipType.name
          );
          targetScholarshipId =
            configScholarship?.id || scholarshipConfig[0]?.id;
          targetSubTypeCode =
            configScholarship?.subTypes[0]?.code ||
            scholarshipConfig[0]?.subTypes[0]?.code;
        }
      }

      // Fallback to first scholarship if still not found
      if (!targetScholarshipId) {
        const defaultScholarship = scholarshipConfig[0];
        targetScholarshipId = defaultScholarship?.id;
        targetSubTypeCode = defaultScholarship?.subTypes[0]?.code;
      }

      // Use selected academic year and semester from the UI state
      const useYear = selectedAcademicYear || academicConfig.currentYear;
      const useSemester = selectedSemester || academicConfig.currentSemester;

      const semesterName =
        useSemester === "FIRST"
          ? "上學期"
          : useSemester === "SECOND"
            ? "下學期"
            : useSemester === "YEARLY"
              ? "全年"
              : "學期";

      const newRanking = {
        scholarship_type_id: targetScholarshipId,
        sub_type_code: targetSubTypeCode || "default",
        academic_year: useYear,
        semester: useSemester,
        ranking_name: `新建排名 - ${useYear}學年度 ${semesterName}`,
        force_new: true,
      };

      const response = await apiClient.college.createRanking(newRanking);
      if (response.success) {
        console.log("Ranking created successfully:", response.data);
        // Refresh rankings
        await fetchRankings();
      } else {
        console.error("Failed to create ranking:", response.message);
        throw new Error(`Failed to create ranking: ${response.message}`);
      }
    } catch (error) {
      console.error("Failed to create ranking:", error);
      throw error;
    }
  };

  const handleApprove = async (appId: number) => {
    try {
      await updateApplicationStatus(appId, "approved", "學院核准通過");
      console.log(`College approved application ${appId}`);
    } catch (error) {
      console.error("Failed to approve application:", error);
    }
  };

  const handleReject = async (appId: number) => {
    try {
      await updateApplicationStatus(appId, "rejected", "學院駁回申請");
      console.log(`College rejected application ${appId}`);
    } catch (error) {
      console.error("Failed to reject application:", error);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-nycu-navy-600">載入學院審核資料中...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-red-600" />
          <p className="text-red-700">載入資料時發生錯誤：{error}</p>
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
          className={`grid w-full grid-cols-${Math.min(availableOptions?.scholarship_types?.length || 3, 5)}`}
        >
          {availableOptions?.scholarship_types?.map(type => (
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
        {availableOptions?.scholarship_types?.map(scholarshipType => (
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
                  申請審核
                </TabsTrigger>
                <TabsTrigger
                  value="ranking"
                  className="flex items-center gap-2"
                >
                  <Trophy className="h-4 w-4" />
                  學生排序
                </TabsTrigger>
                <TabsTrigger
                  value="distribution"
                  className="flex items-center gap-2"
                >
                  <Award className="h-4 w-4" />
                  獎學金分發
                </TabsTrigger>
              </TabsList>

              {/* 申請審核標籤頁 */}
              <TabsContent value="review" className="space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-3xl font-bold tracking-tight">
                      {locale === "zh"
                        ? "學院審核管理"
                        : "College Review Management"}{" "}
                      -{" "}
                      {availableOptions?.scholarship_types?.find(
                        type => type.code === scholarshipType.code
                      )?.name || scholarshipType.name}
                    </h2>
                    <p className="text-muted-foreground">
                      {locale === "zh"
                        ? "學院層級的獎學金申請審核"
                        : "College-level scholarship application reviews"}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* 學期學年選擇 - 移到這裡 */}
                    <Select
                      value={selectedCombination || ""}
                      onValueChange={value => {
                        setSelectedCombination(value);
                        const [year, semester] = value.split("-");
                        setSelectedAcademicYear(parseInt(year));
                        setSelectedSemester(semester || undefined);
                        // 重新載入該獎學金類型的申請資料
                        fetchCollegeApplications(
                          parseInt(year),
                          semester || undefined,
                          activeScholarshipTab
                        );
                      }}
                    >
                      <SelectTrigger className="w-48">
                        <SelectValue placeholder="選擇學期">
                          <div className="flex items-center">
                            <Calendar className="h-4 w-4 mr-2" />
                            {selectedCombination
                              ? `${selectedCombination.split("-")[0]} ${
                                  selectedCombination.split("-")[1] === "FIRST"
                                    ? "上學期"
                                    : selectedCombination.split("-")[1] ===
                                        "SECOND"
                                      ? "下學期"
                                      : selectedCombination.split("-")[1] ===
                                          "YEARLY"
                                        ? "全年"
                                        : selectedCombination.split("-")[1]
                                }`
                              : "選擇學期"}
                          </div>
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {availableOptions?.academic_years?.map(year =>
                          availableOptions?.semesters?.map(semester => (
                            <SelectItem
                              key={`${year}-${semester}`}
                              value={`${year}-${semester}`}
                            >
                              {year} 學年度{" "}
                              {semester === "FIRST"
                                ? "上學期"
                                : semester === "SECOND"
                                  ? "下學期"
                                  : semester === "YEARLY"
                                    ? "全年"
                                    : semester}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>

                    <Button variant="outline" size="sm">
                      <Download className="h-4 w-4 mr-1" />
                      {locale === "zh" ? "匯出" : "Export"}
                    </Button>
                    <div className="flex items-center border rounded-md">
                      <Button
                        variant={viewMode === "card" ? "default" : "ghost"}
                        size="sm"
                        onClick={() => setViewMode("card")}
                      >
                        <Grid className="h-4 w-4" />
                      </Button>
                      <Button
                        variant={viewMode === "table" ? "default" : "ghost"}
                        size="sm"
                        onClick={() => setViewMode("table")}
                      >
                        <List className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Statistics */}
                <div className="grid gap-4 md:grid-cols-4">
                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">
                        {locale === "zh" ? "待審核" : "Pending Review"}
                      </CardTitle>
                      <GraduationCap className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {
                          applications.filter(
                            app =>
                              app.status === "recommended" ||
                              app.status === "submitted"
                          ).length
                        }
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {locale === "zh"
                          ? "需要學院審核"
                          : "Requires college review"}
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">
                        {locale === "zh" ? "審核中" : "Under Review"}
                      </CardTitle>
                      <Eye className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {
                          applications.filter(
                            app =>
                              app.status === "under_review" ||
                              (app.status === "recommended" &&
                                app.college_review_completed)
                          ).length
                        }
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {locale === "zh" ? "學院審核中" : "College reviewing"}
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">
                        {locale === "zh" ? "學院配額" : "College Quota"}
                      </CardTitle>
                      <Award className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold">
                        {rankingData?.collegeQuota !== undefined
                          ? rankingData.collegeQuota.toLocaleString()
                          : rankingData?.totalQuota !== undefined
                            ? rankingData.totalQuota.toLocaleString()
                            : "-"}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {locale === "zh"
                          ? "本院可分配的名額"
                          : "Seats allocated to this college"}
                      </p>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium">
                        {locale === "zh" ? "學院名稱" : "College"}
                      </CardTitle>
                      <Building className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold leading-tight">
                        {collegeDisplayName}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {locale === "zh"
                          ? "目前檢視的學院"
                          : "Currently selected college"}
                      </p>
                    </CardContent>
                  </Card>
                </div>

                {applications.length === 0 ? (
                  <div className="text-center py-8">
                    <School className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
                    <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
                      {locale === "zh"
                        ? "暫無待審核申請"
                        : "No Applications Pending Review"}
                    </h3>
                    <p className="text-nycu-navy-600">
                      {locale === "zh"
                        ? "目前沒有需要學院審核的申請案件"
                        : "No applications currently require college review"}
                    </p>
                  </div>
                ) : (
                  <>
                    {/* Filters */}
                    <div className="flex items-center gap-4">
                      <div className="relative flex-1 max-w-sm">
                        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                        <Input
                          placeholder={
                            locale === "zh"
                              ? "搜尋學生或學號..."
                              : "Search student or ID..."
                          }
                          className="pl-8"
                        />
                      </div>
                      <Select defaultValue="all">
                        <SelectTrigger className="w-40">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="all">
                            {locale === "zh" ? "全部狀態" : "All Status"}
                          </SelectItem>
                          <SelectItem value="pending">
                            {locale === "zh" ? "待審核" : "Pending"}
                          </SelectItem>
                          <SelectItem value="under_review">
                            {locale === "zh" ? "審核中" : "Under Review"}
                          </SelectItem>
                          <SelectItem value="approved">
                            {locale === "zh" ? "已核准" : "Approved"}
                          </SelectItem>
                          <SelectItem value="rejected">
                            {locale === "zh" ? "已駁回" : "Rejected"}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    {/* Applications View */}
                    <Card>
                      <CardHeader>
                        <CardTitle>
                          {locale === "zh" ? "申請清單" : "Applications List"}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>
                                {locale === "zh" ? "學生" : "Student"}
                              </TableHead>
                              <TableHead>
                                {locale === "zh" ? "就讀學期數" : "Terms"}
                              </TableHead>
                              <TableHead>
                                {locale === "zh"
                                  ? "獎學金類型"
                                  : "Scholarship Type"}
                              </TableHead>
                              <TableHead>
                                {locale === "zh" ? "申請類別" : "Type"}
                              </TableHead>
                              <TableHead>
                                {locale === "zh" ? "狀態" : "Status"}
                              </TableHead>
                              <TableHead>
                                {locale === "zh" ? "申請時間" : "Applied"}
                              </TableHead>
                              <TableHead>
                                {locale === "zh" ? "操作" : "Actions"}
                              </TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {applications.map(app => (
                              <TableRow key={app.id}>
                                <TableCell>
                                  <div className="flex flex-col gap-1">
                                    <span className="font-medium">
                                      {app.student_name || "未提供姓名"}
                                    </span>
                                    <span className="text-sm text-muted-foreground">
                                      {app.student_id || "未提供學號"}
                                    </span>
                                  </div>
                                </TableCell>
                                <TableCell>
                                  {app.student_termcount || "-"}
                                </TableCell>
                                <TableCell>
                                  {app.scholarship_type_zh || app.scholarship_type}
                                </TableCell>
                                <TableCell>
                                  <Badge variant={app.is_renewal ? "secondary" : "default"}>
                                    {app.is_renewal ? "續領" : "初領"}
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  <Badge
                                    variant={getStatusColor(app.status as ApplicationStatus)}
                                  >
                                    {app.status_zh || getStatusName(app.status as ApplicationStatus, locale)}
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  {app.created_at
                                    ? new Date(
                                        app.created_at
                                      ).toLocaleDateString("zh-TW", {
                                        year: "numeric",
                                        month: "2-digit",
                                        day: "2-digit",
                                      })
                                    : "未知日期"}
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Dialog>
                                      <DialogTrigger asChild>
                                        <Button
                                          variant="outline"
                                          size="sm"
                                          onClick={() =>
                                            setSelectedApplication(app)
                                          }
                                        >
                                          <Eye className="h-4 w-4" />
                                        </Button>
                                      </DialogTrigger>
                                      <DialogContent className="max-w-4xl max-h-[90vh]">
                                        <DialogHeader>
                                          <DialogTitle>
                                            學院審核 -{" "}
                                            {app.app_id || `APP-${app.id}`}
                                          </DialogTitle>
                                          <DialogDescription>
                                            {app.student_name || "未提供姓名"} (
                                            {app.student_id || "未提供學號"}) -{" "}
                                            {availableOptions?.scholarship_types?.find(
                                              type =>
                                                type.code ===
                                                app.scholarship_type
                                            )?.name || app.scholarship_type}
                                          </DialogDescription>
                                        </DialogHeader>
                                        {selectedApplication && (
                                          <Tabs defaultValue="review" className="w-full">
                                            <TabsList className="grid w-full grid-cols-3">
                                              <TabsTrigger value="review">
                                                審核
                                              </TabsTrigger>
                                              <TabsTrigger value="documents">
                                                文件
                                              </TabsTrigger>
                                              <TabsTrigger value="audit">
                                                操作紀錄
                                              </TabsTrigger>
                                            </TabsList>

                                            <TabsContent value="review" className="space-y-4 mt-4">
                                              <div>
                                                <label className="text-sm font-medium">
                                                  學院審核意見
                                                </label>
                                                <Textarea
                                                  placeholder="請輸入學院審核意見..."
                                                  className="mt-1"
                                                />
                                              </div>
                                              <div className="space-y-2 pt-4">
                                                <div className="flex gap-2">
                                                  <Button
                                                    onClick={() =>
                                                      handleApprove(
                                                        selectedApplication.id
                                                      )
                                                    }
                                                    className="flex-1"
                                                  >
                                                    <CheckCircle className="h-4 w-4 mr-1" />
                                                    學院核准
                                                  </Button>
                                                  <Button
                                                    variant="destructive"
                                                    onClick={() =>
                                                      handleReject(
                                                        selectedApplication.id
                                                      )
                                                    }
                                                    className="flex-1"
                                                  >
                                                    <XCircle className="h-4 w-4 mr-1" />
                                                    學院駁回
                                                  </Button>
                                                </div>
                                                <Button
                                                  variant="outline"
                                                  onClick={() => {
                                                    setApplicationToRequestDocs(selectedApplication);
                                                    setShowDocumentRequestDialog(true);
                                                  }}
                                                  className="w-full border-orange-200 text-orange-600 hover:bg-orange-50 hover:text-orange-700"
                                                >
                                                  <FileText className="h-4 w-4 mr-1" />
                                                  要求補件
                                                </Button>
                                                <Button
                                                  variant="outline"
                                                  onClick={() => {
                                                    setApplicationToDelete(selectedApplication);
                                                    setShowDeleteDialog(true);
                                                  }}
                                                  className="w-full border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
                                                >
                                                  <Trash2 className="h-4 w-4 mr-1" />
                                                  刪除申請
                                                </Button>
                                              </div>
                                            </TabsContent>

                                            <TabsContent value="documents" className="mt-4">
                                              <div className="text-center py-8 text-gray-500">
                                                文件列表功能開發中...
                                              </div>
                                            </TabsContent>

                                            <TabsContent value="audit" className="mt-4">
                                              <ApplicationAuditTrail
                                                applicationId={selectedApplication.id}
                                                locale={locale}
                                              />
                                            </TabsContent>
                                          </Tabs>
                                        )}
                                      </DialogContent>
                                    </Dialog>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  </>
                )}
              </TabsContent>

              {/* 學生排序標籤頁 */}
              <TabsContent value="ranking" className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-3xl font-bold tracking-tight">
                      學生排序管理 - {scholarshipType.name}
                    </h2>
                    <p className="text-muted-foreground">
                      管理獎學金申請的排序和排名
                    </p>
                  </div>
                  <Button
                    onClick={async () => {
                      try {
                        await createNewRanking();
                      } catch (error) {
                        console.error("Failed to create ranking:", error);
                        alert(
                          `無法建立新排名：${error instanceof Error ? error.message : "未知錯誤"}`
                        );
                      }
                    }}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    建立新排名
                  </Button>
                </div>

                {/* Ranking Selection */}
                <Card>
                  <CardHeader>
                    <CardTitle>選擇排名</CardTitle>
                    <CardDescription>選擇要管理的排名清單</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {filteredRankings.length === 0 ? (
                      <div className="text-center py-12">
                        <Trophy className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
                        <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
                          暫無符合條件的排名
                        </h3>
                        <p className="text-nycu-navy-600 mb-4">
                          {scholarshipType.name}{" "}
                          目前在選定的學年度與學期沒有排名，請點擊上方「建立新排名」按鈕開始
                        </p>
                        <Button
                          onClick={async () => {
                            try {
                              await createNewRanking();
                            } catch (error) {
                              console.error("Failed to create ranking:", error);
                              alert(
                                `無法建立新排名：${error instanceof Error ? error.message : "未知錯誤"}`
                              );
                            }
                          }}
                          variant="outline"
                        >
                          <Plus className="h-4 w-4 mr-2" />
                          立即建立排名
                        </Button>
                      </div>
                    ) : (
                      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {filteredRankings.map((ranking) => {
                          const isSelected = selectedRanking === ranking.id;
                          const isLocked = Boolean(ranking.is_finalized);
                          const cardClasses = [
                            "group cursor-pointer rounded-lg border transition-all duration-200",
                            isSelected
                              ? "border-blue-500 bg-blue-50/80 shadow-md ring-2 ring-blue-100"
                              : "border-slate-200 bg-white hover:border-blue-300 hover:shadow-sm",
                            isLocked ? "opacity-95" : "",
                          ]
                            .filter(Boolean)
                            .join(" ");

                          return (
                            <Card
                              key={ranking.id}
                              className={cardClasses}
                              onClick={() => {
                                setSelectedRanking(ranking.id);
                                fetchRankingDetails(ranking.id);
                              }}
                            >
                              <CardContent className="space-y-3 p-5">
                                <div className="flex items-start justify-between">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge
                                      variant={isLocked ? "default" : "secondary"}
                                      className="flex items-center gap-1"
                                    >
                                      {isLocked ? (
                                        <Lock className="h-3 w-3" />
                                      ) : (
                                        <Clock className="h-3 w-3" />
                                      )}
                                      {isLocked ? "已鎖定" : "進行中"}
                                    </Badge>
                                    {ranking.distribution_executed && (
                                      <Badge className="border-green-200 bg-green-50 text-green-700">
                                        {locale === "zh" ? "已執行分發" : "Distributed"}
                                      </Badge>
                                    )}
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className={`h-8 w-8 p-0 ${isLocked ? "text-blue-600" : "text-slate-500 hover:bg-blue-50 hover:text-blue-600"}`}
                                      disabled={isLocked}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        if (!isLocked) {
                                          handleFinalizeRanking(ranking.id);
                                        }
                                      }}
                                    >
                                      {isLocked ? (
                                        <Lock className="h-4 w-4" />
                                      ) : (
                                        <LockOpen className="h-4 w-4" />
                                      )}
                                      <span className="sr-only">
                                        {isLocked
                                          ? locale === "zh"
                                            ? "排名已鎖定"
                                            : "Ranking locked"
                                          : locale === "zh"
                                            ? "鎖定此排名"
                                            : "Lock this ranking"}
                                      </span>
                                    </Button>
                                    {!isLocked && (
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 p-0 text-red-600 hover:bg-red-50"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setRankingToDelete(ranking);
                                          setShowDeleteRankingDialog(true);
                                        }}
                                      >
                                        <Trash2 className="h-4 w-4" />
                                        <span className="sr-only">
                                          {locale === "zh" ? "刪除此排名" : "Delete ranking"}
                                        </span>
                                      </Button>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-3">
                                  <span
                                    className={`h-4 w-4 rounded-full border-2 transition-colors ${
                                      isSelected
                                        ? "border-blue-500 bg-blue-500 shadow-sm"
                                        : "border-slate-300 bg-white group-hover:border-blue-300"
                                    }`}
                                    aria-hidden
                                  />
                                  {editingRankingId === ranking.id ? (
                                    <div
                                      className="flex flex-1 items-center gap-2"
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      <Input
                                        value={editingRankingName}
                                        onChange={(e) => setEditingRankingName(e.target.value)}
                                        className="h-8 flex-1 text-sm"
                                        autoFocus
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter") {
                                            handleSaveRankingName(ranking.id);
                                          } else if (e.key === "Escape") {
                                            handleCancelEditRankingName();
                                          }
                                        }}
                                      />
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 p-0 text-emerald-600 hover:bg-emerald-50 hover:text-emerald-700"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleSaveRankingName(ranking.id);
                                        }}
                                      >
                                        <Check className="h-4 w-4" />
                                        <span className="sr-only">
                                          {locale === "zh" ? "儲存名稱" : "Save name"}
                                        </span>
                                      </Button>
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="h-8 w-8 p-0 text-slate-500 hover:bg-slate-100"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleCancelEditRankingName();
                                        }}
                                      >
                                        <X className="h-4 w-4" />
                                        <span className="sr-only">
                                          {locale === "zh" ? "取消編輯" : "Cancel edit"}
                                        </span>
                                      </Button>
                                    </div>
                                  ) : (
                                    <>
                                      <h3 className="flex-1 text-sm font-semibold text-slate-800">
                                        {ranking.ranking_name}
                                      </h3>
                                      {!isLocked && (
                                        <Button
                                          variant="ghost"
                                          size="icon"
                                          className="h-7 w-7 p-0 text-slate-500 hover:bg-blue-50 hover:text-blue-600"
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            handleEditRankingName(ranking);
                                          }}
                                        >
                                          <Pencil className="h-3.5 w-3.5" />
                                          <span className="sr-only">
                                            {locale === "zh" ? "重新命名" : "Rename"}
                                          </span>
                                        </Button>
                                      )}
                                    </>
                                  )}
                                </div>
                                <div className="flex items-center gap-2 text-xs text-slate-500">
                                  <Trophy className="h-3.5 w-3.5 text-blue-500" />
                                  <span>
                                    {locale === "zh"
                                      ? `申請數 ${ranking.total_applications ?? 0}`
                                      : `Applicants ${ranking.total_applications ?? 0}`}
                                  </span>
                                  {typeof ranking.allocated_count === "number" && (
                                    <>
                                      <span aria-hidden className="text-slate-300">
                                        •
                                      </span>
                                      <span>
                                        {locale === "zh"
                                          ? `已分配 ${ranking.allocated_count}`
                                          : `Allocated ${ranking.allocated_count}`}
                                      </span>
                                    </>
                                  )}
                                  {ranking.finalized_at && (
                                    <>
                                      <span aria-hidden className="text-slate-300">
                                        •
                                      </span>
                                      <span>
                                        {locale === "zh"
                                          ? "已鎖定"
                                          : "Locked"}
                                      </span>
                                    </>
                                  )}
                                </div>
                              </CardContent>
                            </Card>
                          );
                        })}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Ranking Details */}
                {selectedRanking && rankingData && (
                  <div className="space-y-6">
                    {isRankingLoading ? (
                      <div className="flex items-center justify-center p-8">
                        <Loader2 className="h-8 w-8 animate-spin" />
                      </div>
                    ) : (
                      <CollegeRankingTable
                        applications={rankingData.applications}
                        totalQuota={rankingData.totalQuota}
                        subTypeCode={rankingData.subTypeCode}
                        academicYear={rankingData.academicYear}
                        semester={rankingData.semester}
                        isFinalized={rankingData.isFinalized}
                        rankingId={selectedRanking}
                        onRankingChange={handleRankingChange}
                        onReviewApplication={handleReviewApplication}
                      onExecuteDistribution={handleExecuteDistribution}
                      onFinalizeRanking={handleFinalizeRanking}
                      onImportExcel={handleImportExcel}
                      locale={locale}
                      subTypeMeta={rankingData.subTypeMetadata}
                    />
                  )}
                </div>
              )}
              </TabsContent>

              {/* 獎學金分發標籤頁 */}
              <TabsContent value="distribution" className="space-y-6">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h2 className="text-3xl font-bold tracking-tight">
                      獎學金分發 - {scholarshipType.name}
                    </h2>
                    <p className="text-muted-foreground">
                      執行獎學金的分配和發放
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Select
                      value={selectedRanking ? String(selectedRanking) : undefined}
                      onValueChange={value => {
                        if (value === "no-rankings") return;
                        const rankingId = Number(value);
                        if (!Number.isNaN(rankingId)) {
                          if (rankingId !== selectedRanking) {
                            setSelectedRanking(rankingId);
                          }
                          fetchRankingDetails(rankingId);
                        }
                      }}
                      disabled={filteredRankings.length === 0}
                    >
                      <SelectTrigger
                        className="w-64"
                        disabled={filteredRankings.length === 0}
                      >
                        <SelectValue
                          placeholder={
                            locale === "zh" ? "選擇排名" : "Select a ranking"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {filteredRankings.length > 0 ? (
                          filteredRankings.map(ranking => (
                            <SelectItem
                              key={ranking.id}
                              value={String(ranking.id)}
                            >
                              {ranking.ranking_name}
                              {ranking.is_finalized
                                ? locale === "zh"
                                  ? "（已確認）"
                                  : " (Finalized)"
                                : ""}
                            </SelectItem>
                          ))
                        ) : (
                          <SelectItem value="no-rankings" disabled>
                            {locale === "zh"
                              ? "目前沒有符合條件的排名"
                              : "No rankings available"}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>

                    <Button
                      variant="outline"
                      onClick={handleExecuteDistribution}
                      disabled={!selectedRanking}
                    >
                      <Send className="h-4 w-4 mr-2" />
                      {locale === "zh" ? "執行矩陣分配" : "Execute Distribution"}
                    </Button>
                    <Button
                      variant="default"
                      onClick={() => handleFinalizeRanking()}
                      disabled={!selectedRanking || rankingData?.isFinalized}
                      className={
                        rankingData?.isFinalized
                          ? "bg-slate-200 text-slate-600 hover:bg-slate-200 hover:text-slate-600"
                          : ""
                      }
                    >
                      <Lock className="h-4 w-4 mr-2" />
                      {locale === "zh" ? "鎖定排名結果" : "Lock Ranking"}
                    </Button>
                  </div>
                </div>

                {selectedRanking && rankingData && (
                  <DistributionQuotaSummary
                    locale={locale}
                    totalQuota={rankingData.totalQuota}
                    collegeQuota={rankingData.collegeQuota}
                    applications={rankingData.applications}
                    breakdown={rankingData.collegeQuotaBreakdown}
                    subTypeMeta={rankingData.subTypeMetadata}
                  />
                )}

                {selectedRanking ? (
                  <DistributionResultsPanel
                    rankingId={selectedRanking}
                    applications={rankingData?.applications}
                    locale={locale}
                    subTypeQuotaBreakdown={rankingData?.collegeQuotaBreakdown}
                  />
                ) : (
                  <Card>
                    <CardContent className="p-12 text-center">
                      <Trophy className="h-16 w-16 mx-auto mb-4 text-gray-300" />
                      <h3 className="text-lg font-semibold text-gray-700 mb-2">
                        {locale === "zh" ? "請選擇排名" : "Select a Ranking"}
                      </h3>
                      <p className="text-gray-600">
                        {locale === "zh"
                          ? "請在上方選擇要查看分配結果的排名"
                          : "Use the selector above to choose a ranking to view distribution results"}
                      </p>
                    </CardContent>
                  </Card>
                )}
              </TabsContent>
            </Tabs>
          </TabsContent>
        ))}
      </Tabs>

      {/* Delete Application Dialog */}
      {applicationToDelete && (
        <DeleteApplicationDialog
          open={showDeleteDialog}
          onOpenChange={setShowDeleteDialog}
          applicationId={applicationToDelete.id}
          applicationName={applicationToDelete.app_id || `APP-${applicationToDelete.id}`}
          locale={locale}
          requireReason={true}
          onSuccess={() => {
            // Refresh applications list
            fetchCollegeApplications(
              selectedAcademicYear,
              selectedSemester,
              activeScholarshipTab
            );
            // Reset delete state
            setApplicationToDelete(null);
          }}
        />
      )}

      {/* Document Request Dialog */}
      {applicationToRequestDocs && (
        <DocumentRequestForm
          open={showDocumentRequestDialog}
          onOpenChange={setShowDocumentRequestDialog}
          applicationId={applicationToRequestDocs.id}
          applicationName={applicationToRequestDocs.app_id || `APP-${applicationToRequestDocs.id}`}
          locale={locale}
          onSuccess={() => {
            // Refresh applications list
            fetchCollegeApplications(
              selectedAcademicYear,
              selectedSemester,
              activeScholarshipTab
            );
            // Reset document request state
            setApplicationToRequestDocs(null);
          }}
        />
      )}

      {/* Delete Ranking Confirmation Dialog */}
      <Dialog open={showDeleteRankingDialog} onOpenChange={setShowDeleteRankingDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertCircle className="h-5 w-5 text-red-600" />
              確認刪除排名
            </DialogTitle>
            <DialogDescription>
              {rankingToDelete && (
                <>
                  您確定要刪除排名「{rankingToDelete.ranking_name}」嗎？
                  <br />
                  <br />
                  <span className="text-red-600 font-medium">
                    此操作無法復原，將會永久刪除此排名及其所有相關資料。
                  </span>
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <div className="flex gap-2 justify-end">
            <Button
              variant="outline"
              onClick={() => {
                setShowDeleteRankingDialog(false);
                setRankingToDelete(null);
              }}
            >
              取消
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteRanking}
            >
              <Trash2 className="h-4 w-4 mr-2" />
              確認刪除
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
