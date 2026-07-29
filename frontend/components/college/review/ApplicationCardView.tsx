"use client";

/**
 * 學院審核 - 卡片檢視。
 *
 * 與同層的表格檢視顯示相同欄位，只是改用卡片排版，適合在較窄的螢幕
 * 或需要快速掃視少量申請時使用。
 */

import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Award, Eye, School } from "lucide-react";
import {
  ApplicationStatus,
  getApplicationStatusLabel,
  getApplicationStatusBadgeVariant,
} from "@/lib/enums";
import {
  useReferenceData,
  getStudyingStatusName,
  getAcademyName,
  getDepartmentName,
} from "@/hooks/use-reference-data";
import type { Application } from "@/lib/api/types";
import {
  NationalityIdentity,
  ProfessorRecommendation,
  formatAppliedDate,
} from "./application-summary-fields";

type Locale = "zh" | "en";

interface ApplicationCardViewProps {
  applications: Application[];
  locale: Locale;
  getSubTypeName: (subTypeCode: string | undefined, locale: Locale) => string;
  onView: (app: Application) => void;
}

function FieldRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-xs text-muted-foreground shrink-0 pt-0.5">
        {label}
      </span>
      <div className="text-sm text-right">{children}</div>
    </div>
  );
}

export function ApplicationCardView({
  applications,
  locale,
  getSubTypeName,
  onView,
}: ApplicationCardViewProps) {
  const { studyingStatuses, academies, departments } = useReferenceData();

  if (applications.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        {locale === "zh" ? "沒有符合條件的申請" : "No matching applications"}
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {applications.map(app => (
        <Card key={app.id} className="flex flex-col">
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="font-medium truncate">
                  {app.student_name || "未提供姓名"}
                </span>
                <span className="text-sm text-muted-foreground">
                  {app.student_id || "未提供學號"}
                </span>
              </div>
              <Badge
                variant={getApplicationStatusBadgeVariant(
                  app.status as ApplicationStatus
                )}
                className="shrink-0"
              >
                {app.status_zh ||
                  getApplicationStatusLabel(
                    app.status as ApplicationStatus,
                    locale
                  )}
              </Badge>
            </div>
          </CardHeader>

          <CardContent className="flex-1 space-y-3">
            <div className="flex items-center gap-2 text-sm">
              <School className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="truncate">
                {getAcademyName(app.academy_code, academies)}
                <span className="text-muted-foreground">
                  {" · "}
                  {getDepartmentName(app.department_code, departments)}
                </span>
              </span>
            </div>

            <div className="flex items-center gap-2 text-sm">
              <Award className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="truncate">
                {app.scholarship_type_zh || app.scholarship_type}
              </span>
              <Badge
                variant={app.is_renewal ? "secondary" : "default"}
                className="ml-auto shrink-0"
              >
                {app.is_renewal ? "續領" : "初領"}
              </Badge>
            </div>

            <div className="space-y-1.5 border-t pt-3">
              <FieldRow label={locale === "zh" ? "國籍 / 身分" : "Nationality"}>
                <NationalityIdentity app={app} locale={locale} />
              </FieldRow>
              <FieldRow label={locale === "zh" ? "在學學期數" : "Terms"}>
                {app.student_termcount || "-"}
              </FieldRow>
              <FieldRow label={locale === "zh" ? "在學狀態" : "Study Status"}>
                {app.scholarship_period_status !== undefined &&
                app.scholarship_period_status !== null
                  ? getStudyingStatusName(
                      app.scholarship_period_status,
                      studyingStatuses
                    )
                  : "-"}
              </FieldRow>
            </div>

            <div className="space-y-1.5 border-t pt-3">
              <span className="text-xs text-muted-foreground">
                {locale === "zh" ? "教授推薦" : "Prof. Review"}
              </span>
              <div className="flex flex-wrap gap-1">
                <ProfessorRecommendation
                  app={app}
                  locale={locale}
                  getSubTypeName={getSubTypeName}
                />
              </div>
            </div>
          </CardContent>

          <CardFooter className="flex items-center justify-between pt-3 border-t">
            <span className="text-xs text-muted-foreground">
              {locale === "zh" ? "申請時間" : "Applied"}{" "}
              {formatAppliedDate(app.created_at)}
            </span>
            <Button variant="outline" size="sm" onClick={() => onView(app)}>
              <Eye className="h-4 w-4 mr-1" />
              {locale === "zh" ? "檢視" : "View"}
            </Button>
          </CardFooter>
        </Card>
      ))}
    </div>
  );
}
