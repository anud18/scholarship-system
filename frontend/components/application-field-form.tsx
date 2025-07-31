"use client"

import { useState, useEffect } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { 
  FormInput, 
  Plus, 
  Edit, 
  Trash2, 
  Save,
  X,
  Loader2,
  AlertCircle
} from "lucide-react"
import type { ApplicationField, ApplicationFieldCreate, ApplicationFieldUpdate } from "@/lib/api"

interface ApplicationFieldFormProps {
  field?: ApplicationField | null
  scholarshipType: string
  isOpen: boolean
  onClose: () => void
  onSave: (fieldData: ApplicationFieldCreate | ApplicationFieldUpdate) => Promise<void>
  mode: "create" | "edit"
}

const FIELD_TYPES = [
  { value: "text", label: "文字輸入" },
  { value: "textarea", label: "多行文字" },
  { value: "number", label: "數字" },
  { value: "email", label: "電子郵件" },
  { value: "date", label: "日期" },
  { value: "select", label: "下拉選單" },
  { value: "checkbox", label: "核取方塊" },
  { value: "radio", label: "單選按鈕" }
]

export function ApplicationFieldForm({
  field,
  scholarshipType,
  isOpen,
  onClose,
  onSave,
  mode
}: ApplicationFieldFormProps) {
  const [formData, setFormData] = useState<Partial<ApplicationField>>({
    field_name: "",
    field_label: "",
    field_label_en: "",
    field_type: "text",
    is_required: false,
    placeholder: "",
    placeholder_en: "",
    max_length: undefined,
    min_value: undefined,
    max_value: undefined,
    step_value: undefined,
    field_options: [],
    display_order: 0,
    is_active: true,
    help_text: "",
    help_text_en: "",
    validation_rules: {},
    conditional_rules: {}
  })
  
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newOption, setNewOption] = useState({ value: "", label: "", label_en: "" })

  // Initialize form data when field changes
  useEffect(() => {
    if (field && mode === "edit") {
      setFormData({
        field_name: field.field_name,
        field_label: field.field_label,
        field_label_en: field.field_label_en,
        field_type: field.field_type,
        is_required: field.is_required,
        placeholder: field.placeholder,
        placeholder_en: field.placeholder_en,
        max_length: field.max_length,
        min_value: field.min_value,
        max_value: field.max_value,
        step_value: field.step_value,
        field_options: field.field_options || [],
        display_order: field.display_order,
        is_active: field.is_active,
        help_text: field.help_text,
        help_text_en: field.help_text_en,
        validation_rules: field.validation_rules,
        conditional_rules: field.conditional_rules
      })
    } else if (mode === "create") {
      setFormData({
        field_name: "",
        field_label: "",
        field_label_en: "",
        field_type: "text",
        is_required: false,
        placeholder: "",
        placeholder_en: "",
        max_length: undefined,
        min_value: undefined,
        max_value: undefined,
        step_value: undefined,
        field_options: [],
        display_order: 0,
        is_active: true,
        help_text: "",
        help_text_en: "",
        validation_rules: {},
        conditional_rules: {}
      })
    }
  }, [field, mode])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    try {
      // Validate required fields
      if (!formData.field_name || !formData.field_label) {
        throw new Error("欄位名稱和顯示名稱為必填項目")
      }

      // Validate field name format
      if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(formData.field_name)) {
        throw new Error("欄位名稱只能包含英文字母、數字和底線，且必須以字母或底線開頭")
      }

      // Validate options for select/radio fields
      if ((formData.field_type === "select" || formData.field_type === "radio") && 
          (!formData.field_options || formData.field_options.length === 0)) {
        throw new Error("下拉選單和單選按鈕必須至少有一個選項")
      }

      const fieldData = {
        ...formData,
        scholarship_type: scholarshipType
      }

      await onSave(fieldData)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "儲存失敗")
    } finally {
      setIsSubmitting(false)
    }
  }

  const addOption = () => {
    if (newOption.value && newOption.label) {
      setFormData(prev => ({
        ...prev,
        field_options: [...(prev.field_options || []), { ...newOption }]
      }))
      setNewOption({ value: "", label: "", label_en: "" })
    }
  }

  const removeOption = (index: number) => {
    setFormData(prev => ({
      ...prev,
      field_options: prev.field_options?.filter((_, i) => i !== index) || []
    }))
  }

  const updateOption = (index: number, field: string, value: string) => {
    setFormData(prev => ({
      ...prev,
      field_options: prev.field_options?.map((option, i) => 
        i === index ? { ...option, [field]: value } : option
      ) || []
    }))
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FormInput className="h-5 w-5" />
            {mode === "create" ? "新增申請欄位" : "編輯申請欄位"}
          </DialogTitle>
          <DialogDescription>
            {mode === "create" ? "新增一個新的申請表單欄位" : "修改現有欄位的設定"}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Basic Information */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">基本資訊</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="field_name">欄位名稱 (英文) *</Label>
                  <Input
                    id="field_name"
                    value={formData.field_name}
                    onChange={(e) => setFormData(prev => ({ ...prev, field_name: e.target.value }))}
                    placeholder="例如: academic_performance"
                    disabled={mode === "edit"}
                  />
                  <p className="text-xs text-gray-500">只能包含英文字母、數字和底線</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="field_type">欄位類型 *</Label>
                  <Select
                    value={formData.field_type}
                    onValueChange={(value) => setFormData(prev => ({ ...prev, field_type: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FIELD_TYPES.map((type) => (
                        <SelectItem key={type.value} value={type.value}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="field_label">顯示名稱 (中文) *</Label>
                  <Input
                    id="field_label"
                    value={formData.field_label}
                    onChange={(e) => setFormData(prev => ({ ...prev, field_label: e.target.value }))}
                    placeholder="例如: 學業表現說明"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="field_label_en">顯示名稱 (英文)</Label>
                  <Input
                    id="field_label_en"
                    value={formData.field_label_en || ""}
                    onChange={(e) => setFormData(prev => ({ ...prev, field_label_en: e.target.value }))}
                    placeholder="例如: Academic Performance Description"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="placeholder">提示文字 (中文)</Label>
                  <Input
                    id="placeholder"
                    value={formData.placeholder || ""}
                    onChange={(e) => setFormData(prev => ({ ...prev, placeholder: e.target.value }))}
                    placeholder="例如: 請說明您的學業表現"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="placeholder_en">提示文字 (英文)</Label>
                  <Input
                    id="placeholder_en"
                    value={formData.placeholder_en || ""}
                    onChange={(e) => setFormData(prev => ({ ...prev, placeholder_en: e.target.value }))}
                    placeholder="例如: Please describe your academic performance"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Validation Settings */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">驗證設定</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-2">
                <Switch
                  id="is_required"
                  checked={formData.is_required}
                  onCheckedChange={(checked) => setFormData(prev => ({ ...prev, is_required: checked }))}
                />
                <Label htmlFor="is_required">必填欄位</Label>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="max_length">最大字數</Label>
                  <Input
                    id="max_length"
                    type="number"
                    value={formData.max_length || ""}
                    onChange={(e) => setFormData(prev => ({ ...prev, max_length: e.target.value ? parseInt(e.target.value) : undefined }))}
                    placeholder="例如: 1000"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="display_order">顯示順序</Label>
                  <Input
                    id="display_order"
                    type="number"
                    value={formData.display_order || 0}
                    onChange={(e) => setFormData(prev => ({ ...prev, display_order: parseInt(e.target.value) || 0 }))}
                    placeholder="例如: 1"
                  />
                </div>
              </div>

              {/* Number field specific settings */}
              {(formData.field_type === "number") && (
                <div className="grid grid-cols-3 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="min_value">最小值</Label>
                    <Input
                      id="min_value"
                      type="number"
                      value={formData.min_value || ""}
                      onChange={(e) => setFormData(prev => ({ ...prev, min_value: e.target.value ? parseFloat(e.target.value) : undefined }))}
                      placeholder="例如: 0"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="max_value">最大值</Label>
                    <Input
                      id="max_value"
                      type="number"
                      value={formData.max_value || ""}
                      onChange={(e) => setFormData(prev => ({ ...prev, max_value: e.target.value ? parseFloat(e.target.value) : undefined }))}
                      placeholder="例如: 4.0"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="step_value">步進值</Label>
                    <Input
                      id="step_value"
                      type="number"
                      value={formData.step_value || ""}
                      onChange={(e) => setFormData(prev => ({ ...prev, step_value: e.target.value ? parseFloat(e.target.value) : undefined }))}
                      placeholder="例如: 0.01"
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Options for select/radio fields */}
          {(formData.field_type === "select" || formData.field_type === "radio") && (
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">選項設定</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label>新增選項</Label>
                  <div className="grid grid-cols-3 gap-2">
                    <Input
                      placeholder="選項值"
                      value={newOption.value}
                      onChange={(e) => setNewOption(prev => ({ ...prev, value: e.target.value }))}
                    />
                    <Input
                      placeholder="選項標籤 (中文)"
                      value={newOption.label}
                      onChange={(e) => setNewOption(prev => ({ ...prev, label: e.target.value }))}
                    />
                    <Input
                      placeholder="選項標籤 (英文)"
                      value={newOption.label_en}
                      onChange={(e) => setNewOption(prev => ({ ...prev, label_en: e.target.value }))}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={addOption}
                    disabled={!newOption.value || !newOption.label}
                  >
                    <Plus className="h-4 w-4 mr-1" />
                    新增選項
                  </Button>
                </div>

                <div className="space-y-2">
                  <Label>現有選項</Label>
                  <div className="space-y-2">
                    {formData.field_options?.map((option, index) => (
                      <div key={index} className="flex items-center gap-2 p-2 border rounded">
                        <Input
                          value={option.value}
                          onChange={(e) => updateOption(index, "value", e.target.value)}
                          placeholder="選項值"
                          className="flex-1"
                        />
                        <Input
                          value={option.label}
                          onChange={(e) => updateOption(index, "label", e.target.value)}
                          placeholder="選項標籤 (中文)"
                          className="flex-1"
                        />
                        <Input
                          value={option.label_en || ""}
                          onChange={(e) => updateOption(index, "label_en", e.target.value)}
                          placeholder="選項標籤 (英文)"
                          className="flex-1"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => removeOption(index)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Help Text */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">說明文字</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="help_text">說明文字 (中文)</Label>
                <Textarea
                  id="help_text"
                  value={formData.help_text || ""}
                  onChange={(e) => setFormData(prev => ({ ...prev, help_text: e.target.value }))}
                  placeholder="例如: 請詳細描述您的學業成績、排名、特殊成就等"
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="help_text_en">說明文字 (英文)</Label>
                <Textarea
                  id="help_text_en"
                  value={formData.help_text_en || ""}
                  onChange={(e) => setFormData(prev => ({ ...prev, help_text_en: e.target.value }))}
                  placeholder="例如: Please describe your academic grades, ranking, special achievements, etc."
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>

          {/* Status */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">狀態設定</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center space-x-2">
                <Switch
                  id="is_active"
                  checked={formData.is_active}
                  onCheckedChange={(checked) => setFormData(prev => ({ ...prev, is_active: checked }))}
                />
                <Label htmlFor="is_active">啟用此欄位</Label>
              </div>
            </CardContent>
          </Card>
        </form>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSubmitting}>
            <X className="h-4 w-4 mr-2" />
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                儲存中...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {mode === "create" ? "新增欄位" : "更新欄位"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
} 