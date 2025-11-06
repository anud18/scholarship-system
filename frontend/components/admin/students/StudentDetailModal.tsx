"use client";

import { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";
import type { Student, StudentSISData } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCircle, Loader2, User, GraduationCap, Mail, Phone } from "lucide-react";

interface StudentDetailModalProps {
  student: Student;
  open: boolean;
  onClose: () => void;
}

export function StudentDetailModal({ student, open, onClose }: StudentDetailModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sisData, setSisData] = useState<StudentSISData | null>(null);

  useEffect(() => {
    if (open && student.id) {
      fetchSISData();
    }
  }, [open, student.id]);

  const fetchSISData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Use apiClient instead of direct fetch
      const response = await apiClient.students.getSISData(student.id);

      if (response.success && response.data) {
        setSisData(response.data);
      } else {
        // Handle specific error messages
        const message = response.message || "取得學生詳細資料失敗";
        if (message.includes("not found")) {
          setError("無法從 SIS 系統取得學生資料");
        } else if (message.includes("unavailable") || message.includes("503")) {
          setError("SIS 系統暫時無法連線");
        } else {
          setError(message);
        }
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : "網絡錯誤";
      setError(errorMsg);
      console.error("Error fetching SIS data:", err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return "未登入";
    return new Date(dateString).toLocaleString("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const getDegreeLabel = (degree?: string) => {
    const degreeMap: Record<string, string> = {
      "1": "博士",
      "2": "碩士",
      "3": "學士",
    };
    return degree ? degreeMap[degree] || degree : "未知";
  };

  return (
    <Dialog open={open} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            學生詳細資訊
          </DialogTitle>
        </DialogHeader>

        <Tabs defaultValue="basic" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="basic">基本資訊</TabsTrigger>
            <TabsTrigger value="academic">學籍資料</TabsTrigger>
          </TabsList>

          {/* Basic Info Tab */}
          <TabsContent value="basic" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>用戶資訊</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">學號</p>
                    <p className="text-lg font-mono">{student.nycu_id}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">姓名</p>
                    <p className="text-lg">{student.name}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">信箱</p>
                    <p className="text-sm">{student.email}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">狀態</p>
                    <div className="mt-1">
                      <Badge variant={student.status === "在學" ? "default" : "secondary"}>
                        {student.status || "未知"}
                      </Badge>
                    </div>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">系所</p>
                    <p>{student.dept_name || "未設定"}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">系所代碼</p>
                    <p className="font-mono">{student.dept_code || "未設定"}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">註冊時間</p>
                    <p className="text-sm">{formatDate(student.created_at)}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">最後登入</p>
                    <p className="text-sm">{formatDate(student.last_login_at)}</p>
                  </div>
                </div>

                {student.comment && (
                  <>
                    <Separator className="my-3" />
                    <div>
                      <p className="text-sm font-medium text-muted-foreground">備註</p>
                      <p className="text-sm mt-1">{student.comment}</p>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Academic Info Tab */}
          <TabsContent value="academic" className="space-y-4">
            {loading ? (
              <Card>
                <CardContent className="flex items-center justify-center py-8">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  <span className="ml-2 text-muted-foreground">載入學籍資料中...</span>
                </CardContent>
              </Card>
            ) : error ? (
              <Card className="border-yellow-500">
                <CardContent className="flex items-start gap-3 pt-6">
                  <AlertCircle className="h-5 w-5 text-yellow-500 mt-0.5" />
                  <div>
                    <p className="font-medium text-yellow-700">{error}</p>
                    <p className="text-sm text-muted-foreground mt-1">
                      無法取得即時學籍資料,可能是 SIS API 未啟用或學生資料不存在。
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : sisData ? (
              <>
                {/* Basic Academic Info */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <GraduationCap className="h-5 w-5" />
                      基本學籍資料
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">中文姓名</p>
                        <p className="text-lg">{sisData.basic_info.std_cname || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">英文姓名</p>
                        <p className="text-lg">{sisData.basic_info.std_ename || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">學位</p>
                        <p>{getDegreeLabel(sisData.basic_info.std_degree)}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">在學狀態</p>
                        <p>{sisData.basic_info.std_studingstatus || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">性別</p>
                        <p>{sisData.basic_info.std_sex || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">學院</p>
                        <p>{sisData.basic_info.std_aca_cname || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">系所</p>
                        <p>{sisData.basic_info.std_depname || "N/A"}</p>
                      </div>
                      <div>
                        <p className="text-sm font-medium text-muted-foreground">系所代碼</p>
                        <p className="font-mono">{sisData.basic_info.std_depno || "N/A"}</p>
                      </div>
                    </div>

                    <Separator className="my-3" />

                    <div className="space-y-2">
                      <p className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                        <Phone className="h-4 w-4" />
                        聯絡資訊
                      </p>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-xs text-muted-foreground">手機號碼</p>
                          <p className="text-sm">{sisData.basic_info.com_cellphone || "未提供"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">電子郵件</p>
                          <p className="text-sm">{sisData.basic_info.com_email || "未提供"}</p>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Semester Data */}
                {sisData.semesters && sisData.semesters.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>學期成績</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {sisData.semesters.map((semester, index) => (
                          <div
                            key={index}
                            className="p-3 border rounded-lg space-y-2"
                          >
                            <div className="flex items-center justify-between">
                              <p className="font-medium">
                                {semester.academic_year || semester.trm_year} 學年度 第{" "}
                                {semester.term || semester.trm_term} 學期
                              </p>
                              <Badge variant="outline">
                                GPA: {semester.trm_ascore_gpa?.toFixed(2) || "N/A"}
                              </Badge>
                            </div>
                            <div className="grid grid-cols-3 gap-2 text-sm">
                              <div>
                                <span className="text-muted-foreground">學院：</span>
                                {semester.trm_academyname || "N/A"}
                              </div>
                              <div>
                                <span className="text-muted-foreground">系所：</span>
                                {semester.trm_depname || "N/A"}
                              </div>
                              <div>
                                <span className="text-muted-foreground">總學分：</span>
                                {semester.trm_totalcredits || "N/A"}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : null}
          </TabsContent>
        </Tabs>

        <div className="flex justify-end">
          <Button variant="outline" onClick={onClose}>
            關閉
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
