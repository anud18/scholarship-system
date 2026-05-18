"use client";

import React, { createContext, useContext, useState, useCallback, useRef, useMemo, useEffect } from "react";
import { apiClient } from "@/lib/api";
import { useCollegeApplications } from "@/hooks/use-admin";
import { Semester } from "@/lib/enums";
import { logger } from "@/lib/utils/logger";
import { Application } from "@/lib/api/types";

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

interface CollegeRanking {
  id: number;
  ranking_name: string;
  is_finalized: boolean;
  distribution_executed: boolean;
  total_applications: number;
  allocated_count?: number;
  distribution_date?: string;
  scholarship_type_id?: number;
  academic_year?: number;
  semester?: string | null;
  [key: string]: unknown;
}

interface AvailableOptions {
  scholarship_types: Array<{ id: number; code: string; name: string; name_en?: string }>;
  academic_years: number[];
  semesters: string[];
}

interface ManagedCollege {
  code: string;
  name: string;
  name_en: string;
  scholarship_count: number;
}

interface RankingData {
  applications: any[];
  totalQuota: number;
  collegeQuota?: number;
  collegeQuotaBreakdown?: SubTypeQuotaBreakdown;
  subTypeMetadata?: Record<string, { code: string; label: string; label_en: string }>;
  subTypeCode: string;
  academicYear: number;
  semester?: string | null;
  isFinalized: boolean;
}

interface CollegeManagementContextType {
  // User & locale
  locale: "zh" | "en";

  // Applications from hook
  applications: Application[];
  isLoading: boolean;
  error: string | null;
  updateApplicationStatus: any;
  fetchCollegeApplications: (academicYear?: number, semester?: string, scholarshipType?: string) => Promise<void>;

  // View state
  viewMode: "card" | "table";
  setViewMode: (mode: "card" | "table") => void;
  selectedApplication: Application | null;
  setSelectedApplication: (app: Application | null) => void;

  // Tab management
  activeTab: string;
  setActiveTab: (tab: string) => void;
  activeScholarshipTab: string | undefined;
  setActiveScholarshipTab: (tab: string | undefined) => void;

  // Ranking state
  rankingData: RankingData | null;
  setRankingData: (data: RankingData | null) => void;
  rankings: CollegeRanking[];
  setRankings: (rankings: CollegeRanking[]) => void;
  selectedRanking: number | null;
  setSelectedRanking: (id: number | null) => void;
  isRankingLoading: boolean;
  setIsRankingLoading: (loading: boolean) => void;
  filteredRankings: CollegeRanking[];

  // Data version tracking for cross-tab synchronization
  dataVersion: number;
  incrementDataVersion: () => void;

  // Configuration
  scholarshipConfig: ScholarshipConfig[];
  setScholarshipConfig: (config: ScholarshipConfig[]) => void;
  academicConfig: AcademicConfig | null;
  setAcademicConfig: (config: AcademicConfig | null) => void;

  // Selection state
  selectedAcademicYear: number | undefined;
  setSelectedAcademicYear: (year: number | undefined) => void;
  selectedSemester: string | undefined;
  setSelectedSemester: (semester: string | undefined) => void;
  selectedCombination: string | undefined;
  setSelectedCombination: (combination: string | undefined) => void;
  selectedScholarshipType: string | undefined;
  setSelectedScholarshipType: (type: string | undefined) => void;

  // Available options
  availableOptions: AvailableOptions | null;
  setAvailableOptions: (options: AvailableOptions | null) => void;

  // College quota info (for review panel)
  collegeQuotaInfo: {
    collegeQuota: number | null;
    breakdown: Record<string, number>;
  } | null;
  setCollegeQuotaInfo: (info: { collegeQuota: number | null; breakdown: Record<string, number> } | null) => void;

  // Managed college
  managedCollege: ManagedCollege | null;
  setManagedCollege: (college: ManagedCollege | null) => void;
  collegeDisplayName: string;

  // Dialog states
  showDeleteDialog: boolean;
  setShowDeleteDialog: (show: boolean) => void;
  applicationToDelete: Application | null;
  setApplicationToDelete: (app: Application | null) => void;
  showDocumentRequestDialog: boolean;
  setShowDocumentRequestDialog: (show: boolean) => void;
  applicationToRequestDocs: Application | null;
  setApplicationToRequestDocs: (app: Application | null) => void;
  showDeleteRankingDialog: boolean;
  setShowDeleteRankingDialog: (show: boolean) => void;
  rankingToDelete: CollegeRanking | null;
  setRankingToDelete: (ranking: CollegeRanking | null) => void;

  // Ranking editing state
  editingRankingId: number | null;
  setEditingRankingId: (id: number | null) => void;
  editingRankingName: string;
  setEditingRankingName: (name: string) => void;

