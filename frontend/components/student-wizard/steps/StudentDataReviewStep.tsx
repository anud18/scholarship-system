"use client";

import React, { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  User,
  Building2,
  Mail,
  GraduationCap,
  Calendar,
  BookOpen,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { useStudentProfile } from "@/hooks/use-student-profile";

interface StudentDataReviewStepProps {
  onNext: () => void;
  onBack: () => void;
  onConfirm: (confirmed: boolean) => void;
  locale: "zh" | "en";
}

export function StudentDataReviewStep({
  onNext,
  onBack,
  onConfirm,
  locale,
}: StudentDataReviewStepProps) {
  const [confirmed, setConfirmed] = useState(false);

  // Use SWR hook for student profile data
  const { userInfo, studentInfo, isLoading, error, refresh } =
    useStudentProfile();

  const t = {
    zh: {
      title: "確認學籍資料",
      subtitle: "請確認以下資料是否正確，這些資料來自學校資料庫",
      basicInfo: "基本資料",
      academicInfo: "學籍資訊",
      name: "姓名",
      studentId: "學號",
      email: "電子郵件",
      department: "系所",
      deptCode: "系所代碼",
      userType: "身份別",
      status: "狀態",
      role: "系統角色",
      degree: "學位",
      enrollmentStatus: "在學狀態",
      enrollmentYear: "入學年度學期",
      semesterCount: "學期數",
      nationality: "國籍",
      identity: "身分",
      dataNotice: "資料說明",
      dataNoticeContent:
        "以上資料來自學校資料庫，若發現資料有誤，請聯繫教務處註冊組更新。",
      confirmButton: "確認資料無誤，繼續",
      backButton: "返回上一步",
      loading: "正在載入學籍資料...",
      loadError: "載入資料時發生錯誤",
      retry: "重新載入",
      student: "學生",
      employee: "職員",
      reference_data: {
        degrees: {
          博士: "博士",
          碩士: "碩士",
          學士: "學士",
        } as Record<string, string>,
        studying_status: {
          在學: "在學",
          應畢: "應畢",
          延畢: "延畢",
          休學: "休學",
          期中退學: "期中退學",
          期末退學: "期末退學",
          開除學籍: "開除學籍",
          死亡: "死亡",
          保留學籍: "保留學籍",
          放棄入學: "放棄入學",
          畢業: "畢業",
        } as Record<string, string>,
        identity: {
          一般生: "一般生",
          原住民: "原住民",
          "僑生(目前有中華民國國籍生)": "僑生(目前有中華民國國籍生)",
          "外籍生(目前有中華民國國籍生)": "外籍生(目前有中華民國國籍生)",
          外交子女: "外交子女",
          身心障礙生: "身心障礙生",
          運動成績優良甄試學生: "運動成績優良甄試學生",
          離島: "離島",
          退伍軍人: "退伍軍人",
          一般公費生: "一般公費生",
          原住民公費生: "原住民公費生",
          離島公費生: "離島公費生",
          退伍軍人公費生: "退伍軍人公費生",
          願景計畫生: "願景計畫生",
          陸生: "陸生",
          其他: "其他",
        } as Record<string, string>,
      },
    },
    en: {
      title: "Verify Student Data",
      subtitle:
        "Please verify the following information from the university database",
      basicInfo: "Basic Information",
      academicInfo: "Academic Information",
      name: "Name",
      studentId: "Student ID",
      email: "Email",
      department: "Department",
      deptCode: "Department Code",
      userType: "User Type",
      status: "Status",
      role: "System Role",
      degree: "Degree",
      enrollmentStatus: "Enrollment Status",
      enrollmentYear: "Enrollment Year & Semester",
      semesterCount: "Semester Count",
      nationality: "Nationality",
      identity: "Identity",
      dataNotice: "Data Notice",
      dataNoticeContent:
        "The above information is from the university database. If you find any errors, please contact the Office of the Registrar.",
      confirmButton: "Confirm and Continue",
      backButton: "Back",
      loading: "Loading student data...",
      loadError: "Error loading data",
      retry: "Retry",
      student: "Student",
      employee: "Employee",
      reference_data: {
        degrees: {
          博士: "Doctoral",
          碩士: "Master's",
          學士: "Bachelor's",
        } as Record<string, string>,
        studying_status: {
          在學: "Enrolled",
          應畢: "Pending Graduation",
          延畢: "Extended Study",
          休學: "On Leave",
          期中退學: "Withdrawn (Mid-term)",
          期末退學: "Withdrawn (End of Term)",
          開除學籍: "Expelled",
          死亡: "Deceased",
          保留學籍: "Enrollment Reserved",
          放棄入學: "Enrollment Forfeited",
          畢業: "Graduated",
        } as Record<string, string>,
        identity: {
          一般生: "Regular Student",
          原住民: "Indigenous Student",
          "僑生(目前有中華民國國籍生)":
            "Overseas Chinese Student (Currently holds R.O.C. nationality)",
          "外籍生(目前有中華民國國籍生)":
            "Foreign Student (Currently holds R.O.C. nationality)",
          外交子女: "Diplomat's Child",
          身心障礙生: "Student with Disability",
          運動成績優良甄試學生:
            "Outstanding Athletic Performance Admission Student",
          離島: "Outlying Islands Student",
          退伍軍人: "Veteran",
          一般公費生: "Regular Government-Funded Student",
          原住民公費生: "Indigenous Government-Funded Student",
          離島公費生: "Outlying Islands Government-Funded Student",
          退伍軍人公費生: "Veteran Government-Funded Student",
          願景計畫生: "Vision Project Student",
          陸生: "Mainland Chinese Student",
          其他: "Other",
        } as Record<string, string>,
      },
    },
  };

  const text = t[locale];

  // Numeric code -> canonical zh key (lookup happens via t[locale].reference_data)
  const degreeCodeToKey: Record<string, string> = {
    "1": "博士",
    "2": "碩士",
    "3": "學士",
  };

  const studyingStatusCodeToKey: Record<string, string> = {
    "1": "在學",
    "2": "應畢",
    "3": "延畢",
    "4": "休學",
    "5": "期中退學",
    "6": "期末退學",
    "7": "開除學籍",
    "8": "死亡",
    "9": "保留學籍",
    "10": "放棄入學",
    "11": "畢業",
  };

  const identityCodeToKey: Record<string, string> = {
    "1": "一般生",
    "2": "原住民",
    "3": "僑生(目前有中華民國國籍生)",
    "4": "外籍生(目前有中華民國國籍生)",
    "5": "外交子女",
    "6": "身心障礙生",
    "7": "運動成績優良甄試學生",
    "8": "離島",
    "9": "退伍軍人",
    "10": "一般公費生",
    "11": "原住民公費生",
    "12": "離島公費生",
    "13": "退伍軍人公費生",
    "14": "願景計畫生",
    "17": "陸生",
    "30": "其他",
  };

  const lookupDegree = (code: string | number): string => {
    const key = degreeCodeToKey[String(code)];
    if (key) return text.reference_data.degrees[key] || key;
    return String(code);
  };

  const lookupStudyingStatus = (code: string | number): string => {
    const key = studyingStatusCodeToKey[String(code)];
    if (key) return text.reference_data.studying_status[key] || key;
    return String(code);
  };

  const lookupIdentity = (code: string | number): string => {
    const key = identityCodeToKey[String(code)];
    if (key) return text.reference_data.identity[key] || key;
    return String(code);
  };

  const handleConfirm = () => {
    setConfirmed(true);
    onConfirm(true);
    onNext();
  };

  // Loading state
  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-lg text-gray-600">{text.loading}</p>
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (error) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 text-red-500" />
          <p className="text-lg text-red-600 mb-4">{text.loadError}</p>
          <p className="text-sm text-gray-600 mb-6">{error.message}</p>
          <Button onClick={() => refresh()}>{text.retry}</Button>
        </CardContent>
      </Card>
    );
  }

  // No data state (shouldn't happen if no error)
  if (!userInfo) {
    return null;
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-lg">
              <User className="h-6 w-6 text-green-600" />
            </div>
            <div>
              <CardTitle className="text-2xl">{text.title}</CardTitle>
              <CardDescription className="mt-1">
                {text.subtitle}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Basic Information */}
          <div>
            <div className="flex items-center gap-2 mb-4">
              <User className="h-5 w-5 text-nycu-blue-600" />
              <h3 className="text-lg font-semibold text-nycu-navy-800">
                {text.basicInfo}
              </h3>
            </div>
            <Card className="bg-gray-50">
              <CardContent className="p-6">
                <div className="grid md:grid-cols-2 gap-6">
                  {/* Name */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-600">
                      {text.name}
                    </label>
                    <div className="flex items-center gap-2">
                      <div className="text-base font-semibold text-nycu-navy-800">
                        {userInfo.name || "-"}
                      </div>
                    </div>
                  </div>

                  {/* Student ID */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-600">
                      {text.studentId}
                    </label>
                    <div className="flex items-center gap-2">
                      <div className="text-base font-semibold text-nycu-navy-800">
                        {userInfo.nycu_id || "-"}
                      </div>
                    </div>
                  </div>

                  {/* Email */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-600">
                      {text.email}
                    </label>
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-gray-500" />
                      <div className="text-base text-gray-700">
                        {userInfo.email || "-"}
                      </div>
                    </div>
                  </div>

                  {/* Department */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-600">
                      {text.department}
                    </label>
                    <div className="flex items-center gap-2">
                      <Building2 className="h-4 w-4 text-gray-500" />
                      <div className="text-base text-gray-700">
                        {userInfo.dept_name || "-"}
                      </div>
                    </div>
                  </div>

                  {/* User Type */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-600">
                      {text.userType}
                    </label>
                    <p>
                      <Badge
                        variant={
                          userInfo.user_type === "student"
                            ? "default"
                            : "secondary"
                        }
                      >
                        {userInfo.user_type === "student"
                          ? text.student
                          : text.employee}
                      </Badge>
                    </p>
                  </div>

                  {/* Status */}
                  <div className="space-y-2">
                    <label className="text-sm font-medium text-gray-600">
                      {text.status}
                    </label>
                    <p>
                      <Badge variant="outline">{userInfo.status || "-"}</Badge>
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Academic Information - Only for students */}
          {studentInfo && (
            <>
              <Separator />
              <div>
                <div className="flex items-center gap-2 mb-4">
                  <GraduationCap className="h-5 w-5 text-nycu-blue-600" />
                  <h3 className="text-lg font-semibold text-nycu-navy-800">
                    {text.academicInfo}
                  </h3>
                </div>
                <Card className="bg-blue-50/30">
                  <CardContent className="p-6">
                    <div className="grid md:grid-cols-2 gap-6">
                      {/* Degree */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.degree}
                        </label>
                        <div className="flex items-center gap-2">
                          <BookOpen className="h-4 w-4 text-gray-500" />
                          <div className="text-base text-gray-700">
                            {studentInfo.std_degree
                              ? lookupDegree(studentInfo.std_degree)
                              : "-"}
                          </div>
                        </div>
                      </div>

                      {/* Enrollment Status */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.enrollmentStatus}
                        </label>
                        <div className="text-base font-semibold text-green-700">
                          {studentInfo.std_studingstatus
                            ? lookupStudyingStatus(
                                studentInfo.std_studingstatus
                              )
                            : "-"}
                        </div>
                      </div>

                      {/* Enrollment Year */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.enrollmentYear}
                        </label>
                        <div className="flex items-center gap-2">
                          <Calendar className="h-4 w-4 text-gray-500" />
                          <div className="text-base text-gray-700">
                            {studentInfo.std_enrollyear
                              ? locale === "zh"
                                ? `${studentInfo.std_enrollyear} 學年度第 ${studentInfo.std_enrollterm || "?"} 學期`
                                : `Year ${studentInfo.std_enrollyear}, Semester ${studentInfo.std_enrollterm || "?"}`
                              : "-"}
                          </div>
                        </div>
                      </div>

                      {/* Semester Count */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.semesterCount}
                        </label>
                        <div className="text-base text-gray-700">
                          {studentInfo.std_termcount || "-"}
                        </div>
                      </div>

                      {/* Nationality */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.nationality}
                        </label>
                        <div className="text-base text-gray-700">
                          {studentInfo.std_nation || "-"}
                        </div>
                      </div>

                      {/* Identity */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.identity}
                        </label>
                        <div className="text-base text-gray-700">
                          {studentInfo.std_identity
                            ? lookupIdentity(studentInfo.std_identity)
                            : "-"}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}

          {/* Data Notice */}
          <Alert className="border-blue-200 bg-blue-50">
            <AlertCircle className="h-5 w-5 text-blue-600" />
            <AlertDescription>
              <div className="font-semibold text-blue-900 mb-1">
                {text.dataNotice}
              </div>
              <div className="text-sm text-blue-800">
                {text.dataNoticeContent}
              </div>
            </AlertDescription>
          </Alert>

          {/* Action buttons */}
          <div className="flex justify-between pt-4">
            <Button variant="outline" onClick={onBack} size="lg">
              <ChevronLeft className="h-5 w-5 mr-2" />
              {text.backButton}
            </Button>
            <Button
              onClick={handleConfirm}
              size="lg"
              className="nycu-gradient text-white px-8"
            >
              <CheckCircle className="h-5 w-5 mr-2" />
              {text.confirmButton}
              <ChevronRight className="h-5 w-5 ml-2" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
