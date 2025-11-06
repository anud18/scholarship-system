"use client";

import { useState, useEffect, useRef } from "react";
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
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
  Upload,
  Eye,
  Search,
  Download,
  FileSpreadsheet,
} from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { ApplicationFieldForm } from "@/components/application-field-form";
import { ApplicationDocumentForm } from "@/components/application-document-form";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { api } from "@/lib/api";
import type {
  ApplicationField,
  ApplicationDocument,
  ScholarshipFormConfig,
  ApplicationFieldCreate,
  ApplicationFieldUpdate,
  ApplicationDocumentCreate,
  ApplicationDocumentUpdate,
  WhitelistResponse,
} from "@/lib/api";
import { toast } from "sonner";

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

  // Terms document upload
  const [termsFile, setTermsFile] = useState<File | null>(null);
  const [isUploadingTerms, setIsUploadingTerms] = useState(false);

  // Terms preview modal
  const [showTermsPreview, setShowTermsPreview] = useState(false);
  const [termsPreviewFile, setTermsPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  // Example file upload and preview
  const [uploadingExampleDocId, setUploadingExampleDocId] = useState<number | null>(null);
  const [showExamplePreview, setShowExamplePreview] = useState(false);
  const [examplePreviewFile, setExamplePreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  // Form states
  const [fieldFormOpen, setFieldFormOpen] = useState(false);
  const [documentFormOpen, setDocumentFormOpen] = useState(false);
  const [editingField, setEditingField] = useState<ApplicationField | null>(
    null
  );
  const [editingDocument, setEditingDocument] =
    useState<ApplicationDocument | null>(null);

  // Scholarship type data for whitelist
  const [scholarshipTypeData, setScholarshipTypeData] = useState<any | null>(null);
  const [activeConfigId, setActiveConfigId] = useState<number | null>(null);

  // Whitelist management states
  const [whitelist, setWhitelist] = useState<WhitelistResponse[]>([]);
  const [loadingWhitelist, setLoadingWhitelist] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedWhitelistTab, setSelectedWhitelistTab] = useState<string>("all");
  const [selectedStudents, setSelectedStudents] = useState<Set<string>>(new Set());
  const [newStudentNycuId, setNewStudentNycuId] = useState("");
  const [newStudentSubType, setNewStudentSubType] = useState("");
  const [addingStudent, setAddingStudent] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    loadScholarshipData();
  }, [type]);

  const loadFormConfig = async () => {
    try {
      setIsLoading(true);
      setError(null);
      // 管理端需要看到所有欄位（包括停用的）
      const response = await api.applicationFields.getFormConfig(type, true);
      if (response.success && response.data) {
        const config = response.data as ScholarshipFormConfig;
        const { fields = [], documents = [] } = config;
        setFormConfig(config);
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

  const loadScholarshipData = async () => {
    try {
      setLoadingWhitelist(true);
      const response = await api.scholarships.getAll();
      if (response.success && response.data) {
        // Find scholarship matching the type prop by code
        const scholarships = response.data as any[];
        const scholarship = scholarships.find(s => s.code === type);
        if (scholarship) {
          setScholarshipTypeData(scholarship);
          const configId = scholarship.configuration_id;
          setActiveConfigId(configId);

          // Initialize sub_type for new student form
          if (scholarship.eligible_sub_types && scholarship.eligible_sub_types.length > 0) {
            setNewStudentSubType(scholarship.eligible_sub_types[0].value || scholarship.eligible_sub_types[0]);
          }

          // Load whitelist if configuration exists
          if (configId && scholarship.whitelist_enabled) {
            await loadWhitelist(configId);
          }
        }
      }
    } catch (err) {
      console.error("Failed to load scholarship data:", err);
      toast.error("無法載入獎學金資料");
    } finally {
      setLoadingWhitelist(false);
    }
  };

  const loadWhitelist = async (configId: number) => {
    try {
      setLoadingWhitelist(true);
      const response = await api.whitelist.getConfigurationWhitelist(configId);
      if (response.success && response.data) {
        setWhitelist(response.data as WhitelistResponse[]);
      }
    } catch (err: any) {
      console.error("Failed to load whitelist:", err);
      toast.error(err.message || "無法載入白名單");
    } finally {
      setLoadingWhitelist(false);
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
        const savedConfig = response.data as ScholarshipFormConfig;
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

  const handleTermsUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setIsUploadingTerms(true);
      setError(null);
      setSuccessMessage(null);

      const formData = new FormData();
      formData.append("file", file);

      // Get auth token from localStorage (same as api client)
      const token = typeof window !== "undefined"
        ? window.localStorage?.getItem("auth_token")
        : null;

      // Use relative path to leverage Next.js API proxy (CLAUDE.md architecture)
      const response = await fetch(
        `/api/v1/scholarships/${type}/upload-terms`,
        {
          method: "POST",
          body: formData,
          credentials: "include",
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSuccessMessage("申請條款文件上傳成功");
        setTermsFile(file);
        // Reload config to get updated terms URL
        await loadFormConfig();
      } else {
        const errorData = await response.json();
        setError(errorData.message || "上傳申請條款文件失敗");
      }
    } catch (err) {
      console.error("Failed to upload terms document:", err);
      setError("上傳申請條款文件失敗，請稍後再試");
    } finally {
      setIsUploadingTerms(false);
      // Reset file input
      event.target.value = "";
    }
  };

  const handleCloseTermsPreview = () => {
    setShowTermsPreview(false);
    setTermsPreviewFile(null);
  };

  // Field management handlers
  const handleCreateField = async (fieldData: ApplicationFieldCreate) => {
    try {
      const response = await api.applicationFields.createField(fieldData as any);
      if (response.success && response.data) {
        const newField = response.data as unknown as ApplicationField;
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
        const updatedField = response.data as unknown as ApplicationField;
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
      const response = await api.applicationFields.createDocument(documentData as any);
      if (response.success && response.data) {
        const newDocument = response.data as unknown as ApplicationDocument;
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
        const updatedDocument = response.data as unknown as ApplicationDocument;
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

  // Example file handlers
  const handleUploadExample = async (
    documentId: number,
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setUploadingExampleDocId(documentId);
      setError(null);
      setSuccessMessage(null);

      const response = await api.applicationFields.uploadDocumentExample(
        documentId,
        file
      );

      if (response.success) {
        // Update the document in state with new example_file_url
        setDocumentRequirements(prev =>
          prev.map(doc =>
            doc.id === documentId
              ? { ...doc, example_file_url: response.data.example_file_url }
              : doc
          )
        );
        setSuccessMessage("範例文件上傳成功");
      } else {
        setError(response.message || "範例文件上傳失敗");
      }
    } catch (err: any) {
      console.error("Failed to upload example:", err);
      setError(err.message || "範例文件上傳失敗，請稍後再試");
    } finally {
      setUploadingExampleDocId(null);
      // Reset file input
      event.target.value = "";
    }
  };

  const handlePreviewExample = (documentId: number, documentName: string) => {
    const token =
      typeof window !== "undefined"
        ? window.localStorage?.getItem("auth_token")
        : null;

    const encodedDocumentId = encodeURIComponent(String(documentId));
    const encodedToken = encodeURIComponent(token || "");
    const previewUrl = `/api/v1/preview-document-example?documentId=${encodedDocumentId}&token=${encodedToken}`;

    setExamplePreviewFile({
      url: previewUrl,
      filename: `${documentName}_範例`,
      type: "application/pdf",
    });
    setShowExamplePreview(true);
  };

  const handleCloseExamplePreview = () => {
    setShowExamplePreview(false);
    setExamplePreviewFile(null);
  };

  const handleDeleteExample = async (documentId: number) => {
    if (!confirm("確定要刪除此範例文件嗎？")) return;

    try {
      const response = await api.applicationFields.deleteDocumentExample(
        documentId
      );

      if (response.success) {
        // Update the document in state to remove example_file_url
        setDocumentRequirements(prev =>
          prev.map(doc =>
            doc.id === documentId ? { ...doc, example_file_url: undefined } : doc
          )
        );
        setSuccessMessage("範例文件刪除成功");
      } else {
        setError(response.message || "範例文件刪除失敗");
      }
    } catch (err) {
      console.error("Failed to delete example:", err);
      setError("範例文件刪除失敗，請稍後再試");
    }
  };

  // Whitelist operation functions
  const handleAddStudent = async () => {
    if (!newStudentNycuId.trim() || !newStudentSubType || !activeConfigId) {
      toast.error("請填寫學號和選擇子獎學金類型");
      return;
    }

    setAddingStudent(true);
    try {
      const response = await api.whitelist.batchAddWhitelist(activeConfigId, {
        students: [{ nycu_id: newStudentNycuId.trim(), sub_type: newStudentSubType }],
      });

      if (response.success) {
        toast.success(`已將學號 ${newStudentNycuId} 加入白名單`);
        setNewStudentNycuId("");
        if (activeConfigId) {
          await loadWhitelist(activeConfigId);
        }
      } else if (response.data?.failed_items && response.data.failed_items.length > 0) {
        const batchResult = response.data as { success_count: number; failed_items: Array<{ nycu_id: string; reason: string; }>; };
        toast.error(batchResult.failed_items[0].reason);
      }
    } catch (error: any) {
      toast.error(error.message || "無法新增學生到白名單");
    } finally {
      setAddingStudent(false);
    }
  };

  const handleDeleteStudents = async (nycuIds: string[]) => {
    if (nycuIds.length === 0 || !activeConfigId) return;

    try {
      const response = await api.whitelist.batchRemoveWhitelist(activeConfigId, {
        nycu_ids: nycuIds,
      });

      if (response.success) {
        toast.success(`已移除 ${nycuIds.length} 位學生`);
        setSelectedStudents(new Set());
        await loadWhitelist(activeConfigId);
      }
    } catch (error: any) {
      toast.error(error.message || "無法刪除學生");
    }
  };

  const handleImportExcel = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !activeConfigId) return;

    setLoadingWhitelist(true);
    try {
      const response = await api.whitelist.importWhitelistExcel(activeConfigId, file);

      if (response.success && response.data) {
        const result = response.data as { success_count: number; failed_items: Array<{ nycu_id: string; reason: string; }>; };
        const message = `成功: ${result.success_count} 筆，失敗: ${result.failed_items.length} 筆`;
        if (result.failed_items.length > 0) {
          toast.error(message);
          console.error("Import errors:", result.failed_items);
        } else {
          toast.success(message);
        }

        await loadWhitelist(activeConfigId);
      }
    } catch (error: any) {
      toast.error(error.message || "無法匯入 Excel 檔案");
    } finally {
      setLoadingWhitelist(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleExportExcel = async () => {
    if (!activeConfigId || !scholarshipTypeData) return;

    try {
      const blob = await api.whitelist.exportWhitelistExcel(activeConfigId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const semesterLabel = scholarshipTypeData.semester || "yearly";
      a.download = `${formConfig?.title || scholarshipTypeData.name}_白名單_${scholarshipTypeData.academic_year}_${semesterLabel}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);

      toast.success("白名單已下載為 Excel 檔案");
    } catch (error: any) {
      toast.error(error.message || "無法匯出白名單");
    }
  };

  const handleDownloadTemplate = async () => {
    if (!activeConfigId) return;

    try {
      const blob = await api.whitelist.downloadTemplate(activeConfigId);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `白名單匯入模板_${formConfig?.title || scholarshipTypeData?.name}.xlsx`;
      a.click();
      window.URL.revokeObjectURL(url);

      toast.success("匯入模板已下載");
    } catch (error: any) {
      toast.error(error.message || "無法下載模板");
    }
  };

  // Filter whitelist students
  const filteredWhitelist = whitelist.map(item => ({
    ...item,
    students: item.students.filter(
      student =>
        (selectedWhitelistTab === "all" || item.sub_type === selectedWhitelistTab) &&
        (searchQuery === "" ||
          student.nycu_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (student.name?.toLowerCase().includes(searchQuery.toLowerCase()) ?? false))
    ),
  })).filter(item => item.students.length > 0);

  const allStudents = whitelist.flatMap(item => item.students);
  const totalCount = allStudents.length;

  // Get sub-types from scholarship data
  const subTypes = scholarshipTypeData?.eligible_sub_types || [];

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
        <div className="flex items-center gap-3">
          <Input
            id="terms-upload"
            type="file"
            accept=".pdf,.doc,.docx"
            onChange={handleTermsUpload}
            className="hidden"
          />
          {formConfig?.terms_document_url ? (
            <div className="flex items-center gap-3 px-3 py-2 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-center gap-2 flex-1">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <span className="text-sm font-medium text-green-700">已上傳條款文件</span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const token = localStorage.getItem("auth_token");
                    // Append token as query parameter for iframe authentication
                    const previewUrl = `/api/v1/preview-terms?scholarshipType=${type}${token ? `&token=${encodeURIComponent(token)}` : ''}`;

                    // 設定預覽文件資訊並打開 Modal
                    setTermsPreviewFile({
                      url: previewUrl,
                      filename: `${formConfig?.title || "獎學金"}_申請條款.pdf`,
                      type: "application/pdf",
                    });
                    setShowTermsPreview(true);
                  }}
                  className="h-7 text-green-700 hover:text-green-800 hover:bg-green-100"
                >
                  <Eye className="h-4 w-4 mr-1" />
                  預覽
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => document.getElementById("terms-upload")?.click()}
                  disabled={isUploadingTerms}
                  className="h-7 text-green-700 hover:text-green-800 hover:bg-green-100"
                >
                  <Upload className="h-4 w-4 mr-1" />
                  重新上傳
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-3 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
              <div className="flex items-center gap-2 flex-1">
                <AlertCircle className="h-4 w-4 text-red-600" />
                <span className="text-sm font-medium text-red-700">未上傳條款文件</span>
              </div>
              <Button
                onClick={() => document.getElementById("terms-upload")?.click()}
                disabled={isUploadingTerms}
                size="sm"
                variant="outline"
                className="h-7 text-red-700 border-red-300 hover:bg-red-100"
              >
                {isUploadingTerms ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                    上傳中...
                  </>
                ) : (
                  <>
                    <Upload className="h-4 w-4 mr-1" />
                    上傳申請條款
                  </>
                )}
              </Button>
            </div>
          )}
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
      </div>

      {/* Main Content */}
      <Tabs defaultValue="fields" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="fields" className="flex items-center gap-2">
            <FormInput className="h-4 w-4" />
            申請欄位
          </TabsTrigger>
          <TabsTrigger value="documents" className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            文件要求
          </TabsTrigger>
          <TabsTrigger value="whitelist" className="flex items-center gap-2">
            <UserCheck className="h-4 w-4" />
            白名單管理
          </TabsTrigger>
        </TabsList>

        {/* Application Fields Tab */}
        <TabsContent value="fields" className="space-y-4">
          {/* Fixed Fields Card */}
          <Card className="border-2 border-blue-100 shadow-sm">
            <CardHeader className="pb-4 bg-gradient-to-b from-blue-50 to-white">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <FormInput className="h-5 w-5 text-blue-600" />
                  固定欄位（自動帶入）
                </CardTitle>
                <CardDescription className="text-gray-600">
                  這些欄位會從學生資料自動填入，無法新增或刪除
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Fixed Fields Table */}
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
                    {applicationFields.filter(f => f.is_fixed === true).map(field => (
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
                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditingField(field);
                                setFieldFormOpen(true);
                              }}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            {field.id > 0 && (
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

          {/* Dynamic Fields Card */}
          <Card className="border-2 border-gray-100 shadow-sm">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <FormInput className="h-5 w-5 text-blue-600" />
                    動態欄位（可自訂）
                  </CardTitle>
                  <CardDescription className="text-gray-600">
                    自訂{formConfig?.title}申請表單中的欄位類型、驗證規則和要求
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
              {/* Dynamic Fields Table */}
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
                    {applicationFields.filter(f => !f.is_fixed).map(field => (
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
                            <span className="text-sm text-gray-500">
                              {field.is_active ? "啟用" : "停用"}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditingField(field);
                                setFieldFormOpen(true);
                              }}
                              className="text-blue-600 hover:text-blue-700"
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            {field.id > 0 && (
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
          {/* Fixed Documents Card */}
          <Card className="border-2 border-green-100 shadow-sm">
            <CardHeader className="pb-4 bg-gradient-to-b from-green-50 to-white">
              <div>
                <CardTitle className="flex items-center gap-2 text-lg">
                  <FileText className="h-5 w-5 text-green-600" />
                  固定文件（系統預設）
                </CardTitle>
                <CardDescription className="text-gray-600">
                  這些文件由系統自動帶入，無法新增或刪除
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Fixed Documents Table */}
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
                    {documentRequirements.filter(d => d.is_fixed === true).map(doc => (
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
                            {doc.id > 0 && (
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

          {/* Dynamic Documents Card */}
          <Card className="border-2 border-gray-100 shadow-sm">
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="flex items-center gap-2 text-lg">
                    <FileText className="h-5 w-5 text-green-600" />
                    動態文件（可自訂）
                  </CardTitle>
                  <CardDescription className="text-gray-600">
                    自訂{formConfig?.title}申請時需要上傳的文件類型、格式和大小限制
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
              {/* Dynamic Documents Table */}
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
                    {documentRequirements.filter(d => !d.is_fixed).map(doc => (
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
                            <span className="text-sm text-gray-500">
                              {doc.is_active ? "啟用" : "停用"}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            {/* Upload Example Button */}
                            <div className="relative">
                              <input
                                type="file"
                                id={`upload-example-${doc.id}`}
                                className="hidden"
                                accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                                onChange={(e) => handleUploadExample(doc.id, e)}
                                disabled={uploadingExampleDocId === doc.id}
                              />
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  document
                                    .getElementById(`upload-example-${doc.id}`)
                                    ?.click()
                                }
                                disabled={uploadingExampleDocId === doc.id}
                                className="text-green-600 hover:text-green-700"
                                title="上傳範例"
                              >
                                {uploadingExampleDocId === doc.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Upload className="h-4 w-4" />
                                )}
                              </Button>
                            </div>

                            {/* Preview Example Button */}
                            {doc.example_file_url && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() =>
                                  handlePreviewExample(
                                    doc.id,
                                    doc.document_name
                                  )
                                }
                                className="text-purple-600 hover:text-purple-700"
                                title="預覽範例"
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            )}

                            {/* Delete Example Button */}
                            {doc.example_file_url && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleDeleteExample(doc.id)}
                                className="text-orange-600 hover:text-orange-700"
                                title="刪除範例"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            )}

                            {/* Edit Document Button */}
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditingDocument(doc);
                                setDocumentFormOpen(true);
                              }}
                              className="text-blue-600 hover:text-blue-700"
                              title="編輯文件"
                            >
                              <Edit className="h-4 w-4" />
                            </Button>

                            {/* Delete Document Button */}
                            {doc.id > 0 && (
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleDeleteDocument(doc.id)}
                                className="text-red-600 hover:text-red-700"
                                title="刪除文件"
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
        <TabsContent value="whitelist" className="space-y-4">
          {loadingWhitelist && !scholarshipTypeData ? (
            <Card className="border-2 border-gray-100 shadow-sm">
              <CardContent className="flex items-center justify-center py-12">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mr-2" />
                <span>載入白名單資料中...</span>
              </CardContent>
            </Card>
          ) : !scholarshipTypeData?.whitelist_enabled ? (
            <Card className="border-2 border-gray-100 shadow-sm">
              <CardContent className="flex flex-col items-center justify-center py-12">
                <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                  <UserCheck className="h-8 w-8 text-gray-400" />
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                  白名單功能未啟用
                </h3>
                <p className="text-sm text-gray-600 text-center max-w-md">
                  此獎學金類型目前未啟用白名單功能。若需使用白名單功能，請至配置管理頁面啟用。
                </p>
              </CardContent>
            </Card>
          ) : (
            <Card className="border-2 border-gray-100 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <UserCheck className="h-5 w-5" />
                  白名單管理
                </CardTitle>
                <CardDescription>
                  管理可申請 {formConfig?.title} 的學生名單
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Action Buttons */}
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={handleDownloadTemplate}>
                    <FileSpreadsheet className="h-4 w-4 mr-1" />
                    下載模板
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => fileInputRef.current?.click()}>
                    <Upload className="h-4 w-4 mr-1" />
                    匯入 Excel
                  </Button>
                  <Button size="sm" variant="outline" onClick={handleExportExcel}>
                    <Download className="h-4 w-4 mr-1" />
                    匯出 Excel
                  </Button>
                  <div className="flex-1" />
                  <Badge variant="secondary">總計: {totalCount} 人</Badge>
                </div>

                <Separator />

                {/* Add Student Form */}
                <div className="border rounded-lg p-4 bg-muted/30">
                  <h4 className="text-sm font-medium mb-3">新增學生</h4>
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <Input
                        placeholder="請輸入學號"
                        value={newStudentNycuId}
                        onChange={e => setNewStudentNycuId(e.target.value)}
                        onKeyPress={e => e.key === "Enter" && handleAddStudent()}
                      />
                    </div>
                    {subTypes.length > 0 && (
                      <Select value={newStudentSubType} onValueChange={setNewStudentSubType}>
                        <SelectTrigger className="w-[200px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {subTypes.map((type: any) => (
                            <SelectItem key={type.value || type} value={type.value || type}>
                              {type.label || type}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                    <Button onClick={handleAddStudent} disabled={addingStudent}>
                      {addingStudent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4 mr-1" />}
                      新增
                    </Button>
                  </div>
                </div>

                {/* Search and Filter */}
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="搜尋學號或姓名..."
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      className="pl-9"
                    />
                  </div>
                  {selectedStudents.size > 0 && (
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={() => handleDeleteStudents(Array.from(selectedStudents))}
                    >
                      <Trash2 className="h-4 w-4 mr-1" />
                      刪除選中 ({selectedStudents.size})
                    </Button>
                  )}
                </div>

                {/* Tabs by Sub-Type */}
                <Tabs value={selectedWhitelistTab} onValueChange={setSelectedWhitelistTab}>
                  <TabsList>
                    <TabsTrigger value="all">全部</TabsTrigger>
                    {whitelist.map(item => (
                      <TabsTrigger key={item.sub_type} value={item.sub_type}>
                        {item.sub_type} ({item.total})
                      </TabsTrigger>
                    ))}
                  </TabsList>

                  {/* Student Table */}
                  <ScrollArea className="h-[400px] border rounded-md mt-4">
                    {loadingWhitelist ? (
                      <div className="flex items-center justify-center h-full">
                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                      </div>
                    ) : filteredWhitelist.length === 0 ? (
                      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                        <AlertCircle className="h-12 w-12 mb-2" />
                        <p>目前沒有白名單學生</p>
                      </div>
                    ) : (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="w-12">
                              <input
                                type="checkbox"
                                onChange={e => {
                                  if (e.target.checked) {
                                    const allIds = new Set(filteredWhitelist.flatMap(item => item.students.map(s => s.nycu_id)));
                                    setSelectedStudents(allIds);
                                  } else {
                                    setSelectedStudents(new Set());
                                  }
                                }}
                              />
                            </TableHead>
                            <TableHead>學號</TableHead>
                            <TableHead>姓名</TableHead>
                            <TableHead>子獎學金類型</TableHead>
                            <TableHead className="text-right">操作</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {filteredWhitelist.flatMap(item =>
                            item.students.map(student => (
                              <TableRow key={student.student_id}>
                                <TableCell>
                                  <input
                                    type="checkbox"
                                    checked={selectedStudents.has(student.nycu_id)}
                                    onChange={e => {
                                      const newSet = new Set(selectedStudents);
                                      if (e.target.checked) {
                                        newSet.add(student.nycu_id);
                                      } else {
                                        newSet.delete(student.nycu_id);
                                      }
                                      setSelectedStudents(newSet);
                                    }}
                                  />
                                </TableCell>
                                <TableCell className="font-mono">{student.nycu_id}</TableCell>
                                <TableCell>{student.name}</TableCell>
                                <TableCell>
                                  <Badge variant="outline">{student.sub_type}</Badge>
                                </TableCell>
                                <TableCell className="text-right">
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => handleDeleteStudents([student.nycu_id])}
                                  >
                                    <Trash2 className="h-4 w-4" />
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))
                          )}
                        </TableBody>
                      </Table>
                    )}
                  </ScrollArea>
                </Tabs>
              </CardContent>
            </Card>
          )}
        </TabsContent>
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

      {/* Terms Preview Dialog */}
      <FilePreviewDialog
        isOpen={showTermsPreview}
        onClose={handleCloseTermsPreview}
        file={termsPreviewFile}
        locale="zh"
      />

      {/* Example Document Preview Dialog */}
      <FilePreviewDialog
        isOpen={showExamplePreview}
        onClose={handleCloseExamplePreview}
        file={examplePreviewFile}
        locale="zh"
      />

      {/* Hidden file input for Excel import */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xls"
        className="hidden"
        onChange={handleImportExcel}
      />
    </div>
  );
}
