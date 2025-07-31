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
  FileText, 
  Plus, 
  Edit, 
  Trash2, 
  Save,
  X,
  Loader2,
  AlertCircle
} from "lucide-react"
import type { ApplicationDocument, ApplicationDocumentCreate, ApplicationDocumentUpdate } from "@/lib/api"

interface ApplicationDocumentFormProps {
  document?: ApplicationDocument | null
  scholarshipType: string
  isOpen: boolean
  onClose: () => void
  onSave: (documentData: ApplicationDocumentCreate | ApplicationDocumentUpdate) => Promise<void>
  mode: "create" | "edit"
}

const FILE_TYPES = [
  { value: "PDF", label: "PDF" },
  { value: "DOC", label: "DOC" },
  { value: "DOCX", label: "DOCX" },
  { value: "JPG", label: "JPG" },
  { value: "JPEG", label: "JPEG" },
  { value: "PNG", label: "PNG" },
  { value: "TXT", label: "TXT" }
]

const FILE_SIZES = [
  { value: "1MB", label: "1MB" },
  { value: "2MB", label: "2MB" },
  { value: "5MB", label: "5MB" },
  { value: "10MB", label: "10MB" },
  { value: "20MB", label: "20MB" },
  { value: "50MB", label: "50MB" }
]

export function ApplicationDocumentForm({
  document,
  scholarshipType,
  isOpen,
  onClose,
  onSave,
  mode
}: ApplicationDocumentFormProps) {
  const [formData, setFormData] = useState<Partial<ApplicationDocument>>({
    document_name: "",
    document_name_en: "",
    description: "",
    description_en: "",
    is_required: true,
    accepted_file_types: ["PDF"],
    max_file_size: "5MB",
    max_file_count: 1,
    display_order: 0,
    is_active: true,
    upload_instructions: "",
    upload_instructions_en: "",
    validation_rules: {}
  })
  
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [newFileType, setNewFileType] = useState("")

  // Initialize form data when document changes
  useEffect(() => {
    if (document && mode === "edit") {
      setFormData({
        document_name: document.document_name,
        document_name_en: document.document_name_en,
        description: document.description,
        description_en: document.description_en,
        is_required: document.is_required,
        accepted_file_types: document.accepted_file_types,
        max_file_size: document.max_file_size,
        max_file_count: document.max_file_count,
        display_order: document.display_order,
        is_active: document.is_active,
        upload_instructions: document.upload_instructions,
        upload_instructions_en: document.upload_instructions_en,
        validation_rules: document.validation_rules
      })
    } else if (mode === "create") {
      setFormData({
        document_name: "",
        document_name_en: "",
        description: "",
        description_en: "",
        is_required: true,
        accepted_file_types: ["PDF"],
        max_file_size: "5MB",
        max_file_count: 1,
        display_order: 0,
        is_active: true,
        upload_instructions: "",
        upload_instructions_en: "",
        validation_rules: {}
      })
    }
  }, [document, mode])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setIsSubmitting(true)
    setError(null)

    try {
      // Validate required fields
      if (!formData.document_name) {
        throw new Error("文件名稱為必填項目")
      }

      // Validate file types
      if (!formData.accepted_file_types || formData.accepted_file_types.length === 0) {
        throw new Error("至少需要選擇一種支援的檔案格式")
      }

      const documentData = {
        ...formData,
        scholarship_type: scholarshipType
      }

      await onSave(documentData)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : "儲存失敗")
    } finally {
      setIsSubmitting(false)
    }
  }

  const addFileType = () => {
    if (newFileType && !formData.accepted_file_types?.includes(newFileType)) {
      setFormData(prev => ({
        ...prev,
        accepted_file_types: [...(prev.accepted_file_types || []), newFileType]
      }))
      setNewFileType("")
    }
  }

  const removeFileType = (fileType: string) => {
    setFormData(prev => ({
      ...prev,
      accepted_file_types: prev.accepted_file_types?.filter(type => type !== fileType) || []
    }))
  }

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {mode === "create" ? "新增申請文件" : "編輯申請文件"}
          </DialogTitle>
          <DialogDescription>
            {mode === "create" ? "新增一個新的申請文件要求" : "修改現有文件的設定"}
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
                  <Label htmlFor="document_name">文件名稱 (中文) *</Label>
                  <Input
                    id="document_name"
                    value={formData.document_name}
                    onChange={(e) => setFormData(prev => ({ ...prev, document_name: e.target.value }))}
                    placeholder="例如: 成績單"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="document_name_en">文件名稱 (英文)</Label>
                  <Input
                    id="document_name_en"
                    value={formData.document_name_en || ""}
                    onChange={(e) => setFormData(prev => ({ ...prev, document_name_en: e.target.value }))}
                    placeholder="例如: Transcript"
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">文件說明 (中文)</Label>
                <Textarea
                  id="description"
                  value={formData.description || ""}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="例如: 請上傳高中三年完整成績單"
                  rows={3}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description_en">文件說明 (英文)</Label>
                <Textarea
                  id="description_en"
                  value={formData.description_en || ""}
                  onChange={(e) => setFormData(prev => ({ ...prev, description_en: e.target.value }))}
                  placeholder="例如: Please upload complete high school transcript for three years"
                  rows={3}
                />
              </div>
            </CardContent>
          </Card>

          {/* File Requirements */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">檔案要求</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center space-x-2">
                <Switch
                  id="is_required"
                  checked={formData.is_required}
                  onCheckedChange={(checked) => setFormData(prev => ({ ...prev, is_required: checked }))}
                />
                <Label htmlFor="is_required">必要文件</Label>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="max_file_size">檔案大小限制</Label>
                  <Select
                    value={formData.max_file_size}
                    onValueChange={(value) => setFormData(prev => ({ ...prev, max_file_size: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FILE_SIZES.map((size) => (
                        <SelectItem key={size.value} value={size.value}>
                          {size.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="max_file_count">最大檔案數量</Label>
                  <Input
                    id="max_file_count"
                    type="number"
                    value={formData.max_file_count || 1}
                    onChange={(e) => setFormData(prev => ({ ...prev, max_file_count: parseInt(e.target.value) || 1 }))}
                    min={1}
                    max={10}
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

              {/* Accepted File Types */}
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label>支援的檔案格式</Label>
                  <div className="flex gap-2">
                    <Select
                      value={newFileType}
                      onValueChange={setNewFileType}
                    >
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="選擇格式" />
                      </SelectTrigger>
                      <SelectContent>
                        {FILE_TYPES.map((type) => (
                          <SelectItem key={type.value} value={type.value}>
                            {type.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={addFileType}
                      disabled={!newFileType || formData.accepted_file_types?.includes(newFileType)}
                    >
                      <Plus className="h-4 w-4 mr-1" />
                      新增
                    </Button>
                  </div>
                </div>

                <div className="flex gap-2 flex-wrap">
                  {formData.accepted_file_types?.map((fileType) => (
                    <Badge key={fileType} variant="secondary" className="flex items-center gap-1">
                      {fileType}
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-4 w-4 p-0 hover:bg-transparent"
                        onClick={() => removeFileType(fileType)}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </Badge>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Upload Instructions */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">上傳說明</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="upload_instructions">上傳說明 (中文)</Label>
                <Textarea
                  id="upload_instructions"
                  value={formData.upload_instructions || ""}
                  onChange={(e) => setFormData(prev => ({ ...prev, upload_instructions: e.target.value }))}
                  placeholder="例如: 請確保成績單清晰可讀，包含所有學期成績"
                  rows={3}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="upload_instructions_en">上傳說明 (英文)</Label>
                <Textarea
                  id="upload_instructions_en"
                  value={formData.upload_instructions_en || ""}
                  onChange={(e) => setFormData(prev => ({ ...prev, upload_instructions_en: e.target.value }))}
                  placeholder="例如: Please ensure the transcript is clear and readable, including all semester grades"
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
                <Label htmlFor="is_active">啟用此文件要求</Label>
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
                {mode === "create" ? "新增文件" : "更新文件"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
} 