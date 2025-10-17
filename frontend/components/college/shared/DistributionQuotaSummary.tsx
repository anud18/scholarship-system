import { useMemo } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { School, CheckCircle, AlertCircle } from "lucide-react";

type SubTypeQuotaBreakdown = Record<string, { quota?: number; label?: string; label_en?: string }>;

interface DistributionQuotaSummaryProps {
  locale: "zh" | "en";
  totalQuota?: number;
  collegeQuota?: number;
  applications?: Array<{ is_allocated?: boolean }>;
  breakdown?: SubTypeQuotaBreakdown;
  subTypeMeta?: Record<string, { code: string; label: string; label_en: string }>;
}

export function DistributionQuotaSummary({
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
      <Card>
        <CardContent className="px-6 py-4">
          <div className="flex items-center justify-around divide-x divide-slate-200">
            {/* 學院配額 */}
            <div className="flex items-center gap-3 px-4 flex-1">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 text-blue-600 flex-shrink-0">
                <School className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-medium text-blue-700">
                  {locale === "zh" ? "學院配額" : "College Quota"}
                </p>
                <p className="text-xl font-semibold text-blue-900">
                  {formatValue(effectiveQuota)}
                </p>
                {!hasCollegeQuota && (
                  <p className="text-xs text-blue-700/80">
                    {locale === "zh"
                      ? "暫以總配額估算"
                      : "Using global quota"}
                  </p>
                )}
              </div>
            </div>

            {/* 已分配 */}
            <div className="flex items-center gap-3 px-4 flex-1">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-100 text-emerald-600 flex-shrink-0">
                <CheckCircle className="h-4 w-4" />
              </div>
              <div className="flex-1">
                <p className="text-xs font-medium text-emerald-700">
                  {locale === "zh" ? "已分配" : "Allocated"}
                </p>
                <div className="flex items-baseline gap-2">
                  <p className="text-xl font-semibold text-emerald-700">
                    {allocatedCount.toLocaleString()}
                  </p>
                  <p className="text-xs text-gray-500">
                    {locale === "zh"
                      ? `/ ${demandCount.toLocaleString()}`
                      : `/ ${demandCount.toLocaleString()}`}
                  </p>
                </div>
                <Progress
                  value={allocationRate}
                  className="h-1.5 mt-1"
                  indicatorClassName="bg-emerald-500"
                  aria-label={locale === "zh" ? "分配進度" : "Allocation progress"}
                />
              </div>
            </div>

            {/* 剩餘名額 */}
            <div className="flex items-center gap-3 px-4 flex-1">
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-orange-100 text-orange-600 flex-shrink-0">
                <AlertCircle className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-medium text-orange-700">
                  {locale === "zh" ? "剩餘名額" : "Remaining"}
                </p>
                <p className="text-xl font-semibold text-orange-700">
                  {formatValue(remainingQuota)}
                </p>
                <p className="text-xs text-gray-500">
                  {locale === "zh"
                    ? "檢視備取或調整"
                    : "Review or adjust"}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>


      {breakdownItems.length > 0 && (
        <Card className="shadow-sm">
          <CardHeader className="pt-4 pb-2">
            <CardTitle className="text-base">
              {locale === "zh" ? "子項目配額概況" : "Sub-scholarship Overview"}
            </CardTitle>
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
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs font-medium text-slate-700">
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
                          <p className="text-base font-semibold text-slate-800">
                            {formatValue(quotaNumber)}
                          </p>
                        </div>
                      </div>

                      <div className="mt-2">
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
                          className="mt-1 h-1.5"
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
