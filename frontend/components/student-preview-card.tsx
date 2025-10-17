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
import { User, GraduationCap, Calendar, Award } from "lucide-react";

interface StudentBasicInfo {
  department_name?: string;
  academy_name?: string;
  term_count?: number;
  degree?: string;
  enrollyear?: string;
}

interface StudentPreviewCardProps {
  studentId: string;
  studentName: string;
  basicInfo?: StudentBasicInfo;
  academicYear?: number;
  locale?: "zh" | "en";
}

export function StudentPreviewCard({
  studentId,
  studentName,
  basicInfo,
  academicYear,
  locale = "zh",
}: StudentPreviewCardProps) {
  const { previewData, isLoading, error, fetchPreview } = useStudentPreview();
  const [isOpen, setIsOpen] = useState(false);
  const [hasTriggered, setHasTriggered] = useState(false);

  // Debounced hover trigger
  useEffect(() => {
    if (isOpen && !hasTriggered) {
      const timer = setTimeout(() => {
        fetchPreview(studentId, academicYear);
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

  const getDegreeColor = (degree?: string) => {
    if (!degree) return "bg-gray-100 text-gray-800";
    if (degree.includes("博士")) return "bg-purple-100 text-purple-800";
    if (degree.includes("碩士")) return "bg-blue-100 text-blue-800";
    return "bg-green-100 text-green-800";
  };

  return (
    <HoverCard openDelay={200} closeDelay={100} onOpenChange={setIsOpen}>
      <HoverCardTrigger asChild>
        <span className="cursor-pointer hover:underline hover:text-blue-600 transition-colors">
          {studentName}
        </span>
      </HoverCardTrigger>
      <HoverCardContent
        className="w-80 bg-background/90 backdrop-blur-sm border border-border/50 shadow-lg"
        side="right"
        align="start"
      >
        <div className="space-y-3">
          {/* Header - Student Name */}
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-2">
              <User className="h-4 w-4 text-muted-foreground" />
              <div>
                <p className="font-semibold text-base">
                  {previewData?.basic.student_name || studentName}
                </p>
                <p className="text-xs text-muted-foreground">
                  {locale === "zh" ? "學號" : "ID"}: {studentId}
                </p>
              </div>
            </div>
            {(previewData?.basic.degree || basicInfo?.degree) && (
              <Badge variant="outline" className={getDegreeColor(previewData?.basic.degree || basicInfo?.degree)}>
                {previewData?.basic.degree || basicInfo?.degree}
              </Badge>
            )}
          </div>

          <Separator />

          {/* Basic Information */}
          <div className="space-y-2 text-sm">
            {(previewData?.basic.academy_name || basicInfo?.academy_name) && (
              <div className="flex items-start gap-2">
                <GraduationCap className="h-4 w-4 text-muted-foreground mt-0.5" />
                <div className="flex-1">
                  <p className="font-medium">
                    {previewData?.basic.academy_name || basicInfo?.academy_name}
                  </p>
                  {(previewData?.basic.department_name || basicInfo?.department_name) && (
                    <p className="text-xs text-muted-foreground">
                      {previewData?.basic.department_name || basicInfo?.department_name}
                    </p>
                  )}
                </div>
              </div>
            )}

            {(previewData?.basic.enrollyear || basicInfo?.enrollyear) && (
              <div className="flex items-center gap-2 text-xs">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {locale === "zh" ? "入學年度" : "Enrolled"}:
                </span>
                <span>{previewData?.basic.enrollyear || basicInfo?.enrollyear}</span>
              </div>
            )}

            {(previewData?.basic.term_count || basicInfo?.term_count) && (
              <div className="flex items-center gap-2 text-xs">
                <Award className="h-4 w-4 text-muted-foreground" />
                <span className="text-muted-foreground">
                  {locale === "zh" ? "在學學期數" : "Terms"}:
                </span>
                <span>{previewData?.basic.term_count || basicInfo?.term_count}</span>
              </div>
            )}
          </div>

          <Separator />

          {/* Term Data - Async Loading */}
          <div className="space-y-2">
            <p className="text-sm font-medium">
              {locale === "zh" ? "近期學期成績" : "Recent Terms"}
            </p>

            {isLoading && (
              <div className="space-y-2">
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
              <div className="space-y-1.5">
                {previewData.recent_terms.map((term, idx) => (
                  <div
                    key={`${term.academic_year}-${term.term}`}
                    className="text-xs bg-muted/50 rounded-md p-2"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium">
                        {term.academic_year}-{term.term === "1" ? (locale === "zh" ? "上" : "1st") : (locale === "zh" ? "下" : "2nd")}
                      </span>
                      <div className="flex items-center gap-2">
                        {term.gpa !== undefined && (
                          <Badge variant="outline" className="text-xs">
                            GPA: {formatGPA(term.gpa)}
                          </Badge>
                        )}
                        {term.credits !== undefined && (
                          <span className="text-muted-foreground">
                            {term.credits} {locale === "zh" ? "學分" : "cr"}
                          </span>
                        )}
                      </div>
                    </div>
                    {term.rank !== undefined && (
                      <p className="text-muted-foreground mt-1">
                        {locale === "zh" ? "排名" : "Rank"}: {term.rank}
                      </p>
                    )}
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
