"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { NationalityFlag } from "@/components/nationality-flag"
import { getTranslation } from "@/lib/i18n"
import { Search, Eye, CheckCircle, XCircle, Grid, List, Download, GraduationCap, Clock, Calendar, School, AlertCircle, Loader2 } from "lucide-react"
import { useCollegeApplications } from "@/hooks/use-admin"
import { User } from "@/types/user"

interface CollegeDashboardProps {
  user: User
  locale?: "zh" | "en"
}

export function CollegeDashboard({ user, locale = "zh" }: CollegeDashboardProps) {
  const t = (key: string) => getTranslation(locale, key)
  const { applications, isLoading, error, updateApplicationStatus } = useCollegeApplications()

  const [viewMode, setViewMode] = useState<"card" | "table">("card")
  const [selectedApplication, setSelectedApplication] = useState<any>(null)

  const getStatusColor = (status: string) => {
    const statusMap = {
      pending_review: "destructive",
      under_review: "outline", 
      approved: "default",
      rejected: "secondary",
      submitted: "outline",
    }
    return statusMap[status as keyof typeof statusMap] || "secondary"
  }

  const getStatusName = (status: string) => {
    const statusMap = {
      draft: locale === "zh" ? "草稿" : "Draft",
      submitted: locale === "zh" ? "待學院審核" : "Pending College Review",
      under_review: locale === "zh" ? "學院審核中" : "Under College Review",
      approved: locale === "zh" ? "已核准" : "Approved",
      rejected: locale === "zh" ? "已駁回" : "Rejected",
      withdrawn: locale === "zh" ? "已撤回" : "Withdrawn",
    }
    return statusMap[status as keyof typeof statusMap] || status
  }

  const handleApprove = async (appId: number) => {
    try {
      await updateApplicationStatus(appId, 'approved', '學院核准通過')
      console.log(`College approved application ${appId}`)
    } catch (error) {
      console.error('Failed to approve application:', error)
    }
  }

  const handleReject = async (appId: number) => {
    try {
      await updateApplicationStatus(appId, 'rejected', '學院駁回申請')
      console.log(`College rejected application ${appId}`)
    } catch (error) {
      console.error('Failed to reject application:', error)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-nycu-navy-600">載入學院審核資料中...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-6">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-red-600" />
          <p className="text-red-700">載入資料時發生錯誤：{error}</p>
        </div>
      </div>
    )
  }

  if (applications.length === 0) {
    return (
      <div className="text-center py-8">
        <School className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
        <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
          {locale === "zh" ? "暫無待審核申請" : "No Applications Pending Review"}
        </h3>
        <p className="text-nycu-navy-600">
          {locale === "zh" ? "目前沒有需要學院審核的申請案件" : "No applications currently require college review"}
        </p>
      </div>
    )
  }

  const renderCardView = () => (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {applications.map((app) => (
        <Card key={app.id} className="relative">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CardTitle className="text-lg">{app.student_id}</CardTitle>
              </div>
              <Badge variant="outline">
                {locale === "zh" ? "學院審核" : "College Review"}
              </Badge>
            </div>
            <CardDescription>{app.scholarship_type}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <p className="font-medium">{app.scholarship_type}</p>
              <p className="text-sm text-muted-foreground">
                {locale === "zh" ? "申請編號" : "Application ID"}: {app.app_id || `APP-${app.id}`}
              </p>
            </div>

            <div className="flex items-center justify-between text-sm">
              <span>
                {locale === "zh" ? "狀態" : "Status"}: {getStatusName(app.status)}
              </span>
              <span>
                {locale === "zh" ? "申請時間" : "Submitted"}: {new Date(app.created_at).toLocaleDateString()}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <Badge variant={getStatusColor(app.status) as any}>{getStatusName(app.status)}</Badge>
            </div>

            <div className="flex gap-2 pt-2">
              <Dialog>
                <DialogTrigger asChild>
                  <Button variant="outline" size="sm" onClick={() => setSelectedApplication(app)}>
                    <Eye className="h-4 w-4 mr-1" />
                    {locale === "zh" ? "查看" : "View"}
                  </Button>
                </DialogTrigger>
                <DialogContent className="max-w-2xl">
                  <DialogHeader>
                    <DialogTitle>
                      {locale === "zh" ? "學院審核" : "College Review"} - {selectedApplication?.app_id || `APP-${selectedApplication?.id}`}
                    </DialogTitle>
                    <DialogDescription>
                      {selectedApplication && (
                        <span className="flex items-center gap-2">
                          <span>{selectedApplication.student_id}</span>
                          <span>({selectedApplication.scholarship_type})</span>
                        </span>
                      )}
                    </DialogDescription>
                  </DialogHeader>
                  {selectedApplication && (
                    <div className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="text-sm font-medium">
                            {locale === "zh" ? "獎學金類型" : "Scholarship Type"}
                          </label>
                          <p className="text-sm">{selectedApplication.scholarship_type}</p>
                        </div>
                        <div>
                          <label className="text-sm font-medium">
                            {locale === "zh" ? "申請狀態" : "Status"}
                          </label>
                          <p className="text-sm">{getStatusName(selectedApplication.status)}</p>
                        </div>
                      </div>

                      <div>
                        <label className="text-sm font-medium">
                          {locale === "zh" ? "學院審核意見" : "College Review Comments"}
                        </label>
                        <Textarea
                          placeholder={locale === "zh" ? "請輸入學院審核意見..." : "Enter college review comments..."}
                          className="mt-1"
                        />
                      </div>

                      <div className="flex gap-2 pt-4">
                        <Button onClick={() => handleApprove(selectedApplication.id)} className="flex-1">
                          <CheckCircle className="h-4 w-4 mr-1" />
                          {locale === "zh" ? "學院核准" : "College Approve"}
                        </Button>
                        <Button variant="destructive" onClick={() => handleReject(selectedApplication.id)} className="flex-1">
                          <XCircle className="h-4 w-4 mr-1" />
                          {locale === "zh" ? "學院駁回" : "College Reject"}
                        </Button>
                      </div>
                    </div>
                  )}
                </DialogContent>
              </Dialog>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            {locale === "zh" ? "學院審核管理" : "College Review Management"}
          </h2>
          <p className="text-muted-foreground">
            {locale === "zh" ? "學院層級的獎學金申請審核" : "College-level scholarship application reviews"}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4 mr-1" />
            {locale === "zh" ? "匯出" : "Export"}
          </Button>
          <div className="flex items-center border rounded-md">
            <Button
              variant={viewMode === "card" ? "default" : "ghost"}
              size="sm"
              onClick={() => setViewMode("card")}
            >
              <Grid className="h-4 w-4" />
            </Button>
            <Button
              variant={viewMode === "table" ? "default" : "ghost"}
              size="sm"
              onClick={() => setViewMode("table")}
            >
              <List className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Statistics */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "待審核" : "Pending Review"}
            </CardTitle>
            <GraduationCap className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {applications.filter((app) => app.status === "submitted").length}
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh" ? "需要學院審核" : "Requires college review"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "審核中" : "Under Review"}
            </CardTitle>
            <Eye className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {applications.filter((app) => app.status === "under_review").length}
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh" ? "學院審核中" : "College reviewing"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "平均等待天數" : "Avg Wait Days"}
            </CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {applications.length > 0 
                ? Math.round(applications.reduce((sum, app) => sum + (app.days_waiting || 0), 0) / applications.length)
                : 0
              }
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh" ? "天" : "days"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              {locale === "zh" ? "總金額" : "Total Amount"}
            </CardTitle>
            <XCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              NT$ {applications.reduce((sum, app) => sum + (app.amount || 0), 0).toLocaleString()}
            </div>
            <p className="text-xs text-muted-foreground">
              {locale === "zh" ? "申請金額" : "Application amount"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder={locale === "zh" ? "搜尋學生或學號..." : "Search student or ID..."} className="pl-8" />
        </div>
        <Select defaultValue="all">
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{locale === "zh" ? "全部狀態" : "All Status"}</SelectItem>
            <SelectItem value="pending">{locale === "zh" ? "待審核" : "Pending"}</SelectItem>
            <SelectItem value="under_review">{locale === "zh" ? "審核中" : "Under Review"}</SelectItem>
            <SelectItem value="approved">{locale === "zh" ? "已核准" : "Approved"}</SelectItem>
            <SelectItem value="rejected">{locale === "zh" ? "已駁回" : "Rejected"}</SelectItem>
          </SelectContent>
        </Select>
        <Select defaultValue="all">
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{locale === "zh" ? "全部學系" : "All Departments"}</SelectItem>
            <SelectItem value="cs">{locale === "zh" ? "資訊工程" : "Computer Science"}</SelectItem>
            <SelectItem value="ee">{locale === "zh" ? "電機工程" : "Electrical Engineering"}</SelectItem>
            <SelectItem value="bio">{locale === "zh" ? "生物科技" : "Biotechnology"}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Applications View */}
      {viewMode === "card" ? renderCardView() : (
        <Card>
          <CardHeader>
            <CardTitle>{locale === "zh" ? "申請清單" : "Applications List"}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{locale === "zh" ? "學生" : "Student"}</TableHead>
                  <TableHead>{locale === "zh" ? "學系" : "Department"}</TableHead>
                  <TableHead>{locale === "zh" ? "獎學金類型" : "Scholarship Type"}</TableHead>
                  <TableHead>GPA</TableHead>
                  <TableHead>{locale === "zh" ? "金額" : "Amount"}</TableHead>
                  <TableHead>{locale === "zh" ? "狀態" : "Status"}</TableHead>
                  <TableHead>{locale === "zh" ? "等待天數" : "Wait Days"}</TableHead>
                  <TableHead>{locale === "zh" ? "操作" : "Actions"}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {applications.map((app) => (
                  <TableRow key={app.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {app.student_id}
                        </span>
                        <NationalityFlag 
                          countryCode={app.nationality || "OTHER"} 
                          locale={locale} 
                          showLabel={false} 
                        />
                        <span className="text-sm text-muted-foreground">({app.student_id})</span>
                      </div>
                    </TableCell>
                    <TableCell>{app.department || "N/A"}</TableCell>
                    <TableCell>{app.scholarship_type}</TableCell>
                    <TableCell>{app.gpa || "N/A"}</TableCell>
                    <TableCell>NT$ {(app.amount || 0).toLocaleString()}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusColor(app.status) as any}>{getStatusName(app.status)}</Badge>
                    </TableCell>
                    <TableCell>{app.days_waiting || 0} {locale === "zh" ? "天" : "days"}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="outline" size="sm">
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="sm">
                          <CheckCircle className="h-4 w-4" />
                        </Button>
                        <Button variant="outline" size="sm">
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
      )}
    </div>
  )
} 