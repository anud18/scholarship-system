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
import { useReferenceData, getAcademyName, getDepartmentName } from "@/hooks/use-reference-data"
import { useScholarshipData } from "@/hooks/use-scholarship-data"
import { StudentValidationDetail } from "./StudentValidationDetail"

interface StudentInfo {
  application_id: number
  student_name: string
  student_id: string
  student_id_number: string
  email: string
  college: string
  department: string
  term_count: number | string
  sub_type: string
  amount: number
  rank_position: number | null
  backup_info: any[]
  // Validation fields
  is_included: boolean
  exclusion_reason: string | null
  verification_status: string
  verification_message: string | null
  has_fresh_data: boolean
  is_eligible: boolean
  failed_rules: string[]
  warning_rules: string[]
  has_bank_account: boolean
  bank_account_field: string | null
}

interface PreviewData {
  has_matrix_distribution: boolean
  ranking_id: number | null
  students: StudentInfo[]
  summary: {
    total_students: number
    included_count: number
    excluded_count: number
    exclusion_breakdown: {
      missing_data: number
      verification_failed: number
      rules_failed: number
      no_bank_account: number
    }
    total_amount: number
    verification_stats: {
      verified: number
      api_errors: number
      not_verified: number
    }
    by_college: Record<string, { included: number; excluded: number; total_amount: number }>
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

  // Fetch reference data for translations
  const { academies, departments, isLoading: refLoading } = useReferenceData()
  const { subTypeTranslations, isLoading: subTypeLoading } = useScholarshipData()

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
      // Try to extract error message from different error sources
      let errorMessage = "載入學生資料時發生錯誤"

      if (err instanceof Error) {
        errorMessage = err.message
      } else if (typeof err === "object" && err !== null) {
        if ("detail" in err) {
          errorMessage = (err as any).detail
        } else if ("message" in err) {
          errorMessage = (err as any).message
        }
      }

      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  const getStudentsByCollege = (college: string): StudentInfo[] => {
    if (!data) return []
    // Filter by college and only show included students
    return data.students.filter((s) => s.college === college && s.is_included)
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
            <TableHead className="w-[80px] whitespace-nowrap">排名</TableHead>
            <TableHead className="whitespace-nowrap">姓名</TableHead>
            <TableHead className="whitespace-nowrap">學號</TableHead>
            <TableHead className="whitespace-nowrap">身分證字號</TableHead>
            <TableHead className="whitespace-nowrap">Email</TableHead>
            <TableHead className="whitespace-nowrap">系所</TableHead>
            <TableHead className="whitespace-nowrap">在學學期數</TableHead>
            <TableHead className="whitespace-nowrap">獎學金子類型</TableHead>
            <TableHead className="whitespace-nowrap">狀態</TableHead>
            <TableHead className="text-right whitespace-nowrap">金額</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {students.map((student) => (
            <TableRow key={student.application_id}>
              <TableCell className="font-medium whitespace-nowrap">
                {student.rank_position ?? "-"}
              </TableCell>
              <TableCell className="whitespace-nowrap">{student.student_name}</TableCell>
              <TableCell className="whitespace-nowrap">{student.student_id}</TableCell>
              <TableCell className="font-mono text-sm whitespace-nowrap">
                {student.student_id_number}
              </TableCell>
              <TableCell className="text-sm whitespace-nowrap">{student.email}</TableCell>
              <TableCell className="whitespace-nowrap">{getDepartmentName(student.department, departments)}</TableCell>
              <TableCell className="whitespace-nowrap">{student.term_count}</TableCell>
              <TableCell className="whitespace-nowrap">
                <Badge variant="outline">
                  {student.sub_type
                    ? (subTypeTranslations.zh[student.sub_type] || student.sub_type)
                    : "一般"}
                </Badge>
              </TableCell>
              <TableCell className="min-w-[200px]">
                <StudentValidationDetail student={student} />
                {student.backup_info && student.backup_info.length > 0 && (
                  <Badge variant="secondary" className="mt-2">
                    +{student.backup_info.length}候補
                  </Badge>
                )}
              </TableCell>
              <TableCell className="text-right font-medium whitespace-nowrap">
                {formatCurrency(student.amount)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  }

  const renderExcludedStudentTable = (students: StudentInfo[]) => {
    if (students.length === 0) {
      return (
        <div className="text-center py-12 text-muted-foreground">
          沒有被排除的學生
        </div>
      )
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="whitespace-nowrap">姓名</TableHead>
            <TableHead className="whitespace-nowrap">學號</TableHead>
            <TableHead className="whitespace-nowrap">Email</TableHead>
            <TableHead className="whitespace-nowrap">學院</TableHead>
            <TableHead className="whitespace-nowrap">系所</TableHead>
            <TableHead className="whitespace-nowrap">獎學金子類型</TableHead>
            <TableHead className="min-w-[300px]">排除原因與詳細資訊</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {students.map((student) => (
            <TableRow key={student.application_id}>
              <TableCell className="whitespace-nowrap">{student.student_name}</TableCell>
              <TableCell className="whitespace-nowrap">{student.student_id}</TableCell>
              <TableCell className="text-sm whitespace-nowrap">{student.email}</TableCell>
              <TableCell className="whitespace-nowrap">{getAcademyName(student.college, academies)}</TableCell>
              <TableCell className="whitespace-nowrap">
                {getDepartmentName(student.department, departments)}
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <Badge variant="outline">
                  {student.sub_type
                    ? (subTypeTranslations.zh[student.sub_type] || student.sub_type)
                    : "一般"}
                </Badge>
              </TableCell>
              <TableCell className="min-w-[300px]">
                <StudentValidationDetail student={student} />
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

  if (!data || data.students.length === 0) {
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
            <div className="text-2xl font-bold">{data.summary.included_count}</div>
            <p className="text-xs text-muted-foreground">
              {data.summary.excluded_count > 0
                ? `符合條件學生（排除 ${data.summary.excluded_count} 位）`
                : "符合條件學生總數"}
            </p>
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
              {data.has_matrix_distribution ? "矩陣分配" : "統一分配"}
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
              <TabsList className="grid w-full" style={{ gridTemplateColumns: `repeat(${Object.keys(data.summary.by_college).length + 1}, 1fr)` }}>
                {Object.entries(data.summary.by_college).map(([college, stats]) => (
                  <TabsTrigger key={college} value={college} className="flex items-center gap-2">
                    <span>{getAcademyName(college, academies)}</span>
                    <Badge variant="secondary" className="ml-1">
                      {stats.included}
                    </Badge>
                  </TabsTrigger>
                ))}
                {data.summary.excluded_count > 0 && (
                  <TabsTrigger value="excluded" className="flex items-center gap-2">
                    <span>已排除學生</span>
                    <Badge variant="destructive" className="ml-1">
                      {data.summary.excluded_count}
                    </Badge>
                  </TabsTrigger>
                )}
              </TabsList>

              {Object.keys(data.summary.by_college).map((college) => (
                <TabsContent key={college} value={college} className="mt-4">
                  <div className="mb-4 flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-semibold">{getAcademyName(college, academies)}</h3>
                      <p className="text-sm text-muted-foreground">
                        符合條件 {data.summary.by_college[college].included} 位學生
                        {data.summary.by_college[college].excluded > 0 && (
                          <span className="text-orange-600">
                            {" "}（排除 {data.summary.by_college[college].excluded} 位）
                          </span>
                        )}
                        ，總金額 {formatCurrency(data.summary.by_college[college].total_amount)}
                      </p>
                    </div>
                  </div>
                  {renderStudentTable(getStudentsByCollege(college))}
                </TabsContent>
              ))}

              {/* Excluded Students Tab */}
              {data.summary.excluded_count > 0 && (
                <TabsContent value="excluded" className="mt-4">
                  <div className="mb-4">
                    <h3 className="text-lg font-semibold">已排除學生</h3>
                    <p className="text-sm text-muted-foreground mb-3">
                      共 {data.summary.excluded_count} 位學生被排除
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <div className="p-2 bg-gray-50 rounded border">
                        <div className="text-xs text-gray-600">缺少資料</div>
                        <div className="text-lg font-semibold">{data.summary.exclusion_breakdown.missing_data}</div>
                      </div>
                      <div className="p-2 bg-gray-50 rounded border">
                        <div className="text-xs text-gray-600">驗證失敗</div>
                        <div className="text-lg font-semibold">{data.summary.exclusion_breakdown.verification_failed}</div>
                      </div>
                      <div className="p-2 bg-gray-50 rounded border">
                        <div className="text-xs text-gray-600">規則失敗</div>
                        <div className="text-lg font-semibold">{data.summary.exclusion_breakdown.rules_failed}</div>
                      </div>
                      <div className="p-2 bg-gray-50 rounded border">
                        <div className="text-xs text-gray-600">無銀行帳戶</div>
                        <div className="text-lg font-semibold">{data.summary.exclusion_breakdown.no_bank_account}</div>
                      </div>
                    </div>
                  </div>
                  {renderExcludedStudentTable(data.students.filter(s => !s.is_included))}
                </TabsContent>
              )}
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
              {renderStudentTable(data.students.filter((s) => s.is_included))}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
