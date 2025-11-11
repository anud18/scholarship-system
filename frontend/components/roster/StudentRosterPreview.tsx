"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Users, DollarSign, Building2, InfoIcon } from "lucide-react"
import { apiClient } from "@/lib/api"

interface StudentInfo {
  application_id: number
  student_name: string
  student_id: string
  student_id_number: string
  email: string
  college: string
  department: string
  grade: string
  sub_type: string
  amount: number
  rank_position: number | null
  is_allocated: boolean
  backup_info: any[]
}

interface PreviewData {
  has_matrix_distribution: boolean
  ranking_id: number | null
  allocated_students: StudentInfo[]
  summary: {
    total_allocated: number
    total_amount: number
    by_college: Record<string, { allocated: number; total_amount: number }>
  }
}

interface StudentRosterPreviewProps {
  configId: number
  rankingId?: number | null
}

export function StudentRosterPreview({ configId, rankingId }: StudentRosterPreviewProps) {
  const [data, setData] = useState<PreviewData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedCollege, setSelectedCollege] = useState<string>("")

  useEffect(() => {
    loadStudentData()
  }, [configId, rankingId])

  const loadStudentData = async () => {
    setLoading(true)
    setError(null)

    try {
      const params: any = { config_id: configId }
      if (rankingId) {
        params.ranking_id = rankingId
      }

      const response = await apiClient.request("/payment-rosters/preview-students", {
        method: "GET",
        params,
      })

      if (response.success && response.data) {
        setData(response.data)

        // Set default selected college
        if (response.data.has_matrix_distribution) {
          const colleges = Object.keys(response.data.summary.by_college)
          if (colleges.length > 0) {
            setSelectedCollege(colleges[0])
          }
        }
      } else {
        setError("無法載入學生資料")
      }
    } catch (err) {
      console.error("Failed to load student data:", err)
      setError("載入學生資料時發生錯誤")
    } finally {
      setLoading(false)
    }
  }

  const getStudentsByCollege = (college: string): StudentInfo[] => {
    if (!data) return []
    return data.allocated_students.filter((s) => s.college === college)
  }

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("zh-TW", {
      style: "currency",
      currency: "TWD",
      minimumFractionDigits: 0,
    }).format(amount)
  }

  const renderStudentTable = (students: StudentInfo[]) => {
    if (students.length === 0) {
      return (
        <div className="text-center py-12 text-muted-foreground">
          此學院無正取學生
        </div>
      )
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[80px]">排名</TableHead>
            <TableHead>姓名</TableHead>
            <TableHead>學號</TableHead>
            <TableHead>身分證字號</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>系所</TableHead>
            <TableHead>年級</TableHead>
            <TableHead>獎學金子類型</TableHead>
            <TableHead className="text-right">金額</TableHead>
            <TableHead>狀態</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {students.map((student) => (
            <TableRow key={student.application_id}>
              <TableCell className="font-medium">
                {student.rank_position ?? "-"}
              </TableCell>
              <TableCell>{student.student_name}</TableCell>
              <TableCell>{student.student_id}</TableCell>
              <TableCell className="font-mono text-sm">
                {student.student_id_number}
              </TableCell>
              <TableCell className="text-sm">{student.email}</TableCell>
              <TableCell>{student.department}</TableCell>
              <TableCell>{student.grade}</TableCell>
              <TableCell>
                <Badge variant="outline">{student.sub_type || "一般"}</Badge>
              </TableCell>
              <TableCell className="text-right font-medium">
                {formatCurrency(student.amount)}
              </TableCell>
              <TableCell>
                <Badge variant="default">正取</Badge>
                {student.backup_info && student.backup_info.length > 0 && (
                  <Badge variant="secondary" className="ml-1">
                    +{student.backup_info.length}候補
                  </Badge>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-gray-900 mx-auto"></div>
          <p className="mt-4 text-muted-foreground">載入學生名單中...</p>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-12">
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    )
  }

  if (!data || data.allocated_students.length === 0) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <InfoIcon className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
          <p className="text-muted-foreground">
            目前沒有預計分發的學生
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">預計分發人數</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{data.summary.total_allocated}</div>
            <p className="text-xs text-muted-foreground">正取學生總數</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">預計總金額</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(data.summary.total_amount)}
            </div>
            <p className="text-xs text-muted-foreground">所有學生金額總計</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">分配模式</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {data.has_matrix_distribution ? "學院分配" : "統一分配"}
            </div>
            <p className="text-xs text-muted-foreground">
              {data.has_matrix_distribution
                ? `${Object.keys(data.summary.by_college).length} 個學院`
                : "所有學院統一處理"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Student List */}
      <Card>
        <CardHeader>
          <CardTitle>預計分發學生名單</CardTitle>
        </CardHeader>
        <CardContent>
          {data.has_matrix_distribution ? (
            <Tabs value={selectedCollege} onValueChange={setSelectedCollege}>
              <TabsList className="grid w-full" style={{ gridTemplateColumns: `repeat(${Object.keys(data.summary.by_college).length}, 1fr)` }}>
                {Object.entries(data.summary.by_college).map(([college, stats]) => (
                  <TabsTrigger key={college} value={college} className="flex items-center gap-2">
                    <span>{college}</span>
                    <Badge variant="secondary" className="ml-1">
                      {stats.allocated}
                    </Badge>
                  </TabsTrigger>
                ))}
              </TabsList>

              {Object.keys(data.summary.by_college).map((college) => (
                <TabsContent key={college} value={college} className="mt-4">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold">{college} 學院</h3>
                      <p className="text-sm text-muted-foreground">
                        共 {data.summary.by_college[college].allocated} 位學生，
                        總金額 {formatCurrency(data.summary.by_college[college].total_amount)}
                      </p>
                    </div>
                  </div>
                  {renderStudentTable(getStudentsByCollege(college))}
                </TabsContent>
              ))}
            </Tabs>
          ) : (
            <>
              <div className="mb-4">
                <Alert>
                  <InfoIcon className="h-4 w-4" />
                  <AlertDescription>
                    此獎學金配置未啟用 Matrix 分配，顯示所有已核准的申請
                  </AlertDescription>
                </Alert>
              </div>
              {renderStudentTable(data.allocated_students)}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
