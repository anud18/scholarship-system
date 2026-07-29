"use client";

/**
 * Presentational fields shared by the college review 表格檢視 / 卡片檢視.
 *
 * Both views render the same application facts, so the non-trivial bits
 * (SIS 身分別 decoding, 教授推薦 badges) live here to avoid drift.
 */

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { Application } from "@/lib/api/types";

type Locale = "zh" | "en";

/** SIS 身分別代碼 → 中文標籤 (student_data.std_identity) */
const IDENTITY_LABELS: Record<string, string> = {
  "1": "本國生",
  "2": "僑生",
  "3": "外籍生",
  "4": "陸生",
  "5": "港澳生",
  "6": "外籍交換生",
};

interface StudentIdentitySnapshot {
  std_nation?: string | null;
  std_identity?: number | string | null;
}

const identitySnapshot = (app: Application): StudentIdentitySnapshot =>
  (app.student_data as StudentIdentitySnapshot | undefined) ?? {};

export function getNationality(app: Application): string | null {
  return identitySnapshot(app).std_nation || null;
}

export function getIdentityLabel(
  app: Application,
  locale: Locale
): string | null {
  const code = identitySnapshot(app).std_identity;
  if (code === null || code === undefined || code === "") return null;
  return (
    IDENTITY_LABELS[String(code)] ||
    `${locale === "zh" ? "身分別" : "Identity"} ${code}`
  );
}

export function formatAppliedDate(createdAt?: string): string {
  if (!createdAt) return "-";
  return new Date(createdAt).toLocaleDateString("zh-TW", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

/** 國籍 / 身分別 */
export function NationalityIdentity({
  app,
  locale,
}: {
  app: Application;
  locale: Locale;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-sm">{getNationality(app) || "-"}</span>
      <span className="text-xs text-muted-foreground">
        {getIdentityLabel(app, locale) || "-"}
      </span>
    </div>
  );
}

/**
 * 教授推薦徽章。無推薦紀錄但流程需要教授審核時顯示「教授審核中」，
 * 讓學院端知道申請仍卡在教授關卡，而不是看到空白。
 */
export function ProfessorRecommendation({
  app,
  locale,
  getSubTypeName,
}: {
  app: Application;
  locale: Locale;
  getSubTypeName: (subTypeCode: string | undefined, locale: Locale) => string;
}) {
  const items = app.professor_review_items;

  if (!items || items.length === 0) {
    if (app.requires_professor_recommendation) {
      return (
        <Badge
          variant="outline"
          className="text-xs cursor-default border-amber-500 text-amber-700 bg-amber-50"
        >
          {locale === "zh" ? "教授審核中" : "Under prof. review"}
        </Badge>
      );
    }
    return <span className="text-sm text-muted-foreground">—</span>;
  }

  return (
    <div className="flex flex-col gap-0.5">
      {items.map((item, idx) => {
        const isApprove = item.recommendation === "approve";
        return (
          <TooltipProvider key={`${item.sub_type_code}-${idx}`}>
            <Tooltip>
              <TooltipTrigger asChild>
                <Badge
                  variant={isApprove ? "outline" : "destructive"}
                  className={`text-xs cursor-default ${
                    isApprove
                      ? "border-emerald-500 text-emerald-700 bg-emerald-50"
                      : ""
                  }`}
                >
                  {getSubTypeName(item.sub_type_code, locale)}:{" "}
                  {isApprove
                    ? locale === "zh"
                      ? "推薦"
                      : "Approve"
                    : locale === "zh"
                      ? "不推薦"
                      : "Reject"}
                </Badge>
              </TooltipTrigger>
              {item.comments && (
                <TooltipContent>
                  {!isApprove && (
                    <p className="font-medium text-xs mb-1">
                      {locale === "zh" ? "不同意理由" : "Reason for Reject"}
                    </p>
                  )}
                  <p className="max-w-xs whitespace-pre-wrap">
                    {item.comments}
                  </p>
                </TooltipContent>
              )}
            </Tooltip>
          </TooltipProvider>
        );
      })}
    </div>
  );
}
