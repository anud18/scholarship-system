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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { FileUpload } from "@/components/file-upload";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import {
  Loader2,
  AlertCircle,
  FileText,
  FormInput,
  Eye,
  CheckCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  ApplicationField,
  ApplicationDocument,
  ScholarshipFormConfig,
} from "@/lib/api";

type Locale = "zh" | "en";

interface DynamicApplicationFormProps {
  scholarshipType: string;
  locale?: Locale;
  onFieldChange?: (fieldName: string, value: any) => void;
  onFileChange?: (documentType: string, files: File[]) => void;
  initialValues?: Record<string, any>;
  initialFiles?: Record<string, File[]>;
  className?: string;
  selectedSubTypes?: string[];
  currentUserId?: number; // 當前用戶ID，用於預覽現有文件
}

interface FormData {
  [key: string]: any;
}

interface FileData {
  [key: string]: File[];
}

export function DynamicApplicationForm({
  scholarshipType,
  locale = "zh",
  onFieldChange,
  onFileChange,
  initialValues = {},
  initialFiles = {},
  className,
  selectedSubTypes,
  currentUserId,
}: DynamicApplicationFormProps) {
  // State
  const [formConfig, setFormConfig] = useState<ScholarshipFormConfig | null>(
    null
  );
  const [formData, setFormData] = useState<FormData>(initialValues);
  const [fileData, setFileData] = useState<FileData>(initialFiles);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
    downloadUrl?: string;
  } | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  // Load form configuration
  useEffect(() => {
    loadFormConfiguration();
  }, [scholarshipType]);

  // Update form data when initial values change
  useEffect(() => {
    setFormData(initialValues);
  }, [initialValues]);

  // Update file data when initial files change
  useEffect(() => {
    setFileData(initialFiles);
  }, [initialFiles]);

  const loadFormConfiguration = async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response =
        await api.applicationFields.getFormConfig(scholarshipType);

      if (response.success && response.data) {
        setFormConfig(response.data);
      } else {
        setError(
          locale === "zh"
            ? "無法載入表單配置"
            : "Failed to load form configuration"
        );
      }
    } catch (err) {
      console.error("Failed to load form configuration:", err);
      setError(
        locale === "zh"
          ? "載入表單配置時發生錯誤"
          : "Error loading form configuration"
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleFieldChange = (fieldName: string, value: any) => {
    const newFormData = { ...formData, [fieldName]: value };
    setFormData(newFormData);
    onFieldChange?.(fieldName, value);
  };

  const handleFileChange = (documentType: string, files: File[]) => {
    const newFileData = { ...fileData, [documentType]: files };
    setFileData(newFileData);
    onFileChange?.(documentType, files);
  };

  const handlePreviewExistingFile = (document: ApplicationDocument) => {
    if (!document.existing_file_url) return;

    // 從文件 URL 提取檔名
    const documentUrl = document.existing_file_url;
    const filename =
      documentUrl.split("/").pop()?.split("?")[0] || "bank_document";

    // 從 URL 中提取 token（如果有的話）
    let token = "";
    const urlParts = documentUrl.split("?");
    if (urlParts.length > 1) {
      const urlParams = new URLSearchParams(urlParts[1]);
      token = urlParams.get("token") || "";
    }

    // 如果 URL 中沒有 token，嘗試從存儲中獲取
    if (!token) {
      token =
        localStorage.getItem("auth_token") ||
        localStorage.getItem("token") ||
        sessionStorage.getItem("auth_token") ||
        sessionStorage.getItem("token") ||
        "";

      if (!token) {
        console.error("No authentication token available");
        return null;
      }
    }

    // 對於個人資料的文件，使用檔名作為 fileId
    const fileId = filename;
    const fileType = encodeURIComponent("存摺封面");

    // 使用傳遞的用戶ID或預設值
    const userId = currentUserId || 1;

    // 建立預覽 URL
    const previewUrl = `/api/v1/preview?fileId=${fileId}&filename=${encodeURIComponent(filename)}&type=${fileType}&userId=${userId}&token=${token}`;

    // 判斷文件類型
    let fileTypeDisplay = "other";
    if (filename.toLowerCase().endsWith(".pdf")) {
      fileTypeDisplay = "application/pdf";
    } else if (
      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"].some(ext =>
        filename.toLowerCase().endsWith(ext)
      )
    ) {
      fileTypeDisplay = "image";
    }

    // 設定預覽文件資訊並打開modal
    setPreviewFile({
      url: previewUrl,
      filename: filename,
      type: fileTypeDisplay,
      downloadUrl: documentUrl, // 使用原始URL作為下載連結
    });

    setShowPreview(true);
  };

  const handleClosePreview = () => {
    setShowPreview(false);
    setPreviewFile(null);
  };

  const getFieldLabel = (field: ApplicationField) => {
    return locale === "en" && field.field_label_en
      ? field.field_label_en
      : field.field_label;
  };

  const getFieldPlaceholder = (field: ApplicationField) => {
    return locale === "en" && field.placeholder_en
      ? field.placeholder_en
      : field.placeholder || "";
  };

  const getFieldHelpText = (field: ApplicationField) => {
    return locale === "en" && field.help_text_en
      ? field.help_text_en
      : field.help_text;
  };

  const getDocumentName = (doc: ApplicationDocument) => {
    return locale === "en" && doc.document_name_en
      ? doc.document_name_en
      : doc.document_name;
  };

  const getDocumentDescription = (doc: ApplicationDocument) => {
    return locale === "en" && doc.description_en
      ? doc.description_en
      : doc.description;
  };

  const getDocumentInstructions = (doc: ApplicationDocument) => {
    return locale === "en" && doc.upload_instructions_en
      ? doc.upload_instructions_en
      : doc.upload_instructions;
  };

  const renderField = (field: ApplicationField) => {
    if (!field.is_active) return null;

    // Use prefill value for fixed fields if no current value exists
    const fieldValue = formData[field.field_name] || field.prefill_value || "";
    const label = getFieldLabel(field);
    const placeholder = getFieldPlaceholder(field);
    const helpText = getFieldHelpText(field);

    // Add fixed field indicator
    const isFixedField = field.is_fixed === true;

    switch (field.field_type) {
      case "text":
      case "email":
        return (
          <div key={field.field_name} className="space-y-2">
            <Label htmlFor={field.field_name}>
              {label}
              {field.is_required && (
                <span className="text-red-500 ml-1">*</span>
              )}
              {isFixedField && (
                <Badge variant="outline" className="ml-2 text-xs">
                  {locale === "zh" ? "固定欄位" : "Fixed Field"}
                </Badge>
              )}
            </Label>
            <Input
              id={field.field_name}
              type={field.field_type}
              value={fieldValue}
              onChange={e =>
                handleFieldChange(field.field_name, e.target.value)
              }
              placeholder={placeholder}
              maxLength={field.max_length}
              required={field.is_required}
              className={`w-full ${isFixedField ? "bg-blue-50 border-blue-200" : ""}`}
            />
            {isFixedField && fieldValue && (
              <p className="text-sm text-blue-600">
                {locale === "zh"
                  ? "此欄位已從您的個人檔案自動填入，您可以修改內容"
                  : "This field has been auto-filled from your profile and can be modified"}
              </p>
            )}
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      case "number":
        return (
          <div key={field.field_name} className="space-y-2">
            <Label htmlFor={field.field_name}>
              {label}
              {field.is_required && (
                <span className="text-red-500 ml-1">*</span>
              )}
              {isFixedField && (
                <Badge variant="outline" className="ml-2 text-xs">
                  {locale === "zh" ? "固定欄位" : "Fixed Field"}
                </Badge>
              )}
            </Label>
            <Input
              id={field.field_name}
              type="number"
              value={fieldValue}
              onChange={e =>
                handleFieldChange(
                  field.field_name,
                  parseFloat(e.target.value) || ""
                )
              }
              placeholder={placeholder}
              min={field.min_value}
              max={field.max_value}
              step={field.step_value}
              required={field.is_required}
              className={`w-full ${isFixedField ? "bg-blue-50 border-blue-200" : ""}`}
            />
            {isFixedField && fieldValue && (
              <p className="text-sm text-blue-600">
                {locale === "zh"
                  ? "此欄位已從您的個人檔案自動填入，您可以修改內容"
                  : "This field has been auto-filled from your profile and can be modified"}
              </p>
            )}
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      case "date":
        return (
          <div key={field.field_name} className="space-y-2">
            <Label htmlFor={field.field_name}>
              {label}
              {field.is_required && (
                <span className="text-red-500 ml-1">*</span>
              )}
              {isFixedField && (
                <Badge variant="outline" className="ml-2 text-xs">
                  {locale === "zh" ? "固定欄位" : "Fixed Field"}
                </Badge>
              )}
            </Label>
            <Input
              id={field.field_name}
              type="date"
              value={fieldValue}
              onChange={e =>
                handleFieldChange(field.field_name, e.target.value)
              }
              required={field.is_required}
              className={`w-full ${isFixedField ? "bg-blue-50 border-blue-200" : ""}`}
            />
            {isFixedField && fieldValue && (
              <p className="text-sm text-blue-600">
                {locale === "zh"
                  ? "此欄位已從您的個人檔案自動填入，您可以修改內容"
                  : "This field has been auto-filled from your profile and can be modified"}
              </p>
            )}
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      case "textarea":
        return (
          <div key={field.field_name} className="space-y-2">
            <Label htmlFor={field.field_name}>
              {label}
              {field.is_required && (
                <span className="text-red-500 ml-1">*</span>
              )}
              {isFixedField && (
                <Badge variant="outline" className="ml-2 text-xs">
                  {locale === "zh" ? "固定欄位" : "Fixed Field"}
                </Badge>
              )}
            </Label>
            <Textarea
              id={field.field_name}
              value={fieldValue}
              onChange={e =>
                handleFieldChange(field.field_name, e.target.value)
              }
              placeholder={placeholder}
              maxLength={field.max_length}
              required={field.is_required}
              className={`w-full min-h-[120px] ${isFixedField ? "bg-blue-50 border-blue-200" : ""}`}
              rows={6}
            />
            {isFixedField && fieldValue && (
              <p className="text-sm text-blue-600">
                {locale === "zh"
                  ? "此欄位已從您的個人檔案自動填入，您可以修改內容"
                  : "This field has been auto-filled from your profile and can be modified"}
              </p>
            )}
            {field.max_length && (
              <p className="text-sm text-muted-foreground text-right">
                {fieldValue?.length || 0} / {field.max_length}
              </p>
            )}
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      case "select":
        return (
          <div key={field.field_name} className="space-y-2">
            <Label htmlFor={field.field_name}>
              {label}
              {field.is_required && (
                <span className="text-red-500 ml-1">*</span>
              )}
            </Label>
            <Select
              value={fieldValue}
              onValueChange={value =>
                handleFieldChange(field.field_name, value)
              }
              required={field.is_required}
            >
              <SelectTrigger>
                <SelectValue placeholder={placeholder} />
              </SelectTrigger>
              <SelectContent>
                {field.field_options?.map(option => (
                  <SelectItem key={option.value} value={option.value}>
                    {locale === "en" && option.label_en
                      ? option.label_en
                      : option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      case "checkbox":
        return (
          <div key={field.field_name} className="space-y-2">
            <div className="flex items-center space-x-2">
              <Checkbox
                id={field.field_name}
                checked={fieldValue || false}
                onCheckedChange={checked =>
                  handleFieldChange(field.field_name, checked)
                }
                required={field.is_required}
              />
              <Label htmlFor={field.field_name} className="text-sm font-normal">
                {label}
                {field.is_required && (
                  <span className="text-red-500 ml-1">*</span>
                )}
              </Label>
            </div>
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      case "radio":
        return (
          <div key={field.field_name} className="space-y-2">
            <Label>
              {label}
              {field.is_required && (
                <span className="text-red-500 ml-1">*</span>
              )}
            </Label>
            <div className="space-y-2">
              {field.field_options?.map(option => (
                <div key={option.value} className="flex items-center space-x-2">
                  <input
                    type="radio"
                    id={`${field.field_name}_${option.value}`}
                    name={field.field_name}
                    value={option.value}
                    checked={fieldValue === option.value}
                    onChange={e =>
                      handleFieldChange(field.field_name, e.target.value)
                    }
                    required={field.is_required}
                    className="w-4 h-4"
                  />
                  <Label
                    htmlFor={`${field.field_name}_${option.value}`}
                    className="text-sm font-normal"
                  >
                    {locale === "en" && option.label_en
                      ? option.label_en
                      : option.label}
                  </Label>
                </div>
              ))}
            </div>
            {helpText && (
              <p className="text-sm text-muted-foreground">{helpText}</p>
            )}
          </div>
        );

      default:
        return null;
    }
  };

  const renderDocument = (document: ApplicationDocument) => {
    if (!document.is_active) return null;

    const documentName = getDocumentName(document);
    const description = getDocumentDescription(document);
    const instructions = getDocumentInstructions(document);
    const files = fileData[document.document_name] || [];
    const isFixedDocument = document.is_fixed === true;

    return (
      <div
        key={document.document_name}
        className={`space-y-3 p-4 border rounded-lg ${isFixedDocument ? "border-blue-200 bg-blue-50/50" : ""}`}
      >
        <div className="flex items-center justify-between">
          <Label className="text-base font-medium">
            {documentName}
            {document.is_required && (
              <span className="text-red-500 ml-1">*</span>
            )}
            {isFixedDocument && (
              <Badge variant="outline" className="ml-2 text-xs">
                {locale === "zh" ? "固定文件" : "Fixed Document"}
              </Badge>
            )}
          </Label>
          {files.length > 0 && (
            <Badge variant="secondary" className="text-xs">
              {files.length} {locale === "zh" ? "個檔案" : "files"}
            </Badge>
          )}
        </div>

        {isFixedDocument && document.existing_file_url && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium">
              {locale === "zh"
                ? "已上傳檔案 (1/1) - "
                : "Uploaded files (1/1) - "}
              {documentName}
            </h4>
            <Card>
              <CardContent className="flex items-center justify-between p-3">
                <div className="flex items-center space-x-3">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">
                      {locale === "zh" ? "存摺封面" : "Bank Book Cover"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <span className="ml-1 text-blue-600">
                        {locale === "zh" ? "已上傳" : "Uploaded"}
                      </span>
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  {/* 預覽按鈕 */}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handlePreviewExistingFile(document)}
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Badge variant="outline" className="text-xs">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    {locale === "zh" ? "已存在" : "Exists"}
                  </Badge>
                </div>
              </CardContent>
            </Card>
            <p className="text-xs text-blue-600">
              {locale === "zh"
                ? "您可以上傳新檔案來替換現有檔案"
                : "You can upload a new file to replace the existing one"}
            </p>
          </div>
        )}

        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}

        <FileUpload
          onFilesChange={files =>
            handleFileChange(document.document_name, files)
          }
          acceptedTypes={document.accepted_file_types.map(
            type => `.${type.toLowerCase()}`
          )}
          maxSize={
            parseInt(document.max_file_size.replace(/[^\d]/g, "")) * 1024 * 1024
          } // Convert MB to bytes
          maxFiles={document.max_file_count}
          initialFiles={files}
          fileType={document.document_name}
          locale={locale}
        />

        <div className="text-xs text-muted-foreground space-y-1">
          <p>
            {locale === "zh" ? "接受格式：" : "Accepted formats: "}
            {document.accepted_file_types.join(", ")}
          </p>
          <p>
            {locale === "zh" ? "檔案大小限制：" : "File size limit: "}
            {document.max_file_size}
          </p>
          <p>
            {locale === "zh" ? "最多檔案數：" : "Maximum files: "}
            {document.max_file_count}
          </p>
          {instructions && <p className="text-blue-600">{instructions}</p>}

          {/* Example File Preview Button */}
          {document.example_file_url && (
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                const token = localStorage.getItem("auth_token");
                const previewUrl = `/api/v1/preview-document-example?documentId=${document.id}&token=${token}`;

                // Create and trigger download/preview
                const link = window.document.createElement('a');
                link.href = previewUrl;
                link.target = '_blank';
                link.rel = 'noopener noreferrer';
                link.click();
              }}
              className="flex items-center gap-1 text-blue-600 hover:text-blue-800 text-sm font-medium mt-2"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              {locale === "zh" ? "查看範例文件" : "View Example"}
            </button>
          )}
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className={`flex items-center justify-center py-8 ${className}`}>
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">
          {locale === "zh" ? "載入表單中..." : "Loading form..."}
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={className}>
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </div>
    );
  }

  if (!formConfig) {
    return (
      <div className={className}>
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {locale === "zh"
              ? "尚未設定表單配置"
              : "Form configuration not available"}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const activeFields = formConfig.fields
    .filter(field => field.is_active)
    .sort((a, b) => a.display_order - b.display_order);

  const activeDocuments = formConfig.documents
    .filter(doc => doc.is_active)
    .sort((a, b) => a.display_order - b.display_order);

  return (
    <div className={`space-y-6 ${className}`}>
      {/* Application Fields */}
      {activeFields.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FormInput className="h-5 w-5" />
              {locale === "zh" ? "申請資訊" : "Application Information"}
            </CardTitle>
            <CardDescription>
              {locale === "zh"
                ? "請填寫所有必要資訊"
                : "Please fill in all required information"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {activeFields.map(renderField)}
          </CardContent>
        </Card>
      )}

      {/* Document Requirements */}
      {activeDocuments.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              {locale === "zh" ? "必要文件" : "Required Documents"}
            </CardTitle>
            <CardDescription>
              {locale === "zh"
                ? "請上傳所有必要文件"
                : "Please upload all required documents"}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {activeDocuments.map(renderDocument)}
          </CardContent>
        </Card>
      )}

      {activeFields.length === 0 && activeDocuments.length === 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            {locale === "zh"
              ? "此獎學金類型尚未設定申請要求"
              : "No application requirements configured for this scholarship type"}
          </AlertDescription>
        </Alert>
      )}

      {/* File Preview Dialog */}
      <FilePreviewDialog
        isOpen={showPreview}
        onClose={handleClosePreview}
        file={previewFile}
        locale={locale}
      />
    </div>
  );
}
