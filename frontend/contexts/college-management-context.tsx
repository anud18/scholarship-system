"use client";

import React, { createContext, useContext, useState, useCallback, useRef, useMemo, useEffect } from "react";
import { apiClient } from "@/lib/api";
import { useCollegeApplications } from "@/hooks/use-admin";
import { Semester } from "@/lib/enums";

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
  applications: any[];
  isLoading: boolean;
  error: string | null;
  updateApplicationStatus: any;
  fetchCollegeApplications: any;

  // View state
  viewMode: "card" | "table";
  setViewMode: (mode: "card" | "table") => void;
  selectedApplication: any | null;
  setSelectedApplication: (app: any | null) => void;

  // Tab management
  activeTab: string;
  setActiveTab: (tab: string) => void;
  activeScholarshipTab: string | undefined;
  setActiveScholarshipTab: (tab: string | undefined) => void;

  // Ranking state
  rankingData: RankingData | null;
  setRankingData: (data: RankingData | null) => void;
  rankings: any[];
  setRankings: (rankings: any[]) => void;
  selectedRanking: number | null;
  setSelectedRanking: (id: number | null) => void;
  isRankingLoading: boolean;
  setIsRankingLoading: (loading: boolean) => void;
  filteredRankings: any[];

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
  availableOptions: {
    scholarship_types: Array<{ id: number; code: string; name: string; name_en?: string }>;
    academic_years: number[];
    semesters: string[];
  } | null;
  setAvailableOptions: (options: any) => void;

  // College quota info (for review panel)
  collegeQuotaInfo: {
    collegeQuota: number | null;
    breakdown: Record<string, number>;
  } | null;
  setCollegeQuotaInfo: (info: { collegeQuota: number | null; breakdown: Record<string, number> } | null) => void;

  // Managed college
  managedCollege: {
    code: string;
    name: string;
    name_en: string;
    scholarship_count: number;
  } | null;
  setManagedCollege: (college: any) => void;
  collegeDisplayName: string;

  // Dialog states
  showDeleteDialog: boolean;
  setShowDeleteDialog: (show: boolean) => void;
  applicationToDelete: any | null;
  setApplicationToDelete: (app: any | null) => void;
  showDocumentRequestDialog: boolean;
  setShowDocumentRequestDialog: (show: boolean) => void;
  applicationToRequestDocs: any | null;
  setApplicationToRequestDocs: (app: any | null) => void;
  showDeleteRankingDialog: boolean;
  setShowDeleteRankingDialog: (show: boolean) => void;
  rankingToDelete: any | null;
  setRankingToDelete: (ranking: any | null) => void;

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
  refreshPermissions: () => Promise<void>;
  scholarshipConfigError: string | null;
  setScholarshipConfigError: (error: string | null) => void;
}

const CollegeManagementContext = createContext<CollegeManagementContextType | undefined>(undefined);

