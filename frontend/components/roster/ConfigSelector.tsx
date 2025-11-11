"use client"

import { useState, useEffect } from "react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Card, CardContent } from "@/components/ui/card"
import { Search, Loader2 } from "lucide-react"
import { api } from "@/lib/api"

interface ScholarshipConfiguration {
  id: number
  config_name: string
  config_code: string
  academic_year: number
  semester?: string
  scholarship_type: {
    id: number
    name: string
  }
  is_active: boolean
}

interface ConfigSelectorProps {
  onConfigSelect: (configId: number, config: ScholarshipConfiguration) => void
  disabled?: boolean
}

export function ConfigSelector({ onConfigSelect, disabled = false }: ConfigSelectorProps) {
  const [academicYears, setAcademicYears] = useState<number[]>([])
  const [selectedYear, setSelectedYear] = useState<string>("")
  const [selectedSemester, setSelectedSemester] = useState<string>("")
  const [configurations, setConfigurations] = useState<ScholarshipConfiguration[]>([])
  const [selectedConfigId, setSelectedConfigId] = useState<string>("")
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingConfigs, setIsLoadingConfigs] = useState(false)

  // Generate academic years (current year and past 5 years)
  useEffect(() => {
    const currentYear = new Date().getFullYear()
    const taiwanYear = currentYear - 1911 // Convert to Taiwan calendar
    const years = Array.from({ length: 6 }, (_, i) => taiwanYear - i)
    setAcademicYears(years)

    // Set default to current year
    setSelectedYear(taiwanYear.toString())
  }, [])

  // Load configurations when year or semester changes
  useEffect(() => {
    if (selectedYear) {
      loadConfigurations()
    }
  }, [selectedYear, selectedSemester])

  const loadConfigurations = async () => {
    setIsLoadingConfigs(true)
    try {
      // Use admin API to get configurations
      const response = await api.admin.getConfigurations()

      if (response.success && response.data) {
        // Filter by selected criteria
        let filtered = response.data

        // Filter by academic year
        if (selectedYear) {
          filtered = filtered.filter((config: any) =>
            config.academic_year === parseInt(selectedYear)
          )
        }

        // Filter by semester
        if (selectedSemester && selectedSemester !== "all") {
          filtered = filtered.filter((config: any) =>
            config.semester === selectedSemester || !config.semester
          )
        }

        // Filter by active status
        filtered = filtered.filter((config: any) => config.is_active !== false)

        setConfigurations(filtered)
      } else {
        setConfigurations([])
      }
    } catch (error) {
      console.error("Failed to load configurations:", error)
      setConfigurations([])
    } finally {
      setIsLoadingConfigs(false)
    }
  }

  const handleSearch = () => {
    if (!selectedConfigId) {
      return
    }

    setIsLoading(true)

    const selectedConfig = configurations.find(c => c.id.toString() === selectedConfigId)
    if (selectedConfig) {
      onConfigSelect(selectedConfig.id, selectedConfig)
    }

    setIsLoading(false)
  }

  const semesterOptions = [
    { value: "all", label: "整學年" },
    { value: "first", label: "上學期" },
    { value: "second", label: "下學期" },
  ]

  return (
    <Card>
      <CardContent className="pt-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          {/* Academic Year */}
          <div className="space-y-2">
            <Label htmlFor="academic-year">學年度</Label>
            <Select
              value={selectedYear}
              onValueChange={setSelectedYear}
              disabled={disabled}
            >
              <SelectTrigger id="academic-year">
                <SelectValue placeholder="選擇學年度" />
              </SelectTrigger>
              <SelectContent>
                {academicYears.map((year) => (
                  <SelectItem key={year} value={year.toString()}>
                    {year} 學年度
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Semester */}
          <div className="space-y-2">
            <Label htmlFor="semester">學期</Label>
            <Select
              value={selectedSemester}
              onValueChange={setSelectedSemester}
              disabled={disabled}
            >
              <SelectTrigger id="semester">
                <SelectValue placeholder="選擇學期" />
              </SelectTrigger>
              <SelectContent>
                {semesterOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Scholarship Configuration */}
          <div className="space-y-2">
            <Label htmlFor="config">獎學金配置</Label>
            <Select
              value={selectedConfigId}
              onValueChange={setSelectedConfigId}
              disabled={disabled || isLoadingConfigs}
            >
              <SelectTrigger id="config">
                <SelectValue placeholder={
                  isLoadingConfigs ? "載入中..." :
                  configurations.length === 0 ? "無可用配置" :
                  "選擇獎學金配置"
                } />
              </SelectTrigger>
              <SelectContent>
                {configurations.map((config) => (
                  <SelectItem key={config.id} value={config.id.toString()}>
                    {config.config_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Search Button */}
          <div>
            <Button
              onClick={handleSearch}
              disabled={!selectedConfigId || isLoading || disabled}
              className="w-full"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  查詢中...
                </>
              ) : (
                <>
                  <Search className="mr-2 h-4 w-4" />
                  查詢
                </>
              )}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
