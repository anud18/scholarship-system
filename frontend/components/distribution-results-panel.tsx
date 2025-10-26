"use client";

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Users,
  CheckCircle,
  XCircle,
  Download,
  AlertCircle,
  LayoutGrid,
  Trophy,
} from "lucide-react";
import { apiClient } from "@/lib/api";
import {
  ALLOCATION_MATRIX_LAYOUT,
  contiguousRuns,
} from "@/lib/constants/allocation-matrix-layout";
import { useGridMetrics } from "@/hooks/useGridMetrics";
import { usePillMetrics } from "@/hooks/usePillMetrics";
import { useScholarshipData } from "@/hooks/use-scholarship-data";
import * as XLSX from "xlsx";
import { toast } from "sonner";
import { StudentPreviewCard } from "@/components/student-preview-card";

const { Z_INDEX } = ALLOCATION_MATRIX_LAYOUT;

interface DistributionResultsPanelProps {
  rankingId: number;
  applications?: any[];
  locale?: "zh" | "en";
  onClose?: () => void;
  subTypeQuotaBreakdown?: Record<
    string,
    { quota?: number; label?: string; label_en?: string }
  >;
  academicYear?: number;
}

interface SubTypeResult {
  sub_type_code: string;
  label?: string;
  label_en?: string;
  total_quota?: number;
  colleges: {
    [collegeCode: string]: {
      quota: number;
      admitted_count: number;
      backup_count: number;
      admitted: Array<{
        rank_position: number;
        application_id: number;
        student_name: string;
      }>;
      backup: Array<{
        rank_position: number;
        backup_position: number;
        application_id: number;
        student_name: string;
      }>;
    };
  };
}

interface DistributionDetails {
  ranking_id: number;
  ranking_name?: string;
  distribution_executed: boolean;
  total_allocated: number;
  total_applications: number;
  distribution_summary: {
    [subType: string]: SubTypeResult;
  };
  rejected: Array<{
    rank_position: number;
    application_id: number;
    student_name: string;
    student_id: string;
    reason: string;
  }>;
  sub_type_metadata?: Array<{ code: string; label?: string; label_en?: string }>;
}

type SubTypeTranslations = {
  zh: Record<string, string>;
  en: Record<string, string>;
};

type StudentRow = {
  key: string | number;
  applicationId?: number;
  appId?: string | number;
  studentName: string;
  studentId?: string;
  rank: number | null;
  sortRank: number;
  termCount: number | null;
  eligibleCodes: string[];
  eligibleLabels: string[];
  primaryEligibleSubType?: string;
  allocation?: { subType: string; college: string };
  backupEntries: Array<{
    subType: string;
    backupPosition?: number;
    college: string;
  }>;
  rejection?: { reason: string; rank: number };
  statusBadge: { label: string; className: string; icon: string };
};

const VERIFIED_STATUSES = new Set([
  "approved",
  "completed",
  "allocated",
  "finalized",
  "admitted",
  "college_reviewed",
]);

const REJECTED_STATUSES = new Set([
  "rejected",
  "returned",
  "withdrawn",
  "cancelled",
  "ineligible",
  "not_eligible",
  "unqualified",
]);

const normalizeStatus = (status?: string) =>
  typeof status === "string" ? status.toLowerCase() : "";

/**
 * Get styled rejection reason with icon and color
 */
const getRejectionReasonDisplay = (reason: string, locale: "zh" | "en") => {
  const reasonMap: Record<string, { icon: string; color: string; labelZh: string; labelEn: string }> = {
    "申請已被駁回": {
      icon: "❌",
      color: "text-rose-600",
      labelZh: "申請已被駁回",
      labelEn: "Application Rejected"
    },
    "未申請任何合適的子類別": {
      icon: "🚫",
      color: "text-amber-600",
      labelZh: "未申請合適的子類別",
      labelEn: "No Suitable Sub-type Applied"
    },
    "所屬學院無配額": {
      icon: "🏫",
      color: "text-slate-600",
      labelZh: "所屬學院無名額",
      labelEn: "No Quota for College"
    },
    "所有申請的子類別配額已滿": {
      icon: "📊",
      color: "text-blue-600",
      labelZh: "申請類別名額已滿",
      labelEn: "All Quotas Exceeded"
    },
    "學生資料不完整（缺少學院資訊）": {
      icon: "⚠️",
      color: "text-orange-600",
      labelZh: "學生資料不完整",
      labelEn: "Incomplete Student Data"
    },
  };

  // Try to find matching reason
  for (const [key, value] of Object.entries(reasonMap)) {
    if (reason.includes(key)) {
      const label = locale === "zh" ? value.labelZh : value.labelEn;
      return { icon: value.icon, color: value.color, label };
    }
  }

  // Fallback for unknown reasons
  return {
    icon: "ℹ️",
    color: "text-slate-600",
    label: reason,
  };
};

const normalizeSubtypeEntries = (value: any): string[] => {
  if (!value) {
    return [];
  }

  const entries = Array.isArray(value)
    ? value
    : typeof value === "string"
      ? value.split(",")
      : [];

  const results: string[] = [];
  entries.forEach((item) => {
    if (!item) return;

    if (typeof item === "string") {
      const trimmed = item.trim();
      if (trimmed) {
        results.push(trimmed);
      }
      return;
    }

    if (typeof item === "object") {
      const possible =
        item.code ||
        item.sub_type ||
        item.subType ||
        item.name ||
        item.label ||
        item.value;
      if (possible) {
        const trimmed = String(possible).trim();
        if (trimmed) {
          results.push(trimmed);
        }
      }
    }
  });

  return Array.from(new Set(results));
};

