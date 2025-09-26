"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { NationalityFlag } from "@/components/nationality-flag"
import { CollegeRankingTable } from "@/components/college-ranking-table"
import { SemesterSelector } from "@/components/semester-selector"
import { ScholarshipTypeSelector } from "@/components/ui/scholarship-type-selector"
import { getTranslation } from "@/lib/i18n"
import { Search, Eye, CheckCircle, XCircle, Grid, List, Download, GraduationCap, Clock, Calendar, School, AlertCircle, Loader2, Trophy, Users, Award, Send, Plus, RefreshCw } from "lucide-react"
import { useCollegeApplications } from "@/hooks/use-admin"
import { User } from "@/types/user"
import { apiClient } from "@/lib/api"

interface CollegeDashboardProps {
  user: User
  locale?: "zh" | "en"
}

interface ScholarshipConfig {
  id: number
  name: string
  code?: string
  subTypes: { code: string; name: string }[]
}

interface AcademicConfig {
  currentYear: number
  currentSemester: 'FIRST' | 'SECOND'
  availableYears: number[]
}

interface RankingData {
  applications: any[]
  totalQuota: number
  subTypeCode: string
  academicYear: number
  semester?: string
  isFinalized: boolean
}

export function CollegeDashboard({ user, locale = "zh" }: CollegeDashboardProps) {
  const t = (key: string) => getTranslation(locale, key)
  const { applications, isLoading, error, updateApplicationStatus, fetchCollegeApplications } = useCollegeApplications()

  // Configuration fetch functions
  const getAcademicConfig = async (): Promise<AcademicConfig> => {
    if (academicConfig) return academicConfig

    // Calculate current academic year (ROC system)
    const currentDate = new Date()
    const currentYear = currentDate.getFullYear() - 1911
    const currentMonth = currentDate.getMonth() + 1

    // Determine semester based on month (Aug-Jan = FIRST, Feb-July = SECOND)
    const currentSemester: 'FIRST' | 'SECOND' = currentMonth >= 8 || currentMonth <= 1 ? 'FIRST' : 'SECOND'

    const config: AcademicConfig = {
      currentYear,
      currentSemester,
      availableYears: [currentYear - 1, currentYear, currentYear + 1]
    }

    setAcademicConfig(config)
    return config
  }

  const getScholarshipConfig = async (): Promise<ScholarshipConfig[]> => {
    if (scholarshipConfig.length > 0) return scholarshipConfig

    try {
      // Ensure availableOptions is loaded first
      let currentAvailableOptions = availableOptions
      if (!currentAvailableOptions) {
        console.log('Available options not loaded yet, fetching now...')
        await fetchAvailableOptions()
        currentAvailableOptions = availableOptions
      }

      // If still not available after fetching, throw error
      if (!currentAvailableOptions?.scholarship_types) {
        throw new Error('Unable to load available scholarship options from college API')
      }

      // Fetch all scholarships to get the actual IDs that we need for creating rankings
      console.log('Fetching all scholarships to get IDs...')
      const allScholarshipsResponse = await apiClient.scholarships.getAll()

      if (allScholarshipsResponse.success && allScholarshipsResponse.data) {
        console.log('All scholarships:', allScholarshipsResponse.data)
        console.log('Available scholarship types from college:', currentAvailableOptions.scholarship_types)

        // Map college scholarship types to full scholarship data with IDs
        const configs: ScholarshipConfig[] = []

        for (const collegeType of currentAvailableOptions.scholarship_types) {
          // Find the matching scholarship by code
          const fullScholarship = allScholarshipsResponse.data.find((scholarship: any) =>
            scholarship.code === collegeType.code ||
            scholarship.name === collegeType.name ||
            scholarship.name_en === collegeType.name
          )

          if (fullScholarship) {
            configs.push({
              id: fullScholarship.id,
              name: collegeType.name,
              code: collegeType.code,
              subTypes: [{ code: 'default', name: 'Default' }] // Use default sub-type
            })
          } else {
            console.warn(`Could not find full scholarship data for college type: ${collegeType.code} - ${collegeType.name}`)
          }
        }

        console.log('Mapped scholarship configs:', configs)
        setScholarshipConfig(configs)
        return configs
      }

      // If no data available, throw error instead of using fallback data
      throw new Error('Failed to retrieve scholarship data from API')

    } catch (error) {
      console.error('Failed to fetch scholarship configuration:', error)
      throw new Error(`Failed to retrieve scholarship configuration: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  const [viewMode, setViewMode] = useState<"card" | "table">("card")
  const [selectedApplication, setSelectedApplication] = useState<any>(null)
  const [activeTab, setActiveTab] = useState("review")
  const [activeScholarshipTab, setActiveScholarshipTab] = useState<string>() // 獎學金類型選擇 tab
  const [rankingData, setRankingData] = useState<RankingData | null>(null)
  const [rankings, setRankings] = useState<any[]>([])
  const [selectedRanking, setSelectedRanking] = useState<number | null>(null)
  const [isRankingLoading, setIsRankingLoading] = useState(false)
  const [scholarshipConfig, setScholarshipConfig] = useState<ScholarshipConfig[]>([])
  const [academicConfig, setAcademicConfig] = useState<AcademicConfig | null>(null)

  // 學期選擇相關狀態
  const [selectedAcademicYear, setSelectedAcademicYear] = useState<number>()
  const [selectedSemester, setSelectedSemester] = useState<string>()
  const [selectedCombination, setSelectedCombination] = useState<string>()
  const [selectedScholarshipType, setSelectedScholarshipType] = useState<string>()

  // 可用選項狀態
  const [availableOptions, setAvailableOptions] = useState<{
    scholarship_types: Array<{ code: string; name: string; name_en?: string }>;
    academic_years: number[];
    semesters: string[];
  } | null>(null)

  // Fetch rankings and configuration on component mount
  useEffect(() => {
    const initializeData = async () => {
      await getAcademicConfig()
      await fetchAvailableOptions()
      await fetchRankings()
      await getScholarshipConfig()
    }
    initializeData()
  }, [])

  const fetchAvailableOptions = async () => {
    try {
      const response = await apiClient.college.getAvailableCombinations()
      if (response.success && response.data) {
        setAvailableOptions(response.data)

        // 取得當前學期資訊
        const currentConfig = await getAcademicConfig()
        const currentCombination = `${currentConfig.currentYear}-${currentConfig.currentSemester}`

        // 檢查當前學期組合是否存在於可用選項中
        const hasCurrentCombination = response.data.academic_years?.includes(currentConfig.currentYear) &&
          response.data.semesters?.includes(currentConfig.currentSemester)

        // 檢查是否有學年制獎學金（YEARLY 選項）
        const hasYearlyOption = response.data.semesters?.includes('YEARLY')

        // 設定預設學期組合
        if (hasCurrentCombination && !selectedCombination) {
          setSelectedCombination(currentCombination)
          setSelectedAcademicYear(currentConfig.currentYear)
          setSelectedSemester(currentConfig.currentSemester)
        } else if (hasYearlyOption && !selectedCombination && response.data.academic_years?.length > 0) {
          // 如果有學年制獎學金，優先選擇當前年度的全年選項
          const yearlyYear = response.data.academic_years.includes(currentConfig.currentYear)
            ? currentConfig.currentYear
            : response.data.academic_years[0]
          const yearlyCombination = `${yearlyYear}-YEARLY`
          setSelectedCombination(yearlyCombination)
          setSelectedAcademicYear(yearlyYear)
          setSelectedSemester('YEARLY')
        } else if (!selectedCombination && response.data.academic_years?.length > 0 && response.data.semesters?.length > 0) {
          // 否則設定第一個可用的學期
          const firstYear = response.data.academic_years[0]
          const firstSemester = response.data.semesters[0]
          const fallbackCombination = `${firstYear}-${firstSemester}`
          setSelectedCombination(fallbackCombination)
          setSelectedAcademicYear(firstYear)
          setSelectedSemester(firstSemester)
        }

        // 設定第一個獎學金類型為預設 tab
        if (response.data.scholarship_types && response.data.scholarship_types.length > 0 && !activeScholarshipTab) {
          const firstType = response.data.scholarship_types[0].code
          setActiveScholarshipTab(firstType)

          // 使用已設定的學期載入申請資料
          let useYear, useSemester
          if (hasCurrentCombination) {
            useYear = currentConfig.currentYear
            useSemester = currentConfig.currentSemester
          } else if (hasYearlyOption) {
            useYear = response.data.academic_years.includes(currentConfig.currentYear)
              ? currentConfig.currentYear
              : response.data.academic_years[0]
            useSemester = 'YEARLY'
          } else {
            useYear = response.data.academic_years?.[0] || undefined
            useSemester = response.data.semesters?.[0] || undefined
          }

          fetchCollegeApplications(useYear, useSemester, firstType)
        }
      } else {
        console.error('Failed to fetch available options:', response.message)
        throw new Error(`Failed to retrieve available options: ${response.message}`)
      }
    } catch (error) {
      console.error('Failed to fetch available options:', error)
      throw new Error(`Failed to retrieve available options from database: ${error instanceof Error ? error.message : 'Unknown error'}`)
    }
  }

  const fetchRankings = async () => {
    try {
      console.log('Fetching rankings...')
      const response = await apiClient.college.getRankings()
      if (response.success && response.data) {
        console.log(`Fetched ${response.data.length} rankings:`, response.data)
        setRankings(response.data)
      } else {
        console.warn('No rankings found or error:', response.message)
        setRankings([])
      }
    } catch (error) {
      console.error('Failed to fetch rankings:', error)
      setRankings([])
    }
  }

  const fetchRankingDetails = async (rankingId: number) => {
    setIsRankingLoading(true)
    try {
      const response = await apiClient.college.getRanking(rankingId)
      if (response.success && response.data) {
        // Transform the API response to match the expected format for CollegeRankingTable
        const transformedApplications = (response.data.items || []).map((item: any) => ({
          id: item.application?.id || item.id,
          app_id: item.application?.app_id || `APP-${item.id}`,
          student_name: item.student_name || '未提供姓名',
          student_id: item.student_id || 'N/A',
          scholarship_type: item.application?.scholarship_type || item.scholarship_type || '',
          sub_type: item.application?.sub_type || item.sub_type || '',
          total_score: item.total_score || 0,
          rank_position: item.rank_position || 0,
          is_allocated: item.is_allocated || false,
          status: item.status || 'pending',
          review_status: item.application?.status || 'pending'
        }))

        setRankingData({
          applications: transformedApplications,
          totalQuota: response.data.total_quota,
          subTypeCode: response.data.sub_type_code,
          academicYear: response.data.academic_year,
          semester: response.data.semester,
          isFinalized: response.data.is_finalized
        })

        console.log(`Loaded ranking ${rankingId} with ${transformedApplications.length} applications`)
      } else {
        console.error('Failed to load ranking details:', response.message)
        // Clear ranking data on failure
        setRankingData(null)
      }
    } catch (error) {
      console.error('Failed to fetch ranking details:', error)
      // Clear ranking data on error
      setRankingData(null)
    } finally {
      setIsRankingLoading(false)
    }
  }

  const handleRankingChange = (newOrder: any[]) => {
    if (rankingData) {
      setRankingData({
        ...rankingData,
        applications: newOrder
      })
    }
  }

  const handleReviewApplication = async (applicationId: number) => {
    // Handle application review
    console.log('Reviewing application:', applicationId)
  }

  const handleExecuteDistribution = async () => {
    if (selectedRanking) {
      try {
        const response = await apiClient.college.executeDistribution(selectedRanking, {})
        if (response.success) {
          // Refresh ranking data
          await fetchRankingDetails(selectedRanking)
        } else {
          console.error('Failed to execute distribution:', response.message)
        }
      } catch (error) {
        console.error('Failed to execute distribution:', error)
      }
    }
  }

  const handleFinalizeRanking = async () => {
    if (selectedRanking) {
      try {
        const response = await apiClient.college.finalizeRanking(selectedRanking)
        if (response.success) {
          // Refresh rankings list
          await fetchRankings()
          // Update current ranking data
          if (rankingData) {
            setRankingData({
              ...rankingData,
              isFinalized: true
            })
          }
        } else {
          console.error('Failed to finalize ranking:', response.message)
        }
      } catch (error) {
        console.error('Failed to finalize ranking:', error)
      }
    }
  }

  const createNewRanking = async (scholarshipTypeId?: number, subTypeCode?: string) => {
    try {
      // Get academic configuration from API or system settings
      const academicConfig = await getAcademicConfig()
      const scholarshipConfig = await getScholarshipConfig()

      if (!scholarshipTypeId && scholarshipConfig.length === 0) {
        throw new Error("No scholarship types available")
      }

      // Determine the scholarship type to use
      let targetScholarshipId = scholarshipTypeId
      let targetSubTypeCode = subTypeCode

      // If no specific scholarship type provided, find the one matching current tab
      if (!targetScholarshipId && activeScholarshipTab && availableOptions?.scholarship_types) {
        const currentScholarshipType = availableOptions.scholarship_types.find(
          type => type.code === activeScholarshipTab
        )
        if (currentScholarshipType) {
          // Get the scholarship ID from the scholarship config
          const configScholarship = scholarshipConfig.find(
            config => config.name === currentScholarshipType.name
          )
          targetScholarshipId = configScholarship?.id || scholarshipConfig[0]?.id
          targetSubTypeCode = configScholarship?.subTypes[0]?.code || scholarshipConfig[0]?.subTypes[0]?.code
        }
      }

      // Fallback to first scholarship if still not found
      if (!targetScholarshipId) {
        const defaultScholarship = scholarshipConfig[0]
        targetScholarshipId = defaultScholarship?.id
        targetSubTypeCode = defaultScholarship?.subTypes[0]?.code
      }

      // Use selected academic year and semester from the UI state
      const useYear = selectedAcademicYear || academicConfig.currentYear
      const useSemester = selectedSemester || academicConfig.currentSemester

      const semesterName = useSemester === 'FIRST' ? '上學期' :
                          useSemester === 'SECOND' ? '下學期' :
                          useSemester === 'YEARLY' ? '全年' : '學期'

      const newRanking = {
        scholarship_type_id: targetScholarshipId,
        sub_type_code: targetSubTypeCode || 'default',
        academic_year: useYear,
        semester: useSemester,
        ranking_name: `新建排名 - ${useYear}學年度 ${semesterName}`
      }

      const response = await apiClient.college.createRanking(newRanking)
      if (response.success) {
        console.log('Ranking created successfully:', response.data)
        // Refresh rankings
        await fetchRankings()
      } else {
        console.error('Failed to create ranking:', response.message)
        throw new Error(`Failed to create ranking: ${response.message}`)
      }
    } catch (error) {
      console.error('Failed to create ranking:', error)
      throw error
    }
  }

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

  return (
    <div className="space-y-6">
      {/* 獎學金類型選擇 - 最上層 Tab */}
      <Tabs value={activeScholarshipTab || ""} onValueChange={(scholarshipType) => {
        setActiveScholarshipTab(scholarshipType)
        // 切換獎學金類型時重新載入資料
        fetchCollegeApplications(selectedAcademicYear, selectedSemester, scholarshipType)
      }} className="w-full">
        <TabsList className={`grid w-full grid-cols-${Math.min(availableOptions?.scholarship_types?.length || 3, 5)}`}>
          {availableOptions?.scholarship_types?.map((type) => (
            <TabsTrigger key={type.code} value={type.code} className="flex items-center gap-2">
              <Award className="h-4 w-4" />
              {type.name}
            </TabsTrigger>
          ))}
        </TabsList>

        {/* 每個獎學金類型的內容 */}
        {availableOptions?.scholarship_types?.map((scholarshipType) => (
          <TabsContent key={scholarshipType.code} value={scholarshipType.code} className="space-y-6">
            {/* 子 Tab - 申請審核、學生排序、獎學金分發 */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="review" className="flex items-center gap-2">
                  <GraduationCap className="h-4 w-4" />
                  申請審核
                </TabsTrigger>
                <TabsTrigger value="ranking" className="flex items-center gap-2">
                  <Trophy className="h-4 w-4" />
                  學生排序
                </TabsTrigger>
                <TabsTrigger value="distribution" className="flex items-center gap-2">
                  <Award className="h-4 w-4" />
                  獎學金分發
                </TabsTrigger>
              </TabsList>

              {/* 申請審核標籤頁 */}
              <TabsContent value="review" className="space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-3xl font-bold tracking-tight">
                      {locale === "zh" ? "學院審核管理" : "College Review Management"} - {availableOptions?.scholarship_types?.find(type => type.code === scholarshipType.code)?.name || scholarshipType.name}
                    </h2>
                    <p className="text-muted-foreground">
                      {locale === "zh" ? "學院層級的獎學金申請審核" : "College-level scholarship application reviews"}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* 學期學年選擇 - 移到這裡 */}
                    <Select value={selectedCombination || ""} onValueChange={(value) => {
                      setSelectedCombination(value)
                      const [year, semester] = value.split('-')
                      setSelectedAcademicYear(parseInt(year))
                      setSelectedSemester(semester || undefined)
                      // 重新載入該獎學金類型的申請資料
                      fetchCollegeApplications(parseInt(year), semester || undefined, activeScholarshipTab)
                    }}>
                      <SelectTrigger className="w-48">
                        <SelectValue placeholder="選擇學期">
                          <div className="flex items-center">
                            <Calendar className="h-4 w-4 mr-2" />
                            {selectedCombination ?
                              `${selectedCombination.split('-')[0]} ${
                                selectedCombination.split('-')[1] === 'FIRST' ? '上學期' :
                                selectedCombination.split('-')[1] === 'SECOND' ? '下學期' :
                                selectedCombination.split('-')[1] === 'YEARLY' ? '全年' :
                                selectedCombination.split('-')[1]
                              }`
                              : "選擇學期"
                            }
                          </div>
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent>
                        {availableOptions?.academic_years?.map((year) =>
                          availableOptions?.semesters?.map((semester) => (
                            <SelectItem key={`${year}-${semester}`} value={`${year}-${semester}`}>
                              {year} 學年度 {
                                semester === 'FIRST' ? '上學期' :
                                semester === 'SECOND' ? '下學期' :
                                semester === 'YEARLY' ? '全年' : semester
                              }
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>

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
                        {applications.filter((app) => app.status === "recommended" || app.status === "submitted").length}
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
                        {applications.filter((app) => app.status === "under_review" || (app.status === "recommended" && app.college_review_completed)).length}
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
                      <Clock className="h-4 w-4 text-muted-foreground" />
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
                      <Award className="h-4 w-4 text-muted-foreground" />
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

                {applications.length === 0 ? (
                  <div className="text-center py-8">
                    <School className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
                    <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
                      {locale === "zh" ? "暫無待審核申請" : "No Applications Pending Review"}
                    </h3>
                    <p className="text-nycu-navy-600">
                      {locale === "zh" ? "目前沒有需要學院審核的申請案件" : "No applications currently require college review"}
                    </p>
                  </div>
                ) : (
                  <>
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
                    </div>

                    {/* Applications View */}
                    <Card>
                      <CardHeader>
                        <CardTitle>{locale === "zh" ? "申請清單" : "Applications List"}</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>{locale === "zh" ? "學生" : "Student"}</TableHead>
                              <TableHead>{locale === "zh" ? "獎學金類型" : "Scholarship Type"}</TableHead>
                              <TableHead>{locale === "zh" ? "狀態" : "Status"}</TableHead>
                              <TableHead>{locale === "zh" ? "申請時間" : "Applied"}</TableHead>
                              <TableHead>{locale === "zh" ? "操作" : "Actions"}</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {applications.map((app) => (
                              <TableRow key={app.id}>
                                <TableCell>
                                  <div className="flex flex-col gap-1">
                                    <span className="font-medium">
                                      {app.student_name || "未提供姓名"}
                                    </span>
                                    <span className="text-sm text-muted-foreground">
                                      {app.student_id || "未提供學號"}
                                    </span>
                                  </div>
                                </TableCell>
                                <TableCell>
                                  {availableOptions?.scholarship_types?.find(type => type.code === app.scholarship_type)?.name || app.scholarship_type}
                                </TableCell>
                                <TableCell>
                                  <Badge variant={getStatusColor(app.status) as any}>
                                    {getStatusName(app.status)}
                                  </Badge>
                                </TableCell>
                                <TableCell>
                                  {app.created_at ? new Date(app.created_at).toLocaleDateString('zh-TW', {
                                    year: 'numeric',
                                    month: '2-digit',
                                    day: '2-digit'
                                  }) : '未知日期'}
                                </TableCell>
                                <TableCell>
                                  <div className="flex gap-1">
                                    <Dialog>
                                      <DialogTrigger asChild>
                                        <Button variant="outline" size="sm" onClick={() => setSelectedApplication(app)}>
                                          <Eye className="h-4 w-4" />
                                        </Button>
                                      </DialogTrigger>
                                      <DialogContent className="max-w-2xl">
                                        <DialogHeader>
                                          <DialogTitle>學院審核 - {app.app_id || `APP-${app.id}`}</DialogTitle>
                                          <DialogDescription>
                                            {app.student_name || "未提供姓名"} ({app.student_id || "未提供學號"}) - {availableOptions?.scholarship_types?.find(type => type.code === app.scholarship_type)?.name || app.scholarship_type}
                                          </DialogDescription>
                                        </DialogHeader>
                                        {selectedApplication && (
                                          <div className="space-y-4">
                                            <div>
                                              <label className="text-sm font-medium">學院審核意見</label>
                                              <Textarea
                                                placeholder="請輸入學院審核意見..."
                                                className="mt-1"
                                              />
                                            </div>
                                            <div className="flex gap-2 pt-4">
                                              <Button onClick={() => handleApprove(selectedApplication.id)} className="flex-1">
                                                <CheckCircle className="h-4 w-4 mr-1" />
                                                學院核准
                                              </Button>
                                              <Button variant="destructive" onClick={() => handleReject(selectedApplication.id)} className="flex-1">
                                                <XCircle className="h-4 w-4 mr-1" />
                                                學院駁回
                                              </Button>
                                            </div>
                                          </div>
                                        )}
                                      </DialogContent>
                                    </Dialog>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </CardContent>
                    </Card>
                  </>
                )}
              </TabsContent>

              {/* 學生排序標籤頁 */}
              <TabsContent value="ranking" className="space-y-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-3xl font-bold tracking-tight">學生排序管理 - {scholarshipType.name}</h2>
                    <p className="text-muted-foreground">管理獎學金申請的排序和排名</p>
                  </div>
                  <Button onClick={async () => {
                    try {
                      await createNewRanking()
                    } catch (error) {
                      console.error('Failed to create ranking:', error)
                      alert(`無法建立新排名：${error instanceof Error ? error.message : '未知錯誤'}`)
                    }
                  }}>
                    <Plus className="h-4 w-4 mr-2" />
                    建立新排名
                  </Button>
                </div>

                {/* Ranking Selection */}
                <Card>
                  <CardHeader>
                    <CardTitle>選擇排名</CardTitle>
                    <CardDescription>選擇要管理的排名清單</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {rankings.length === 0 ? (
                      <div className="text-center py-12">
                        <Trophy className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
                        <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
                          暫無排名資料
                        </h3>
                        <p className="text-nycu-navy-600 mb-4">
                          {scholarshipType.name} 目前還沒有建立任何排名，請點擊上方「建立新排名」按鈕開始
                        </p>
                        <Button onClick={async () => {
                          try {
                            await createNewRanking()
                          } catch (error) {
                            console.error('Failed to create ranking:', error)
                            alert(`無法建立新排名：${error instanceof Error ? error.message : '未知錯誤'}`)
                          }
                        }} variant="outline">
                          <Plus className="h-4 w-4 mr-2" />
                          立即建立排名
                        </Button>
                      </div>
                    ) : (
                      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {rankings.map((ranking) => (
                          <Card
                            key={ranking.id}
                            className={`cursor-pointer transition-colors ${selectedRanking === ranking.id ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'}`}
                            onClick={() => {
                              setSelectedRanking(ranking.id)
                              fetchRankingDetails(ranking.id)
                            }}
                          >
                            <CardContent className="p-4">
                              <div className="flex items-center justify-between mb-2">
                                <Badge variant={ranking.is_finalized ? "default" : "secondary"}>
                                  {ranking.is_finalized ? "已確認" : "進行中"}
                                </Badge>
                                <Trophy className="h-4 w-4 text-blue-600" />
                              </div>
                              <h3 className="font-medium mb-1">{ranking.ranking_name}</h3>
                              <p className="text-sm text-gray-600">
                                申請數: {ranking.total_applications} | 配額: {ranking.total_quota}
                              </p>
                            </CardContent>
                          </Card>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Ranking Details */}
                {selectedRanking && rankingData && (
                  <div className="space-y-6">
                    {isRankingLoading ? (
                      <div className="flex items-center justify-center p-8">
                        <Loader2 className="h-8 w-8 animate-spin" />
                      </div>
                    ) : (
                      <CollegeRankingTable
                        applications={rankingData.applications}
                        totalQuota={rankingData.totalQuota}
                        subTypeCode={rankingData.subTypeCode}
                        academicYear={rankingData.academicYear}
                        semester={rankingData.semester}
                        isFinalized={rankingData.isFinalized}
                        onRankingChange={handleRankingChange}
                        onReviewApplication={handleReviewApplication}
                        onExecuteDistribution={handleExecuteDistribution}
                        onFinalizeRanking={handleFinalizeRanking}
                        locale={locale}
                      />
                    )}
                  </div>
                )}
              </TabsContent>

              {/* 獎學金分發標籤頁 */}
              <TabsContent value="distribution" className="space-y-6">
                <div>
                  <h2 className="text-3xl font-bold tracking-tight">獎學金分發 - {scholarshipType.name}</h2>
                  <p className="text-muted-foreground">執行獎學金的分配和發放</p>
                </div>

                <div className="grid gap-6 md:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Award className="h-5 w-5" />
                        分發統計
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex justify-between">
                        <span>總申請數</span>
                        <span className="font-semibold">{applications.length}</span>
                      </div>
                      <div className="flex justify-between">
                        <span>可分發配額</span>
                        <span className="font-semibold text-green-600">10</span>
                      </div>
                      <div className="flex justify-between">
                        <span>已分發數量</span>
                        <span className="font-semibold text-blue-600">8</span>
                      </div>
                      <div className="flex justify-between">
                        <span>剩餘配額</span>
                        <span className="font-semibold text-orange-600">2</span>
                      </div>
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Send className="h-5 w-5" />
                        分發操作
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <p className="text-sm text-gray-600">
                        根據已確認的排名執行獎學金分配
                      </p>
                      <div className="space-y-2">
                        <Button
                          className="w-full"
                          onClick={handleExecuteDistribution}
                          disabled={!selectedRanking}
                        >
                          <Send className="h-4 w-4 mr-2" />
                          執行自動分發
                        </Button>
                        <Button
                          variant="outline"
                          className="w-full"
                          onClick={handleFinalizeRanking}
                          disabled={!selectedRanking}
                        >
                          <Trophy className="h-4 w-4 mr-2" />
                          確認排名結果
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Distribution History */}
                <Card>
                  <CardHeader>
                    <CardTitle>分發紀錄</CardTitle>
                    <CardDescription>查看歷史分發紀錄</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>分發批次</TableHead>
                          <TableHead>獎學金類型</TableHead>
                          <TableHead>分發數量</TableHead>
                          <TableHead>執行時間</TableHead>
                          <TableHead>狀態</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        <TableRow>
                          <TableCell>2024-001</TableCell>
                          <TableCell>博士生卓越獎學金</TableCell>
                          <TableCell>8/10</TableCell>
                          <TableCell>2024-01-15 14:30</TableCell>
                          <TableCell>
                            <Badge>已完成</Badge>
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
