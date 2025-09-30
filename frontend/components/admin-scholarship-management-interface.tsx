"use client";

import { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  FormInput,
  FileText,
  UserCheck,
  Plus,
  Edit,
  Trash2,
  Save,
  GraduationCap,
  Loader2,
  AlertCircle,
  CheckCircle,
} from "lucide-react";
import { WhitelistManagement } from "@/components/whitelist-management";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ApplicationFieldForm } from "@/components/application-field-form";
import { ApplicationDocumentForm } from "@/components/application-document-form";
import { api } from "@/lib/api";
import type {
  ApplicationField,
  ApplicationDocument,
  ScholarshipFormConfig,
  ApplicationFieldCreate,
  ApplicationFieldUpdate,
  ApplicationDocumentCreate,
  ApplicationDocumentUpdate,
} from "@/lib/api";

type ScholarshipType = "undergraduate_freshman" | "direct_phd" | "phd";

interface AdminScholarshipManagementInterfaceProps {
  type: ScholarshipType;
  className?: string;
}

export function AdminScholarshipManagementInterface({
  type,
  className,
}: AdminScholarshipManagementInterfaceProps) {
  // State for form configuration
  const [formConfig, setFormConfig] = useState<ScholarshipFormConfig | null>(
    null
  );
  const [applicationFields, setApplicationFields] = useState<
    ApplicationField[]
  >([]);
  const [documentRequirements, setDocumentRequirements] = useState<
    ApplicationDocument[]
  >([]);

  // Loading and error states
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Form states
  const [fieldFormOpen, setFieldFormOpen] = useState(false);
  const [documentFormOpen, setDocumentFormOpen] = useState(false);
  const [editingField, setEditingField] = useState<ApplicationField | null>(
    null
  );
  const [editingDocument, setEditingDocument] =
    useState<ApplicationDocument | null>(null);

  // Auto-hide success message
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => {
        setSuccessMessage(null);
      }, 3000);

      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  // Load form configuration on component mount
  useEffect(() => {
    loadFormConfig();
  }, [type]);

  const loadFormConfig = async () => {
    try {
      setIsLoading(true);
      setError(null);
      // 管理端需要看到所有欄位（包括停用的）
      const response = await api.applicationFields.getFormConfig(type, true);
      if (response.success && response.data) {
        const { fields = [], documents = [] } = response.data;
        setFormConfig(response.data);
        setApplicationFields(fields);
        setDocumentRequirements(documents);
      } else {
        setApplicationFields([]);
        setDocumentRequirements([]);
        setFormConfig(null);
        setError("尚未設定表單配置，請先於後台建立。");
      }
    } catch (err) {
      console.error("Failed to load form configuration:", err);
      setApplicationFields([]);
      setDocumentRequirements([]);
      setFormConfig(null);
      setError("載入表單配置時發生錯誤，請稍後再試");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSaveSettings = async () => {
    try {
      setIsSaving(true);
      setError(null);
      setSuccessMessage(null);

      // Prepare data for API
      const configData = {
        fields: applicationFields.map(field => ({
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
          field_options: field.field_options,
          display_order: field.display_order,
          is_active: field.is_active,
          help_text: field.help_text,
          help_text_en: field.help_text_en,
          validation_rules: field.validation_rules,
          conditional_rules: field.conditional_rules,
        })),
        documents: documentRequirements.map(doc => ({
          document_name: doc.document_name,
          document_name_en: doc.document_name_en,
          description: doc.description,
          description_en: doc.description_en,
          is_required: doc.is_required,
          accepted_file_types: doc.accepted_file_types,
          max_file_size: doc.max_file_size,
          max_file_count: doc.max_file_count,
          display_order: doc.display_order,
          is_active: doc.is_active,
          upload_instructions: doc.upload_instructions,
          upload_instructions_en: doc.upload_instructions_en,
          validation_rules: doc.validation_rules,
        })),
      };

      const response = await api.applicationFields.saveFormConfig(
        type,
        configData
      );

      if (response.success) {
        setSuccessMessage(`${formConfig?.title}設定已成功保存`);
        // 不要重新載入配置，保持當前狀態
        // 只有在需要獲取新的 ID 時才重新載入
        const savedConfig = response.data;
        if (savedConfig) {
          // 更新現有項目的 ID（如果是新創建的）
          if (savedConfig.fields) {
            setApplicationFields(prev =>
              prev.map(field => {
                const updatedField = savedConfig.fields?.find(
                  f => f.field_name === field.field_name
                );
                return updatedField ? { ...field, id: updatedField.id } : field;
              })
            );
          }
          if (savedConfig.documents) {
            setDocumentRequirements(prev =>
              prev.map(doc => {
                const updatedDoc = savedConfig.documents?.find(
                  d => d.document_name === doc.document_name
                );
                return updatedDoc ? { ...doc, id: updatedDoc.id } : doc;
              })
            );
          }
        }
      } else {
        setError(response.message || "保存設定時發生錯誤");
      }
    } catch (err) {
      console.error("Failed to save configuration:", err);
      setError("保存設定時發生錯誤，請稍後再試");
    } finally {
      setIsSaving(false);
    }
  };

  // Field management handlers
  const handleCreateField = async (fieldData: ApplicationFieldCreate) => {
    try {
      const response = await api.applicationFields.createField(fieldData);
      if (response.success && response.data) {
        const newField = response.data;
        setApplicationFields(prev => [...prev, newField]);
        setSuccessMessage("欄位新增成功");
        setFieldFormOpen(false);
      } else {
        setError(response.message || "新增欄位失敗");
      }
    } catch (err) {
      console.error("Failed to create field:", err);
      setError("新增欄位失敗，請稍後再試");
    }
  };

  const handleUpdateField = async (fieldData: ApplicationFieldUpdate) => {
    if (!editingField) return;

    try {
      const response = await api.applicationFields.updateField(
        editingField.id,
        fieldData
      );
      if (response.success && response.data) {
        const updatedField = response.data;
        setApplicationFields(prev =>
          prev.map(field =>
            field.id === editingField.id ? updatedField : field
          )
        );
        setSuccessMessage("欄位更新成功");
        setFieldFormOpen(false);
        setEditingField(null);
      } else {
        setError(response.message || "更新欄位失敗");
      }
    } catch (err) {
      console.error("Failed to update field:", err);
      setError("更新欄位失敗，請稍後再試");
    }
  };

  const handleDeleteField = async (fieldId: number) => {
    try {
      const response = await api.applicationFields.deleteField(fieldId);
      if (response.success) {
        setApplicationFields(prev =>
          prev.filter(field => field.id !== fieldId)
        );
        setSuccessMessage("欄位刪除成功");
      } else {
        setError(response.message || "刪除欄位失敗");
      }
    } catch (err) {
      console.error("Failed to delete field:", err);
      setError("刪除欄位失敗，請稍後再試");
    }
  };

  // Document management handlers
  const handleCreateDocument = async (
    documentData: ApplicationDocumentCreate
  ) => {
    try {
      const response = await api.applicationFields.createDocument(documentData);
      if (response.success && response.data) {
        const newDocument = response.data;
        setDocumentRequirements(prev => [...prev, newDocument]);
        setSuccessMessage("文件要求新增成功");
        setDocumentFormOpen(false);
      } else {
        setError(response.message || "新增文件要求失敗");
      }
    } catch (err) {
      console.error("Failed to create document:", err);
      setError("新增文件要求失敗，請稍後再試");
    }
  };

  const handleFieldSave = async (
    fieldData: ApplicationFieldCreate | ApplicationFieldUpdate
  ) => {
    if (editingField) {
      await handleUpdateField(fieldData as ApplicationFieldUpdate);
    } else {
      await handleCreateField(fieldData as ApplicationFieldCreate);
    }
  };

  const handleDocumentSave = async (
    documentData: ApplicationDocumentCreate | ApplicationDocumentUpdate
  ) => {
    if (editingDocument) {
      await handleUpdateDocument(documentData as ApplicationDocumentUpdate);
    } else {
      await handleCreateDocument(documentData as ApplicationDocumentCreate);
    }
  };

  const handleUpdateDocument = async (
    documentData: ApplicationDocumentUpdate
  ) => {
    if (!editingDocument) return;

    try {
      const response = await api.applicationFields.updateDocument(
        editingDocument.id,
        documentData
      );
      if (response.success && response.data) {
        const updatedDocument = response.data;
        setDocumentRequirements(prev =>
          prev.map(doc =>
            doc.id === editingDocument.id ? updatedDocument : doc
          )
        );
        setSuccessMessage("文件要求更新成功");
        setDocumentFormOpen(false);
        setEditingDocument(null);
      } else {
        setError(response.message || "更新文件要求失敗");
      }
    } catch (err) {
      console.error("Failed to update document:", err);
      setError("更新文件要求失敗，請稍後再試");
    }
  };

  const handleDeleteDocument = async (documentId: number) => {
    try {
      const response = await api.applicationFields.deleteDocument(documentId);
      if (response.success) {
        setDocumentRequirements(prev =>
          prev.filter(doc => doc.id !== documentId)
        );
        setSuccessMessage("文件要求刪除成功");
      } else {
        setError(response.message || "刪除文件要求失敗");
      }
    } catch (err) {
      console.error("Failed to delete document:", err);
      setError("刪除文件要求失敗，請稍後再試");
    }
  };

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center py-8 ${className}`}>
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">載入設定中...</span>
      </div>
    );
  }

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Error/Success Messages */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {successMessage && (
        <Alert
          variant="default"
          className="border-green-200 bg-green-50 text-green-800"
        >
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>{successMessage}</AlertDescription>
        </Alert>
      )}

      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div
            className={`p-3 rounded-lg ${formConfig?.color === "blue" ? "bg-blue-100" : formConfig?.color === "purple" ? "bg-purple-100" : "bg-green-100"}`}
          >
            <GraduationCap
              className={`h-6 w-6 ${formConfig?.color === "blue" ? "text-blue-600" : formConfig?.color === "purple" ? "text-purple-600" : "text-green-600"}`}
            />
          </div>
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {formConfig?.title}管理設定
            </h2>
            <p className="text-sm text-gray-600">
              管理申請要求、文件設定{formConfig?.hasWhitelist ? "和白名單" : ""}
            </p>
          </div>
        </div>
        <Button
          onClick={handleSaveSettings}
          disabled={isSaving}
          className="nycu-gradient text-white px-6"
        >
          {isSaving ? (
            <>
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              儲存中...
            </>
          ) : (
            <>
              <Save className="h-4 w-4 mr-2" />
              儲存所有設定
            </>
          )}
        </Button>
      </div>

      {/* Main Content */}
      <Tabs defaultValue="fields" className="space-y-6">
        <TabsList
          className={`grid w-full ${formConfig?.hasWhitelist ? "grid-cols-3" : "grid-cols-2"}`}
        >
          <TabsTrigger value="fields" className="flex items-center gap-2">
            <FormInput className="h-4 w-4" />
            申請欄位
          </TabsTrigger>
          <TabsTrigger value="documents" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            文件要求
          </TabsTrigger>
          {formConfig?.hasWhitelist && (
            <TabsTrigger value="whitelist" className="flex items-center gap-2">
              <UserCheck className="h-4 w-4" />
              白名單管理
            </TabsTrigger>
          )}
        </TabsList>

        {/* Application Fields Tab */}
        <TabsContent value="fields" className="space-y-4">
          <Card className="border-2 border-gray-100 shadow-sm">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <FormInput className="h-5 w-5 text-blue-600" />
                    申請表單欄位管理
                  </CardTitle>
                  <CardDescription className="text-gray-600">
                    設定{formConfig?.title}申請表單中的欄位類型、驗證規則和要求
                  </CardDescription>
                </div>
                <Button
                  onClick={() => {
                    setEditingField(null);
                    setFieldFormOpen(true);
                  }}
                  className="nycu-gradient text-white"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  新增欄位
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Fields Table */}
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader className="bg-gray-50">
                    <TableRow>
                      <TableHead className="font-semibold">欄位資訊</TableHead>
                      <TableHead className="font-semibold">類型</TableHead>
                      <TableHead className="font-semibold">必填</TableHead>
                      <TableHead className="font-semibold">狀態</TableHead>
                      <TableHead className="font-semibold">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {applicationFields.map(field => (
                      <TableRow
                        key={field.id || field.field_name}
                        className="hover:bg-gray-50"
                      >
                        <TableCell>
                          <div>
                            <div className="font-medium text-gray-900">
                              {field.field_label}
                            </div>
                            <div className="text-sm text-gray-500">
                              {field.field_name}
                            </div>
                            {field.placeholder && (
                              <div className="text-xs text-gray-400 mt-1">
                                {field.placeholder}
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className="capitalize font-medium"
                          >
                            {field.field_type}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              field.is_required ? "destructive" : "secondary"
                            }
                          >
                            {field.is_required ? "必填" : "選填"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Switch
                              checked={field.is_active}
                              onCheckedChange={checked => {
                                setApplicationFields(prev =>
                                  prev.map(f =>
                                    f.field_name === field.field_name
                                      ? { ...f, is_active: checked }
                                      : f
                                  )
                                );
                              }}
                            />
                            <span
                              className={`text-xs ${field.is_active ? "text-green-600" : "text-gray-500"}`}
                            >
                              {field.is_active ? "啟用" : "停用"}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditingField(field);
                                setFieldFormOpen(true);
                              }}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            {field.id && field.id > 0 && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleDeleteField(field.id)}
                                className="text-red-600 hover:text-red-700"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Documents Tab */}
        <TabsContent value="documents" className="space-y-4">
          <Card className="border-2 border-gray-100 shadow-sm">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <FileText className="h-5 w-5 text-green-600" />
                    申請文件管理
                  </CardTitle>
                  <CardDescription className="text-gray-600">
                    設定{formConfig?.title}
                    申請時需要上傳的文件類型、格式和大小限制
                  </CardDescription>
                </div>
                <Button
                  onClick={() => {
                    setEditingDocument(null);
                    setDocumentFormOpen(true);
                  }}
                  className="nycu-gradient text-white"
                >
                  <Plus className="h-4 w-4 mr-2" />
                  新增文件
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Documents Table */}
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader className="bg-gray-50">
                    <TableRow>
                      <TableHead className="font-semibold">文件資訊</TableHead>
                      <TableHead className="font-semibold">必要性</TableHead>
                      <TableHead className="font-semibold">支援格式</TableHead>
                      <TableHead className="font-semibold">大小限制</TableHead>
                      <TableHead className="font-semibold">狀態</TableHead>
                      <TableHead className="font-semibold">操作</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {documentRequirements.map(doc => (
                      <TableRow
                        key={doc.id || doc.document_name}
                        className="hover:bg-gray-50"
                      >
                        <TableCell>
                          <div>
                            <div className="font-medium text-gray-900">
                              {doc.document_name}
                            </div>
                            <div className="text-sm text-gray-500">
                              {doc.description}
                            </div>
                            {doc.upload_instructions && (
                              <div className="text-xs text-gray-400 mt-1">
                                {doc.upload_instructions}
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              doc.is_required ? "destructive" : "secondary"
                            }
                          >
                            {doc.is_required ? "必要" : "選填"}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-1 flex-wrap">
                            {doc.accepted_file_types.map(type => (
                              <Badge
                                key={type}
                                variant="outline"
                                className="text-xs"
                              >
                                {type}
                              </Badge>
                            ))}
                          </div>
                        </TableCell>
                        <TableCell>
                          <span className="text-sm font-medium text-gray-700">
                            {doc.max_file_size}
                          </span>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Switch
                              checked={doc.is_active}
                              onCheckedChange={checked => {
                                setDocumentRequirements(prev =>
                                  prev.map(d =>
                                    d.document_name === doc.document_name
                                      ? { ...d, is_active: checked }
                                      : d
                                  )
                                );
                              }}
                            />
                            <span
                              className={`text-xs ${doc.is_active ? "text-green-600" : "text-gray-500"}`}
                            >
                              {doc.is_active ? "啟用" : "停用"}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditingDocument(doc);
                                setDocumentFormOpen(true);
                              }}
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            {doc.id && doc.id > 0 && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleDeleteDocument(doc.id)}
                                className="text-red-600 hover:text-red-700"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Whitelist Tab */}
        {formConfig?.hasWhitelist && (
          <TabsContent value="whitelist" className="space-y-4">
            <WhitelistManagement
              scholarshipType={type}
              title={`${formConfig.title}白名單管理`}
            />
          </TabsContent>
        )}
      </Tabs>

      {/* Application Field Form */}
      <ApplicationFieldForm
        field={editingField}
        scholarshipType={type}
        isOpen={fieldFormOpen}
        onClose={() => {
          setFieldFormOpen(false);
          setEditingField(null);
        }}
        onSave={handleFieldSave}
        mode={editingField ? "edit" : "create"}
      />

      {/* Application Document Form */}
      <ApplicationDocumentForm
        document={editingDocument}
        scholarshipType={type}
        isOpen={documentFormOpen}
        onClose={() => {
          setDocumentFormOpen(false);
          setEditingDocument(null);
        }}
        onSave={handleDocumentSave}
        mode={editingDocument ? "edit" : "create"}
      />
    </div>
  );
}
