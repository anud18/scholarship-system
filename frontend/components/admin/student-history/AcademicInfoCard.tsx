"use client";

import { AlertCircle, GraduationCap } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  getAcademyName,
  getDegreeName,
  getStudyingStatusName,
  useReferenceData,
} from "@/hooks/use-reference-data";
import type { AcademicInfo } from "@/lib/api/modules/student-history";

interface AcademicInfoCardProps {
  academicInfo: AcademicInfo;
  snapshotName: string | null;
}

function parseRefId(value: string | null | undefined): number | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

export function AcademicInfoCard({
  academicInfo,
  snapshotName,
}: AcademicInfoCardProps) {
  const { degrees, studyingStatuses, academies } = useReferenceData();

  if (!academicInfo.available) {
    return (
      <Card className="border-yellow-500">
        <CardContent className="flex items-start gap-3 pt-6">
          <AlertCircle className="h-5 w-5 text-yellow-500 mt-0.5" />
          <div>
            <p className="font-medium text-yellow-700">無即時學籍資料</p>
            <p className="text-sm text-muted-foreground mt-1">
              {academicInfo.error ??
                "無法取得 SIS 即時學籍資料,以下顯示造冊時的姓名快照。"}
            </p>
            {snapshotName && (
              <p className="text-sm mt-2">
                <span className="text-muted-foreground">造冊快照姓名:</span>{" "}
                <span className="font-medium">{snapshotName}</span>
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  const info = academicInfo.basic_info;
  if (!info) {
    return null;
  }

  const degreeLabel = getDegreeName(parseRefId(info.std_degree), degrees);
  const statusLabel = getStudyingStatusName(parseRefId(info.std_studingstatus), studyingStatuses);
  const academyLabel = info.std_aca_cname || getAcademyName(info.std_academyno, academies);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GraduationCap className="h-5 w-5" />
          學籍資料
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">中文姓名</p>
            <p className="text-lg">{info.std_cname ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">英文姓名</p>
            <p className="text-lg">{info.std_ename ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">學位</p>
            <p>{degreeLabel}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">在學狀態</p>
            <p>{statusLabel}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">學院</p>
            <p>{academyLabel}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">系所</p>
            <p>{info.std_depname ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">系所代碼</p>
            <p className="font-mono">{info.std_depno ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">電子郵件</p>
            <p className="text-sm">{info.com_email ?? "N/A"}</p>
          </div>
        </div>
        <Separator className="my-3" />
      </CardContent>
    </Card>
  );
}