const getStatusBadgeMeta = (
  status: string | undefined,
  locale: "zh" | "en"
) => {
  const normalized = normalizeStatus(status);

  const meta =
    VERIFIED_STATUSES.has(normalized)
      ? {
          labelZh: "已檢核",
          labelEn: "Verified",
          className: "bg-emerald-100 text-emerald-700",
          icon: "🟢",
        }
      : REJECTED_STATUSES.has(normalized)
        ? {
            labelZh: "不符合",
            labelEn: "Not Eligible",
            className: "bg-rose-100 text-rose-700",
            icon: "🔴",
          }
        : {
            labelZh: "待檢核",
            labelEn: "Pending",
            className: "bg-amber-100 text-amber-700",
            icon: "🟠",
          };

  return {
    label: locale === "zh" ? meta.labelZh : meta.labelEn,
    className: meta.className,
    icon: meta.icon,
  };
};

export function DistributionResultsPanel({
  rankingId,
  applications,
  locale = "zh",
  onClose,
  subTypeQuotaBreakdown,
  academicYear,
}: DistributionResultsPanelProps) {
  const [distributionData, setDistributionData] =
    useState<DistributionDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ✨ Use SWR hook to fetch sub-type translations (auto-detects user role)
  const { subTypeTranslations } = useScholarshipData();
  const handleExportDistribution = () => {
    try {
      if (!distributionData) {
        toast.error(locale === "zh" ? "目前沒有分配資料" : "No distribution data available");
        return;
      }

      // Sheet 1: Overview (分配概覽)
      const overviewData = [
        {
          '項目': locale === "zh" ? "排名名稱" : "Ranking Name",
          '數值': distributionData.ranking_name || "-",
        },
        {
          '項目': locale === "zh" ? "總申請數" : "Total Applications",
          '數值': distributionData.total_applications,
        },
        {
          '項目': locale === "zh" ? "正取人數" : "Admitted",
          '數值': distributionData.total_allocated,
        },
        {
          '項目': locale === "zh" ? "備取人數" : "Backup",
          '數值': totalBackup,
        },
        {
          '項目': locale === "zh" ? "未獲分配" : "Not Allocated",
          '數值': totalRejected,
        },
        {
          '項目': locale === "zh" ? "分配成功率" : "Success Rate",
          '數值': distributionData.total_applications > 0
            ? `${((distributionData.total_allocated / distributionData.total_applications) * 100).toFixed(1)}%`
            : "0%",
        },
      ];

      // Add sub-type breakdown to overview
      subTypeKeys.forEach((subType) => {
        const quota = aggregated.quotaMap[subType] ?? 0;
        const admitted = aggregated.admittedCount[subType] ?? 0;
        const backups = aggregated.backupCount[subType] ?? 0;
        const label = getColumnLabel(subType);

        overviewData.push({
          '項目': `${label} - ${locale === "zh" ? "配額" : "Quota"}`,
          '數值': quota,
        });
        overviewData.push({
          '項目': `${label} - ${locale === "zh" ? "正取" : "Admitted"}`,
          '數值': admitted,
        });
        if (backups > 0) {
          overviewData.push({
            '項目': `${label} - ${locale === "zh" ? "備取" : "Backup"}`,
            '數值': backups,
          });
        }
      });

      const worksheetOverview = XLSX.utils.json_to_sheet(overviewData);
      worksheetOverview['!cols'] = [
        { wch: 30 }, // 項目
        { wch: 20 }, // 數值
      ];

      // Sheet 2: Details (詳細清單)
      const detailsData = studentRows.map((student) => {
        const allocation = student.allocation;
        const hasBackups = student.backupEntries.length > 0;

        let allocationType = "-";
        let allocatedSubType = "-";
        let backupSubTypes = "-";
        let backupPositions = "-";

        if (allocation) {
          allocationType = locale === "zh" ? "正取" : "Admitted";
          allocatedSubType = getColumnLabel(allocation.subType);
        } else if (hasBackups) {
          allocationType = locale === "zh" ? "備取" : "Backup";
          // Show all backup sub-types and positions
          backupSubTypes = student.backupEntries
            .map((entry) => getColumnLabel(entry.subType))
            .join(", ");
          backupPositions = student.backupEntries
            .map((entry) => entry.backupPosition?.toString() || "-")
            .join(", ");
        } else if (student.rejection) {
          allocationType = locale === "zh" ? "未獲分配" : "Not Allocated";
        } else {
          allocationType = locale === "zh" ? "待處理" : "Pending";
        }

        return {
          '排名': student.rank ?? "-",
          '學生姓名': student.studentName,
          '學號': student.studentId || "-",
          '就讀學期數': student.termCount ?? "-",
          '符合子項目': student.eligibleLabels.join(", ") || "-",
          '分配狀態': allocationType,
          '正取子項目': allocatedSubType,
          '備取子項目': backupSubTypes,
          '備取順位': backupPositions,
          '申請編號': student.appId || "-",
        };
      });

      const worksheetDetails = XLSX.utils.json_to_sheet(detailsData);
      worksheetDetails['!cols'] = [
        { wch: 10 }, // 排名
        { wch: 20 }, // 學生姓名
        { wch: 15 }, // 學號
        { wch: 12 }, // 就讀學期數
        { wch: 30 }, // 符合子項目
        { wch: 12 }, // 分配狀態
        { wch: 25 }, // 正取子項目
        { wch: 25 }, // 備取子項目
        { wch: 12 }, // 備取順位
        { wch: 20 }, // 申請編號
      ];

      // Sheet 3: Rejected (駁回清單)
      const rejectedData = distributionData.rejected?.map((student) => ({
        '排名': student.rank_position,
        '學生姓名': student.student_name,
        '學號': student.student_id,
        '原因': student.reason,
      })) || [];

      const worksheetRejected = XLSX.utils.json_to_sheet(rejectedData);
      worksheetRejected['!cols'] = [
        { wch: 10 }, // 排名
        { wch: 20 }, // 學生姓名
        { wch: 15 }, // 學號
        { wch: 40 }, // 原因
      ];

      // Create workbook with all sheets
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheetOverview, locale === "zh" ? '分配概覽' : 'Overview');
      XLSX.utils.book_append_sheet(workbook, worksheetDetails, locale === "zh" ? '詳細清單' : 'Details');
      XLSX.utils.book_append_sheet(workbook, worksheetRejected, locale === "zh" ? '駁回清單' : 'Rejected');

      // Generate filename
      const timestamp = new Date().toISOString().split('T')[0];
      const rankingName = distributionData.ranking_name?.replace(/[^a-zA-Z0-9\u4e00-\u9fa5]/g, '_') || 'distribution';
      const filename = `分配矩陣_${rankingName}_${timestamp}.xlsx`;

      // Download file
      XLSX.writeFile(workbook, filename);

      toast.success(
        locale === "zh"
          ? `已匯出分配矩陣資料，共 ${studentRows.length} 位學生`
          : `Exported distribution matrix with ${studentRows.length} students`
      );
    } catch (error) {
      console.error('Export error:', error);
      toast.error(error instanceof Error ? error.message : (locale === "zh" ? "無法匯出資料" : "Failed to export data"));
    }
  };

  useEffect(() => {
    fetchDistributionDetails();
  }, [rankingId]);

  // ✨ Translations are now loaded automatically via useScholarshipData hook
  // No need for manual useEffect anymore!

  const subTypeMetaMap = useMemo(() => {
    if (!distributionData?.sub_type_metadata) {
      return {} as Record<string, { label: string; label_en: string }>;
    }

    const entries = Array.isArray(distributionData.sub_type_metadata)
      ? distributionData.sub_type_metadata
      : [];

    return entries.reduce(
      (acc: Record<string, { label: string; label_en: string }>, item: any) => {
        if (item && item.code) {
          acc[item.code] = {
            label: item.label || item.code,
            label_en: item.label_en || item.label || item.code,
          };
        }
        return acc;
      },
      {} as Record<string, { label: string; label_en: string }>
    );
  }, [distributionData]);

  const fetchDistributionDetails = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await apiClient.college.getDistributionDetails(rankingId);
      if (response.success && response.data) {
        setDistributionData(response.data);
      } else {
        setError(response.message || "Failed to load distribution details");
      }
    } catch (err) {
      console.error("Failed to fetch distribution details:", err);
      setError("An error occurred while fetching distribution details");
    } finally {
      setIsLoading(false);
    }
  };

  const aggregated = useMemo(() => {
    const empty = {
      subTypes: [] as string[],
      subTypeInfo: {} as Record<string, { label: string; labelEn: string }>,
      allocationMap: new Map<number, { subType: string; college: string }>(),
      backupMap: new Map<
        number,
        Array<{ subType: string; backupPosition?: number; college: string }>
      >(),
      quotaMap: {} as Record<string, number>,
      admittedCount: {} as Record<string, number>,
      backupCount: {} as Record<string, number>,
      rejectedMap: new Map<number, { reason: string; rank: number }>(),
    };

    if (!distributionData?.distribution_summary) {
      return empty;
    }

    const quotaBreakdown = subTypeQuotaBreakdown || {};

    const applicationIds = new Set<number>();
    if (Array.isArray(applications)) {
      applications.forEach((app: any) => {
        let maybeId: number | undefined;

        if (typeof app?.id === "number") {
          maybeId = app.id;
        } else if (typeof app?.id === "string") {
          const parsed = Number(app.id);
          maybeId = Number.isNaN(parsed) ? undefined : parsed;
        } else if (typeof app?.application_id === "number") {
          maybeId = app.application_id;
        }

        if (typeof maybeId === "number" && !Number.isNaN(maybeId)) {
          applicationIds.add(maybeId);
        }
      });
    }

    const allocationMap = new Map<number, { subType: string; college: string }>();
    const backupMap = new Map<
      number,
      Array<{ subType: string; backupPosition?: number; college: string }>
    >();
    const quotaMap: Record<string, number> = {};
    const admittedCount: Record<string, number> = {};
    const backupCount: Record<string, number> = {};
    const subTypeInfo: Record<string, { label: string; labelEn: string }> = {};

    const subTypeKeys = Object.keys(distributionData.distribution_summary);
    const filterByApplications =
      distributionData.distribution_executed && applicationIds.size > 0;

    subTypeKeys.forEach((subType) => {
      const subEntry = distributionData.distribution_summary[subType] || {};
      const colleges = subEntry.colleges ?? {};
      const fallbackMeta = subTypeMetaMap[subType] || {
        label: subEntry.label || subType,
        label_en: subEntry.label_en || subEntry.label || subType,
      };
      const overrideMeta = quotaBreakdown[subType];
      const overrideLabel =
        typeof overrideMeta?.label === "string"
          ? overrideMeta.label.trim()
          : undefined;
      const overrideLabelEn =
        typeof overrideMeta?.label_en === "string"
          ? overrideMeta.label_en.trim()
          : undefined;
      const computedLabel = fallbackMeta.label || subType;
      const computedLabelEn = fallbackMeta.label_en || fallbackMeta.label || subType;

      subTypeInfo[subType] = {
        label: overrideLabel || computedLabel,
        labelEn: overrideLabelEn || overrideLabel || computedLabelEn,
      };

      let subtotalQuota = 0;

      Object.entries(colleges).forEach(([collegeCode, collegeInfo]) => {
        const { quota = 0, admitted = [], backup = [] } = collegeInfo || {};

        const shouldInclude =
          !filterByApplications ||
          admitted.some((student) =>
            applicationIds.has(student.application_id)
          ) ||
          backup.some((student) =>
            applicationIds.has(student.application_id)
          );

        if (!shouldInclude) {
          return;
        }

        const quotaValue =
          typeof quota === "number" && !Number.isNaN(quota)
            ? quota
            : Number(quota) || 0;
        subtotalQuota += quotaValue;

        admitted.forEach((student) => {
          if (typeof student.application_id !== "number") return;
          allocationMap.set(student.application_id, {
            subType,
            college: collegeCode,
          });
          admittedCount[subType] = (admittedCount[subType] || 0) + 1;
        });

        backup.forEach((student) => {
          if (typeof student.application_id !== "number") return;
          const list = backupMap.get(student.application_id) || [];
          list.push({
            subType,
            backupPosition: student.backup_position,
            college: collegeCode,
          });
          backupMap.set(student.application_id, list);
          backupCount[subType] = (backupCount[subType] || 0) + 1;
        });
      });

      const totalQuotaFromEntry =
        typeof subEntry.total_quota === "number" && !Number.isNaN(subEntry.total_quota)
          ? subEntry.total_quota
          : undefined;
      const overrideQuotaRaw = overrideMeta?.quota;
      const overrideQuota =
        typeof overrideQuotaRaw === "number"
          ? overrideQuotaRaw
          : overrideQuotaRaw !== undefined
            ? Number(overrideQuotaRaw)
            : undefined;

      quotaMap[subType] =
        typeof overrideQuota === "number" && !Number.isNaN(overrideQuota)
          ? overrideQuota
          : typeof totalQuotaFromEntry === "number"
            ? totalQuotaFromEntry
            : subtotalQuota;
    });

    const rejectedMap = new Map<number, { reason: string; rank: number }>();
    distributionData.rejected?.forEach((student) => {
      if (typeof student.application_id === "number") {
        rejectedMap.set(student.application_id, {
          reason: student.reason,
          rank: student.rank_position,
        });
      }
    });

    Object.entries(subTypeMetaMap).forEach(([code, meta]) => {
      if (!subTypeInfo[code]) {
        subTypeInfo[code] = {
          label: meta.label,
          labelEn: meta.label_en || meta.label,
        };
      }
    });

    return {
      subTypes: subTypeKeys,
      subTypeInfo,
      allocationMap,
      backupMap,
      quotaMap,
      admittedCount,
      backupCount,
      rejectedMap,
    };
  }, [distributionData, applications, subTypeMetaMap, subTypeQuotaBreakdown]);
  const studentRows = useMemo(() => {
    if (!Array.isArray(applications)) {
      return [];
    }

    const labelForSubtype = (subType: string) => {
      if (!subType) {
        return locale === "zh" ? "未命名" : "Unnamed";
      }
      const meta = aggregated.subTypeInfo[subType];
      if (meta) {
        return locale === "zh" ? meta.label : meta.labelEn || meta.label;
      }
      const dict =
        locale === "zh"
          ? subTypeTranslations.zh
          : subTypeTranslations.en;
      const direct = dict?.[subType];
      const lower = dict?.[subType.toLowerCase()];
      return (
        direct ||
        lower ||
        subType
          .replace(/_/g, " ")
          .replace(/\s+/g, " ")
          .trim()
          .toUpperCase()
      );
    };

    return applications
      .map((app: any, index: number) => {
        const eligibleCodes = normalizeSubtypeEntries(
          app?.eligible_subtypes
        );

        let applicationId: number | undefined;
        if (typeof app?.id === "number") {
          applicationId = app.id;
        } else if (typeof app?.id === "string") {
          const parsed = Number(app.id);
          applicationId = Number.isNaN(parsed) ? undefined : parsed;
        } else if (typeof app?.application_id === "number") {
          applicationId = app.application_id;
        }

        const rawRank =
          typeof app?.rank_position === "number" && !Number.isNaN(app.rank_position)
            ? app.rank_position
            : null;
        const sortRank = rawRank ?? Number.MAX_SAFE_INTEGER;
        const allocation = applicationId
          ? aggregated.allocationMap.get(applicationId)
          : undefined;
        const backups = applicationId
          ? aggregated.backupMap.get(applicationId) || []
          : [];
        const rejection = applicationId
          ? aggregated.rejectedMap.get(applicationId)
          : undefined;
        const statusBadge = getStatusBadgeMeta(
          app?.review_status || app?.status,
          locale
        );
        const eligibleLabels = eligibleCodes.map((code) =>
          labelForSubtype(code)
        );

        const termCandidates = [
          app?.student_termcount,
          app?.student_term_count,
          app?.studentTermCount,
          app?.application?.student_info?.term_count,
          app?.application?.student_info?.study_terms,
          app?.application?.student_info?.termCount,
        ];
        let termCount: number | null = null;
        for (const candidate of termCandidates) {
          if (termCount !== null) break;
          if (typeof candidate === "number" && !Number.isNaN(candidate)) {
            termCount = candidate;
            break;
          }
          if (candidate !== undefined) {
            const parsed = Number(candidate);
            if (!Number.isNaN(parsed)) {
              termCount = parsed;
              break;
            }
          }
        }

        return {
          key: applicationId ?? `row-${index}`,
          applicationId,
          appId: app?.app_id,
          studentName: app?.student_name || "-",
          studentId: app?.student_id,
          rank: rawRank,
          sortRank,
          termCount,
          eligibleCodes,
          eligibleLabels,
          primaryEligibleSubType: eligibleCodes[0],
          allocation,
          backupEntries: backups,
          rejection,
          statusBadge,
        };
      })
      .sort((a, b) => a.sortRank - b.sortRank) as StudentRow[];
  }, [applications, aggregated, locale, subTypeTranslations]);

  const getColumnLabel = (subType: string) => {
    if (!subType) {
      return locale === "zh" ? "未命名" : "Unnamed";
    }
    const meta = aggregated.subTypeInfo[subType];
    if (meta) {
      return locale === "zh" ? meta.label : meta.labelEn || meta.label;
    }
    const dict =
      locale === "zh"
        ? subTypeTranslations.zh
        : subTypeTranslations.en;
    const direct = dict?.[subType];
    const lower = dict?.[subType.toLowerCase()];
    return (
      direct ||
      lower ||
      subType
        .replace(/_/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .toUpperCase()
    );
  };

  /**
   * RunPill - Run-level pill that wraps around contiguous card groups
   * Positioned absolutely at row level, uses grid metrics for precise geometry
   */
  const RunPill = ({
    runStart,
    runEnd,
    labels,
    tone,
    rowKey,
    rankColumnWidth,
  }: {
    runStart: number;
    runEnd: number;
    labels: string[];
    tone: "blue" | "warm" | "muted";
    rowKey: string | number;
    rankColumnWidth: number;
  }) => {
    const gridMetrics = useGridMetrics(rankColumnWidth);
    const geometry = usePillMetrics(rowKey, runStart, runEnd, gridMetrics);

    if (!geometry.visible) {
      return null;
    }

    const { PILL_CARD_RADIUS } = ALLOCATION_MATRIX_LAYOUT;

    // Calculate corner radius: min(card radius, half height)
    const pillRadius = Math.min(PILL_CARD_RADIUS, geometry.height / 2);

    return (
      <div
        className="alloc-matrix-pill"
        data-tone={tone}
        data-pill-run={`${runStart}-${runEnd}`}
        style={{
          position: "absolute",
          left: `${geometry.left}px`,
          top: `${geometry.top}px`,
          width: `${geometry.width}px`,
          height: `${geometry.height}px`,
          ["--pill-radius" as string]: `${pillRadius}px`,
          zIndex: Z_INDEX.PILL,
          pointerEvents: "none",
        }}
      >
        {/* Pill content - labels */}
        <div className="flex h-full items-center px-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-semibold opacity-60 uppercase tracking-wider">
              {locale === "zh" ? "符合" : "Eligible"}
            </span>
            {labels.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {labels.map((label, idx) => (
                  <span
                    key={`${label}-${idx}`}
                    className="inline-flex items-center rounded px-1.5 py-0.5 text-[9px] font-medium bg-white/50 border border-white/70"
                  >
                    {label}
                  </span>
                ))}
              </div>
            ) : (
              <span className="text-[10px] opacity-40">
                {locale === "zh" ? "無" : "None"}
              </span>
            )}
          </div>
        </div>
      </div>
    );
  };

  const StudentInfoCard = ({
    student,
    tone = "neutral",
    footer,
  }: {
    student: StudentRow;
    tone?: "neutral" | "warm" | "muted";
    footer?: ReactNode;
  }) => {
    // Enhanced toggle handle appearance based on tone
    const handleStyles = {
      warm: {
        // Backup position - warm orange handle
        gradient: "from-orange-50 via-orange-100 to-orange-50",
        border: "border-orange-300",
        shadow: "shadow-[0_4px_8px_rgba(251,146,60,0.3),0_2px_4px_rgba(251,146,60,0.2),0_8px_16px_rgba(251,146,60,0.1)]",
        highlight: "bg-gradient-to-br from-orange-200/20 to-transparent",
        textColor: "text-orange-900"
      },
      muted: {
        // Unassigned - muted gray handle
        gradient: "from-slate-50 via-slate-100 to-slate-50",
        border: "border-slate-300",
        shadow: "shadow-[0_2px_4px_rgba(0,0,0,0.08),0_1px_2px_rgba(0,0,0,0.04)]",
        highlight: "bg-gradient-to-br from-slate-200/20 to-transparent",
        textColor: "text-slate-700"
      },
      neutral: {
        // Allocated position - prominent white handle
        gradient: "from-white via-slate-50 to-white",
        border: "border-slate-400",
        shadow: "shadow-[0_6px_12px_rgba(0,0,0,0.15),0_3px_6px_rgba(0,0,0,0.1),0_12px_24px_rgba(0,0,0,0.05)]",
        highlight: "bg-gradient-to-br from-white/40 to-transparent",
        textColor: "text-slate-900"
      }
    }[tone];

    const termText =
      typeof student.termCount === "number"
        ? locale === "zh"
          ? `在學 ${student.termCount} 學期`
          : `${student.termCount} ${student.termCount === 1 ? "term" : "terms"} enrolled`
        : null;

    return (
      <div
        className={`
          relative overflow-hidden rounded-2xl
          bg-gradient-to-b ${handleStyles.gradient}
          ${handleStyles.border} border-2
          ${handleStyles.shadow}
          transform transition-all duration-200
          hover:scale-[1.02] hover:shadow-xl
        `}
      >
        {/* Top highlight for 3D effect */}
        <div className={`absolute inset-x-0 top-0 h-6 ${handleStyles.highlight} pointer-events-none`} />

        {/* Glass effect overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/10 to-transparent pointer-events-none" />

        {/* Content */}
        <div className="relative px-3 py-3.5">
          {/* 分發狀態：右上角絕對定位 */}
          {footer && (
            <div className="absolute top-2 right-2.5 z-10 max-w-[calc(100%-5rem)]">
              <div className="text-[9px]">{footer}</div>
            </div>
          )}

          {/* 第一行：姓名 - 學號 */}
          <p className={`text-xs font-bold ${handleStyles.textColor} tracking-tight pr-14`}>
            {student.studentName}
            {student.studentId && (
              <span className="font-medium"> - {student.studentId}</span>
            )}
          </p>

          {/* 第二行：在學學期 */}
          {termText && (
            <div className="mt-1 text-[10px] text-slate-500">{termText}</div>
          )}

          {/* 申請編號：右下角絕對定位 */}
          {student.appId && (
            <div className="absolute bottom-2 right-2.5 text-[9px] text-slate-400 opacity-70">
              {student.appId}
            </div>
          )}
        </div>

        {/* Bottom edge shadow for depth */}
        <div className="absolute inset-x-2 bottom-0 h-[1px] bg-gradient-to-r from-transparent via-black/10 to-transparent" />
      </div>
    );
  };

  const renderRankBadge = (rank: number | null) => {
    if (rank === null) {
      return (
        <Badge variant="outline" className="border-slate-300 text-slate-600">
          {locale === "zh" ? "待排序" : "Waitlist"}
        </Badge>
      );
    }

    if (rank >= 1 && rank <= 3) {
      const styles: Record<number, string> = {
        1: "bg-yellow-100 text-yellow-800 border-yellow-300",
        2: "bg-gray-100 text-gray-800 border-gray-300",
        3: "bg-orange-100 text-orange-800 border-orange-300",
      };
      return (
        <Badge variant="outline" className={styles[rank] || ""}>
          <Trophy className="mr-1 h-3 w-3" aria-hidden />#{rank}
        </Badge>
      );
    }

    return (
      <Badge variant="outline" className="border-slate-300 text-slate-700">
        #{rank}
      </Badge>
    );
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-8 text-center">
          <p className="text-slate-600">
            {locale === "zh" ? "載入分配結果中..." : "Loading distribution results..."}
          </p>
        </CardContent>
      </Card>
    );
  }

  if (error || !distributionData || !distributionData.distribution_summary) {
    return (
      <Card>
        <CardContent className="p-8">
          <div className="flex items-center gap-2 text-red-600">
            <AlertCircle className="h-5 w-5" />
            <p>{error || "No distribution data available"}</p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const subTypeKeys = aggregated.subTypes;
  const totalBackup = subTypeKeys.reduce(
    (sum, key) => sum + (aggregated.backupCount[key] || 0),
    0
  );
  const hasGridData = subTypeKeys.length > 0 && studentRows.length > 0;
  const totalRejected = distributionData.rejected?.length ?? 0;
  const pendingDistribution =
    !!distributionData && distributionData.distribution_executed === false;
  const columnSegments = ["220px"];
  if (subTypeKeys.length > 0) {
    columnSegments.push(`repeat(${subTypeKeys.length}, minmax(260px, 1fr))`);
  }
  columnSegments.push("minmax(260px, 1fr)");
  const gridTemplateColumns = columnSegments.join(" ");

  return (
    <div className="space-y-6">
      {pendingDistribution && (
        <Card className="border border-amber-200 bg-amber-50">
          <CardContent className="flex items-center gap-3 py-4">
            <AlertCircle className="h-5 w-5 text-amber-600" />
            <div className="text-sm text-amber-800">
              {locale === "zh"
                ? "尚未執行分發。以下資料僅顯示學院設定的配額與申請需求概況。"
                : "Distribution has not been executed yet. Showing quota configuration and demand overview only."}
            </div>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardContent className="px-6 py-4">
          <div className="flex items-center justify-around divide-x divide-slate-200">
            {/* 總申請數 */}
            <div className="flex items-center gap-3 px-4 flex-1">
              <Users className="h-6 w-6 text-blue-600 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium text-slate-600">
                  {locale === "zh" ? "總申請數" : "Total Applications"}
                </p>
                <p className="text-xl font-bold text-slate-900">
                  {distributionData.total_applications.toLocaleString()}
                </p>
              </div>
            </div>

            {/* 正取人數 + 備取 */}
            <div className="flex items-center gap-3 px-4 flex-1">
              <CheckCircle className="h-6 w-6 text-green-600 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium text-slate-600">
                  {locale === "zh" ? "正取人數" : "Admitted"}
                </p>
                <div className="flex items-baseline gap-2">
                  <p className="text-xl font-bold text-green-600">
                    {distributionData.total_allocated.toLocaleString()}
                  </p>
                  <p className="text-xs text-slate-500">
                    {locale === "zh"
                      ? `備取 ${totalBackup.toLocaleString()}`
                      : `${totalBackup.toLocaleString()} backups`}
                  </p>
                </div>
              </div>
            </div>

            {/* 未獲分配 */}
            <div className="flex items-center gap-3 px-4 flex-1">
              <XCircle className="h-6 w-6 text-rose-600 flex-shrink-0" />
              <div>
                <p className="text-xs font-medium text-slate-600">
                  {locale === "zh" ? "未獲分配" : "Not Allocated"}
                </p>
                <p className="text-xl font-bold text-rose-600">
                  {totalRejected.toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="border-b">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <LayoutGrid className="h-5 w-5 text-blue-600" />
                {locale === "zh" ? "分配矩陣" : "Distribution Matrix"}
              </CardTitle>
              <CardDescription>
                {locale === "zh"
                  ? "橫軸為子獎學金，縱軸為學生排名；白色卡片代表實際分配結果。"
                  : "Columns represent sub-scholarships and rows follow ranking order. White cards highlight actual allocations."}
              </CardDescription>
            </div>
            <Button variant="outline" size="sm" onClick={handleExportDistribution}>
              <Download className="mr-2 h-4 w-4" />
              {locale === "zh" ? "匯出" : "Export"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {hasGridData ? (
            <div className="overflow-x-auto">
              <div className="min-w-[900px]">
                <div
                  className="grid"
                  style={{
                    gridTemplateColumns,
                  }}
                >
                  <div className="sticky top-0 left-0 z-30 bg-slate-100 px-3 py-3 text-sm font-semibold text-slate-700 shadow-[inset_-1px_-1px_0_rgba(15,23,42,0.05)]">
                    {locale === "zh" ? "排名" : "Rank"}
                  </div>
                  {subTypeKeys.map((subType) => {
                    const quota = aggregated.quotaMap[subType] ?? 0;
                    const admitted = aggregated.admittedCount[subType] ?? 0;
                    const backups = aggregated.backupCount[subType] ?? 0;
                    return (
                      <div
                        key={`header-${subType}`}
                        className="sticky top-0 z-20 bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-700 shadow-[inset_0_-1px_0_rgba(15,23,42,0.05)]"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate">{getColumnLabel(subType)}</span>
                          <Badge variant="outline" className="bg-white text-slate-600">
                            {locale === "zh" ? `配額 ${quota}` : `Quota ${quota}`}
                          </Badge>
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-[11px] text-slate-500">
                          <span>
                            {locale === "zh"
                              ? `正取 ${admitted}`
                              : `Admitted ${admitted}`}
                          </span>
                          {backups > 0 && (
                            <span>
                              {locale === "zh"
                                ? `備取 ${backups}`
                                : `Backup ${backups}`}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  <div className="sticky top-0 z-20 bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-700 shadow-[inset_0_-1px_0_rgba(15,23,42,0.05)]">
                    {locale === "zh" ? "未獲分發" : "Unassigned"}
                  </div>

                  {studentRows.map((student) => {
                    const rowKey = student.key;
                    const hasAllocation = Boolean(student.allocation);
                    const hasBackup = student.backupEntries.length > 0;
                    const isUnassigned = !hasAllocation && !hasBackup;

                    // Calculate contiguous runs of eligible columns
                    const eligibleIndexes = student.eligibleCodes
                      .map((code) => subTypeKeys.indexOf(code))
                      .filter((idx) => idx >= 0)
                      .sort((a, b) => a - b);
                    const eligibleRuns = contiguousRuns(eligibleIndexes);
                    // Map to pill tone (blue for allocated, warm for backup, muted for unassigned)
                    const pillTone: "blue" | "warm" | "muted" = hasAllocation
                      ? "blue"
                      : hasBackup
                        ? "warm"
                        : "muted";

                    return (
                      <div
                        key={rowKey}
                        style={{
                          display: "grid",
                          gridColumn: "1 / -1",
                          gridTemplateColumns: "subgrid",
                          position: "relative",
                          overflow: "visible"
                        }}
                        data-row-container={rowKey}
                      >
                        {/* Render run-level pills */}
                        {eligibleRuns.map(([runStart, runEnd]) => (
                          <RunPill
                            key={`pill-${rowKey}-${runStart}-${runEnd}`}
                            runStart={runStart}
                            runEnd={runEnd}
                            labels={student.eligibleLabels}
                            tone={pillTone}
                            rowKey={rowKey}
                            rankColumnWidth={220}
                          />
                        ))}

                        {/* Grid cells using display: contents for grid participation */}
                        <div className="contents group">
                          <div className="sticky left-0 z-10 flex items-center justify-center bg-white px-3 py-4 shadow-[1px_0_0_rgba(15,23,42,0.08)] transition-colors group-hover:bg-slate-50">
                            {renderRankBadge(student.rank)}
                          </div>

                          {subTypeKeys.map((subType, subTypeIndex) => {
                            const eligible = student.eligibleCodes.includes(subType);
                            const isAllocated = student.allocation?.subType === subType;
                            const backupInfo = student.backupEntries.find(
                              (entry) => entry.subType === subType
                            );

                            const cellClasses = [
                              "relative px-4 py-4 transition-colors overflow-visible",
                              // Make eligible cells transparent to show the pill behind
                              eligible
                                ? "bg-transparent"
                                : "bg-white",
                              "group-hover:bg-slate-50/50",
                            ].join(" ");

                            return (
                              <div
                                key={`${rowKey}-${subType}`}
                                className={cellClasses}
                                data-row-key={rowKey}
                                data-subtype-index={subTypeIndex}
                              >

                              {isAllocated ? (
                                <div
                                  className="relative"
                                  style={{ zIndex: Z_INDEX.CARD }}
                                  data-student-card
                                >
                                  <StudentPreviewCard
                                    studentId={student.studentId || ''}
                                    studentName={student.studentName}
                                    academicYear={academicYear}
                                    locale={locale}
                                  >
                                    <StudentInfoCard
                                      student={student}
                                      footer={
                                        <div className="flex items-center justify-between">
                                          <span className="text-slate-600">
                                            {locale === "zh"
                                              ? "已分配至本子項目"
                                              : "Allocated to this sub-type"}
                                          </span>
                                          <div className="ml-2 w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                                        </div>
                                      }
                                    />
                                  </StudentPreviewCard>
                                </div>
                              ) : backupInfo ? (
                                <div
                                  className="relative"
                                  style={{ zIndex: Z_INDEX.CARD }}
                                  data-student-card
                                >
                                  <StudentPreviewCard
                                    studentId={student.studentId || ''}
                                    studentName={student.studentName}
                                    academicYear={academicYear}
                                    locale={locale}
                                  >
                                    <StudentInfoCard
                                      student={student}
                                      tone="warm"
                                      footer={
                                        <div className="flex items-center justify-between">
                                          <span className="text-orange-700">
                                            {locale === "zh"
                                              ? `備取順位 ${backupInfo.backupPosition ?? "-"}`
                                              : `Backup position ${backupInfo.backupPosition ?? "-"}`}
                                          </span>
                                          <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
                                        </div>
                                      }
                                    />
                                  </StudentPreviewCard>
                                </div>
                              ) : eligible ? (
                                <div
                                  className="relative flex h-full items-center justify-center"
                                  style={{ zIndex: Z_INDEX.CARD }}
                                >
                                  {/* Empty for eligible cells - the track shows through */}
                                </div>
                              ) : (
                                <div className="flex h-full items-center justify-center text-2xl text-slate-200">
                                  —
                                </div>
                              )}
                            </div>
                          );
                        })}
                        <div className="relative px-4 py-4 transition-colors group-hover:bg-slate-50">
                          {isUnassigned ? (
                            <div className="relative" style={{ zIndex: Z_INDEX.CARD }}>
                              <StudentPreviewCard
                                studentId={student.studentId || ''}
                                studentName={student.studentName}
                                academicYear={academicYear}
                                locale={locale}
                              >
                                <StudentInfoCard
                                  student={student}
                                  tone="muted"
                                  footer={
                                  <div className="flex items-start gap-2">
                                    {student.rejection ? (
                                      <>
                                        <span
                                          className={`flex-1 text-[10px] leading-snug font-medium ${
                                            getRejectionReasonDisplay(student.rejection.reason, locale).color
                                          }`}
                                          style={{
                                            display: "-webkit-box",
                                            WebkitLineClamp: 2,
                                            WebkitBoxOrient: "vertical",
                                            overflow: "hidden",
                                            textOverflow: "ellipsis",
                                            maxWidth: "160px",
                                          }}
                                          title={
                                            locale === "zh"
                                              ? `未獲分發：${getRejectionReasonDisplay(student.rejection.reason, locale).label}`
                                              : `Not allocated: ${getRejectionReasonDisplay(student.rejection.reason, locale).label}`
                                          }
                                        >
                                          <span className="text-[11px] mr-1">
                                            {getRejectionReasonDisplay(student.rejection.reason, locale).icon}
                                          </span>
                                          {getRejectionReasonDisplay(student.rejection.reason, locale).label}
                                        </span>
                                        <div className={`w-2 h-2 rounded-full animate-pulse flex-shrink-0 mt-0.5 ${
                                          getRejectionReasonDisplay(student.rejection.reason, locale).color.includes('rose')
                                            ? 'bg-rose-500'
                                            : getRejectionReasonDisplay(student.rejection.reason, locale).color.includes('amber')
                                            ? 'bg-amber-500'
                                            : getRejectionReasonDisplay(student.rejection.reason, locale).color.includes('blue')
                                            ? 'bg-blue-500'
                                            : getRejectionReasonDisplay(student.rejection.reason, locale).color.includes('orange')
                                            ? 'bg-orange-500'
                                            : 'bg-slate-500'
                                        }`} />
                                      </>
                                    ) : (
                                      <span className="flex-1 text-[10px] leading-snug text-slate-600">
                                        {locale === "zh" ? "尚未分發" : "Awaiting allocation"}
                                      </span>
                                    )}
                                  </div>
                                }
                              />
                            </StudentPreviewCard>
                            </div>
                          ) : (
                            <div className="flex h-full items-center justify-center text-2xl text-slate-200">
                              —
                            </div>
                          )}
                        </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center gap-2 px-6 py-16 text-center text-slate-500">
              <LayoutGrid className="h-10 w-10 text-slate-300" />
              <p className="text-sm font-medium">
                {locale === "zh"
                  ? "目前尚無分配紀錄，請先執行分發作業。"
                  : "No distribution data yet. Execute the allocation to populate the matrix."}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {distributionData.rejected && distributionData.rejected.length > 0 && (
        <Card className="border-red-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-red-700">
              <XCircle className="h-5 w-5" />
              {locale === "zh" ? "未獲分配名單" : "Rejected Applications"}
            </CardTitle>
            <CardDescription>
              {locale === "zh"
                ? "未分配到任何子項目或超出配額的申請"
                : "Applications not allocated to any sub-type or exceeding quota"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-20">
                    {locale === "zh" ? "排名" : "Rank"}
                  </TableHead>
                  <TableHead>{locale === "zh" ? "學生姓名" : "Student Name"}</TableHead>
                  <TableHead>{locale === "zh" ? "學號" : "Student ID"}</TableHead>
                  <TableHead>{locale === "zh" ? "原因" : "Reason"}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {distributionData.rejected.map((student) => (
                  <TableRow key={student.application_id}>
                    <TableCell>
                      <Badge variant="outline">#{student.rank_position}</Badge>
                    </TableCell>
                    <TableCell className="font-medium">{student.student_name}</TableCell>
                    <TableCell className="text-sm text-gray-600">
                      {student.student_id}
                    </TableCell>
                    <TableCell className="text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-base">
                          {getRejectionReasonDisplay(student.reason, locale).icon}
                        </span>
                        <span className={`font-medium ${getRejectionReasonDisplay(student.reason, locale).color}`}>
                          {getRejectionReasonDisplay(student.reason, locale).label}
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
