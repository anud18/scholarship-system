"use client";

import { useEffect, useMemo, useState } from "react";
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
} from "lucide-react";
import { apiClient } from "@/lib/api";

interface DistributionResultsPanelProps {
  rankingId: number;
  applications?: any[];
  locale?: "zh" | "en";
  onClose?: () => void;
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
}: DistributionResultsPanelProps) {
  const [distributionData, setDistributionData] =
    useState<DistributionDetails | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subTypeTranslations, setSubTypeTranslations] =
    useState<SubTypeTranslations>({ zh: {}, en: {} });

  useEffect(() => {
    fetchDistributionDetails();
  }, [rankingId]);

  useEffect(() => {
    let isMounted = true;
    const loadTranslations = async () => {
      try {
        const response = await apiClient.college.getSubTypeTranslations();
        if (response.success && response.data && isMounted) {
          setSubTypeTranslations({
            zh: response.data.zh || {},
            en: response.data.en || {},
          });
        }
      } catch (err) {
        console.error("Failed to load sub-type translations:", err);
      }
    };

    loadTranslations();
    return () => {
      isMounted = false;
    };
  }, []);

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
      subTypeInfo[subType] = {
        label: fallbackMeta.label || subType,
        labelEn: fallbackMeta.label_en || fallbackMeta.label || subType,
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

      quotaMap[subType] =
        typeof totalQuotaFromEntry === "number"
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
  }, [distributionData, applications, subTypeMetaMap]);
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

        return {
          key: applicationId ?? `row-${index}`,
          applicationId,
          appId: app?.app_id,
          studentName: app?.student_name || "-",
          studentId: app?.student_id,
          rank: rawRank,
          sortRank,
          eligibleCodes,
          eligibleLabels,
          primaryEligibleSubType: eligibleCodes[0],
          allocation,
          backupEntries: backups,
          rejection,
          statusBadge,
        };
      })
      .sort((a, b) => a.sortRank - b.sortRank);
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

  const renderEligibleTags = (
    labels: string[],
    tone: "default" | "warm" = "default"
  ) => (
    <div
      className={`rounded-xl ${
        tone === "warm" ? "bg-orange-100/70" : "bg-slate-100/80"
      } p-3 shadow-inner`}
    >
      <p className="text-[11px] font-medium text-slate-600">
        {locale === "zh" ? "符合子項目" : "Eligible Sub-scholarships"}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        {labels.length > 0 ? (
          labels.map((label, idx) => (
            <span
              key={`${label}-${idx}`}
              className="rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-700 shadow-sm"
            >
              {label}
            </span>
          ))
        ) : (
          <span className="text-[11px] text-slate-500">
            {locale === "zh" ? "尚未提供" : "Not provided"}
          </span>
        )}
      </div>
    </div>
  );

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
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center">
              <Users className="h-8 w-8 text-blue-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-slate-600">
                  {locale === "zh" ? "總申請數" : "Total Applications"}
                </p>
                <p className="text-2xl font-bold text-slate-900">
                  {distributionData.total_applications.toLocaleString()}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center">
              <CheckCircle className="h-8 w-8 text-green-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-slate-600">
                  {locale === "zh" ? "正取人數" : "Admitted"}
                </p>
                <p className="text-2xl font-bold text-green-600">
                  {distributionData.total_allocated.toLocaleString()}
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  {locale === "zh"
                    ? `備取 ${totalBackup.toLocaleString()} 名`
                    : `${totalBackup.toLocaleString()} backups`}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex items-center">
              <XCircle className="h-8 w-8 text-rose-600" />
              <div className="ml-4">
                <p className="text-sm font-medium text-slate-600">
                  {locale === "zh" ? "未獲分配" : "Not Allocated"}
                </p>
                <p className="text-2xl font-bold text-rose-600">
                  {totalRejected.toLocaleString()}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

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
            <Button variant="outline" size="sm">
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
                    gridTemplateColumns: `160px repeat(${subTypeKeys.length}, minmax(240px, 1fr))`,
                  }}
                >
                  <div className="sticky top-0 left-0 z-30 border-b border-slate-200 bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-700 shadow-[inset_-1px_-1px_0_rgba(15,23,42,0.05)]">
                    {locale === "zh" ? "排名 / 學生" : "Rank / Student"}
                  </div>
                  {subTypeKeys.map((subType) => {
                    const quota = aggregated.quotaMap[subType] ?? 0;
                    const admitted = aggregated.admittedCount[subType] ?? 0;
                    const backups = aggregated.backupCount[subType] ?? 0;
                    return (
                      <div
                        key={`header-${subType}`}
                        className="sticky top-0 z-20 border-b border-l border-slate-200 bg-slate-100 px-4 py-3 text-sm font-semibold text-slate-700 shadow-[inset_0_-1px_0_rgba(15,23,42,0.05)]"
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

                  {studentRows.map((student) => {
                    const rowKey = student.key;
                    return (
                      <div key={rowKey} className="contents group">
                        <div className="sticky left-0 z-10 border-b border-slate-200 bg-white px-4 py-4 shadow-[1px_0_0_rgba(15,23,42,0.08)] transition-colors group-hover:bg-slate-50">
                          <div className="flex items-center gap-2">
                            <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-700">
                              {student.rank !== null
                                ? locale === "zh"
                                  ? `第 ${student.rank} 名`
                                  : `Rank ${student.rank}`
                                : locale === "zh"
                                  ? "未排序"
                                  : "Unranked"}
                            </span>
                            <span className="text-sm font-semibold text-slate-800">
                              {student.studentName}
                            </span>
                          </div>
                          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                            {student.studentId && (
                              <span>
                                {locale === "zh"
                                  ? `學號 ${student.studentId}`
                                  : `ID ${student.studentId}`}
                              </span>
                            )}
                            {student.appId && (
                              <span className="text-slate-400">
                                {locale === "zh"
                                  ? `申請 ${student.appId}`
                                  : `App ${student.appId}`}
                              </span>
                            )}
                          </div>
                          <span
                            className={`mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${student.statusBadge.className}`}
                          >
                            <span aria-hidden>{student.statusBadge.icon}</span>
                            <span>{student.statusBadge.label}</span>
                          </span>
                        </div>

                        {subTypeKeys.map((subType) => {
                          const eligible = student.eligibleCodes.includes(subType);
                          const isAllocated =
                            student.allocation?.subType === subType;
                          const backupInfo = student.backupEntries.find(
                            (entry) => entry.subType === subType
                          );
                          const cellClasses = [
                            "relative border-b border-l border-slate-200 px-4 py-4 transition-colors",
                            eligible ? "bg-slate-50/60" : "bg-white",
                            "group-hover:bg-slate-50",
                          ].join(" ");

                          return (
                            <div key={`${rowKey}-${subType}`} className={cellClasses}>
                              {isAllocated ? (
                                <div className="space-y-3">
                                  <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                                    <div className="flex items-start justify-between gap-2">
                                      <div>
                                        <p className="text-sm font-semibold text-slate-900">
                                          {student.studentName}
                                        </p>
                                        <p className="text-xs text-slate-500">
                                          {locale === "zh"
                                            ? `實際分配：${getColumnLabel(subType)}`
                                            : `Allocated: ${getColumnLabel(subType)}`}
                                        </p>
                                      </div>
                                      <span
                                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${student.statusBadge.className}`}
                                      >
                                        <span aria-hidden>{student.statusBadge.icon}</span>
                                        <span>{student.statusBadge.label}</span>
                                      </span>
                                    </div>
                                    <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                                      <span>
                                        {locale === "zh"
                                          ? `排名 ${student.rank ?? "-"}`
                                          : `Rank ${student.rank ?? "-"}`}
                                      </span>
                                      {student.appId && (
                                        <span>
                                          {locale === "zh"
                                            ? `申請 ${student.appId}`
                                            : `App ${student.appId}`}
                                        </span>
                                      )}
                                    </div>
                                  </div>
                                  {renderEligibleTags(student.eligibleLabels)}
                                </div>
                              ) : backupInfo ? (
                                <div className="space-y-3">
                                  <div className="rounded-xl border border-orange-300 bg-orange-50/70 p-4 shadow-sm">
                                    <div className="flex items-start justify-between gap-2">
                                      <div>
                                        <p className="text-sm font-semibold text-slate-900">
                                          {student.studentName}
                                        </p>
                                        <p className="text-xs font-medium text-orange-700">
                                          {locale === "zh"
                                            ? `備取第 ${backupInfo.backupPosition ?? "-"} 位`
                                            : `Backup #${backupInfo.backupPosition ?? "-"}`}
                                        </p>
                                      </div>
                                      <span className="rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-orange-700 shadow-sm">
                                        {locale === "zh" ? "備取" : "Backup"}
                                      </span>
                                    </div>
                                    <p className="mt-2 text-xs text-slate-600">
                                      {locale === "zh"
                                        ? "若前序名額釋出，將自動遞補"
                                        : "Advances when seats are released"}
                                    </p>
                                  </div>
                                  {renderEligibleTags(student.eligibleLabels, "warm")}
                                </div>
                              ) : eligible ? (
                                subType === student.primaryEligibleSubType ? (
                                  <div className="space-y-3">
                                    <div className="rounded-xl border border-dashed border-slate-300 bg-white/80 p-4 text-center text-xs font-medium text-slate-500">
                                      {locale === "zh"
                                        ? "符合資格，尚未分配"
                                        : "Eligible, awaiting allocation"}
                                    </div>
                                    {renderEligibleTags(student.eligibleLabels)}
                                  </div>
                                ) : (
                                  <div className="flex h-full items-center justify-center">
                                    <span className="rounded-full border border-dashed border-slate-300 px-3 py-1 text-[11px] text-slate-500">
                                      {locale === "zh" ? "符合資格" : "Eligible"}
                                    </span>
                                  </div>
                                )
                              ) : (
                                <div className="flex h-full items-center justify-center text-2xl text-slate-200">
                                  —
                                </div>
                              )}
                            </div>
                          );
                        })}
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
                    <TableCell className="text-sm text-red-600">
                      {student.reason}
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
