"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Search, Eye, Edit, CheckCircle, Users, FileText } from "lucide-react"
import apiClient from "@/lib/api"
import { User } from "@/types/user"

interface ProfessorInterfaceProps {
  user: User
}

export function ProfessorInterface({ user }: ProfessorInterfaceProps) {
  const [studentApplications, setStudentApplications] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [selectedStudent, setSelectedStudent] = useState<any>(null)
  const [recommendation, setRecommendation] = useState("")
  const [selectedAwards, setSelectedAwards] = useState<string[]>([])

  // Fetch applications for professor review
  useEffect(() => {
    const fetchApplications = async () => {
      setLoading(true)
      setError(null)
      try {
        // This endpoint may need to be adjusted if a dedicated professor review list exists
        const res = await apiClient.request<any>(
          "/applications/review/list?status=pending_recommendation"
        )
        setStudentApplications(res.data || [])
      } catch (e: any) {
        setError(e.message || "Failed to load applications")
      } finally {
        setLoading(false)
      }
    }
    fetchApplications()
  }, [])

  const getStatusColor = (status: string) => {
    const statusMap = {
      pending_recommendation: "destructive",
      recommended: "default",
      under_review: "outline",
      approved: "default",
      rejected: "secondary",
    }
    return statusMap[status as keyof typeof statusMap] || "secondary"
  }

  const handleRecommend = async (appId: number) => {
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      await apiClient.applications.submitRecommendation(
        appId,
        "professor_recommendation",
        recommendation,
        selectedAwards
      )
      setSuccess("Recommendation submitted!")
      setRecommendation("")
      setSelectedAwards([])
      // Optionally refetch applications
      // ...
    } catch (e: any) {
      setError(e.message || "Failed to submit recommendation")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">指導學生管理</h2>
          <p className="text-muted-foreground">管理指導學生的獎學金申請與推薦</p>
        </div>
      </div>

      {/* 統計卡片 */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">指導學生</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">8</div>
            <p className="text-xs text-muted-foreground">博士班學生</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">待推薦申請</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {studentApplications.filter((app) => app.needsRecommendation).length}
            </div>
            <p className="text-xs text-muted-foreground">需要處理</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">已推薦申請</CardTitle>
            <CheckCircle className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {studentApplications.filter((app) => !app.needsRecommendation).length}
            </div>
            <p className="text-xs text-muted-foreground">本月完成</p>
          </CardContent>
        </Card>
      </div>

      {/* 搜尋列 */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="搜尋學生姓名或學號..." className="pl-8" />
        </div>
      </div>

      {/* 學生申請列表 */}
      <Card>
        <CardHeader>
          <CardTitle>指導學生獎學金申請</CardTitle>
          <CardDescription>管理您指導學生的獎學金申請與推薦</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>學生</TableHead>
                <TableHead>獎學金類型</TableHead>
                <TableHead>研究主題</TableHead>
                <TableHead>GPA</TableHead>
                <TableHead>狀態</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {studentApplications.map((app) => (
                <TableRow key={app.id}>
                  <TableCell>
                    <div>
                      <p className="font-medium">{app.studentName}</p>
                      <p className="text-sm text-muted-foreground">{app.studentId}</p>
                    </div>
                  </TableCell>
                  <TableCell>{app.typeName}</TableCell>
                  <TableCell className="max-w-xs">
                    <p className="truncate" title={app.researchTopic}>
                      {app.researchTopic}
                    </p>
                  </TableCell>
                  <TableCell>{app.gpa}</TableCell>
                  <TableCell>
                    <Badge variant={getStatusColor(app.status) as any}>{app.statusName}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button variant="outline" size="sm" onClick={() => setSelectedStudent(app)}>
                            <Eye className="h-4 w-4" />
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="max-w-2xl">
                          <DialogHeader>
                            <DialogTitle>學生申請詳情 - {selectedStudent?.id}</DialogTitle>
                            <DialogDescription>
                              {selectedStudent?.studentName} ({selectedStudent?.studentId})
                            </DialogDescription>
                          </DialogHeader>
                          {selectedStudent && (
                            <div className="space-y-4">
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <label className="text-sm font-medium">獎學金類型</label>
                                  <p>{selectedStudent.typeName}</p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium">申請金額</label>
                                  <p>NT$ {selectedStudent.amount.toLocaleString()}</p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium">GPA</label>
                                  <p>{selectedStudent.gpa}</p>
                                </div>
                                <div>
                                  <label className="text-sm font-medium">提交日期</label>
                                  <p>{selectedStudent.submittedAt}</p>
                                </div>
                              </div>

                              <div>
                                <label className="text-sm font-medium">研究主題</label>
                                <p className="mt-1">{selectedStudent.researchTopic}</p>
                              </div>

                              {selectedStudent.needsRecommendation && (
                                <div>
                                  <label className="text-sm font-medium">選擇可申請獎學金組合</label>
                                  <div className="flex flex-col gap-2 mt-2">
                                    <label className="flex items-center gap-2">
                                      <input
                                        type="checkbox"
                                        value="phd"
                                        checked={selectedAwards.includes("phd")}
                                        onChange={(e) => {
                                          if (e.target.checked) setSelectedAwards([...selectedAwards, "phd"])
                                          else setSelectedAwards(selectedAwards.filter(a => a !== "phd"))
                                        }}
                                      />
                                      國科會博士生獎學金
                                    </label>
                                    <label className="flex items-center gap-2">
                                      <input
                                        type="checkbox"
                                        value="phd_moe_1"
                                        checked={selectedAwards.includes("phd_moe_1")}
                                        onChange={e => {
                                          if (e.target.checked) setSelectedAwards([...selectedAwards, "phd_moe_1"])
                                          else setSelectedAwards(selectedAwards.filter(a => a !== "phd_moe_1"))
                                        }}
                                      />
                                      教育部博士生獎學金+1萬
                                    </label>
                                    <label className="flex items-center gap-2">
                                      <input
                                        type="checkbox"
                                        value="phd_moe_2"
                                        checked={selectedAwards.includes("phd_moe_2")}
                                        onChange={e => {
                                          if (e.target.checked) setSelectedAwards([...selectedAwards, "phd_moe_2"])
                                          else setSelectedAwards(selectedAwards.filter(a => a !== "phd_moe_2"))
                                        }}
                                      />
                                      教育部博士生獎學金+2萬
                                    </label>
                                  </div>
                                </div>
                              )}

                              {selectedStudent.needsRecommendation && (
                                <div className="flex gap-2">
                                  <Button
                                    onClick={() => handleRecommend(selectedStudent.id)}
                                    disabled={loading}
                                  >
                                    <CheckCircle className="h-4 w-4 mr-1" />
                                    {loading ? "Submitting..." : "提交推薦"}
                                  </Button>
                                </div>
                              )}
                            </div>
                          )}
                        </DialogContent>
                      </Dialog>

                      {app.needsRecommendation && (
                        <Button size="sm" onClick={() => handleRecommend(app.id)}>
                          <Edit className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
