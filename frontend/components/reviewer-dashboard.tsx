"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { NationalityFlag } from "@/components/nationality-flag";
import { getTranslation } from "@/lib/i18n";
import {
  Search,
  Eye,
  CheckCircle,
  XCircle,
  Grid,
  List,
  Download,
} from "lucide-react";

interface User {
  id: string;
  name: string;
  email: string;
  role: string;
}

interface ReviewerDashboardProps {
  user: User;
  locale?: "zh" | "en";
}

export function ReviewerDashboard({
  user,
  locale = "zh",
}: ReviewerDashboardProps) {
  const t = (key: string) => getTranslation(locale, key);

  const [viewMode, setViewMode] = useState<"card" | "table">("card");
  const [selectedApplication, setSelectedApplication] = useState<any>(null);

  const [applications] = useState([
    {
      id: "APP-2025-000198",
      studentName: "張小明",
      studentNameEn: "Chang, Xiao-Ming",
      studentId: "B10901001",
      nationality: "TWN",
      type: "undergraduate_freshman",
      typeName: t("scholarships.undergraduate_freshman"),
      status: "pending_review",
      statusName: t("status.pending_review"),
      submittedAt: "2025-06-01",
      gpa: 3.91,
      amount: 50000,
      priority: "high",
      daysWaiting: 3,
    },
    {
      id: "APP-2025-000199",
      studentName: "李小華",
      studentNameEn: "Lee, Xiao-Hua",
      studentId: "B10901002",
      nationality: "USA",
      type: "phd",
      typeName: t("scholarships.phd"),
      status: "pending_review",
      statusName: t("status.pending_review"),
      submittedAt: "2025-06-02",
      gpa: 3.75,
      amount: 120000,
      priority: "medium",
      daysWaiting: 2,
    },
    {
      id: "APP-2025-000200",
      studentName: "王小美",
      studentNameEn: "Wang, Xiao-Mei",
      studentId: "D10901001",
      nationality: "JPN",
      type: "direct_phd",
      typeName: t("scholarships.direct_phd"),
      status: "under_review",
      statusName: t("status.under_review"),
      submittedAt: "2025-05-28",
      gpa: 3.88,
      amount: 150000,
      priority: "high",
      daysWaiting: 7,
    },
  ]);

  const getStatusColor = (status: string) => {
    const statusMap = {
      pending_review: "destructive",
      under_review: "outline",
      approved: "default",
      partial_approved: "outline",
      rejected: "secondary",
    };
    return statusMap[status as keyof typeof statusMap] || "secondary";
  };

  const getPriorityColor = (priority: string) => {
    const priorityMap = {
      high: "destructive",
      medium: "outline",
      low: "secondary",
    };
    return priorityMap[priority as keyof typeof priorityMap] || "secondary";
  };

  const handleApprove = (appId: string) => {
    console.log(`Approving application ${appId}`);
  };

  const handleReject = (appId: string) => {
    console.log(`Rejecting application ${appId}`);
  };

  const renderCardView = () => (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {applications.map(app => (
        <Card key={app.id} className="relative">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-lg">
                  {locale === "zh" ? app.studentName : app.studentNameEn}
                </CardTitle>
                <NationalityFlag
                  countryCode={app.nationality}
                  locale={locale}
                  showLabel={false}
                />
              </div>
              <Badge variant={getPriorityColor(app.priority) as any}>
                {app.priority === "high"
                  ? locale === "zh"
                    ? "高"
                    : "High"
                  : app.priority === "medium"
                    ? locale === "zh"
                      ? "中"
                      : "Med"
                    : locale === "zh"
                      ? "低"
                      : "Low"}
              </Badge>
            </div>
            <CardDescription>{app.studentId}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="font-medium">{app.typeName}</p>
              <p className="text-sm text-muted-foreground">
                {locale === "zh" ? "申請編號" : "Application ID"}: {app.id}
              </p>
            </div>

            <div className="flex items-center justify-between text-sm">
              <span>GPA: {app.gpa}</span>
              <span>
                {locale === "zh" ? "金額" : "Amount"}: NT${" "}
                {app.amount.toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <Badge variant={getStatusColor(app.status) as any}>
                {app.statusName}
              </Badge>
              <span className="text-sm text-muted-foreground">
                {locale === "zh" ? "等待" : "Waiting"} {app.daysWaiting}{" "}
                {locale === "zh" ? "天" : "days"}
              </span>
            </div>

            <div className="flex gap-2 pt-2">
              <Dialog>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setSelectedApplication(app)}
                  >
                    <Eye className="h-4 w-4 mr-1" />
                    {t("form.view")}
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle>
                      {locale === "zh" ? "申請詳情" : "Application Details"} -{" "}
                      {selectedApplication?.id}
                    </DialogTitle>
                    <DialogDescription>
                      {selectedApplication && (
                        <span className="flex items-center gap-2">
                          <span>
                            {locale === "zh"
                              ? selectedApplication.studentName
                              : selectedApplication.studentNameEn}
                          </span>
                          <NationalityFlag
                            countryCode={selectedApplication.nationality}
                            locale={locale}
                            showLabel={true}
                          />
                          <span>({selectedApplication.studentId})</span>
                        </span>
                      )}
                    </DialogDescription>
                  </DialogHeader>
                  {selectedApplication && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-sm font-medium">
                            {locale === "zh"
                              ? "獎學金類型"
                              : "Scholarship Type"}
                          </label>
                          <p>{selectedApplication.typeName}</p>
                        </div>
                        <div>
                          <label className="text-sm font-medium">
                            {locale === "zh" ? "申請金額" : "Amount"}
                          </label>
                          <p>
                            NT$ {selectedApplication.amount.toLocaleString()}
                          </p>
                        </div>
                        <div>
                          <label className="text-sm font-medium">GPA</label>
                          <p>{selectedApplication.gpa}</p>
                        </div>
                        <div>
                          <label className="text-sm font-medium">
                            {locale === "zh" ? "提交日期" : "Submitted Date"}
                          </label>
                          <p>{selectedApplication.submittedAt}</p>
                        </div>
                      </div>

                      <div>
                        <label className="text-sm font-medium">
                          {locale === "zh" ? "審核意見" : "Review Comments"}
                        </label>
                        <Textarea
                          placeholder={
                            locale === "zh"
                              ? "請輸入審核意見..."
                              : "Please enter review comments..."
                          }
                          rows={3}
                        />
                      </div>

                      <div className="flex gap-2">
                        <Button
                          onClick={() => handleApprove(selectedApplication.id)}
                        >
                          <CheckCircle className="h-4 w-4 mr-1" />
                          {t("form.approve")}
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => handleReject(selectedApplication.id)}
                        >
                          <XCircle className="h-4 w-4 mr-1" />
                          {t("form.reject")}
                        </Button>
                      </div>
                    </div>
                  )}
                </DialogContent>
              </Dialog>

              <Button size="sm" onClick={() => handleApprove(app.id)}>
                <CheckCircle className="h-4 w-4 mr-1" />
                {t("form.approve")}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                onClick={() => handleReject(app.id)}
              >
                <XCircle className="h-4 w-4 mr-1" />
                {t("form.reject")}
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );

  const renderTableView = () => (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>
                {locale === "zh" ? "申請編號" : "Application ID"}
              </TableHead>
              <TableHead>{locale === "zh" ? "學生" : "Student"}</TableHead>
              <TableHead>{locale === "zh" ? "國籍" : "Nationality"}</TableHead>
              <TableHead>
                {locale === "zh" ? "獎學金類型" : "Scholarship Type"}
              </TableHead>
              <TableHead>GPA</TableHead>
              <TableHead>{locale === "zh" ? "金額" : "Amount"}</TableHead>
              <TableHead>{locale === "zh" ? "狀態" : "Status"}</TableHead>
              <TableHead>
                {locale === "zh" ? "等待天數" : "Days Waiting"}
              </TableHead>
              <TableHead>{locale === "zh" ? "操作" : "Actions"}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {applications.map(app => (
              <TableRow key={app.id}>
                <TableCell className="font-medium">{app.id}</TableCell>
                <TableCell>
                  <div>
                    <p className="font-medium">
                      {locale === "zh" ? app.studentName : app.studentNameEn}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {app.studentId}
                    </p>
                  </div>
                </TableCell>
                <TableCell>
                  <NationalityFlag
                    countryCode={app.nationality}
                    locale={locale}
                    showLabel={true}
                  />
                </TableCell>
                <TableCell>{app.typeName}</TableCell>
                <TableCell>{app.gpa}</TableCell>
                <TableCell>NT$ {app.amount.toLocaleString()}</TableCell>
                <TableCell>
                  <Badge variant={getStatusColor(app.status) as any}>
                    {app.statusName}
                  </Badge>
                </TableCell>
                <TableCell>
                  {app.daysWaiting} {locale === "zh" ? "天" : "days"}
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button variant="outline" size="sm">
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button size="sm" onClick={() => handleApprove(app.id)}>
                      <CheckCircle className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleReject(app.id)}
                    >
                      <XCircle className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{t("nav.review")}</h2>
          <p className="text-muted-foreground">
            {locale === "zh"
              ? "管理獎學金申請的審核流程"
              : "Manage scholarship application review process"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <Download className="h-4 w-4 mr-1" />
            {locale === "zh" ? "匯出報告" : "Export Report"}
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="relative">
            <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder={
                locale === "zh"
                  ? "搜尋申請編號或學生姓名..."
                  : "Search application ID or student name..."
              }
              className="pl-8 w-64"
            />
          </div>
          <Select defaultValue="all">
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                {locale === "zh" ? "全部狀態" : "All Status"}
              </SelectItem>
              <SelectItem value="pending">
                {t("status.pending_review")}
              </SelectItem>
              <SelectItem value="under_review">
                {t("status.under_review")}
              </SelectItem>
              <SelectItem value="approved">{t("status.approved")}</SelectItem>
              <SelectItem value="rejected">{t("status.rejected")}</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant={viewMode === "card" ? "default" : "outline"}
            size="sm"
            onClick={() => setViewMode("card")}
          >
            <Grid className="h-4 w-4" />
          </Button>
          <Button
            variant={viewMode === "table" ? "default" : "outline"}
            size="sm"
            onClick={() => setViewMode("table")}
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {viewMode === "card" ? renderCardView() : renderTableView()}
    </div>
  );
}
