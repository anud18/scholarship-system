"use client";

import { useState, useEffect, useMemo } from "react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Checkbox } from "@/components/ui/checkbox";
import { ProgressTimeline } from "@/components/progress-timeline";
import { FileUpload } from "@/components/file-upload";
import { DynamicApplicationForm } from "@/components/dynamic-application-form";
import { ApplicationDetailDialog } from "@/components/application-detail-dialog";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { StudentApplicationWizard } from "@/components/student-wizard/StudentApplicationWizard";
import { DocumentRequestAlert } from "@/components/document-request-alert";
import type { StudentDocumentRequest } from "@/lib/api/modules/document-requests";
import {
  Edit,
  Eye,
  Trash2,
  Save,
  AlertTriangle,
  AlertCircle,
  Info,
  FileText,
  Calendar,
  User as UserIcon,
  Loader2,
  Check,
  ClipboardList,
  Award,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { getTranslation } from "@/lib/i18n";
import { useApplications } from "@/hooks/use-applications";
import { FormValidator, Locale } from "@/lib/validators";
import api, {
  ScholarshipType,
  Application as ApiApplication,
  ApplicationFile,
  ApplicationCreate,
  ApplicationField,
  ApplicationDocument,
} from "@/lib/api";
import {
  ApplicationStatus,
  getApplicationStatusLabel,
  getApplicationStatusBadgeVariant,
} from "@/lib/enums";
import {
  getApplicationTimeline,
  getDisplayStatusInfo,
} from "@/lib/utils/application-helpers";
import { clsx } from "@/lib/utils";
import { User } from "@/types/user";

// 使用API的Application類型
type Application = ApiApplication;

interface EnhancedStudentPortalProps {
  user: User & {
    studentType: "phd" | "master" | "undergraduate" | "other";
  };
  locale: Locale;
  initialTab?: "scholarship-list" | "new-application" | "applications";
  onApplicationSubmitted?: () => void;
  editingApplicationId?: number | null;
  onStartEditing?: (applicationId: number) => void;
  onClearEditing?: () => void;
}

type BadgeVariant = "secondary" | "default" | "outline" | "destructive";

export function EnhancedStudentPortal({
  user,
  locale,
  initialTab = "scholarship-list",
  onApplicationSubmitted,
  editingApplicationId,
  onStartEditing,
  onClearEditing,
}: EnhancedStudentPortalProps) {
  const t = (key: string) => getTranslation(locale, key);
  const validator = useMemo(() => new FormValidator(locale), [locale]);

  const [activeTab, setActiveTab] = useState(initialTab);

  const {
    applications,
    isLoading: applicationsLoading,
    error: applicationsError,
    fetchApplications,
    createApplication,
    saveApplicationDraft,
    submitApplication: submitApplicationApi,
    withdrawApplication,
    uploadDocument,
    updateApplication,
    deleteApplication,
  } = useApplications();

  // Get the editing application from the applications list
  const editingApplication = editingApplicationId
    ? applications.find(app => app.id === editingApplicationId) || null
    : null;

  const [selectedSubTypes, setSelectedSubTypes] = useState<
    Record<string, string[]>
  >({});

  // 直接從 eligibleScholarships (API) 取得名稱，找不到就顯示 code
  const getScholarshipTypeName = (scholarshipType: string): string => {
    const scholarship = eligibleScholarships.find(
      s => s.code === scholarshipType
    );
    return scholarship
      ? locale === "zh"
        ? scholarship.name
        : scholarship.name_en || scholarship.name
      : scholarshipType;
  };

  // Helper function to handle sub-type selection based on selection mode
  const handleSubTypeSelection = (
    scholarshipType: string,
    subTypeValue: string,
    selectionMode: "single" | "multiple" | "hierarchical"
  ) => {
    setSelectedSubTypes(prev => {
      const currentSelected = prev[scholarshipType] || [];
      let newSelected: string[];

      switch (selectionMode) {
        case "single":
          // Single mode: only one selection allowed
          newSelected = currentSelected.includes(subTypeValue)
            ? []
            : [subTypeValue];
          break;

        case "hierarchical":
          // Hierarchical mode: sequential selection only
          const scholarship = eligibleScholarships.find(
            s => s.code === scholarshipType
          );
          const validSubTypes =
            scholarship?.eligible_sub_types?.filter(
              st => st.value && st.value !== "general"
            ) || [];
          const orderedValues = validSubTypes
            .map(st => st.value!)
            .filter(Boolean);

          if (currentSelected.includes(subTypeValue)) {
            // Deselecting - remove this and all subsequent selections
            const indexToRemove = currentSelected.indexOf(subTypeValue);
            newSelected = currentSelected.slice(0, indexToRemove);
          } else {
            // Selecting - only allow if this is the next in sequence
            const expectedIndex = currentSelected.length;
            const expectedValue = orderedValues[expectedIndex];
            if (subTypeValue === expectedValue) {
              newSelected = [...currentSelected, subTypeValue];
            } else {
              // Not the next in sequence, don't change selection
              newSelected = currentSelected;
            }
          }
          break;

        case "multiple":
        default:
          // Multiple mode: free selection
          newSelected = currentSelected.includes(subTypeValue)
            ? currentSelected.filter(t => t !== subTypeValue)
            : [...currentSelected, subTypeValue];
          break;
      }

      return {
        ...prev,
        [scholarshipType]: newSelected,
      };
    });
  };

  // Load form data when editingApplication changes
  useEffect(() => {
    if (editingApplication && initialTab === "new-application") {
      handleEditApplication(editingApplication);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingApplication, initialTab]);

  // Debug authentication status
  useEffect(() => {
    console.log("EnhancedStudentPortal mounted with user:", user);
    const token =
      typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;
    console.log("Current auth token exists:", !!token);
    console.log(
      "Token preview:",
      token ? token.substring(0, 20) + "..." : "No token"
    );
  }, [user]);

  // Use real application data from API
  // State for eligible scholarships
  const [eligibleScholarships, setEligibleScholarships] = useState<
    ScholarshipType[]
  >([]);
  const [isLoadingScholarships, setIsLoadingScholarships] = useState(true);
  const [scholarshipsError, setScholarshipsError] = useState<string | null>(
    null
  );

  // State for scholarship application info (form fields and documents)
  const [scholarshipApplicationInfo, setScholarshipApplicationInfo] = useState<{
    [scholarshipType: string]: {
      fields: ApplicationField[];
      documents: ApplicationDocument[];
      isLoading: boolean;
      error: string | null;
    };
  }>({});

  // State for document requests
  const [documentRequests, setDocumentRequests] = useState<StudentDocumentRequest[]>([]);
  const [isLoadingDocumentRequests, setIsLoadingDocumentRequests] = useState(false);

  // Fetch eligible scholarships on component mount
  useEffect(() => {
    const fetchEligibleScholarships = async () => {
      try {
        setIsLoadingScholarships(true);
        const response = await api.scholarships.getEligible();

        // Debug: Check the raw API response
        console.log("Debug: Raw API response:", response);
        console.log("Debug: API response success:", response.success);
        console.log("Debug: API response data:", response.data);

        let scholarshipData: ScholarshipType[] = [];
        if (response.success && response.data) {
          scholarshipData = response.data;
        } else {
          setScholarshipsError(response.message || "無法獲取獎學金資料");
          setEligibleScholarships([]);
          return;
        }

        if (scholarshipData.length === 0) {
          setScholarshipsError("目前沒有符合資格的獎學金");
        } else {
          // Debug: Check the structure of scholarship data
          console.log(
            "Debug: First scholarship data structure:",
            scholarshipData[0]
          );
          console.log(
            "Debug: All scholarship configuration_ids:",
            scholarshipData.map(s => ({
              code: s.code,
              configuration_id: s.configuration_id,
            }))
          );

          setEligibleScholarships(scholarshipData);
          setScholarshipsError(null);

          // 自動載入每個獎學金的申請資訊
          scholarshipData.forEach(scholarship => {
            fetchScholarshipApplicationInfo(scholarship.code);
          });
        }
      } catch (error) {
        console.error("Error fetching scholarships:", error); // Debug log
        setScholarshipsError(
          error instanceof Error ? error.message : "發生未知錯誤"
        );
        setEligibleScholarships([]);
      } finally {
        setIsLoadingScholarships(false);
      }
    };

    fetchEligibleScholarships();
  }, []);

  // Fetch document requests on component mount
  useEffect(() => {
    const fetchDocumentRequests = async () => {
      try {
        setIsLoadingDocumentRequests(true);
        const response = await api.documentRequests.getMyDocumentRequests("pending");

        if (response.success && response.data) {
          setDocumentRequests(response.data);
        } else {
          console.error("Failed to fetch document requests:", response.message);
          setDocumentRequests([]);
        }
      } catch (error) {
        console.error("Error fetching document requests:", error);
        setDocumentRequests([]);
      } finally {
        setIsLoadingDocumentRequests(false);
      }
    };

    fetchDocumentRequests();
  }, []);

  // Handler for fulfilling document requests
  const handleFulfillDocumentRequest = async (requestId: number) => {
    try {
      const response = await api.documentRequests.fulfillDocumentRequest(requestId);

      if (response.success) {
        // Remove fulfilled request from the list
        setDocumentRequests(prev => prev.filter(req => req.id !== requestId));
        alert(
          locale === "zh"
            ? "文件補件已標記為完成"
            : "Document request marked as fulfilled"
        );
      } else {
        alert(
          response.message ||
            (locale === "zh" ? "操作失敗" : "Operation failed")
        );
      }
    } catch (error: any) {
      console.error("Failed to fulfill document request:", error);
      alert(
        error?.response?.data?.message ||
          (locale === "zh" ? "標記完成時發生錯誤" : "Error marking as fulfilled")
      );
    }
  };

  // 獲取獎學金申請資訊（表單欄位和文件要求）
  const fetchScholarshipApplicationInfo = async (scholarshipType: string) => {
    // 如果已經載入過，直接返回
    if (
      scholarshipApplicationInfo[scholarshipType] &&
      !scholarshipApplicationInfo[scholarshipType].isLoading
    ) {
      return scholarshipApplicationInfo[scholarshipType];
    }

    // 設置載入狀態
    setScholarshipApplicationInfo(prev => ({
      ...prev,
      [scholarshipType]: {
        ...prev[scholarshipType],
        isLoading: true,
        error: null,
      },
    }));

    try {
      const response =
        await api.applicationFields.getFormConfig(scholarshipType);

      if (response.success && response.data) {
        setScholarshipApplicationInfo(prev => ({
          ...prev,
          [scholarshipType]: {
            fields: response.data?.fields || [],
            documents: response.data?.documents || [],
            isLoading: false,
            error: null,
          },
        }));
      } else {
        setScholarshipApplicationInfo(prev => ({
          ...prev,
          [scholarshipType]: {
            fields: [],
            documents: [],
            isLoading: false,
            error: response.message || "無法獲取申請資訊",
          },
        }));
      }
    } catch (error) {
      console.error(
        `Failed to fetch application info for ${scholarshipType}:`,
        error
      );
      setScholarshipApplicationInfo(prev => ({
        ...prev,
        [scholarshipType]: {
          fields: [],
          documents: [],
          isLoading: false,
          error:
            error instanceof Error ? error.message : "獲取申請資訊時發生錯誤",
        },
      }));
    }
  };

  // Form state for new application
  const [newApplicationData, setNewApplicationData] =
    useState<ApplicationCreate>({
      scholarship_type: "",
      configuration_id: 0, // Will be set when scholarship is selected
      form_data: {
        fields: {},
        documents: [],
      },
    });

  // Dynamic form state
  const [dynamicFormData, setDynamicFormData] = useState<Record<string, any>>(
    {}
  );
  const [dynamicFileData, setDynamicFileData] = useState<
    Record<string, File[]>
  >({});

  // Terms agreement state
  const [agreeTerms, setAgreeTerms] = useState(false);

  // Terms preview modal
  const [showTermsPreview, setShowTermsPreview] = useState(false);
  const [termsPreviewFile, setTermsPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  // File upload state (for backwards compatibility)
  const [uploadedFiles, setUploadedFiles] = useState<{
    [documentType: string]: File[];
  }>({});
  const [selectedScholarship, setSelectedScholarship] =
    useState<ScholarshipType | null>(null);
  const eligibleSubTypes = selectedScholarship?.eligible_sub_types ?? [];
  const selectionMode =
    selectedScholarship?.sub_type_selection_mode ?? "multiple";

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formProgress, setFormProgress] = useState(0);

  // Calculate form completion progress (based on dynamic form configuration)
  useEffect(() => {
    if (!newApplicationData.scholarship_type) {
      setFormProgress(0);
      return;
    }

    // Get form configuration to calculate proper progress
    const calculateProgress = async () => {
      try {
        const response = await api.applicationFields.getFormConfig(
          newApplicationData.scholarship_type
        );
        if (!response.success || !response.data) {
          setFormProgress(0);
          return;
        }

        const { fields, documents } = response.data;

        // Calculate total required items
        const requiredFields = fields.filter(f => f.is_active && f.is_required);
        const requiredDocuments = documents.filter(
          d => d.is_active && d.is_required
        );
        let totalRequired = requiredFields.length + requiredDocuments.length;

        // Add sub-type selection as a required item if applicable
        const scholarship = selectedScholarship;
        if (
          scholarship?.eligible_sub_types &&
          scholarship.eligible_sub_types.length > 0 &&
          scholarship.eligible_sub_types[0]?.value !== "general" &&
          scholarship.eligible_sub_types[0]?.value !== null
        ) {
          totalRequired += 1;
        }

        // Add terms agreement as a required item
        totalRequired += 1;

        if (totalRequired === 0) {
          setFormProgress(100); // No requirements means 100% complete
          return;
        }

        let completedItems = 0;

        // Check required fields completion
        requiredFields.forEach(field => {
          const fieldValue = dynamicFormData[field.field_name];
          const isFixed = field.is_fixed === true;
          const hasPrefillValue =
            field.prefill_value !== undefined &&
            field.prefill_value !== null &&
            field.prefill_value !== "";

          // Fixed fields with prefill values are auto-completed
          if (isFixed && hasPrefillValue) {
            completedItems++;
          } else if (
            fieldValue !== undefined &&
            fieldValue !== null &&
            fieldValue !== ""
          ) {
            completedItems++;
          }
        });

        // Check required documents completion
        requiredDocuments.forEach(doc => {
          const docFiles = dynamicFileData[doc.document_name];
          // For fixed documents, check if they have existing_file_url or files
          const isFixedDocument = doc.is_fixed === true;

          if (isFixedDocument && doc.existing_file_url) {
            // Fixed document with existing file URL is considered complete
            completedItems++;
          } else if (docFiles && docFiles.length > 0) {
            // Regular document with uploaded files is complete
            completedItems++;
          }
        });

        // Check sub-type selection completion
        if (
          scholarship?.eligible_sub_types &&
          scholarship.eligible_sub_types.length > 0 &&
          scholarship.eligible_sub_types[0]?.value !== "general" &&
          scholarship.eligible_sub_types[0]?.value !== null
        ) {
          if (
            selectedSubTypes[newApplicationData.scholarship_type]?.length > 0
          ) {
            completedItems++;
          }
        }

        // Check terms agreement completion
        if (agreeTerms) {
          completedItems++;
        }

        // Calculate percentage
        const progress = Math.round((completedItems / totalRequired) * 100);
        setFormProgress(progress);
      } catch (error) {
        console.error("Error calculating progress:", error);
        setFormProgress(0);
      }
    };

    calculateProgress();
  }, [
    newApplicationData.scholarship_type,
    dynamicFormData,
    dynamicFileData,
    selectedScholarship,
    selectedSubTypes,
    agreeTerms,
  ]);

  // 新增狀態用於詳情對話框
  const [selectedApplicationForDetails, setSelectedApplicationForDetails] =
    useState<Application | null>(null);
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);

  const handleSubmitApplication = async () => {
    if (!newApplicationData.scholarship_type) {
      alert(
        locale === "zh" ? "請選擇獎學金類型" : "Please select scholarship type"
      );
      return;
    }

    if (!agreeTerms) {
      alert(
        locale === "zh"
          ? "您必須同意申請條款才能提交申請"
          : "You must agree to the terms and conditions to submit the application"
      );
      return;
    }

    try {
      setIsSubmitting(true);

      // Debug: Log current state before submission
      console.log("Debug: handleSubmitApplication called");
      console.log(
        "Debug: newApplicationData at submission:",
        newApplicationData
      );
      console.log(
        "Debug: selectedScholarship at submission:",
        selectedScholarship
      );
      console.log(
        "Debug: configuration_id at submission:",
        newApplicationData.configuration_id
      );

      // Format form fields according to backend requirements
      const formFields: Record<
        string,
        {
          field_id: string;
          field_type: string;
          value: string;
          required: boolean;
        }
      > = {};

      // Convert dynamic form data to required format
      Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
        formFields[fieldName] = {
          field_id: fieldName,
          field_type: "text", // You might need to get this from field configuration
          value: String(value),
          required: true, // This should come from field configuration
        };
      });

      // Format documents according to backend requirements - 使用整合後的文件結構
      const documents = Object.entries(dynamicFileData).map(
        ([docType, files]) => {
          const file = files[0]; // Assuming single file per document type
          return {
            document_id: docType,
            document_type: docType,
            file_path: file.name, // This should be the server path after upload
            original_filename: file.name,
            upload_time: new Date().toISOString(),
          };
        }
      );

      // Prepare the application data according to backend format
      const applicationData = {
        scholarship_type: newApplicationData.scholarship_type,
        configuration_id: newApplicationData.configuration_id,
        scholarship_subtype_list: selectedSubTypes[
          newApplicationData.scholarship_type
        ]?.length
          ? selectedSubTypes[newApplicationData.scholarship_type]
          : ["general"],
        agree_terms: agreeTerms,
        form_data: {
          fields: formFields,
          documents: documents,
        },
      };

      console.log("Debug: Final applicationData being sent:", applicationData);
      console.log(
        "Debug: Final configuration_id being sent:",
        applicationData.configuration_id
      );

      if (editingApplication) {
        // 編輯模式 - 更新草稿然後提交
        console.log("Updating application with data:", applicationData);
        await updateApplication(editingApplication.id, applicationData);

        // 上傳新文件
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            if (!(file as any).isUploaded) {
              await uploadDocument(editingApplication.id, file, docType);
            }
          }
        }

        // 提交編輯後的申請
        await submitApplicationApi(editingApplication.id);
      } else {
        // 新建模式 - 先創建草稿，然後提交
        console.log(
          "Creating application as draft with data:",
          applicationData
        );
        const createdApplication = await createApplication(
          applicationData,
          true
        ); // 創建為草稿

        if (!createdApplication || !createdApplication.id) {
          throw new Error("Failed to create application");
        }

        // 上傳文件
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            await uploadDocument(createdApplication.id, file, docType);
          }
        }

        // 提交草稿
        await submitApplicationApi(createdApplication.id);
      }

      // 重置表單
      setNewApplicationData({
        scholarship_type: "",
        configuration_id: 0, // Reset configuration_id
        form_data: {
          fields: {},
          documents: [],
        },
      });
      setDynamicFormData({});
      setDynamicFileData({});
      setUploadedFiles({});
      setSelectedScholarship(null);
      setAgreeTerms(false);

      // 清除編輯狀態並通知父組件切換到「我的申請」tab
      onClearEditing?.();

      // 重新載入申請列表
      await fetchApplications();

      // 通知父組件切換到「我的申請」tab
      onApplicationSubmitted?.();

      alert(
        locale === "zh"
          ? "申請提交成功！"
          : "Application submitted successfully!"
      );
    } catch (error) {
      console.error("Failed to submit application:", error);
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      alert(
        locale === "zh"
          ? `提交失敗: ${errorMessage}`
          : `Failed to submit application: ${errorMessage}`
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!newApplicationData.scholarship_type) {
      alert(
        locale === "zh" ? "請選擇獎學金類型" : "Please select scholarship type"
      );
      return;
    }

    try {
      setIsSubmitting(true);

      // Format form fields according to backend requirements
      const formFields: Record<
        string,
        {
          field_id: string;
          field_type: string;
          value: string;
          required: boolean;
        }
      > = {};

      // Convert dynamic form data to required format
      Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
        formFields[fieldName] = {
          field_id: fieldName,
          field_type: "text", // You might need to get this from field configuration
          value: String(value),
          required: true, // This should come from field configuration
        };
      });

      // Format documents according to backend requirements
      const documents = Object.entries(dynamicFileData).map(
        ([docType, files]) => {
          const file = files[0]; // Assuming single file per document type
          return {
            document_id: docType,
            document_type: docType,
            file_path: file.name, // This should be the server path after upload
            original_filename: file.name,
            upload_time: new Date().toISOString(),
          };
        }
      );

      // Prepare the application data according to backend format
      const applicationData = {
        scholarship_type: newApplicationData.scholarship_type,
        configuration_id: newApplicationData.configuration_id,
        scholarship_subtype_list: selectedSubTypes[
          newApplicationData.scholarship_type
        ]?.length
          ? selectedSubTypes[newApplicationData.scholarship_type]
          : ["general"],
        agree_terms: agreeTerms,
        form_data: {
          fields: formFields,
          documents: documents,
        },
      };

      if (editingApplication) {
        // 編輯模式 - 更新現有申請
        console.log("Updating draft application with data:", applicationData);
        await updateApplication(editingApplication.id, applicationData);

        // 上傳新文件
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            if (!(file as any).isUploaded) {
              await uploadDocument(editingApplication.id, file, docType);
            }
          }
        }

        alert(locale === "zh" ? "草稿已更新" : "Draft updated successfully");
      } else {
        // 新建模式 - 創建新草稿
        console.log("Saving new draft with data:", applicationData);
        const application = await saveApplicationDraft(applicationData);

        if (application && application.id) {
          // 上傳文件
          for (const [docType, files] of Object.entries(dynamicFileData)) {
            for (const file of files) {
              if (!(file as any).isUploaded) {
                await uploadDocument(application.id, file, docType);
              }
            }
          }

          alert(
            locale === "zh"
              ? "草稿已保存，您可以繼續編輯"
              : "Draft saved successfully. You can continue editing."
          );
        } else {
          alert(locale === "zh" ? "儲存草稿失敗" : "Failed to save draft");
          return;
        }
      }

      // 重新載入申請列表
      await fetchApplications();

      // 如果是編輯模式，保持在編輯狀態；如果是新建模式，重置表單
      if (!editingApplication) {
        // Reset form only for new applications
        setNewApplicationData({
          scholarship_type: "",
          configuration_id: 0,
          form_data: {
            fields: {},
            documents: [],
          },
        });
        setDynamicFormData({});
        setDynamicFileData({});
        setAgreeTerms(false);
        setSelectedSubTypes({});
      }
    } catch (error) {
      console.error("Failed to save draft:", error);
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      alert(
        locale === "zh"
          ? `保存失敗: ${errorMessage}`
          : `Failed to save draft: ${errorMessage}`
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleWithdrawApplication = async (applicationId: number) => {
    try {
      await withdrawApplication(applicationId);
    } catch (error) {
      console.error("Failed to withdraw application:", error);
    }
  };

  const handleDeleteApplication = async (applicationId: number) => {
    if (
      !confirm(
        locale === "zh"
          ? "確定要刪除此草稿嗎？此操作無法復原。"
          : "Are you sure you want to delete this draft? This action cannot be undone."
      )
    ) {
      return;
    }

    try {
      await deleteApplication(applicationId);

      // 如果刪除的是正在編輯的申請，清除編輯狀態
      if (editingApplicationId === applicationId) {
        onClearEditing?.();
      }

      alert(locale === "zh" ? "草稿已成功刪除" : "Draft deleted successfully");
    } catch (error) {
      console.error("Failed to delete application:", error);
      alert(
        locale === "zh"
          ? "刪除草稿時發生錯誤"
          : "Error occurred while deleting draft"
      );
    }
  };

  // 查看詳情處理函數
  const handleViewDetails = async (application: Application) => {
    try {
      // 從後端獲取完整的申請詳情，包括 form_data
      const response = await api.applications.getApplicationById(
        application.id
      );
      if (response.success && response.data) {
        setSelectedApplicationForDetails(response.data);
      } else {
        // 如果獲取失敗，使用原始的申請資料
        setSelectedApplicationForDetails(application);
      }
    } catch (error) {
      console.error("Failed to fetch application details:", error);
      // 如果獲取失敗，使用原始的申請資料
      setSelectedApplicationForDetails(application);
    }

    setIsDetailsDialogOpen(true);
  };

  // 取消編輯函數
  const handleCancelEdit = () => {
    // 清除編輯狀態
    onClearEditing?.();

    // 重置表單
    setNewApplicationData({
      scholarship_type: "",
      configuration_id: 0,
      form_data: {
        fields: {},
        documents: [],
      },
    });
    setDynamicFormData({});
    setDynamicFileData({});
    setUploadedFiles({});
    setSelectedScholarship(null);
    setAgreeTerms(false);
    setSelectedSubTypes({});
  };

  // 編輯處理函數
  const handleCloseTermsPreview = () => {
    setShowTermsPreview(false);
    setTermsPreviewFile(null);
  };


  // Handle application completion - switch to applications tab and refresh
  const handleApplicationComplete = () => {
    fetchApplications();
    setActiveTab("applications");

    // 通知父組件切換到「我的申請」tab
    onApplicationSubmitted?.();

    // Optionally show a success message
    // You can use a toast library if available
    alert(
      locale === "zh"
        ? "申請提交成功！請在「我的申請」查看進度"
        : "Application submitted successfully! View progress in 'My Applications'"
    );
  };
  const handleEditApplication = async (application: Application) => {
    // 通知父組件開始編輯（這會設置 editingApplicationId 和切換 Tab）
    // StudentApplicationWizard 會自動載入編輯數據到第四階段
    onStartEditing?.(application.id);
  };

  // Loading state
  if (isLoadingScholarships) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">{t("messages.loading_data")}</p>
          {isLoadingScholarships && (
            <p className="text-sm text-muted-foreground mt-2">
              {t("messages.loading_scholarship_info")}
            </p>
          )}
        </CardContent>
      </Card>
    );
  }

  // Error state
  if (scholarshipsError) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-4" />
          <p className="text-destructive">{scholarshipsError}</p>
        </CardContent>
      </Card>
    );
  }

  // No eligible scholarships
  if (eligibleScholarships.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-center">
          <AlertTriangle className="h-8 w-8 text-orange-500 mx-auto mb-4" />
          <h3 className="text-lg font-semibold mb-2">
            {t("messages.no_eligible_scholarships")}
          </h3>
          <p className="text-muted-foreground">
            {t("messages.no_eligible_scholarships_desc")}
          </p>
        </CardContent>
      </Card>
    );
  }

  const renderApplicationCard = (application: Application) => (
    <Card key={application.id} className="mb-4">
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{application.scholarship_type}</span>
          <div className="flex gap-2">
            {(() => {
              const statusInfo = getDisplayStatusInfo(application, locale);
              return (
                <>
                  <Badge variant={statusInfo.statusVariant}>
                    {statusInfo.statusLabel}
                  </Badge>
                  {statusInfo.showStage && statusInfo.stageLabel && (
                    <Badge variant={statusInfo.stageVariant}>
                      {statusInfo.stageLabel}
                    </Badge>
                  )}
                </>
              );
            })()}
          </div>
        </CardTitle>
        <CardDescription>
          {t("applications.submitted_at")}:{" "}
          {application.submitted_at
            ? new Date(application.submitted_at).toLocaleDateString()
            : "-"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ProgressTimeline steps={getApplicationTimeline(application, locale)} />
        {application.status === "draft" && (
          <div className="mt-4 flex justify-end space-x-2">
            <Button
              variant="outline"
              onClick={() => handleWithdrawApplication(application.id)}
            >
              {t("applications.withdraw")}
            </Button>
            <Button onClick={handleSubmitApplication}>
              {t("applications.submit")}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );

  return (
    <div className="space-y-6">
      {/* Document Request Alert - Show pending document requests */}
      {!isLoadingDocumentRequests && documentRequests.length > 0 && (
        <DocumentRequestAlert
          documentRequests={documentRequests}
          locale={locale}
          onFulfill={handleFulfillDocumentRequest}
        />
      )}

      {/* Conditional rendering based on activeTab */}
      {activeTab === "applications" && (
        <Card>
          <CardHeader>
            <CardTitle>{t("portal.application_records")}</CardTitle>
            <CardDescription>
              {locale === "zh"
                ? "查看您的獎學金申請狀態與進度"
                : "View your scholarship application status and progress"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {applicationsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin" />
              </div>
            ) : applicationsError ? (
              <div className="text-destructive text-center py-4">
                {applicationsError}
              </div>
            ) : applications.length === 0 ? (
              <div className="text-center py-8" data-testid="applications-empty-state">
                <div className="flex flex-col items-center gap-2">
                  <FileText className="h-12 w-12 text-muted-foreground" />
                  <p className="text-lg font-medium text-muted-foreground">
                    {locale === "zh"
                      ? "尚無申請記錄"
                      : "No application records"}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {locale === "zh"
                      ? "您可以點擊「新增申請」開始申請獎學金"
                      : "Click 'New Application' to start your scholarship application"}
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {applications.map(app => (
                  <div key={app.id} className="space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="font-medium">
                          {getScholarshipTypeName(app.scholarship_type)}
                        </h4>
                        <p className="text-sm text-muted-foreground">
                          {locale === "zh" ? "申請編號" : "Application ID"}:{" "}
                          {app.app_id || `APP-${app.id}`}
                        </p>
                      </div>
                      <Badge
                        variant={getApplicationStatusBadgeVariant(
                          app.status as ApplicationStatus
                        )}
                      >
                        {getApplicationStatusLabel(
                          app.status as ApplicationStatus,
                          locale
                        )}
                      </Badge>
                    </div>

                    {/* Progress Timeline */}
                    <Card>
                      <CardHeader>
                        <CardTitle className="text-base flex items-center gap-2">
                          <Calendar className="h-4 w-4" />
                          {locale === "zh" ? "審核進度" : "Review Progress"}
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <ProgressTimeline
                          steps={getApplicationTimeline(app, locale)}
                          orientation="horizontal"
                        />
                      </CardContent>
                    </Card>

                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleViewDetails(app)}
                      >
                        <Eye className="h-4 w-4 mr-1" />
                        {locale === "zh" ? "查看詳情" : "View Details"}
                      </Button>
                      {app.status === "draft" && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleEditApplication(app)}
                          >
                            <Edit className="h-4 w-4 mr-1" />
                            {locale === "zh" ? "編輯" : "Edit"}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDeleteApplication(app.id)}
                            className="text-destructive hover:text-destructive"
                          >
                            <Trash2 className="h-4 w-4 mr-1" />
                            {locale === "zh" ? "刪除草稿" : "Delete Draft"}
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {activeTab === "new-application" && (
        <StudentApplicationWizard
          user={user}
          locale={locale}
          onApplicationComplete={handleApplicationComplete}
          editingApplication={editingApplication}
          initialStep={editingApplication ? 3 : undefined}
        />
      )}

      {activeTab === "scholarship-list" && (
        <>
          {/* Scholarship Info Cards */}
          {eligibleScholarships.map(scholarship => {
            const applicationInfo = scholarshipApplicationInfo[scholarship.code];
            // Check if scholarship has eligible sub-types AND no common errors
            const hasCommonErrors = scholarship.errors?.some(rule => !rule.sub_type) || false;
            const isEligible =
              Array.isArray(scholarship.eligible_sub_types) &&
              scholarship.eligible_sub_types.length > 0 &&
              !hasCommonErrors;  // If there are common errors, student is not eligible

            return (
              <Card
                key={scholarship.id}
                className={clsx(
                  "border border-gray-100",
                  isEligible
                    ? "bg-white hover:border-primary/30 transition-colors"
                    : "bg-gray-50/50 border-gray-100 hover:bg-gray-50/80 transition-colors"
                )}
              >
                <CardHeader className="pb-4">
                  {/* Title and Status Badge */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-xl">
                        {locale === "zh"
                          ? scholarship.name
                          : scholarship.name_en || scholarship.name}
                      </CardTitle>
                    </div>
                    {isEligible ? (
                      <Badge
                        variant="outline"
                        className="bg-emerald-50 text-emerald-600 border-emerald-100 text-base px-4 py-1"
                      >
                        <Check className="h-4 w-4 mr-1.5" />
                        {t("messages.eligible")}
                      </Badge>
                    ) : (
                      <Badge
                        variant="outline"
                        className="bg-amber-50 text-amber-600 border-amber-100 text-base px-4 py-1"
                      >
                        <AlertTriangle className="h-4 w-4 mr-1.5" />
                        {t("messages.not_eligible")}
                      </Badge>
                    )}
                  </div>

                  {/* Eligible Programs Section - only show if student is eligible */}
                  {isEligible &&
                    scholarship.eligible_sub_types &&
                    scholarship.eligible_sub_types.length > 0 &&
                    scholarship.eligible_sub_types[0]?.value !== "general" &&
                    scholarship.eligible_sub_types[0]?.value !== null && (
                      <div className="mt-3 bg-indigo-50/30 rounded-lg border border-indigo-100/50 divide-y divide-indigo-100/50">
                        <div className="px-3 py-2">
                          <p className="text-sm font-medium text-indigo-900">
                            {getTranslation(
                              locale,
                              "scholarship_sections.eligible_programs"
                            )}
                          </p>
                        </div>
                        <div className="px-3 py-2 flex flex-wrap gap-1.5">
                          {scholarship.eligible_sub_types.map((subType, index) => (
                            <Badge
                              key={subType.value || index}
                              variant="outline"
                              className="bg-white text-indigo-600 border-indigo-100 shadow-sm"
                            >
                              {locale === "zh" ? subType.label : subType.label_en}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                </CardHeader>

                <CardContent>
                  <div className="grid grid-cols-2 gap-6">
                    {/* Left Column - Eligibility & Period */}
                    <div className="space-y-4">
                      {/* 申請資格 */}
                      <div className="rounded-lg border border-gray-100 overflow-hidden">
                        <div className="bg-sky-50/50 px-3 py-2 border-b border-gray-100">
                          <div className="flex items-center gap-2">
                            <Info className="h-4 w-4 text-sky-500" />
                            <p className="text-sm font-medium text-sky-700">
                              {getTranslation(
                                locale,
                                "scholarship_sections.eligibility"
                              )}
                            </p>
                          </div>
                        </div>
                        <div className="p-3 space-y-4">
                          {/* Get common rules */}
                          {(() => {
                            const commonPassedRules = scholarship.passed?.filter(rule => !rule.sub_type) || [];
                            const commonErrorRules = scholarship.errors?.filter(rule => !rule.sub_type) || [];

                            const hasSubTypes = scholarship.eligible_sub_types &&
                              scholarship.eligible_sub_types.some(st => st.value && st.value !== "general");

                            // If no subtypes (general scholarship), show common rules directly
                            if (!hasSubTypes && (commonPassedRules.length > 0 || commonErrorRules.length > 0)) {
                              return (
                                <div>
                                  <div className="flex flex-wrap gap-1">
                                    {/* Passed rules */}
                                    {commonPassedRules.map(rule => (
                                      <Badge
                                        key={rule.rule_id}
                                        variant="outline"
                                        className="bg-emerald-50 text-emerald-600 border-emerald-100"
                                      >
                                        {getTranslation(
                                          locale,
                                          `eligibility_tags.${rule.tag}`
                                        )}
                                      </Badge>
                                    ))}
                                    {/* Error rules */}
                                    {commonErrorRules.map(rule => {
                                      // Determine color and icon based on status
                                      const isDataUnavailable = rule.status === 'data_unavailable';
                                      const bgColor = isDataUnavailable ? 'bg-amber-50' : 'bg-rose-50';
                                      const textColor = isDataUnavailable ? 'text-amber-600' : 'text-rose-600';
                                      const borderColor = isDataUnavailable ? 'border-amber-100' : 'border-rose-100';
                                      const Icon = isDataUnavailable ? AlertCircle : AlertTriangle;
                                      const displayMessage = rule.system_message || rule.message;

                                      return (
                                        <Badge
                                          key={rule.rule_id}
                                          variant="outline"
                                          className={`${bgColor} ${textColor} ${borderColor}`}
                                          title={displayMessage} // tooltip
                                        >
                                          <Icon className="h-3 w-3 mr-1" />
                                          {getTranslation(
                                            locale,
                                            `eligibility_tags.${rule.tag}`
                                          )}
                                        </Badge>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            }

                            // Sub-type specific sections with common rules appended
                            return scholarship.eligible_sub_types?.map((subTypeInfo) => {
                              const subType = subTypeInfo.value;
                              if (!subType || subType === "general") return null;

                              const passedRulesForType = scholarship.passed?.filter(
                                rule => rule.sub_type === subType
                              ) || [];
                              const errorRulesForType = scholarship.errors?.filter(
                                rule => rule.sub_type === subType
                              ) || [];

                              // Combine common rules with subtype-specific rules
                              const allPassedRules = [...commonPassedRules, ...passedRulesForType];
                              const allErrorRules = [...commonErrorRules, ...errorRulesForType];

                              // Only show subtype section if there are any rules for it
                              if (allPassedRules.length === 0 && allErrorRules.length === 0)
                                return null;

                              return (
                                <div key={subType}>
                                  <p className="text-sm font-medium text-gray-800 mb-2">
                                    {locale === "zh" ? subTypeInfo.label : subTypeInfo.label_en || subTypeInfo.label}
                                  </p>
                                  <div className="flex flex-wrap gap-1">
                                    {/* Passed rules (common + subtype-specific) */}
                                    {allPassedRules.map(rule => (
                                      <Badge
                                        key={rule.rule_id}
                                        variant="outline"
                                        className="bg-emerald-50 text-emerald-600 border-emerald-100"
                                      >
                                        {getTranslation(
                                          locale,
                                          `eligibility_tags.${rule.tag}`
                                        )}
                                      </Badge>
                                    ))}
                                    {/* Error rules (common + subtype-specific) */}
                                    {allErrorRules.map(rule => {
                                      // Determine color and icon based on status
                                      const isDataUnavailable = rule.status === 'data_unavailable';
                                      const bgColor = isDataUnavailable ? 'bg-amber-50' : 'bg-rose-50';
                                      const textColor = isDataUnavailable ? 'text-amber-600' : 'text-rose-600';
                                      const borderColor = isDataUnavailable ? 'border-amber-100' : 'border-rose-100';
                                      const Icon = isDataUnavailable ? AlertCircle : AlertTriangle;
                                      const displayMessage = rule.system_message || rule.message;

                                      return (
                                        <Badge
                                          key={rule.rule_id}
                                          variant="outline"
                                          className={`${bgColor} ${textColor} ${borderColor}`}
                                          title={displayMessage} // tooltip
                                        >
                                          <Icon className="h-3 w-3 mr-1" />
                                          {getTranslation(
                                            locale,
                                            `eligibility_tags.${rule.tag}`
                                          )}
                                        </Badge>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            });
                          })()}

                          {/* Warnings - keep at the end */}
                          {scholarship.warnings &&
                            scholarship.warnings.length > 0 && (
                              <div>
                                <p className="text-sm font-medium text-amber-700 mb-2">
                                  {locale === "zh" ? "注意事項" : "Warnings"}
                                </p>
                                <div className="flex flex-wrap gap-1">
                                  {scholarship.warnings?.map(rule => (
                                    <Badge
                                      key={rule.rule_id}
                                      variant="outline"
                                      className="bg-amber-50 text-amber-600 border-amber-100"
                                    >
                                      <AlertTriangle className="h-3 w-3 mr-1" />
                                      {getTranslation(
                                        locale,
                                        `eligibility_tags.${rule.tag}`
                                      )}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                            )}
                        </div>
                      </div>

                      {/* 申請期間 */}
                      {scholarship.application_start_date &&
                        scholarship.application_end_date && (
                          <div className="rounded-lg border border-gray-100 overflow-hidden">
                            <div className="bg-amber-50/50 px-3 py-2 border-b border-gray-100">
                              <div className="flex items-center gap-2">
                                <Calendar className="h-4 w-4 text-amber-500" />
                                <p className="text-sm font-medium text-amber-700">
                                  {getTranslation(
                                    locale,
                                    "scholarship_sections.period"
                                  )}
                                </p>
                              </div>
                            </div>
                            <div className="p-3">
                              <p className="text-sm text-gray-600">
                                {new Date(
                                  scholarship.application_start_date
                                ).toLocaleDateString()}{" "}
                                -{" "}
                                {new Date(
                                  scholarship.application_end_date
                                ).toLocaleDateString()}
                              </p>
                            </div>
                          </div>
                        )}
                    </div>

                    {/* Right Column - Application Fields & Documents */}
                    <div className="space-y-4">
                      {/* Loading State */}
                      {applicationInfo?.isLoading && (
                        <div className="rounded-lg border border-gray-100 p-3">
                          <div className="flex items-center gap-2">
                            <Loader2 className="h-4 w-4 animate-spin text-sky-500" />
                            <p className="text-sm font-medium">
                              {locale === "zh" ? "申請資訊" : "Application Info"}
                            </p>
                          </div>
                          <p className="text-sm text-gray-600 mt-2">
                            {t("applications.loading")}
                          </p>
                        </div>
                      )}

                      {/* Error State */}
                      {applicationInfo?.error && (
                        <div className="rounded-lg border border-rose-100 bg-rose-50/50 p-3">
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-rose-500" />
                            <p className="text-sm font-medium text-rose-700">
                              {t("applications.load_error")}
                            </p>
                          </div>
                          <p className="text-sm text-rose-600 mt-2">
                            {applicationInfo.error}
                          </p>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              fetchScholarshipApplicationInfo(scholarship.code)
                            }
                            className="mt-2"
                          >
                            {t("applications.retry")}
                          </Button>
                        </div>
                      )}

                      {/* Application Fields */}
                      {applicationInfo &&
                        !applicationInfo.isLoading &&
                        !applicationInfo.error && (
                          <div className="rounded-lg border border-gray-100 overflow-hidden">
                            <div className="bg-violet-50/50 px-3 py-2 border-b border-gray-100">
                              <div className="flex items-center gap-2">
                                <Edit className="h-4 w-4 text-violet-500" />
                                <p className="text-sm font-medium text-violet-700">
                                  {getTranslation(
                                    locale,
                                    "scholarship_sections.fields"
                                  )}
                                </p>
                              </div>
                            </div>
                            <div className="p-3">
                              <div className="flex flex-wrap gap-1.5">
                                {applicationInfo.fields
                                  .filter(field => field.is_active)
                                  .map((field, index) => (
                                    <Badge
                                      key={`${scholarship.id}-field-${field.id}-${index}`}
                                      variant="outline"
                                      className="text-xs bg-white text-gray-600 border-gray-200"
                                    >
                                      {locale === "zh"
                                        ? field.field_label
                                        : field.field_label_en || field.field_label}
                                    </Badge>
                                  ))}
                              </div>
                            </div>
                          </div>
                        )}

                      {/* Required Documents */}
                      {applicationInfo &&
                        !applicationInfo.isLoading &&
                        !applicationInfo.error && (
                          <div className="rounded-lg border border-gray-100 overflow-hidden">
                            <div className="bg-emerald-50/50 px-3 py-2 border-b border-gray-100">
                              <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-emerald-500" />
                                <p className="text-sm font-medium text-emerald-700">
                                  {getTranslation(
                                    locale,
                                    "scholarship_sections.required_docs"
                                  )}
                                </p>
                              </div>
                            </div>
                            <div className="p-3">
                              <div className="flex flex-wrap gap-1.5">
                                {applicationInfo.documents
                                  .filter(doc => doc.is_required && doc.is_active)
                                  .map((doc, index) => (
                                    <Badge
                                      key={`${scholarship.id}-req-doc-${doc.id}-${index}`}
                                      variant="outline"
                                      className="text-xs bg-white text-gray-600 border-gray-200"
                                    >
                                      {locale === "zh"
                                        ? doc.document_name
                                        : doc.document_name_en || doc.document_name}
                                    </Badge>
                                  ))}
                              </div>
                            </div>
                          </div>
                        )}

                      {/* Optional Documents */}
                      {applicationInfo &&
                        !applicationInfo.isLoading &&
                        !applicationInfo.error &&
                        applicationInfo.documents.filter(
                          doc => !doc.is_required && doc.is_active
                        ).length > 0 && (
                          <div className="rounded-lg border border-gray-100 overflow-hidden">
                            <div className="bg-sky-50/50 px-3 py-2 border-b border-gray-100">
                              <div className="flex items-center gap-2">
                                <FileText className="h-4 w-4 text-sky-500" />
                                <p className="text-sm font-medium text-sky-700">
                                  {getTranslation(
                                    locale,
                                    "scholarship_sections.optional_docs"
                                  )}
                                </p>
                              </div>
                            </div>
                            <div className="p-3">
                              <div className="flex flex-wrap gap-1.5">
                                {applicationInfo.documents
                                  .filter(doc => !doc.is_required && doc.is_active)
                                  .map((doc, index) => (
                                    <Badge
                                      key={`${scholarship.id}-opt-doc-${doc.id}-${index}`}
                                      variant="outline"
                                      className="text-xs bg-white text-gray-600 border-gray-200"
                                    >
                                      {locale === "zh"
                                        ? doc.document_name
                                        : doc.document_name_en || doc.document_name}
                                    </Badge>
                                  ))}
                              </div>
                            </div>
                          </div>
                        )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </>
      )}

      {/* 申請詳情對話框 */}
      <ApplicationDetailDialog
        application={selectedApplicationForDetails}
        isOpen={isDetailsDialogOpen}
        onClose={() => setIsDetailsDialogOpen(false)}
        locale={locale}
        user={user}
      />

      {/* Terms Preview Dialog */}
      <FilePreviewDialog
        isOpen={showTermsPreview}
        onClose={handleCloseTermsPreview}
        file={termsPreviewFile}
        locale={locale}
      />
    </div>
  );
}
