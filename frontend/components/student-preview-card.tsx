"use client";

import { useState, useEffect } from "react";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { useStudentPreview } from "@/hooks/use-student-preview";
import {
  useReferenceData,
  getIdentityName,
  getSchoolIdentityName,
  getDegreeName,
  getGenderName,
  getAcademyName,
  getDepartmentName,
  getStudyingStatusName,
} from "@/hooks/use-reference-data";
import { User, GraduationCap, Calendar, Award, Mail, Phone, MapPin } from "lucide-react";
import { getCurrentSemesterROC } from "@/src/utils/dateUtils";

interface StudentPreviewCardProps {
  studentId: string;
  studentName: string;
  academicYear?: number;
  locale?: "zh" | "en";
  children?: React.ReactNode;
}

export function StudentPreviewCard({
  studentId,
  studentName,
  academicYear,
  locale = "zh",
  children,
}: StudentPreviewCardProps) {
  const { previewData, isLoading, error, fetchPreview } = useStudentPreview();
  const { academies, departments, degrees, genders, identities, schoolIdentities, studyingStatuses } = useReferenceData();
  const [isOpen, setIsOpen] = useState(false);
  const [hasTriggered, setHasTriggered] = useState(false);

  // Debounced hover trigger
  useEffect(() => {
    if (isOpen && !hasTriggered) {
      const timer = setTimeout(() => {
        // If academicYear is not provided, use current academic year
        let yearToUse = academicYear;
        if (!yearToUse) {
          // Get current semester (e.g., "114-1") and extract year
          const currentSemester = getCurrentSemesterROC();
          const [yearStr] = currentSemester.split("-");
          yearToUse = parseInt(yearStr, 10);
        }
        fetchPreview(studentId, yearToUse);
        setHasTriggered(true);
      }, 300); // 300ms debounce

      return () => clearTimeout(timer);
    }
  }, [isOpen, hasTriggered, studentId, academicYear, fetchPreview]);

  // Reset trigger when card closes
  useEffect(() => {
    if (!isOpen) {
      setHasTriggered(false);
    }
  }, [isOpen]);

  const formatGPA = (gpa?: number) => {
    if (gpa === undefined || gpa === null) return "-";
    return gpa.toFixed(2);
  };

  const getDegreeColor = (degreeId?: number) => {
    if (!degreeId) return "bg-gray-100 text-gray-800";
    const degreeName = getDegreeName(degreeId, degrees);
    if (degreeName.includes("博士")) return "bg-purple-100 text-purple-800";
    if (degreeName.includes("碩士")) return "bg-blue-100 text-blue-800";
    return "bg-green-100 text-green-800";
  };

  // Helper to render info row
  const InfoRow = ({
    icon: Icon,
    label,
    value,
  }: {
    icon?: any;
    label: string;
    value?: string;
  }) => {
    if (!value) return null;
    return (
      <div className="flex items-start gap-2 text-xs">
        {Icon && <Icon className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />}
        <div className="flex-1">
          <p className="text-muted-foreground font-medium">{label}:</p>
          <p className="text-foreground">{value}</p>
        </div>
      </div>
    );
  };

  const basic = previewData?.basic;

  return (
    <HoverCard openDelay={200} closeDelay={100} onOpenChange={setIsOpen}>
      <HoverCardTrigger asChild>
        {children ? (
          <div className="cursor-pointer">{children}</div>
        ) : (
          <span className="cursor-pointer hover:underline hover:text-blue-600 transition-colors">
            {studentName}
          </span>
        )}
      </HoverCardTrigger>
      <HoverCardContent
        className="w-96 max-h-96 overflow-y-auto bg-background/90 backdrop-blur-sm border border-border/50 shadow-lg z-[100]"
        side="right"
        align="start"
      >
        <div className="space-y-3 text-xs">
          {/* Header - Name & ID */}
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1">
              <p className="font-semibold text-sm">
                {basic?.std_cname || studentName}
              </p>
              {basic?.std_ename && (
                <p className="text-muted-foreground text-xs">{basic.std_ename}</p>
              )}
              <p className="text-muted-foreground text-xs">
                {locale === "zh" ? "學號" : "ID"}: {basic?.std_stdcode || studentId}
              </p>
            </div>
            {basic?.std_degree && (
              <Badge variant="outline" className={getDegreeColor(basic.std_degree)}>
                {getDegreeName(basic.std_degree, degrees)}
              </Badge>
            )}
          </div>

          <Separator />

          {/* === 學籍資訊 === */}
          <div className="space-y-1.5">
            <p className="font-semibold text-xs">{locale === "zh" ? "學籍資訊" : "Academic Info"}</p>
            <div className="space-y-1 ml-2">
              {basic?.std_academyno && (
                <InfoRow
                  label={locale === "zh" ? "學院" : "Academy"}
                  value={getAcademyName(basic.std_academyno, academies)}
                />
              )}
              {basic?.std_depno && (
                <InfoRow
                  label={locale === "zh" ? "系所" : "Department"}
                  value={getDepartmentName(basic.std_depno, departments)}
                />
              )}
              {basic?.std_studingstatus && (
                <InfoRow
                  label={locale === "zh" ? "在學狀態" : "Studying Status"}
                  value={getStudyingStatusName(basic.std_studingstatus, studyingStatuses)}
                />
              )}
              {basic?.mgd_title && (
                <InfoRow
                  label={locale === "zh" ? "學籍狀態" : "Status"}
                  value={basic.mgd_title}
                />
              )}
            </div>
          </div>

          <Separator />

          {/* === 入學資訊 === */}
          <div className="space-y-1.5">
            <p className="font-semibold text-xs">{locale === "zh" ? "入學資訊" : "Enrollment"}</p>
            <div className="space-y-1 ml-2">
              {basic?.std_enrollyear && (
                <InfoRow
                  icon={Calendar}
                  label={locale === "zh" ? "入學年度" : "Enrolled Year"}
                  value={`${basic.std_enrollyear}/${basic.std_enrollterm || ""}`}
                />
              )}
              {basic?.std_termcount && (
                <InfoRow
                  icon={Award}
                  label={locale === "zh" ? "學期數" : "Terms"}
                  value={`${basic.std_termcount}`}
                />
              )}
              {basic?.std_highestschname && (
                <InfoRow
                  label={locale === "zh" ? "最高學歷" : "Education"}
                  value={basic.std_highestschname}
                />
              )}
            </div>
          </div>

          <Separator />

          {/* === 個人資訊 === */}
          <div className="space-y-1.5">
            <p className="font-semibold text-xs">{locale === "zh" ? "個人資訊" : "Personal Info"}</p>
            <div className="space-y-1 ml-2">
              {basic?.std_sex && (
                <InfoRow
                  label={locale === "zh" ? "性別" : "Gender"}
                  value={getGenderName(basic.std_sex, genders)}
                />
              )}
              {basic?.std_identity && (
                <InfoRow
                  label={locale === "zh" ? "學生身分" : "Identity"}
                  value={getIdentityName(basic.std_identity, identities)}
                />
              )}
              {basic?.std_schoolid && (
                <InfoRow
                  label={locale === "zh" ? "在學身分" : "School Identity"}
                  value={getSchoolIdentityName(basic.std_schoolid, schoolIdentities)}
                />
              )}
              {basic?.std_nation && (
                <InfoRow
                  label={locale === "zh" ? "國籍" : "Nationality"}
                  value={basic.std_nation}
                />
              )}
              {basic?.std_overseaplace && (
                <InfoRow
                  label={locale === "zh" ? "僑居地" : "Overseas Place"}
                  value={basic.std_overseaplace}
                />
              )}
            </div>
          </div>

          <Separator />

          {/* === 聯絡資訊 === */}
          <div className="space-y-1.5">
            <p className="font-semibold text-xs">{locale === "zh" ? "聯絡資訊" : "Contact"}</p>
            <div className="space-y-1 ml-2">
              {basic?.com_email && (
                <InfoRow
                  icon={Mail}
                  label="Email"
                  value={basic.com_email}
                />
              )}
              {basic?.com_cellphone && (
                <InfoRow
                  icon={Phone}
                  label={locale === "zh" ? "手機" : "Phone"}
                  value={basic.com_cellphone}
                />
              )}
              {basic?.com_commadd && (
                <InfoRow
                  icon={MapPin}
                  label={locale === "zh" ? "地址" : "Address"}
                  value={basic.com_commadd}
                />
              )}
            </div>
          </div>

          <Separator />

          {/* Term Data - Async Loading */}
          <div className="space-y-2">
            <p className="font-semibold text-xs">
              {locale === "zh" ? "近期學期成績" : "Recent Terms"}
            </p>

            {isLoading && (
              <div className="space-y-2 ml-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
              </div>
            )}

            {error && (
              <p className="text-xs text-red-500">
                {locale === "zh" ? "無法載入學期資料" : "Failed to load term data"}
              </p>
            )}

            {!isLoading && !error && previewData?.recent_terms && previewData.recent_terms.length > 0 && (
              <div className="space-y-1 ml-2">
                {previewData.recent_terms.map((term) => (
                  <div
                    key={`${term.academic_year}-${term.term}`}
                    className="bg-muted/50 rounded-md p-1.5 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {term.academic_year}-{term.term === "1" ? (locale === "zh" ? "上" : "1st") : (locale === "zh" ? "下" : "2nd")}
                      </span>
                      {term.gpa !== undefined && (
                        <Badge variant="outline" className="text-xs">
                          GPA: {formatGPA(term.gpa)}
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {!isLoading && !error && (!previewData?.recent_terms || previewData.recent_terms.length === 0) && (
              <p className="text-xs text-muted-foreground">
                {locale === "zh" ? "無學期資料" : "No term data available"}
              </p>
            )}
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