  // Auto-save state
  saveStatus: 'idle' | 'saving' | 'saved' | 'error';
  setSaveStatus: (status: 'idle' | 'saving' | 'saved' | 'error') => void;
  saveTimeoutRef: React.MutableRefObject<NodeJS.Timeout | undefined>;

  // Helper functions
  getAcademicConfig: () => Promise<AcademicConfig>;
  getScholarshipConfig: () => Promise<ScholarshipConfig[]>;
  fetchAvailableOptions: () => Promise<void>;
  fetchRankings: () => Promise<void>;
  refreshPermissions: () => Promise<void>;
  scholarshipConfigError: string | null;
  setScholarshipConfigError: (error: string | null) => void;
}

const CollegeManagementContext = createContext<CollegeManagementContextType | undefined>(undefined);

export function CollegeManagementProvider({
  children,
  locale = "zh",
  userRole,
}: {
  children: React.ReactNode;
  locale?: "zh" | "en";
  userRole?: string;
}) {
  const {
    applications,
    isLoading,
    error,
    updateApplicationStatus,
    fetchCollegeApplications,
  } = useCollegeApplications();

  // View state
  const [viewMode, setViewMode] = useState<"card" | "table">("card");
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null);

  // Tab management
  const [activeTab, setActiveTab] = useState("review");
  const [activeScholarshipTab, setActiveScholarshipTab] = useState<string>();

  // Ranking state
  const [rankingData, setRankingData] = useState<RankingData | null>(null);
  const [rankings, setRankings] = useState<CollegeRanking[]>([]);
  const [selectedRanking, setSelectedRanking] = useState<number | null>(null);
  const [isRankingLoading, setIsRankingLoading] = useState(false);

  // Data version tracking for cross-tab synchronization
  const [dataVersion, setDataVersion] = useState(0);
  const incrementDataVersion = useCallback(() => {
    setDataVersion(v => v + 1);
  }, []);

  // Configuration
  const [scholarshipConfig, setScholarshipConfig] = useState<ScholarshipConfig[]>([]);
  const [academicConfig, setAcademicConfig] = useState<AcademicConfig | null>(null);

  // Selection state
  const [selectedAcademicYear, setSelectedAcademicYear] = useState<number>();
  const [selectedSemester, setSelectedSemester] = useState<string>();
  const [selectedCombination, setSelectedCombination] = useState<string>();
  const [selectedScholarshipType, setSelectedScholarshipType] = useState<string>();

  // Available options
  const [availableOptions, setAvailableOptions] = useState<{
    scholarship_types: Array<{ id: number; code: string; name: string; name_en?: string }>;
    academic_years: number[];
    semesters: string[];
  } | null>(null);

  // College quota info (for review panel)
  const [collegeQuotaInfo, setCollegeQuotaInfo] = useState<{
    collegeQuota: number | null;
    breakdown: Record<string, number>;
  } | null>(null);

  // Managed college
  const [managedCollege, setManagedCollege] = useState<{
    code: string;
    name: string;
    name_en: string;
    scholarship_count: number;
  } | null>(null);

  // Dialog states
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [applicationToDelete, setApplicationToDelete] = useState<Application | null>(null);
  const [showDocumentRequestDialog, setShowDocumentRequestDialog] = useState(false);
  const [applicationToRequestDocs, setApplicationToRequestDocs] = useState<Application | null>(null);
  const [showDeleteRankingDialog, setShowDeleteRankingDialog] = useState(false);
  const [rankingToDelete, setRankingToDelete] = useState<CollegeRanking | null>(null);

  // Ranking editing state
  const [editingRankingId, setEditingRankingId] = useState<number | null>(null);
  const [editingRankingName, setEditingRankingName] = useState<string>("");

  // Auto-save state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const saveTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

  // Scholarship config error state
  const [scholarshipConfigError, setScholarshipConfigError] = useState<string | null>(null);

  // Computed values
  const collegeDisplayName = useMemo(() => {
    if (managedCollege) {
      return `${managedCollege.name} (${managedCollege.code})`;
    }
    return locale === "zh" ? "⚠️ 未分配學院管理權限" : "⚠️ No College Assigned";
  }, [managedCollege, locale]);

  const filteredRankings = useMemo(() => {
    const activeConfig = scholarshipConfig.find(
      config => config.code === activeScholarshipTab
    );

    const desiredSemester = selectedSemester
      ? selectedSemester === Semester.YEARLY
        ? null
        : selectedSemester
      : undefined;

    const filtered = rankings.filter(ranking => {
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

    // 按 ID 降序排序，保證順序穩定，避免卡片跳動
    return filtered.sort((a, b) => b.id - a.id);
  }, [
    rankings,
    scholarshipConfig,
    activeScholarshipTab,
    selectedAcademicYear,
    selectedSemester,
  ]);

  // Helper functions
  const getAcademicConfig = useCallback(async (): Promise<AcademicConfig> => {
    if (academicConfig) return academicConfig;

    const currentDate = new Date();
    const currentYear = currentDate.getFullYear() - 1911;
    const currentMonth = currentDate.getMonth() + 1;

    const currentSemester: "FIRST" | "SECOND" =
      currentMonth >= 8 || currentMonth <= 1 ? "FIRST" : "SECOND";

    const config: AcademicConfig = {
      currentYear,
      currentSemester,
      availableYears: [currentYear - 1, currentYear, currentYear + 1],
    };

    setAcademicConfig(config);
    return config;
  }, [academicConfig]);

  const getScholarshipConfig = useCallback(async (): Promise<ScholarshipConfig[]> => {
    if (scholarshipConfig.length > 0) return scholarshipConfig;

    try {
      let currentAvailableOptions = availableOptions;
      if (!currentAvailableOptions) {
        logger.debug("Available options not loaded yet, fetching now");
        const isAdmin = userRole === "admin" || userRole === "super_admin";
        const response = isAdmin
          ? await apiClient.manualDistribution.getAvailableCombinations()
          : await apiClient.college.getAvailableCombinations();
        logger.debug("Available combinations API response received", {
          success: response.success,
        });

        if (response.success && response.data) {
          currentAvailableOptions = response.data;
        } else {
          logger.error("API returned unsuccessful response", {
            success: response.success,
          });
        }
      }

      if (!currentAvailableOptions?.scholarship_types) {
        logger.error("No scholarship types available");
        setScholarshipConfigError(
          locale === "zh"
            ? "無法從學院 API 載入可用的獎學金選項。"
            : "Unable to load available scholarship options from college API"
        );
        return [];
      }

      if (currentAvailableOptions.scholarship_types.length === 0) {
        logger.error("Scholarship types array is empty");
        setScholarshipConfigError(
          locale === "zh"
            ? "沒有可用的獎學金。請聯絡管理員。"
            : "No active scholarships available. Please contact administrator."
        );
        return []; // Return empty array to prevent further processing
      }

      logger.debug("Fetching all scholarships to get IDs");
      const allScholarshipsResponse = await apiClient.scholarships.getAll();

      if (allScholarshipsResponse.success && allScholarshipsResponse.data) {
        logger.debug("Scholarships loaded", {
          allCount: allScholarshipsResponse.data.length,
          collegeTypesCount: currentAvailableOptions.scholarship_types.length,
        });

        const configs: ScholarshipConfig[] = [];

        for (const collegeType of currentAvailableOptions.scholarship_types) {
          const fullScholarship = allScholarshipsResponse.data.find(
            (scholarship: {
              id: number;
              code?: string;
              name?: string;
              name_en?: string;
            }) =>
              scholarship.code === collegeType.code ||
              scholarship.name === collegeType.name ||
              scholarship.name_en === collegeType.name
          );

          if (fullScholarship) {
            configs.push({
              id: fullScholarship.id,
              name: collegeType.name,
              code: collegeType.code,
              subTypes: [{ code: "default", name: "Default" }],
            });
          } else {
            logger.warn(
              "Could not find full scholarship data for college type",
              { code: collegeType.code, name: collegeType.name }
            );
          }
        }

        logger.debug("Mapped scholarship configs", { count: configs.length });
        setScholarshipConfig(configs);
        return configs;
      }

      setScholarshipConfigError(
        locale === "zh"
          ? "無法從 API 取得獎學金資料。"
          : "Failed to retrieve scholarship data from API"
      );
      return [];
    } catch (error) {
      logger.error("Failed to fetch scholarship configuration", { error });
      setScholarshipConfigError(
        locale === "zh"
          ? `無法取得獎學金配置: ${error instanceof Error ? error.message : "未知錯誤"}`
          : `Failed to retrieve scholarship configuration: ${error instanceof Error ? error.message : "Unknown error"}`
      );
      return [];
    }
  }, [scholarshipConfig, availableOptions, userRole]);

  const fetchAvailableOptions = useCallback(async () => {
    try {
      logger.debug("Fetching available combinations");
      const isAdmin = userRole === "admin" || userRole === "super_admin";
      const response = isAdmin
        ? await apiClient.manualDistribution.getAvailableCombinations()
        : await apiClient.college.getAvailableCombinations();
      logger.debug("fetchAvailableOptions response received", {
        success: response.success,
      });

      if (response.success && response.data) {
        if (response.data.scholarship_types && response.data.scholarship_types.length > 0) {
          setAvailableOptions(response.data);
          setScholarshipConfigError(null); // Clear any previous error
        } else {
          logger.warn(
            "API returned no scholarship types in available combinations"
          );
          setScholarshipConfigError(
            locale === "zh"
              ? "沒有可用的獎學金。請聯絡管理員。"
              : "No active scholarships available. Please contact administrator."
          );
          setAvailableOptions(null); // Ensure availableOptions is null if no types
        }
      } else {
        logger.error("API returned unsuccessful response or no data", {
          success: response.success,
        });
        setScholarshipConfigError(
          locale === "zh"
            ? "無法取得可用的獎學金組合。請聯絡管理員。"
            : "Failed to retrieve available scholarship combinations. Please contact administrator."
        );
        setAvailableOptions(null); // Ensure availableOptions is null on API failure
      }
    } catch (error) {
      logger.error("Failed to fetch available options", { error });
      setScholarshipConfigError(
        locale === "zh"
          ? `無法取得可用的獎學金選項: ${error instanceof Error ? error.message : "未知錯誤"}`
          : `Failed to fetch available scholarship options: ${error instanceof Error ? error.message : "Unknown error"}`
      );
      setAvailableOptions(null); // Clear availableOptions on error
    }
  }, [userRole]);

  const fetchRankings = useCallback(async () => {
    try {
      logger.debug("Fetching rankings");
      const response = await apiClient.college.getRankings();

      if (response.success && response.data) {
        logger.debug("Rankings fetched", { count: response.data.length });

        // Normalize semester values (consistent with RankingManagementPanel logic)
        const rawRankings = response.data as Array<{ semester?: string | null; [key: string]: unknown }>;
        const normalizedRankings = rawRankings.map(
          (ranking) => {
            const rawSemester =
              typeof ranking.semester === "string" && ranking.semester.length > 0
                ? ranking.semester.toLowerCase()
                : null;
            const safeSemester =
              rawSemester && rawSemester !== "yearly"
                ? rawSemester
                : null;
            return { ...ranking, semester: safeSemester };
          }
        );

        setRankings(normalizedRankings as CollegeRanking[]);
      }
    } catch (error) {
      logger.error("Failed to fetch rankings", { error });
    }
  }, []);

  const refreshPermissions = useCallback(async () => {
    try {
      logger.debug("Refreshing permissions and scholarship configuration");

      // Reset error state
      setScholarshipConfigError(null);

      // Refetch all configuration
      await getAcademicConfig();
      await fetchAvailableOptions();
      await getScholarshipConfig();

      logger.debug("Permissions refreshed successfully");
    } catch (error) {
      logger.error("Failed to refresh permissions", { error });
      setScholarshipConfigError(
        locale === "zh"
          ? "無法重新整理權限設置。請稍後再試。"
          : "Failed to refresh permissions. Please try again later."
      );
    }
  }, [getAcademicConfig, fetchAvailableOptions, getScholarshipConfig, locale]);

  const value: CollegeManagementContextType = {
    locale,
    applications,
    isLoading,
    error,
    updateApplicationStatus,
    fetchCollegeApplications,
    viewMode,
    setViewMode,
    selectedApplication,
    setSelectedApplication,
    activeTab,
    setActiveTab,
    activeScholarshipTab,
    setActiveScholarshipTab,
    rankingData,
    setRankingData,
    rankings,
    setRankings,
    selectedRanking,
    setSelectedRanking,
    isRankingLoading,
    setIsRankingLoading,
    filteredRankings,
    dataVersion,
    incrementDataVersion,
    scholarshipConfig,
    setScholarshipConfig,
    academicConfig,
    setAcademicConfig,
    selectedAcademicYear,
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    selectedCombination,
    setSelectedCombination,
    selectedScholarshipType,
    setSelectedScholarshipType,
    availableOptions,
    setAvailableOptions,
    collegeQuotaInfo,
    setCollegeQuotaInfo,
    managedCollege,
    setManagedCollege,
    collegeDisplayName,
    showDeleteDialog,
    setShowDeleteDialog,
    applicationToDelete,
    setApplicationToDelete,
    showDocumentRequestDialog,
    setShowDocumentRequestDialog,
    applicationToRequestDocs,
    setApplicationToRequestDocs,
    showDeleteRankingDialog,
    setShowDeleteRankingDialog,
    rankingToDelete,
    setRankingToDelete,
    editingRankingId,
    setEditingRankingId,
    editingRankingName,
    setEditingRankingName,
    saveStatus,
    setSaveStatus,
    saveTimeoutRef,
    getAcademicConfig,
    getScholarshipConfig,
    fetchAvailableOptions,
    fetchRankings,
    refreshPermissions,
    scholarshipConfigError,
    setScholarshipConfigError,
  };

  return (
    <CollegeManagementContext.Provider value={value}>
      {children}
    </CollegeManagementContext.Provider>
  );
}

export function useCollegeManagement() {
  const context = useContext(CollegeManagementContext);
  if (context === undefined) {
    throw new Error(
      "useCollegeManagement must be used within a CollegeManagementProvider"
    );
  }
  return context;
}
