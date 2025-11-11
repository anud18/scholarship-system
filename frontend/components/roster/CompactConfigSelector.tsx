"use client"

import { useState, useEffect } from "react"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { api } from "@/lib/api"

interface ScholarshipConfiguration {
  id: number
  config_name: string
  config_code: string
  academic_year: number
  semester?: string | null
  scholarship_type: {
    id: number
    name: string
  }
  is_active: boolean
  quotas?: any
  has_college_quota?: boolean
}

interface ScholarshipType {
  id: number
  code: string
  name: string
}

interface PeriodOption {
  key: string
  label: string
  academic_year: number
  semester: string | null
}

interface CompactConfigSelectorProps {
  onConfigSelect: (configId: number, config: ScholarshipConfiguration) => void
  disabled?: boolean
}

export function CompactConfigSelector({ onConfigSelect, disabled = false }: CompactConfigSelectorProps) {
  const [scholarshipTypes, setScholarshipTypes] = useState<ScholarshipType[]>([])
  const [selectedTypeId, setSelectedTypeId] = useState<string>("")

  const [configurations, setConfigurations] = useState<ScholarshipConfiguration[]>([])
  const [periodOptions, setPeriodOptions] = useState<PeriodOption[]>([])
  const [selectedPeriod, setSelectedPeriod] = useState<string>("")

  const [isLoadingTypes, setIsLoadingTypes] = useState(false)
  const [isLoadingPeriods, setIsLoadingPeriods] = useState(false)

  // Load scholarship types on mount
  useEffect(() => {
    loadScholarshipTypes()
  }, [])

  // Load periods when type changes
  useEffect(() => {
    if (selectedTypeId) {
      setSelectedPeriod("")
      setPeriodOptions([])
      loadPeriodsForType(parseInt(selectedTypeId))
    } else {
      setConfigurations([])
      setPeriodOptions([])
      setSelectedPeriod("")
    }
  }, [selectedTypeId])

  // Load config when period is selected (auto or manual)
  useEffect(() => {
    if (selectedPeriod) {
      const [yearStr, semester] = selectedPeriod.split(":")
      const year = parseInt(yearStr)
      const semesterValue = semester === "null" ? null : semester

      const matchingConfig = configurations.find(
        config => config.academic_year === year && config.semester === semesterValue
      )

      if (matchingConfig) {
        onConfigSelect(matchingConfig.id, matchingConfig)
      }
    }
  }, [selectedPeriod, configurations])

  const loadScholarshipTypes = async () => {
    setIsLoadingTypes(true)
    try {
      // Get all scholarship configurations to extract scholarship types
      const response = await api.admin.getScholarshipConfigurations({
        is_active: true
      })

      if (response.success && response.data) {
        // Extract unique scholarship types from configurations
        const typesMap = new Map<number, ScholarshipType>()

        response.data.forEach((config: any) => {
          if (config.scholarship_type_id && config.scholarship_type_name) {
            typesMap.set(config.scholarship_type_id, {
              id: config.scholarship_type_id,
              code: config.scholarship_type_code || "",
              name: config.scholarship_type_name,
            })
          }
        })

        const types = Array.from(typesMap.values()).sort((a, b) =>
          a.name.localeCompare(b.name, 'zh-TW')
        )

        setScholarshipTypes(types)
      } else {
        console.error("Failed to load scholarship types")
        setScholarshipTypes([])
      }
    } catch (error) {
      console.error("Failed to load scholarship types:", error)
      setScholarshipTypes([])
    } finally {
      setIsLoadingTypes(false)
    }
  }

  const loadPeriodsForType = async (typeId: number) => {
    setIsLoadingPeriods(true)
    try {
      const response = await api.admin.getScholarshipConfigurations({
        scholarship_type_id: typeId,
        is_active: true
      })

      if (response.success && response.data) {
        const configs = response.data
        setConfigurations(configs)

        // Extract unique period combinations
        const periodsMap = new Map<string, PeriodOption>()

        configs.forEach((config: ScholarshipConfiguration) => {
          const key = `${config.academic_year}:${config.semester || "null"}`
          if (!periodsMap.has(key)) {
            periodsMap.set(key, {
              key: key,
              label: formatPeriod(config.academic_year, config.semester),
              academic_year: config.academic_year,
              semester: config.semester || null
            })
          }
        })

        // Sort periods: newest year first, then by semester (second > first > null)
        const periods = Array.from(periodsMap.values()).sort((a, b) => {
          // Sort by academic year descending
          if (a.academic_year !== b.academic_year) {
            return b.academic_year - a.academic_year
          }

          // Sort by semester: second (3) > first (2) > null (1)
          const getSemesterOrder = (sem: string | null) => {
            if (sem === "second") return 3
            if (sem === "first") return 2
            return 1
          }

          return getSemesterOrder(b.semester) - getSemesterOrder(a.semester)
        })

        setPeriodOptions(periods)

        // Auto-select the first (latest) period
        if (periods.length > 0) {
          setSelectedPeriod(periods[0].key)
        }
      } else {
        setConfigurations([])
        setPeriodOptions([])
      }
    } catch (error) {
      console.error("Failed to load configurations:", error)
      setConfigurations([])
      setPeriodOptions([])
    } finally {
      setIsLoadingPeriods(false)
    }
  }

  const formatPeriod = (year: number, semester?: string | null): string => {
    if (!semester) return `${year}-整學年`
    return semester === "first" ? `${year}-上學期` : `${year}-下學期`
  }

  return (
    <div className="flex items-center gap-2">
      {/* Scholarship Type Selector */}
      <Select
        value={selectedTypeId}
        onValueChange={setSelectedTypeId}
        disabled={disabled || isLoadingTypes}
      >
        <SelectTrigger className="w-[200px]">
          <SelectValue placeholder={
            isLoadingTypes ? "載入中..." :
            scholarshipTypes.length === 0 ? "無可用獎學金類型" :
            "選擇獎學金類型"
          } />
        </SelectTrigger>
        <SelectContent>
          {scholarshipTypes.map((type) => (
            <SelectItem key={type.id} value={type.id.toString()}>
              {type.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Academic Year - Semester Selector */}
      <Select
        value={selectedPeriod}
        onValueChange={setSelectedPeriod}
        disabled={disabled || !selectedTypeId || isLoadingPeriods}
      >
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder={
            isLoadingPeriods ? "載入中..." :
            !selectedTypeId ? "請先選擇獎學金類型" :
            periodOptions.length === 0 ? "無可用期間" :
            "選擇學年度-學期"
          } />
        </SelectTrigger>
        <SelectContent>
          {periodOptions.map((period) => (
            <SelectItem key={period.key} value={period.key}>
              {period.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