export function CollegeManagementProvider({
  children,
  locale = "zh",
}: {
  children: React.ReactNode;
  locale?: "zh" | "en";
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
  const [selectedApplication, setSelectedApplication] = useState<any>(null);

  // Tab management
  const [activeTab, setActiveTab] = useState("review");
  const [activeScholarshipTab, setActiveScholarshipTab] = useState<string>();

  // Ranking state
  const [rankingData, setRankingData] = useState<RankingData | null>(null);
  const [rankings, setRankings] = useState<any[]>([]);
  const [selectedRanking, setSelectedRanking] = useState<number | null>(null);
  const [isRankingLoading, setIsRankingLoading] = useState(false);

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
  const [applicationToDelete, setApplicationToDelete] = useState<any>(null);
  const [showDocumentRequestDialog, setShowDocumentRequestDialog] = useState(false);
  const [applicationToRequestDocs, setApplicationToRequestDocs] = useState<any>(null);
  const [showDeleteRankingDialog, setShowDeleteRankingDialog] = useState(false);
  const [rankingToDelete, setRankingToDelete] = useState<any>(null);

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
        console.log("Available options not loaded yet, fetching now...");
        const response = await apiClient.college.getAvailableCombinations();
        console.log("Available combinations API response:", response);

        if (response.success && response.data) {
          currentAvailableOptions = response.data;
        } else {
          console.error("API returned unsuccessful response:", response);
        }
      }

      if (!currentAvailableOptions?.scholarship_types) {
        console.error("No scholarship types available:", currentAvailableOptions);
        setScholarshipConfigError(
          locale === "zh"
            ? "無法從學院 API 載入可用的獎學金選項。"
            : "Unable to load available scholarship options from college API"
        );
        return [];
      }

      if (currentAvailableOptions.scholarship_types.length === 0) {
        console.error("Scholarship types array is empty");
        setScholarshipConfigError(
          locale === "zh"
            ? "沒有可用的獎學金。請聯絡管理員。"
            : "No active scholarships available. Please contact administrator."
        );
        return []; // Return empty array to prevent further processing
      }

      console.log("Fetching all scholarships to get IDs...");
      const allScholarshipsResponse = await apiClient.scholarships.getAll();

      if (allScholarshipsResponse.success && allScholarshipsResponse.data) {
        console.log("All scholarships:", allScholarshipsResponse.data);
        console.log(
          "Available scholarship types from college:",
          currentAvailableOptions.scholarship_types
        );

        const configs: ScholarshipConfig[] = [];

        for (const collegeType of currentAvailableOptions.scholarship_types) {
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
              subTypes: [{ code: "default", name: "Default" }],
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

      setScholarshipConfigError(
        locale === "zh"
          ? "無法從 API 取得獎學金資料。"
          : "Failed to retrieve scholarship data from API"
      );
      return [];
    } catch (error) {
      console.error("Failed to fetch scholarship configuration:", error);
      setScholarshipConfigError(
        locale === "zh"
          ? `無法取得獎學金配置: ${error instanceof Error ? error.message : "未知錯誤"}`
          : `Failed to retrieve scholarship configuration: ${error instanceof Error ? error.message : "Unknown error"}`
      );
      return [];
    }
  }, [scholarshipConfig, availableOptions]);

  const fetchAvailableOptions = useCallback(async () => {
    try {
      console.log("Fetching available combinations...");
      const response = await apiClient.college.getAvailableCombinations();
      console.log("fetchAvailableOptions response:", response);

      if (response.success && response.data) {
        if (response.data.scholarship_types && response.data.scholarship_types.length > 0) {
          console.log("Setting availableOptions:", response.data);
          setAvailableOptions(response.data);
          setScholarshipConfigError(null); // Clear any previous error
        } else {
          console.warn("API returned no scholarship types in available combinations.");
          setScholarshipConfigError(
            locale === "zh"
              ? "沒有可用的獎學金。請聯絡管理員。"
              : "No active scholarships available. Please contact administrator."
          );
          setAvailableOptions(null); // Ensure availableOptions is null if no types
        }
      } else {
        console.error("API returned unsuccessful response or no data:", response);
        setScholarshipConfigError(
          locale === "zh"
            ? "無法取得可用的獎學金組合。請聯絡管理員。"
            : "Failed to retrieve available scholarship combinations. Please contact administrator."
        );
        setAvailableOptions(null); // Ensure availableOptions is null on API failure
      }
    } catch (error) {
      console.error("Failed to fetch available options:", error);
      setScholarshipConfigError(
        locale === "zh"
          ? `無法取得可用的獎學金選項: ${error instanceof Error ? error.message : "未知錯誤"}`
          : `Failed to fetch available scholarship options: ${error instanceof Error ? error.message : "Unknown error"}`
      );
      setAvailableOptions(null); // Clear availableOptions on error
    }
  }, []);

  const refreshPermissions = useCallback(async () => {
    try {
      console.log("Refreshing permissions and scholarship configuration...");

      // Reset error state
      setScholarshipConfigError(null);

      // Refetch all configuration
      await getAcademicConfig();
      await fetchAvailableOptions();
      await getScholarshipConfig();

      console.log("Permissions refreshed successfully");
    } catch (error) {
      console.error("Failed to refresh permissions:", error);
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
