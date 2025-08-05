/**
 * 學期選擇器組件 - 提供學年學期的 dropdown 選擇功能
 */

import React, { useState, useEffect } from 'react';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '@/components/ui/select';
import { Loader2, Calendar } from 'lucide-react';
import { cn } from '@/lib/utils';
import { apiClient } from '@/lib/api';

interface SemesterOption {
  value: string;
  label: string;
  label_en: string;
  is_current: boolean;
}

interface AcademicYearOption {
  value: number;
  label: string;
  label_en: string;
  is_current: boolean;
}

interface CombinationOption {
  value: string;
  academic_year: number;
  semester: string;
  label: string;
  label_en: string;
  is_current: boolean;
  application_count?: number;
}

interface SemesterSelectorProps {
  /** 選擇模式：separate（分別選擇學年和學期）、combined（組合選擇）、auto（根據獎學金制度自動選擇） */
  mode?: 'separate' | 'combined' | 'auto';
  /** 獎學金ID或代碼，用於自動判斷顯示模式 */
  scholarshipId?: number;
  scholarshipCode?: string;
  /** 強制指定申請週期：semester（學期制）或 yearly（學年制） */
  applicationCycle?: 'semester' | 'yearly';
  /** 是否顯示申請統計數量 */
  showStatistics?: boolean;
  /** 是否只顯示有資料的學期 */
  activePeriodsOnly?: boolean;
  /** 當前選中的學年 */
  selectedAcademicYear?: number;
  /** 當前選中的學期 */
  selectedSemester?: string;
  /** 當前選中的組合值 */
  selectedCombination?: string;
  /** 學年變更回調 */
  onAcademicYearChange?: (year: number) => void;
  /** 學期變更回調 */
  onSemesterChange?: (semester: string) => void;
  /** 組合變更回調 */
  onCombinationChange?: (combination: string, academicYear: number, semester: string | null) => void;
  /** 自定義樣式 */
  className?: string;
}

