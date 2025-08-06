"use client"

import { useState } from "react"
import { Modal } from "@/components/ui/modal"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Card } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Copy, X } from "lucide-react"
import { Checkbox } from "@/components/ui/checkbox"
import { ScholarshipRule, ScholarshipType } from "@/lib/api"

interface CopyRulesModalProps {
  isOpen: boolean
  onClose: () => void
  rules: ScholarshipRule[]
  scholarshipTypes: ScholarshipType[]
  currentScholarshipType: ScholarshipType
  currentYear: number | null
  currentSemester: string | null
  availableYears: number[]
  onCopy: (targetYear: number, targetSemester?: string, overwriteExisting?: boolean) => Promise<void>
  isBulkMode?: boolean
}

export function CopyRulesModal({
  isOpen,
  onClose,
  rules,
  scholarshipTypes,
  currentScholarshipType,
  currentYear,
  currentSemester,
  availableYears,
  onCopy,
  isBulkMode = false
}: CopyRulesModalProps) {
  const [targetYear, setTargetYear] = useState<number | null>(null)
  const [customYear, setCustomYear] = useState<string>("")
  const [targetSemester, setTargetSemester] = useState<string | null>(null)
  const [yearInputMode, setYearInputMode] = useState<"existing" | "custom">("existing")
  const [overwriteExisting, setOverwriteExisting] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleCopy = async () => {
    const finalYear = yearInputMode === "custom" ? parseInt(customYear) : targetYear
    if (!finalYear || isNaN(finalYear)) {
      setError('請選擇或輸入有效的學年')
      return
    }

    setIsLoading(true)
    setError(null) // Clear previous errors
    
    try {
      await onCopy(finalYear, targetSemester || undefined, overwriteExisting)
      onClose()
    } catch (error: any) {
      // Extract meaningful error message
      let errorMessage = '複製失敗，請稍後再試'
      
      if (error?.message) {
        errorMessage = error.message
      } else if (typeof error === 'string') {
        errorMessage = error
      } else if (error?.response?.data?.message) {
        errorMessage = error.response.data.message
      }
      
      setError(errorMessage)
      console.error('複製失敗:', error)
    } finally {
      setIsLoading(false)
    }
  }

  const handleClose = () => {
    setTargetYear(null)
    setCustomYear("")
    setTargetSemester(null)
    setYearInputMode("existing")
    setOverwriteExisting(false)
    setError(null)
    onClose()
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={isBulkMode ? `批量複製規則 (${rules.length} 條)` : "複製規則"}
      size="md"
    >
      <div className="space-y-6">
        {/* 來源資訊 */}
        <Card className="p-4 bg-muted/50">
          <h4 className="font-semibold mb-3">來源資訊</h4>
          <div className="space-y-2 text-sm">
            <div>
              <span className="text-muted-foreground">獎學金類型：</span>
              {currentScholarshipType.name}
            </div>
            <div>
              <span className="text-muted-foreground">學年度：</span>
              {currentYear || "未指定"}學年
            </div>
            {currentScholarshipType.application_cycle === 'semester' && (
              <div>
                <span className="text-muted-foreground">學期：</span>
                {currentSemester === 'first' ? '第一學期' : 
                 currentSemester === 'second' ? '第二學期' : '未指定'}
              </div>
            )}
            <div>
              <span className="text-muted-foreground">規則數量：</span>
              {rules.length} 條
            </div>
          </div>
        </Card>

        {/* 規則列表預覽 */}
        {!isBulkMode && rules.length > 0 && (
          <Card className="p-4">
            <h4 className="font-semibold mb-3">要複製的規則</h4>
            <div className="space-y-2">
              {rules.map((rule) => (
                <div key={rule.id} className="text-sm p-2 bg-muted/30 rounded">
                  <div className="font-medium">{rule.rule_name}</div>
                  {rule.tag && (
                    <div className="text-xs text-muted-foreground">標籤: {rule.tag}</div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* 目標設定 */}
        <div className="space-y-4">
          <h4 className="font-semibold">複製到</h4>
          
          {/* 學年度選擇方式 */}
          <Tabs value={yearInputMode} onValueChange={(value) => setYearInputMode(value as "existing" | "custom")}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="existing">現有學年</TabsTrigger>
              <TabsTrigger value="custom">自定義學年</TabsTrigger>
            </TabsList>
            
            <TabsContent value="existing" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label>目標學年度 *</Label>
                <Select
                  value={targetYear?.toString() || ""}
                  onValueChange={(value) => setTargetYear(parseInt(value))}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="選擇現有學年度" />
                  </SelectTrigger>
                  <SelectContent>
                    {availableYears.map((year) => (
                      <SelectItem key={year} value={year.toString()}>
                        {year}學年
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </TabsContent>
            
            <TabsContent value="custom" className="space-y-4 mt-4">
              <div className="space-y-2">
                <Label>自定義學年度 *</Label>
                <Input
                  type="number"
                  placeholder="例如：114"
                  value={customYear}
                  onChange={(e) => setCustomYear(e.target.value)}
                  min="100"
                  max="200"
                />
                <p className="text-xs text-muted-foreground">
                  請輸入民國年份，例如：114 代表 114學年度
                </p>
              </div>
            </TabsContent>
          </Tabs>

          {/* 學期選擇 */}
          {currentScholarshipType.application_cycle === 'semester' && (
            <div className="space-y-2">
              <Label>目標學期</Label>
              <Select
                value={targetSemester || ""}
                onValueChange={setTargetSemester}
              >
                <SelectTrigger>
                  <SelectValue placeholder="選擇目標學期" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="first">第一學期</SelectItem>
                  <SelectItem value="second">第二學期</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* 覆蓋選項 */}
          <div className="flex items-center space-x-2 p-3 bg-orange-50 rounded-md">
            <Checkbox
              id="overwrite-existing"
              checked={overwriteExisting}
              onCheckedChange={setOverwriteExisting}
            />
            <Label htmlFor="overwrite-existing" className="text-sm">
              覆蓋已存在的重複規則
            </Label>
          </div>
        </div>

        {/* 提示說明 */}
        <div className="text-xs text-muted-foreground bg-blue-50 p-3 rounded-md">
          <p>• <strong>現有學年</strong>：複製到已存在的學年/學期</p>
          <p>• <strong>自定義學年</strong>：創建新的學年/學期規則（如 114學年度）</p>
          <p>• 複製規則時會保持原規則的所有設定，僅更改學年度和學期</p>
          <p>• 預設會跳過已存在的重複規則，勾選「覆蓋」選項可強制替換</p>
          <p>• 重複檢查基於：規則名稱、類型、條件欄位、運算子和期望值</p>
        </div>
      </div>

      {/* 錯誤訊息 */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-md">
          <p className="text-sm font-medium">複製失敗</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* 操作按鈕 */}
      <div className="flex justify-end gap-2 pt-4 border-t">
        <Button variant="outline" onClick={handleClose} disabled={isLoading}>
          <X className="h-4 w-4 mr-1" />
          取消
        </Button>
        <Button 
          onClick={handleCopy} 
          disabled={
            (yearInputMode === "existing" ? !targetYear : !customYear || isNaN(parseInt(customYear))) || 
            isLoading
          }
          className="nycu-gradient text-white"
        >
          <Copy className="h-4 w-4 mr-1" />
          {isLoading ? "複製中..." : `複製 ${rules.length} 條規則`}
        </Button>
      </div>
    </Modal>
  )
}