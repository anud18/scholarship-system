"use client"

import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Plus, Search, Edit, Trash2, FileCode, Copy, Upload } from "lucide-react"
import { ScholarshipType, ScholarshipRule, api } from "@/lib/api"
import { ScholarshipRuleModal } from "./scholarship-rule-modal"
import { CopyRulesModal } from "./copy-rules-modal"

interface AdminRuleManagementProps {
  scholarshipTypes: ScholarshipType[]
}

export function AdminRuleManagement({ scholarshipTypes }: AdminRuleManagementProps) {
  const [rules, setRules] = useState<ScholarshipRule[]>([])
  const [filteredRules, setFilteredRules] = useState<ScholarshipRule[]>([])
  const [selectedScholarshipType, setSelectedScholarshipType] = useState<ScholarshipType | null>(null)
  const [selectedYear, setSelectedYear] = useState<number | null>(113)
  const [selectedSemester, setSelectedSemester] = useState<string | null>("first")
  const [searchTerm, setSearchTerm] = useState("")
  const [availableYears, setAvailableYears] = useState<number[]>([])
  const [loading, setLoading] = useState(false)
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false)
  const [selectedRule, setSelectedRule] = useState<ScholarshipRule | null>(null)
  const [isCreating, setIsCreating] = useState(false)
  const [isCopyModalOpen, setIsCopyModalOpen] = useState(false)
  const [selectedRulesForCopy, setSelectedRulesForCopy] = useState<ScholarshipRule[]>([])
  const [isBulkCopyModalOpen, setIsBulkCopyModalOpen] = useState(false)

  // 自動選擇第一個獎學金類型
  useEffect(() => {
    if (scholarshipTypes.length > 0 && !selectedScholarshipType) {
      setSelectedScholarshipType(scholarshipTypes[0])
    }
  }, [scholarshipTypes, selectedScholarshipType])

  // 獲取所有可用的年份
  useEffect(() => {
    const fetchAvailableYears = async () => {
      try {
        const response = await api.admin.getAvailableYears()
        if (response.success && response.data) {
          setAvailableYears(response.data)
        } else {
          throw new Error(response.message || '獲取可用年份失敗')
        }
      } catch (error) {
        console.error('獲取可用年份失敗:', error)
        throw error
      }
    }
    fetchAvailableYears()
  }, [])

  // 當選擇的獎學金類型改變時，處理學期設置並載入規則
  useEffect(() => {
    if (selectedScholarshipType) {
      // 如果是學年制獎學金，清除學期選擇
      if (selectedScholarshipType.application_cycle === 'yearly') {
        setSelectedSemester(null)
      } else if (selectedScholarshipType.application_cycle === 'semester' && !selectedSemester) {
        // 如果是學期制但沒有選擇學期，設置預設值
        setSelectedSemester('first')
      }
      loadRules()
    }
  }, [selectedScholarshipType, selectedYear, selectedSemester])

  // 過濾規則
  useEffect(() => {
    let filtered = rules

    if (searchTerm) {
      filtered = filtered.filter(rule => 
        rule.rule_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (rule.tag && rule.tag.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (rule.description && rule.description.toLowerCase().includes(searchTerm.toLowerCase()))
      )
    }

    // 依照優先級排序 (1 在最上面)
    filtered.sort((a, b) => a.priority - b.priority)

    setFilteredRules(filtered)
  }, [rules, searchTerm])

  const loadRules = async () => {
    if (!selectedScholarshipType) return

    setLoading(true)
    try {
      // 根據獎學金類型決定是否包含學期參數
      const params: any = {
        scholarship_type_id: selectedScholarshipType.id,
        academic_year: selectedYear
      }
      
      // 只有學期制的獎學金才傳送 semester 參數
      if (selectedScholarshipType.application_cycle === 'semester') {
        params.semester = selectedSemester
      }
      
      const response = await api.admin.getScholarshipRules(params)
      if (response.success && response.data) {
        setRules(response.data)
      } else {
        throw new Error(response.message || '載入規則失敗')
      }
    } catch (error) {
      console.error('載入規則失敗:', error)
      throw error
    } finally {
      setLoading(false)
    }
  }

  const handleCreateRule = () => {
    setSelectedRule(null)
    setIsCreating(true)
    setIsRuleModalOpen(true)
  }

  const handleEditRule = (rule: ScholarshipRule) => {
    setSelectedRule(rule)
    setIsCreating(false)
    setIsRuleModalOpen(true)
  }

  const handleDeleteRule = async (rule: ScholarshipRule) => {
    if (!confirm(`確定要刪除規則「${rule.rule_name}」嗎？`)) return

    try {
      await api.admin.deleteScholarshipRule(rule.id)
      await loadRules()
    } catch (error) {
      console.error('刪除規則失敗:', error)
    }
  }

  const handleRuleSubmit = async (ruleData: Partial<ScholarshipRule>) => {
    if (!selectedScholarshipType) return

    try {
      if (isCreating) {
        await api.admin.createScholarshipRule(ruleData as any)
      } else if (selectedRule) {
        await api.admin.updateScholarshipRule(selectedRule.id, ruleData as any)
      }
      await loadRules()
    } catch (error) {
      console.error('提交規則失敗:', error)
      throw error
    }
  }

  const handleCopyRule = (rule: ScholarshipRule) => {
    setSelectedRulesForCopy([rule])
    setIsCopyModalOpen(true)
  }

  const handleBulkCopyRules = () => {
    if (filteredRules.length === 0) return
    setSelectedRulesForCopy(filteredRules)
    setIsBulkCopyModalOpen(true)
  }

  const handleCopyRules = async (targetYear: number, targetSemester?: string, overwriteExisting: boolean = false) => {
    try {
      console.log('[COPY RULES] Starting copy process...')
      console.log('[COPY RULES] Source:', {
        year: selectedYear,
        semester: selectedSemester,
        rulesCount: selectedRulesForCopy.length,
        ruleIds: selectedRulesForCopy.map(rule => rule.id)
      })
      console.log('[COPY RULES] Target:', {
        year: targetYear,
        semester: targetSemester,
        overwriteExisting
      })
      
      const copyRequest = {
        source_academic_year: selectedYear || undefined,
        source_semester: selectedSemester || undefined,
        target_academic_year: targetYear,
        target_semester: targetSemester,
        rule_ids: selectedRulesForCopy.map(rule => rule.id),
        overwrite_existing: overwriteExisting
      }

      console.log('[COPY RULES] Request payload:', copyRequest)
      
      const response = await api.admin.copyRulesBetweenPeriods(copyRequest)
      
      console.log('[COPY RULES] Response:', response)
      console.log('[COPY RULES] Response data:', response.data)
      
      if (response.success) {
        const copiedCount = response.data?.length || 0
        const skippedCount = selectedRulesForCopy.length - copiedCount
        
        console.log('[COPY RULES] Results:', {
          totalRules: selectedRulesForCopy.length,
          copiedCount,
          skippedCount,
          copiedRules: response.data
        })
        
        let message = `成功複製 ${copiedCount} 條規則`
        if (skippedCount > 0) {
          message += `，跳過 ${skippedCount} 條重複規則`
        }
        
        console.log('[COPY RULES] Alert message:', message)
        alert(message)
        
        // 如果複製到新的年份（不在現有列表中），重新載入可用年份
        if (!availableYears.includes(targetYear)) {
          console.log('[COPY RULES] New year detected, reloading available years...')
          try {
            const response = await api.admin.getAvailableYears()
            if (response.success && response.data) {
              setAvailableYears(response.data)
            }
          } catch (error) {
            console.error('Failed to reload available years:', error)
          }
        }
        
        // 如果複製到當前顯示的期間，重新載入規則
        if (targetYear === selectedYear && 
            ((!targetSemester && !selectedSemester) || targetSemester === selectedSemester)) {
          console.log('[COPY RULES] Reloading rules for current period...')
          await loadRules()
        }
      } else {
        console.error('[COPY RULES] Copy failed:', response.message)
        throw new Error(response.message || '複製失敗')
      }
    } catch (error) {
      console.error('[COPY RULES] Error in copy process:', error)
      console.error('複製規則失敗:', error)
      alert('複製規則失敗: ' + (error as Error).message)
    }
  }

  if (scholarshipTypes.length === 0) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <FileCode className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
          <p className="text-muted-foreground">尚無獎學金類型</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 獎學金類型選擇 */}
      <Tabs 
        value={selectedScholarshipType?.id.toString() || ""} 
        onValueChange={(value) => {
          const type = scholarshipTypes.find(t => t.id.toString() === value)
          setSelectedScholarshipType(type || null)
        }}
      >
        <TabsList className="grid w-full grid-cols-3">
          {scholarshipTypes.map((type) => (
            <TabsTrigger key={type.id} value={type.id.toString()}>
              {type.name}
            </TabsTrigger>
          ))}
        </TabsList>

        {scholarshipTypes.map((type) => (
          <TabsContent key={type.id} value={type.id.toString()}>
            <Card className="p-6">
              {/* 過濾器 */}
              <div className="flex flex-col lg:flex-row gap-4 mb-6">
                <div className="flex-1">
                  <div className="relative">
                    <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="搜尋規則名稱、標籤或描述..."
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                      className="pl-8"
                    />
                  </div>
                </div>
                <div className="flex gap-2">
                  <Select
                    value={selectedYear?.toString() || ""}
                    onValueChange={(value) => setSelectedYear(parseInt(value))}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue placeholder="學年" />
                    </SelectTrigger>
                    <SelectContent>
                      {availableYears.map((year) => (
                        <SelectItem key={year} value={year.toString()}>
                          {year}學年
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {type.application_cycle === 'semester' && (
                    <Select
                      value={selectedSemester || ""}
                      onValueChange={setSelectedSemester}
                    >
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="學期" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="first">第一學期</SelectItem>
                        <SelectItem value="second">第二學期</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                  <Button 
                    onClick={handleBulkCopyRules} 
                    variant="outline"
                    disabled={filteredRules.length === 0}
                    title="批量複製當前顯示的所有規則"
                  >
                    <Upload className="h-4 w-4 mr-1" />
                    批量複製
                  </Button>
                  <Button onClick={handleCreateRule} className="nycu-gradient text-white">
                    <Plus className="h-4 w-4 mr-1" />
                    新增規則
                  </Button>
                </div>
              </div>

              {/* 操作說明 */}
              {filteredRules.length > 0 && (
                <div className="text-xs text-muted-foreground mb-4 p-2 bg-blue-50 rounded-md">
                  💡 <strong>複製規則功能：</strong>點擊規則操作欄中的 <Copy className="inline h-3 w-3 mx-1" /> 可複製單一規則，或使用上方「批量複製」按鈕複製所有顯示的規則到其他學年/學期。
                </div>
              )}

              {/* 規則列表 - Table 格式 */}
              {loading ? (
                <div className="flex justify-center p-8">
                  <div className="text-muted-foreground">載入中...</div>
                </div>
              ) : filteredRules.length === 0 ? (
                <div className="flex items-center justify-center p-8">
                  <div className="text-center">
                    <FileCode className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-muted-foreground">
                      {searchTerm ? "找不到符合條件的規則" : "尚無審核規則"}
                    </p>
                  </div>
                </div>
              ) : (
                <div className="border rounded-md">
                  <table className="w-full">
                    <thead className="border-b bg-muted/50">
                      <tr>
                        <th className="text-left p-4 font-semibold">規則名稱</th>
                        <th className="text-left p-4 font-semibold">規則類型</th>
                        <th className="text-left p-4 font-semibold">屬性</th>
                        <th className="text-left p-4 font-semibold">條件</th>
                        <th className="text-left p-4 font-semibold">優先級</th>
                        <th className="text-left p-4 font-semibold">狀態</th>
                        <th className="text-right p-4 font-semibold">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRules.map((rule) => (
                        <tr key={rule.id} className="border-b hover:bg-muted/25 transition-colors">
                          <td className="p-4">
                            <div className="space-y-1">
                              <div className="font-medium">{rule.rule_name}</div>
                              {rule.description && (
                                <div className="text-xs text-muted-foreground line-clamp-2">
                                  {rule.description}
                                </div>
                              )}
                              {rule.tag && (
                                <Badge variant="outline" className="text-xs whitespace-nowrap">
                                  {rule.tag}
                                </Badge>
                              )}
                            </div>
                          </td>
                          <td className="p-4">
                            <Badge variant="outline" className="text-xs whitespace-nowrap">
                              {rule.rule_type}
                            </Badge>
                          </td>
                          <td className="p-4">
                            <div className="flex gap-1">
                              {rule.is_hard_rule && (
                                <Badge variant="destructive" className="text-xs whitespace-nowrap">必要</Badge>
                              )}
                              {rule.is_warning && (
                                <Badge variant="outline" className="text-xs whitespace-nowrap">警告</Badge>
                              )}
                            </div>
                          </td>
                          <td className="p-4">
                            <div className="text-sm font-mono">
                              <span>{rule.condition_field}</span>
                              <span className="mx-1 text-muted-foreground">{rule.operator}</span>
                              <span>{rule.expected_value}</span>
                            </div>
                          </td>
                          <td className="p-4">
                            <Badge variant="secondary" className="text-xs whitespace-nowrap">
                              {rule.priority}
                            </Badge>
                          </td>
                          <td className="p-4">
                            <div className="flex gap-1">
                              {rule.is_active ? (
                                <Badge className="text-xs bg-green-500 whitespace-nowrap">已啟用</Badge>
                              ) : (
                                <Badge variant="secondary" className="text-xs whitespace-nowrap">已停用</Badge>
                              )}
                              
                              {rule.is_initial_enabled && (
                                <Badge className="text-xs bg-blue-500 whitespace-nowrap">初領</Badge>
                              )}
                              
                              {rule.is_renewal_enabled && (
                                <Badge className="text-xs bg-orange-500 whitespace-nowrap">續領</Badge>
                              )}
                            </div>
                          </td>
                          <td className="p-4">
                            <div className="flex justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleEditRule(rule)}
                                title="編輯規則"
                              >
                                <Edit className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleCopyRule(rule)}
                                title="複製規則"
                                className="text-blue-600 hover:text-blue-700"
                              >
                                <Copy className="h-4 w-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="text-red-600 hover:text-red-700"
                                onClick={() => handleDeleteRule(rule)}
                                title="刪除規則"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      {/* 規則編輯/新增 Modal */}
      {selectedScholarshipType && (
        <ScholarshipRuleModal
          isOpen={isRuleModalOpen}
          onClose={() => setIsRuleModalOpen(false)}
          rule={selectedRule}
          scholarshipTypeId={selectedScholarshipType.id}
          academicYear={selectedYear || 113}
          semester={selectedScholarshipType.application_cycle === 'semester' ? selectedSemester : null}
          onSubmit={handleRuleSubmit}
        />
      )}

      {/* 複製規則 Modal */}
      {selectedScholarshipType && (
        <>
          <CopyRulesModal
            isOpen={isCopyModalOpen}
            onClose={() => {
              setIsCopyModalOpen(false)
              setSelectedRulesForCopy([])
            }}
            rules={selectedRulesForCopy}
            scholarshipTypes={scholarshipTypes}
            currentScholarshipType={selectedScholarshipType}
            currentYear={selectedYear}
            currentSemester={selectedSemester}
            availableYears={availableYears}
            onCopy={handleCopyRules}
            isBulkMode={false}
          />
          
          <CopyRulesModal
            isOpen={isBulkCopyModalOpen}
            onClose={() => {
              setIsBulkCopyModalOpen(false)
              setSelectedRulesForCopy([])
            }}
            rules={selectedRulesForCopy}
            scholarshipTypes={scholarshipTypes}
            currentScholarshipType={selectedScholarshipType}
            currentYear={selectedYear}
            currentSemester={selectedSemester}
            availableYears={availableYears}
            onCopy={handleCopyRules}
            isBulkMode={true}
          />
        </>
      )}
    </div>
  )
}