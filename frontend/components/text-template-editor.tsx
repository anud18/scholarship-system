"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Edit, Save, X, Mail, AlertCircle, Loader2, FileText, Plus } from "lucide-react";
import { api } from "@/lib/api";

interface EmailTemplate {
  id: number;
  template_key: string;
  template_name: string;
  subject_template: string;
  body_template: string;
  category: string;
  variables: string[];
  is_active: boolean;
  description?: string;
}

interface EditDialogProps {
  template: EmailTemplate | null;
  open: boolean;
  onClose: () => void;
  onSave: (template: EmailTemplate) => void;
}

function EditDialog({ template, open, onClose, onSave }: EditDialogProps) {
  const [editedTemplate, setEditedTemplate] = useState<Partial<EmailTemplate>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (template) {
      setEditedTemplate(template);
    }
  }, [template]);

  const handleSave = async () => {
    if (!template) return;

    setIsSaving(true);
    setError(null);

    try {
      const response = await api.emailManagement.updateEmailTemplate(
        template.id,
        editedTemplate
      );
      if (response.data) {
        onSave(response.data);
      }
      onClose();
    } catch (err) {
      console.error("Failed to save template:", err);
      setError(err instanceof Error ? err.message : "保存模板失敗");
    } finally {
      setIsSaving(false);
    }
  };

  const insertVariable = (variable: string, field: "subject" | "body") => {
    const variableTag = `{{${variable}}}`;
    if (field === "subject") {
      setEditedTemplate((prev) => ({
        ...prev,
        subject_template: (prev.subject_template || "") + variableTag,
      }));
    } else {
      setEditedTemplate((prev) => ({
        ...prev,
        body_template: (prev.body_template || "") + variableTag,
      }));
    }
  };

  if (!template) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit className="h-5 w-5" />
            編輯模板：{template.template_name}
          </DialogTitle>
          <DialogDescription>{template.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Template Info */}
          <div className="flex items-center gap-4 text-sm">
            <Badge>{template.category}</Badge>
            <span className="text-gray-600">模板 Key: {template.template_key}</span>
          </div>

          {/* Variables Helper */}
          {template.variables && template.variables.length > 0 && (
            <div className="border rounded-lg p-4 bg-blue-50">
              <h4 className="font-semibold text-sm mb-2">可用變數</h4>
              <div className="flex flex-wrap gap-2">
                {template.variables.map((variable) => (
                  <Badge
                    key={variable}
                    variant="outline"
                    className="cursor-pointer hover:bg-blue-100"
                    onClick={() => {
                      navigator.clipboard.writeText(`{{${variable}}}`);
                    }}
                  >
                    {`{{${variable}}}`}
                  </Badge>
                ))}
              </div>
              <p className="text-xs text-gray-600 mt-2">點擊變數複製到剪貼板</p>
            </div>
          )}

          {/* Subject Template */}
          <div className="space-y-2">
            <Label htmlFor="subject_template">
              主旨模板
              <span className="text-xs text-gray-500 ml-2">(支持變數：使用 {`{{變數名}}`} 格式)</span>
            </Label>
            <Input
              id="subject_template"
              value={editedTemplate.subject_template || ""}
              onChange={(e) =>
                setEditedTemplate((prev) => ({
                  ...prev,
                  subject_template: e.target.value,
                }))
              }
              placeholder="輸入郵件主旨模板"
            />
            {template.variables && template.variables.length > 0 && (
              <div className="flex gap-2 flex-wrap">
                <span className="text-xs text-gray-600">快速插入：</span>
                {template.variables.slice(0, 5).map((variable) => (
                  <Button
                    key={variable}
                    size="sm"
                    variant="ghost"
                    className="h-6 text-xs"
                    onClick={() => insertVariable(variable, "subject")}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    {variable}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {/* Body Template */}
          <div className="space-y-2">
            <Label htmlFor="body_template">
              內容模板
              <span className="text-xs text-gray-500 ml-2">(支持變數和簡單 HTML 標籤)</span>
            </Label>
            <Textarea
              id="body_template"
              value={editedTemplate.body_template || ""}
              onChange={(e) =>
                setEditedTemplate((prev) => ({
                  ...prev,
                  body_template: e.target.value,
                }))
              }
              placeholder="輸入郵件內容模板"
              rows={15}
              className="font-mono text-sm"
            />
            {template.variables && template.variables.length > 0 && (
              <div className="flex gap-2 flex-wrap">
                <span className="text-xs text-gray-600">快速插入：</span>
                {template.variables.slice(0, 8).map((variable) => (
                  <Button
                    key={variable}
                    size="sm"
                    variant="ghost"
                    className="h-6 text-xs"
                    onClick={() => insertVariable(variable, "body")}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    {variable}
                  </Button>
                ))}
              </div>
            )}
          </div>

          {/* Preview */}
          <div className="space-y-2">
            <h4 className="font-semibold text-sm">簡單預覽</h4>
            <div className="border rounded-lg p-4 bg-gray-50 space-y-2">
              <div>
                <span className="text-xs font-semibold text-gray-600">主旨：</span>
                <p className="text-sm">{editedTemplate.subject_template}</p>
              </div>
              <div>
                <span className="text-xs font-semibold text-gray-600">內容：</span>
                <div
                  className="text-sm whitespace-pre-wrap"
                  dangerouslySetInnerHTML={{ __html: editedTemplate.body_template || "" }}
                />
              </div>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Help */}
          <Alert>
            <FileText className="h-4 w-4" />
            <AlertDescription>
              <strong>變數使用說明：</strong>
              <ul className="list-disc list-inside mt-2 text-xs space-y-1">
                <li>使用 {`{{變數名}}`} 格式插入變數</li>
                <li>支持簡單 HTML 標籤：{`<b>, <i>, <br>, <p>`} 等</li>
                <li>換行請使用 {`<br>`} 標籤或實際換行</li>
              </ul>
            </AlertDescription>
          </Alert>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={isSaving}>
            <X className="mr-2 h-4 w-4" />
            取消
          </Button>
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                保存中...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                保存
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function TextTemplateEditor() {
  const [templates, setTemplates] = useState<EmailTemplate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<EmailTemplate | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [filterCategory, setFilterCategory] = useState<string>("all");

  useEffect(() => {
    fetchTemplates();
  }, []);

  const fetchTemplates = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.emailManagement.getEmailTemplates();
      setTemplates(response.data || []);
    } catch (err) {
      console.error("Failed to fetch templates:", err);
      setError(err instanceof Error ? err.message : "載入模板失敗");
    } finally {
      setIsLoading(false);
    }
  };

  const handleEditTemplate = (template: EmailTemplate) => {
    setSelectedTemplate(template);
    setEditOpen(true);
  };

  const handleSaveTemplate = (updatedTemplate: EmailTemplate) => {
    setTemplates((prev) =>
      prev.map((t) => (t.id === updatedTemplate.id ? updatedTemplate : t))
    );
  };

  const categories = Array.from(new Set(templates.map((t) => t.category)));
  const filteredTemplates =
    filterCategory === "all"
      ? templates
      : templates.filter((t) => t.category === filterCategory);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold mb-2">文字模板</h3>
          <p className="text-sm text-gray-600">
            這些模板存儲在資料庫中，可以直接編輯主旨和內容。
          </p>
        </div>

        {/* Category Filter */}
        <Select value={filterCategory} onValueChange={setFilterCategory}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="選擇類別" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">所有類別</SelectItem>
            {categories.map((category) => (
              <SelectItem key={category} value={category}>
                {category}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredTemplates.map((template) => (
          <Card key={template.id} className="hover:shadow-lg transition-shadow">
            <CardHeader>
              <div className="flex items-start justify-between">
                <div>
                  <CardTitle className="text-base">{template.template_name}</CardTitle>
                  <CardDescription className="text-xs mt-1">{template.template_key}</CardDescription>
                </div>
                <Badge variant={template.is_active ? "default" : "secondary"}>
                  {template.is_active ? "啟用" : "停用"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {template.description && (
                <p className="text-sm text-gray-600">{template.description}</p>
              )}

              {/* Subject Preview */}
              <div>
                <p className="text-xs font-semibold text-gray-700 mb-1">主旨預覽：</p>
                <p className="text-sm text-gray-800 line-clamp-1">{template.subject_template}</p>
              </div>

              {/* Body Preview */}
              <div>
                <p className="text-xs font-semibold text-gray-700 mb-1">內容預覽：</p>
                <p className="text-sm text-gray-600 line-clamp-3">{template.body_template}</p>
              </div>

              {/* Variables */}
              {template.variables && template.variables.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-700 mb-2">
                    變數 ({template.variables.length}):
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {template.variables.slice(0, 4).map((variable) => (
                      <Badge key={variable} variant="outline" className="text-xs">
                        {variable}
                      </Badge>
                    ))}
                    {template.variables.length > 4 && (
                      <Badge variant="outline" className="text-xs">
                        +{template.variables.length - 4}
                      </Badge>
                    )}
                  </div>
                </div>
              )}

              {/* Actions */}
              <Button
                size="sm"
                variant="default"
                onClick={() => handleEditTemplate(template)}
                className="w-full"
              >
                <Edit className="mr-2 h-4 w-4" />
                編輯模板
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      {filteredTemplates.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
          <p>未找到符合條件的模板</p>
        </div>
      )}

      <EditDialog
        template={selectedTemplate}
        open={editOpen}
        onClose={() => setEditOpen(false)}
        onSave={handleSaveTemplate}
      />
    </div>
  );
}