export const SemesterSelector: React.FC<SemesterSelectorProps> = ({
  mode = 'auto',
  scholarshipId,
  scholarshipCode,
  applicationCycle,
  showStatistics = false,
  activePeriodsOnly = false,
  selectedAcademicYear,
  selectedSemester,
  selectedCombination,
  onAcademicYearChange,
  onSemesterChange,
  onCombinationChange,
  className
}) => {
  const [loading, setLoading] = useState(false);
  const [actualMode, setActualMode] = useState<'separate' | 'combined' | 'yearly'>('combined');
  const [detectedCycle, setDetectedCycle] = useState<'semester' | 'yearly'>('semester');
  const [scholarshipName, setScholarshipName] = useState<string>();
  const [academicYears, setAcademicYears] = useState<AcademicYearOption[]>([]);
  const [semesters, setSemesters] = useState<SemesterOption[]>([]);
  const [combinations, setCombinations] = useState<CombinationOption[]>([]);
  const [currentInfo, setCurrentInfo] = useState<any>(null);

  // 載入根據獎學金制度的適當資料
  const loadScholarshipBasedData = async () => {
    try {
      setLoading(true);
      
      // 使用新的 scholarship-configurations API 來獲取實際配置的學期
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      
      if (activePeriodsOnly) {
        // 獲取有實際申請資料的學期
        const url = `${API_BASE}/api/v1/reference-data/active-academic-periods`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch active academic periods');
        
        const data = await response.json();
        setCombinations(data.active_periods || []);
        setDetectedCycle('semester');
        setActualMode('combined');
        setCurrentInfo({
          current_period: data.current_period,
          cycle: 'semester'
        });
      } else {
        // 獲取 ScholarshipConfiguration 中實際配置的學期
        const result = await apiClient.admin.getAvailableSemesters(scholarshipCode);
        
        if (result.success && result.data) {
          // 轉換 API 回傳的期間格式為組件需要的格式
          const configuredPeriods = result.data.map((period: string) => {
            if (period.includes('-')) {
              // 學期制：格式如 "114-1", "114-2"
              const [year, sem] = period.split('-');
              const academicYear = parseInt(year);
              const semester = sem === '1' ? 'first' : 'second';
              const semesterLabel = sem === '1' ? '第一學期' : '第二學期';
              
              return {
                value: period,
                academic_year: academicYear,
                semester: semester,
                label: `${academicYear}學年${semesterLabel}`,
                label_en: `Academic Year ${academicYear + 1911}-${academicYear + 1912} ${sem === '1' ? 'First' : 'Second'} Semester`,
                is_current: false, // TODO: 需要判斷當前學期
                cycle: 'semester'
              };
            } else {
              // 學年制：格式如 "114"
              const academicYear = parseInt(period);
              
              return {
                value: period,
                academic_year: academicYear,
                semester: null,
                label: `${academicYear}學年`,
                label_en: `Academic Year ${academicYear + 1911}-${academicYear + 1912}`,
                is_current: false, // TODO: 需要判斷當前學年
                cycle: 'yearly'
              };
            }
          });
          
          setCombinations(configuredPeriods);
          
          // 根據配置的期間類型決定顯示模式
          const hasSemesterPeriods = configuredPeriods.some((p: any) => p.cycle === 'semester');
          const hasYearlyPeriods = configuredPeriods.some((p: any) => p.cycle === 'yearly');
          
          if (hasYearlyPeriods && !hasSemesterPeriods) {
            setDetectedCycle('yearly');
            setActualMode('yearly');
          } else {
            setDetectedCycle('semester');
            setActualMode('combined');
          }
          
          setCurrentInfo({
            current_period: configuredPeriods.find((p: any) => p.is_current)?.value || null,
            cycle: hasYearlyPeriods && !hasSemesterPeriods ? 'yearly' : 'semester'
          });
        } else {
          // 如果沒有配置的期間，顯示空列表
          setCombinations([]);
          setDetectedCycle('semester');
          setActualMode('combined');
        }
      }
    } catch (error) {
      console.error('Error loading scholarship period data:', error);
      // 發生錯誤時顯示空列表
      setCombinations([]);
      setDetectedCycle('semester');
      setActualMode('combined');
    } finally {
      setLoading(false);
    }
  };

  // 載入基本的學期和學年資料
  const loadBasicData = async () => {
    try {
      setLoading(true);
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${API_BASE}/api/v1/reference-data/semesters`);
      if (!response.ok) throw new Error('Failed to fetch semester data');
      
      const data = await response.json();
      setAcademicYears(data.academic_years || []);
      setSemesters(data.semesters || []);
      setCurrentInfo({
        current_academic_year: data.current_academic_year,
        current_semester: data.current_semester
      });
      setActualMode('separate');
    } catch (error) {
      console.error('Error loading semester data:', error);
    } finally {
      setLoading(false);
    }
  };

  // 載入組合資料
  const loadCombinationData = async () => {
    try {
      setLoading(true);
      
      const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      let url = `${API_BASE}/api/v1/reference-data/semester-academic-year-combinations`;
      if (showStatistics) {
        url += '?include_statistics=true';
      }
      
      if (activePeriodsOnly) {
        url = `${API_BASE}/api/v1/reference-data/active-academic-periods`;
      }
      
      const response = await fetch(url);
      if (!response.ok) throw new Error('Failed to fetch combination data');
      
      const data = await response.json();
      
      if (activePeriodsOnly) {
        setCombinations(data.active_periods || []);
      } else {
        setCombinations(data.combinations || []);
      }
    } catch (error) {
      console.error('Error loading combination data:', error);
    } finally {
      setLoading(false);
    }
  };

  // 初始化載入資料
  useEffect(() => {
    if ((mode === 'auto' || mode === 'combined') && scholarshipCode) {
      // 自動模式或組合模式且有獎學金代碼：載入特定獎學金的配置學期
      loadScholarshipBasedData();
    } else if (mode === 'separate') {
      // 分別選擇模式：載入基本學年學期資料
      loadBasicData();
    } else {
      // 其他組合模式：載入所有組合資料
      loadCombinationData();
    }
  }, [mode, scholarshipId, scholarshipCode, applicationCycle, showStatistics, activePeriodsOnly]);

  // 處理學年變更
  const handleAcademicYearChange = (value: string) => {
    const year = parseInt(value);
    onAcademicYearChange?.(year);
  };

  // 處理學期變更
  const handleSemesterChange = (value: string) => {
    onSemesterChange?.(value);
  };

  // 處理組合變更
  const handleCombinationChange = (value: string) => {
    const combination = combinations.find(c => c.value === value);
    if (combination) {
      onCombinationChange?.(value, combination.academic_year, combination.semester || null);
    }
  };

  if (loading) {
    return (
      <div className={cn("flex items-center space-x-2", className)}>
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-sm text-muted-foreground">載入中...</span>
      </div>
    );
  }

  // 分別選擇模式
  if (mode === 'separate') {
    return (
      <div className={cn("flex items-center space-x-4", className)}>
        <div className="flex items-center space-x-2">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm">學年：</span>
          <Select value={selectedAcademicYear?.toString()} onValueChange={handleAcademicYearChange}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="選擇學年" />
            </SelectTrigger>
            <SelectContent>
              {academicYears.map(year => (
                <SelectItem key={year.value} value={year.value.toString()}>
                  <div className="flex items-center justify-between w-full">
                    <span>{year.label}</span>
                    {year.is_current && <span className="text-green-600 text-xs ml-2">(當前)</span>}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        
        <div className="flex items-center space-x-2">
          <span className="text-sm">學期：</span>
          <Select value={selectedSemester} onValueChange={handleSemesterChange}>
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder="選擇學期" />
            </SelectTrigger>
            <SelectContent>
              {semesters.map(semester => (
                <SelectItem key={semester.value} value={semester.value}>
                  <div className="flex items-center justify-between w-full">
                    <span>{semester.label}</span>
                    {semester.is_current && <span className="text-green-600 text-xs ml-2">(當前)</span>}
                  </div>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
    );
  }

  // 組合選擇模式（包含學年制和學期制）
  const isYearlyMode = actualMode === 'yearly' || detectedCycle === 'yearly';
  const labelText = isYearlyMode ? '學年：' : '學期：';
  const placeholderText = isYearlyMode ? '選擇學年' : '選擇學年學期';
  
  return (
    <div className={cn("flex items-center space-x-4", className)}>
      <div className="flex items-center space-x-2">
        <Calendar className="h-4 w-4 text-muted-foreground" />
        <span className="text-sm">{labelText}</span>
        <Select value={selectedCombination} onValueChange={handleCombinationChange}>
          <SelectTrigger className={cn("min-w-[160px]", isYearlyMode ? "w-[160px]" : "w-[220px]")}>
            <SelectValue placeholder={placeholderText} />
          </SelectTrigger>
          <SelectContent>
            {combinations.map(combination => (
              <SelectItem key={combination.value} value={combination.value}>
                <div className="flex items-center justify-between w-full">
                  <span>{combination.label}</span>
                  <div className="flex items-center space-x-2 ml-2">
                    {combination.is_current && <span className="text-green-600 text-xs">當前</span>}
                    {showStatistics && combination.application_count !== undefined && (
                      <span className="text-muted-foreground text-xs">({combination.application_count}件)</span>
                    )}
                  </div>
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        
        {/* 顯示獎學金名稱和制度資訊 */}
        {scholarshipName && (
          <div className="flex items-center space-x-2 text-sm text-muted-foreground">
            <span>•</span>
            <span>{scholarshipName}</span>
            <span className={cn(
              "px-2 py-1 rounded text-xs",
              isYearlyMode ? "bg-green-100 text-green-800" : "bg-blue-100 text-blue-800"
            )}>
              {isYearlyMode ? '學年制' : '學期制'}
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

export default SemesterSelector;