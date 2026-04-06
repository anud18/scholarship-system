"use client";

import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Checkbox } from "@/components/ui/checkbox";
import { DynamicApplicationForm } from "@/components/dynamic-application-form";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { Input } from "@/components/ui/input";
import { FileUpload } from "@/components/file-upload";
import {
  Award,
  ChevronLeft,
  Send,
  Save,
  Loader2,
  CheckCircle,
  AlertCircle,
  Info,
  FileText,
  Eye,
  User,
  CreditCard,
  X,
} from "lucide-react";
import api, {
  ScholarshipType,
  ApplicationCreate,
  Application,
} from "@/lib/api";
import { clsx } from "@/lib/utils";
import { useApplications } from "@/hooks/use-applications";
import { useStudentProfile } from "@/hooks/use-student-profile";
import {
  validateAdvisorInfo,
  validateBankInfo,
  validateAdvisorEmail,
  sanitizeAdvisorInfo,
  sanitizeBankInfo,
} from "@/lib/validations/user-profile";
import { toast } from "sonner";

interface ScholarshipApplicationStepProps {
  onBack: () => void;
  onComplete: () => void;
  locale: "zh" | "en";
  userId: number;
  editingApplication?: Application | null;
}

export function ScholarshipApplicationStep({
  onBack,
  onComplete,
  locale,
  userId,
  editingApplication,
}: ScholarshipApplicationStepProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [eligibleScholarships, setEligibleScholarships] = useState<
    ScholarshipType[]
  >([]);
  const [selectedScholarship, setSelectedScholarship] =
    useState<ScholarshipType | null>(null);
  const [selectedSubTypes, setSelectedSubTypes] = useState<string[]>([]);
  const [subTypePreferences, setSubTypePreferences] = useState<string[]>([]);
  const [dynamicFormData, setDynamicFormData] = useState<Record<string, any>>(
    {}
  );
  const [dynamicFileData, setDynamicFileData] = useState<
    Record<string, File[]>
  >({});
  const [formProgress, setFormProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Personal info states
  const {
    profile,
    userInfo,
    studentInfo,
    refresh: refreshProfile,
  } = useStudentProfile();
  const [advisorName, setAdvisorName] = useState("");
  const [advisorEmail, setAdvisorEmail] = useState("");
  const [advisorNycuId, setAdvisorNycuId] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [bankDocumentFiles, setBankDocumentFiles] = useState<File[]>([]);
  const [existingBankDocument, setExistingBankDocument] = useState<
    string | null
  >(null);
  const [advisorErrors, setAdvisorErrors] = useState<string[]>([]);
  const [bankErrors, setBankErrors] = useState<string[]>([]);
  const [emailValidationError, setEmailValidationError] = useState("");
  const [savingPersonalInfo, setSavingPersonalInfo] = useState(false);
  const [personalInfoSaved, setPersonalInfoSaved] = useState(false);
  const [showBankDocPreview, setShowBankDocPreview] = useState(false);
  const [bankDocPreviewFile, setBankDocPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  // Submit preview dialog
  const [showSubmitPreview, setShowSubmitPreview] = useState(false);

  // Terms document states
  const [showTermsPreview, setShowTermsPreview] = useState(false);
  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [termsPreviewFile, setTermsPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  const {
    createApplication,
    uploadDocument,
    submitApplication: submitApplicationApi,
    updateApplication,
  } = useApplications();

  const t = {
    zh: {
      title: "填寫資料與申請獎學金",
      subtitle: "填寫個人資料、選擇獎學金類型並完成申請",
      personalInfoTitle: "個人資料",
      advisorInfo: "指導教授資訊",
      advisorName: "教授姓名",
      advisorNamePlaceholder: "請輸入指導教授姓名",
      advisorEmail: "教授 Email",
      advisorEmailPlaceholder: "professor@nycu.edu.tw",
      advisorId: "指導教授本校人事編號",
      advisorIdPlaceholder: "請輸入指導教授本校人事編號",
      bankInfo: "郵局帳號資訊",
      accountNumber: "郵局局號加帳號共 14 碼",
      accountNumberPlaceholder: "請輸入 14 碼郵局帳號",
      bankDocument: "存摺封面照片",
      documentUploaded: "已上傳文件",
      preview: "預覽",
      deleteBankDoc: "刪除",
      fileFormats: "支援格式：JPG, JPEG, PNG, PDF",
      fileSizeLimit: "檔案大小限制：10MB",
      savePersonalInfo: "儲存個人資料",
      personalInfoSaved: "個人資料已儲存",
      personalInfoSaveFailed: "儲存個人資料失敗",
      selectScholarship: "選擇獎學金",
      selectScholarshipPlaceholder: "請選擇要申請的獎學金",
      noEligibleScholarships: "目前沒有符合資格的獎學金",
      selectPrograms: "選擇申請項目",
      programsRequired: "請至少選擇一個申請項目",
      formProgress: "表單完成度",
      completeAllRequired: "請完成所有必填項目",
      saveDraft: "暫存草稿（請按「提交申請」才會正式送出）",
      submitApplication: "提交申請",
      backButton: "返回上一步",
      submitting: "提交中...",
      saving: "儲存中...",
      loading: "載入中...",
      loadError: "載入獎學金資料失敗",
      submitSuccess: "申請提交成功！",
      submitError: "提交申請時發生錯誤",
      draftSaved: "草稿已儲存",
      singleSelection: "單選模式",
      multipleSelection: "可選擇多個項目",
      hierarchicalSelection: "請依序選擇項目（需按順序選取）",
      selectPrevious: "請先選擇前面的項目",
      eligible: "符合資格",
      notEligible: "不符合資格",
      scholarshipInfo: "獎學金資訊",
      applicationPeriod: "申請期間",
      termsAvailable: "此獎學金有申請條款文件",
      viewTerms: "查看申請條款",
      agreeTerms: "我已閱讀並同意申請條款",
      mustAgreeTerms: "請先閱讀並同意申請條款",
    },
    en: {
      title: "Fill Info & Apply for Scholarship",
      subtitle: "Fill personal information, select scholarship type and apply",
      personalInfoTitle: "Personal Information",
      advisorInfo: "Advisor Information",
      advisorName: "Advisor Name",
      advisorNamePlaceholder: "Enter advisor's name",
      advisorEmail: "Advisor Email",
      advisorEmailPlaceholder: "professor@nycu.edu.tw",
      advisorId: "Advisor NYCU ID",
      advisorIdPlaceholder: "Enter advisor's NYCU personnel ID",
      bankInfo: "Post Office Account",
      accountNumber: "Post Office Account (14 digits)",
      accountNumberPlaceholder: "Enter 14-digit post office account number",
      bankDocument: "Passbook Cover Photo",
      documentUploaded: "Document Uploaded",
      preview: "Preview",
      deleteBankDoc: "Delete",
      fileFormats: "Supported formats: JPG, JPEG, PNG, PDF",
      fileSizeLimit: "File size limit: 10MB",
      savePersonalInfo: "Save Personal Info",
      personalInfoSaved: "Personal info saved",
      personalInfoSaveFailed: "Failed to save personal info",
      selectScholarship: "Select Scholarship",
      selectScholarshipPlaceholder: "Please select a scholarship to apply",
      noEligibleScholarships: "No eligible scholarships available",
      selectPrograms: "Select Programs",
      programsRequired: "Please select at least one program",
      formProgress: "Form Completion",
      completeAllRequired: "Please complete all required fields",
      saveDraft: 'Save Draft (Click "Submit Application" to officially submit)',
      submitApplication: "Submit Application",
      backButton: "Back",
      submitting: "Submitting...",
      saving: "Saving...",
      loading: "Loading...",
      loadError: "Failed to load scholarship data",
      submitSuccess: "Application submitted successfully!",
      submitError: "Error submitting application",
      draftSaved: "Draft saved successfully",
      singleSelection: "Single selection",
      multipleSelection: "Multiple selections allowed",
      hierarchicalSelection:
        "Please select items in order (sequential selection required)",
      selectPrevious: "Select previous items first",
      eligible: "Eligible",
      notEligible: "Not Eligible",
      scholarshipInfo: "Scholarship Information",
      applicationPeriod: "Application Period",
      termsAvailable: "This scholarship has application terms document",
      viewTerms: "View Application Terms",
      agreeTerms: "I have read and agree to the application terms",
      mustAgreeTerms: "Please read and agree to the application terms first",
    },
  };

  const text = t[locale];

  // Populate personal info from profile
  useEffect(() => {
    if (profile) {
      setAdvisorName(profile.advisor_name || "");
      setAdvisorEmail(profile.advisor_email || "");
      setAdvisorNycuId(profile.advisor_nycu_id || "");
      setAccountNumber(profile.account_number || "");
      setExistingBankDocument(profile.bank_document_photo_url || null);
      if (profile.advisor_name && profile.account_number) {
        setPersonalInfoSaved(true);
      }
    }
  }, [profile]);

  const handleAdvisorEmailChange = (email: string) => {
    setAdvisorEmail(email);
    setEmailValidationError("");
    setPersonalInfoSaved(false);
    if (advisorErrors.length > 0) setAdvisorErrors([]);
    if (email.trim() !== "") {
      const validation = validateAdvisorEmail(email);
      if (!validation.isValid)
        setEmailValidationError(validation.errors[0] || "");
    }
  };

  const handleSavePersonalInfo = async () => {
    const advisorValid = validateAdvisorInfo({
      advisor_name: advisorName,
      advisor_email: advisorEmail,
      advisor_nycu_id: advisorNycuId,
    });
    setAdvisorErrors(advisorValid.errors);
    const bankValid = validateBankInfo({ account_number: accountNumber });
    setBankErrors(bankValid.errors);
    if (!advisorValid.isValid || !bankValid.isValid) return;

    setSavingPersonalInfo(true);
    try {
      const advisorData = sanitizeAdvisorInfo({
        advisor_name: advisorName,
        advisor_email: advisorEmail,
        advisor_nycu_id: advisorNycuId,
      });
      const advisorResp = await api.userProfiles.updateAdvisorInfo({
        ...advisorData,
        change_reason: "Updated in scholarship application wizard",
      });
      if (!advisorResp.success)
        throw new Error(advisorResp.message || "Failed to update advisor info");

      const bankData = sanitizeBankInfo({ account_number: accountNumber });
      const bankResp = await api.userProfiles.updateBankInfo({
        ...bankData,
        change_reason: "Updated in scholarship application wizard",
      });
      if (!bankResp.success)
        throw new Error(bankResp.message || "Failed to update bank info");

      if (bankDocumentFiles.length > 0) {
        const uploadResp = await api.userProfiles.uploadBankDocumentFile(
          bankDocumentFiles[0]
        );
        if (!uploadResp.success)
          throw new Error(uploadResp.message || "Failed to upload document");
      }

      await refreshProfile();
      setPersonalInfoSaved(true);
      toast.success(text.personalInfoSaved);
    } catch (err: any) {
      toast.error(err.message || text.personalInfoSaveFailed);
    } finally {
      setSavingPersonalInfo(false);
    }
  };

  const handlePreviewBankDocument = () => {
    if (!existingBankDocument) return;
    const filename =
      existingBankDocument.split("/").pop()?.split("?")[0] || "bank_document";
    const token = localStorage.getItem("auth_token") || "";
    const previewUrl = `/api/v1/preview?fileId=${filename}&filename=${encodeURIComponent(filename)}&type=${encodeURIComponent("bank_document")}&token=${token}`;
    let fileTypeDisplay = "other";
    if (filename.toLowerCase().endsWith(".pdf"))
      fileTypeDisplay = "application/pdf";
    else if (
      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"].some(ext =>
        filename.toLowerCase().endsWith(ext)
      )
    )
      fileTypeDisplay = "image";
    setBankDocPreviewFile({ url: previewUrl, filename, type: fileTypeDisplay });
    setShowBankDocPreview(true);
  };

  const handleDeleteBankDocument = async () => {
    try {
      const response = await api.userProfiles.deleteBankDocument();
      if (response.success) {
        toast.success(locale === "zh" ? "文件已刪除" : "Document deleted");
        setExistingBankDocument(null);
        await refreshProfile();
      } else {
        throw new Error(response.message || "Delete failed");
      }
    } catch (err: any) {
      toast.error(err.message || "刪除失敗");
    }
  };

  useEffect(() => {
    loadEligibleScholarships();
  }, []);

  useEffect(() => {
    calculateProgress();
  }, [selectedScholarship, selectedSubTypes, dynamicFormData, dynamicFileData]);

  useEffect(() => {
    setSubTypePreferences(prev => {
      const kept = prev.filter(st => selectedSubTypes.includes(st));
      const newOnes = selectedSubTypes.filter(st => !prev.includes(st));
      return [...kept, ...newOnes];
    });
  }, [selectedSubTypes]);

  // Load editing application data
  useEffect(() => {
    if (editingApplication && eligibleScholarships.length > 0) {
      // Find and set the scholarship
      const scholarship = eligibleScholarships.find(
        s => s.code === editingApplication.scholarship_type
      );
      if (scholarship) {
        setSelectedScholarship(scholarship);
      }

      // Load sub-types
      if (
        editingApplication.scholarship_subtype_list &&
        editingApplication.scholarship_subtype_list.length > 0
      ) {
        const validSubTypes =
          editingApplication.scholarship_subtype_list.filter(
            st => st !== "general"
          );
        setSelectedSubTypes(validSubTypes);
      }

      // Load form data
      const formData =
        editingApplication.submitted_form_data ||
        editingApplication.form_data ||
        {};
      if (formData.fields) {
        const existingFormData: Record<string, any> = {};
        Object.entries(formData.fields).forEach(
          ([fieldId, fieldData]: [string, any]) => {
            if (
              fieldData &&
              typeof fieldData === "object" &&
              "value" in fieldData
            ) {
              existingFormData[fieldId] = fieldData.value;
            }
          }
        );
        setDynamicFormData(existingFormData);
      }

      // Load file data
      if (formData.documents) {
        const existingFileData: Record<string, File[]> = {};
        formData.documents.forEach((doc: any) => {
          if (doc.document_id && doc.original_filename) {
            const fileData = {
              id: doc.file_id || doc.id,
              filename: doc.filename || doc.original_filename,
              original_filename: doc.original_filename,
              file_size: doc.file_size,
              mime_type: doc.mime_type,
              file_type: doc.document_type,
              file_path: doc.file_path,
              download_url: doc.download_url,
              is_verified: doc.is_verified,
              uploaded_at: doc.upload_time,
              name: doc.original_filename,
              size: doc.file_size || 0,
              originalSize: doc.file_size || 0,
              type: doc.mime_type || "application/octet-stream",
              isUploaded: true,
            };
            existingFileData[doc.document_id] = [fileData as any];
          }
        });
        setDynamicFileData(existingFileData);
      }

      // Set agreed to terms
      if (editingApplication.agree_terms) {
        setAgreedToTerms(true);
      }
    }
  }, [editingApplication, eligibleScholarships]);

  const loadEligibleScholarships = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.scholarships.getEligible();
      if (response.success && response.data) {
        // Filter to only show eligible scholarships (no common errors)
        const eligible = response.data.filter(
          (scholarship: ScholarshipType) => {
            const hasCommonErrors =
              scholarship.errors?.some(rule => !rule.sub_type) || false;
            return (
              Array.isArray(scholarship.eligible_sub_types) &&
              scholarship.eligible_sub_types.length > 0 &&
              !hasCommonErrors
            );
          }
        );
        setEligibleScholarships(eligible);
      } else {
        setError(response.message || text.loadError);
      }
    } catch (err: any) {
      setError(err.message || text.loadError);
    } finally {
      setLoading(false);
    }
  };

  const calculateProgress = async () => {
    if (!selectedScholarship) {
      setFormProgress(0);
      return;
    }

    try {
      const response = await api.applicationFields.getFormConfig(
        selectedScholarship.code
      );
      if (!response.success || !response.data) {
        setFormProgress(0);
        return;
      }

      const { fields, documents } = response.data;
      const requiredFields = fields.filter(
        f => f.is_active && f.is_required && !f.is_fixed
      );
      const requiredDocuments = documents.filter(
        d => d.is_active && d.is_required && !d.is_fixed
      );

      let totalRequired = requiredFields.length + requiredDocuments.length;

      // Add sub-type selection as required if applicable
      const hasSpecialSubTypes =
        selectedScholarship.eligible_sub_types &&
        selectedScholarship.eligible_sub_types.length > 0 &&
        selectedScholarship.eligible_sub_types[0]?.value !== "general" &&
        selectedScholarship.eligible_sub_types[0]?.value !== null;

      if (hasSpecialSubTypes) {
        totalRequired += 1;
      }

      if (totalRequired === 0) {
        setFormProgress(100);
        return;
      }

      let completedItems = 0;

      // Check required fields
      requiredFields.forEach(field => {
        const fieldValue = dynamicFormData[field.field_name];
        const isFixed = field.is_fixed === true;
        const hasPrefillValue =
          field.prefill_value !== undefined &&
          field.prefill_value !== null &&
          field.prefill_value !== "";

        if (
          (isFixed && hasPrefillValue) ||
          (fieldValue !== undefined && fieldValue !== null && fieldValue !== "")
        ) {
          completedItems++;
        }
      });

      // Check required documents
      requiredDocuments.forEach(doc => {
        const docFiles = dynamicFileData[doc.document_name];
        const isFixedDocument = doc.is_fixed === true;

        if (
          (isFixedDocument && doc.existing_file_url) ||
          (docFiles && docFiles.length > 0)
        ) {
          completedItems++;
        }
      });

      // Check sub-type selection
      if (hasSpecialSubTypes && selectedSubTypes.length > 0) {
        completedItems++;
      }

      const progress = Math.round((completedItems / totalRequired) * 100);
      setFormProgress(progress);
    } catch (error) {
      console.error("Error calculating progress:", error);
      setFormProgress(0);
    }
  };

  const handleScholarshipChange = (scholarshipCode: string) => {
    const scholarship = eligibleScholarships.find(
      s => s.code === scholarshipCode
    );
    setSelectedScholarship(scholarship || null);
    setSelectedSubTypes([]);
    setDynamicFormData({});
    setDynamicFileData({});
    setAgreedToTerms(false); // Reset terms agreement when scholarship changes
  };

  const handlePreviewTerms = () => {
    if (!selectedScholarship || !selectedScholarship.terms_document_url) return;

    // Get token from localStorage for authentication
    const token =
      typeof window !== "undefined" ? localStorage.getItem("auth_token") : null;

    // Append token as query parameter for iframe authentication
    const previewUrl = `/api/v1/preview-terms?scholarshipType=${selectedScholarship.code}${token ? `&token=${encodeURIComponent(token)}` : ""}`;

    setTermsPreviewFile({
      url: previewUrl,
      filename: `${selectedScholarship.name}_申請條款.pdf`,
      type: "application/pdf",
    });
    setShowTermsPreview(true);
  };

  const handleCloseTermsPreview = () => {
    setShowTermsPreview(false);
    setTermsPreviewFile(null);
  };

  const handleSubTypeSelection = (subTypeValue: string) => {
    if (!selectedScholarship) return;

    const selectionMode =
      selectedScholarship.sub_type_selection_mode || "multiple";
    let newSelected: string[] = [];

    switch (selectionMode) {
      case "single":
        newSelected = selectedSubTypes.includes(subTypeValue)
          ? []
          : [subTypeValue];
        break;
      case "hierarchical":
        const validSubTypes =
          selectedScholarship.eligible_sub_types?.filter(
            st => st.value && st.value !== "general"
          ) || [];
        const orderedValues = validSubTypes
          .map(st => st.value!)
          .filter(Boolean);

        if (selectedSubTypes.includes(subTypeValue)) {
          const indexToRemove = selectedSubTypes.indexOf(subTypeValue);
          newSelected = selectedSubTypes.slice(0, indexToRemove);
        } else {
          const expectedIndex = selectedSubTypes.length;
          const expectedValue = orderedValues[expectedIndex];
          if (subTypeValue === expectedValue) {
            newSelected = [...selectedSubTypes, subTypeValue];
          } else {
            newSelected = selectedSubTypes;
          }
        }
        break;
      case "multiple":
      default:
        newSelected = selectedSubTypes.includes(subTypeValue)
          ? selectedSubTypes.filter(t => t !== subTypeValue)
          : [...selectedSubTypes, subTypeValue];
        break;
    }

    setSelectedSubTypes(newSelected);
  };

  const handleMovePreference = (index: number, direction: "up" | "down") => {
    setSubTypePreferences(prev => {
      const newPrefs = [...prev];
      const targetIndex = direction === "up" ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= newPrefs.length) return prev;
      [newPrefs[index], newPrefs[targetIndex]] = [
        newPrefs[targetIndex],
        newPrefs[index],
      ];
      return newPrefs;
    });
  };

  const handleSaveDraft = async () => {
    if (!selectedScholarship) return;

    setSubmitting(true);
    try {
      const formFields: Record<string, any> = {};
      Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
        formFields[fieldName] = {
          field_id: fieldName,
          field_type: "text",
          value: String(value),
          required: true,
        };
      });

      const documents = Object.entries(dynamicFileData).map(
        ([docType, files]) => {
          const file = files[0];
          return {
            document_id: docType,
            document_type: docType,
            file_path: file.name,
            original_filename: file.name,
            upload_time: new Date().toISOString(),
          };
        }
      );

      const applicationData: ApplicationCreate = {
        scholarship_type: selectedScholarship.code,
        configuration_id: selectedScholarship.configuration_id || 0,
        scholarship_subtype_list:
          selectedSubTypes.length > 0 ? selectedSubTypes : ["general"],
        agree_terms: agreedToTerms,
        sub_type_preferences:
          subTypePreferences.length > 0 ? subTypePreferences : undefined,
        form_data: {
          fields: formFields,
          documents: documents,
        },
      };

      if (editingApplication && editingApplication.id) {
        // Update existing draft
        await updateApplication(editingApplication.id, applicationData);

        // Upload new files only
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            if (!(file as any).isUploaded) {
              await uploadDocument(editingApplication.id, file, docType);
            }
          }
        }

        alert(text.draftSaved);
      } else {
        // Create new draft
        const application = await createApplication(applicationData, true);

        if (application && application.id) {
          // Upload files
          for (const [docType, files] of Object.entries(dynamicFileData)) {
            for (const file of files) {
              await uploadDocument(application.id, file, docType);
            }
          }

          alert(text.draftSaved);
        }
      }
    } catch (error: any) {
      alert(text.submitError + ": " + error.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (!selectedScholarship) return;

    setSubmitting(true);
    try {
      const formFields: Record<string, any> = {};
      Object.entries(dynamicFormData).forEach(([fieldName, value]) => {
        formFields[fieldName] = {
          field_id: fieldName,
          field_type: "text",
          value: String(value),
          required: true,
        };
      });

      const documents = Object.entries(dynamicFileData).map(
        ([docType, files]) => {
          const file = files[0];
          return {
            document_id: docType,
            document_type: docType,
            file_path: file.name,
            original_filename: file.name,
            upload_time: new Date().toISOString(),
          };
        }
      );

      const applicationData: ApplicationCreate = {
        scholarship_type: selectedScholarship.code,
        configuration_id: selectedScholarship.configuration_id || 0,
        scholarship_subtype_list:
          selectedSubTypes.length > 0 ? selectedSubTypes : ["general"],
        agree_terms: agreedToTerms,
        sub_type_preferences:
          subTypePreferences.length > 0 ? subTypePreferences : undefined,
        form_data: {
          fields: formFields,
          documents: documents,
        },
      };

      let applicationId: number;

      if (editingApplication && editingApplication.id) {
        // Update existing draft
        await updateApplication(editingApplication.id, applicationData);
        applicationId = editingApplication.id;

        // Upload new files only
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            if (!(file as any).isUploaded) {
              await uploadDocument(applicationId, file, docType);
            }
          }
        }
      } else {
        // Create new application
        const application = await createApplication(applicationData, true);

        if (!application || !application.id) {
          throw new Error("Failed to create application");
        }
        applicationId = application.id;

        // Upload files
        for (const [docType, files] of Object.entries(dynamicFileData)) {
          for (const file of files) {
            await uploadDocument(applicationId, file, docType);
          }
        }
      }

      // Submit application
      await submitApplicationApi(applicationId);

      alert(text.submitSuccess);
      onComplete();
    } catch (error: any) {
      alert(text.submitError + ": " + error.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-lg text-gray-600">{text.loading}</p>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 text-red-500" />
          <p className="text-lg text-red-600 mb-4">{text.loadError}</p>
          <p className="text-sm text-gray-600">{error}</p>
        </CardContent>
      </Card>
    );
  }

  const eligibleSubTypes = selectedScholarship?.eligible_sub_types ?? [];
  const selectionMode =
    selectedScholarship?.sub_type_selection_mode ?? "multiple";
  const hasSpecialSubTypes =
    eligibleSubTypes.length > 0 &&
    eligibleSubTypes[0]?.value !== "general" &&
    eligibleSubTypes[0]?.value !== null;

  return (
    <div className="space-y-6">
      {/* Personal Information Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-violet-100 rounded-lg">
              <User className="h-6 w-6 text-violet-600" />
            </div>
            <div>
              <CardTitle className="text-2xl">
                {text.personalInfoTitle}
              </CardTitle>
              <CardDescription>
                {locale === "zh"
                  ? "請填寫指導教授資訊與郵局帳號資料"
                  : "Please provide advisor information and bank account details"}
              </CardDescription>
            </div>
            {personalInfoSaved && (
              <Badge className="ml-auto bg-green-100 text-green-700 border-green-200">
                <CheckCircle className="h-3 w-3 mr-1" />
                {locale === "zh" ? "已儲存" : "Saved"}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Advisor Information */}
          <div>
            <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
              <User className="h-4 w-4 text-violet-600" />
              {text.advisorInfo}
            </h3>
            {advisorErrors.length > 0 && (
              <Alert variant="destructive" className="mb-3">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {advisorErrors.map((e, i) => (
                    <div key={i}>{e}</div>
                  ))}
                </AlertDescription>
              </Alert>
            )}
            <div className="grid md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="advisor_name">
                  {text.advisorName} <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="advisor_name"
                  placeholder={text.advisorNamePlaceholder}
                  value={advisorName}
                  onChange={e => {
                    setAdvisorName(e.target.value);
                    setPersonalInfoSaved(false);
                    if (advisorErrors.length > 0) setAdvisorErrors([]);
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="advisor_email">
                  {text.advisorEmail} <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="advisor_email"
                  type="email"
                  placeholder={text.advisorEmailPlaceholder}
                  value={advisorEmail}
                  onChange={e => handleAdvisorEmailChange(e.target.value)}
                  className={emailValidationError ? "border-red-500" : ""}
                />
                {emailValidationError && (
                  <div className="text-sm text-red-600 flex items-center gap-2">
                    <AlertCircle className="w-4 h-4" />
                    {emailValidationError}
                  </div>
                )}
              </div>
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="advisor_nycu_id">
                  {text.advisorId} <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="advisor_nycu_id"
                  placeholder={text.advisorIdPlaceholder}
                  value={advisorNycuId}
                  onChange={e => {
                    setAdvisorNycuId(e.target.value);
                    setPersonalInfoSaved(false);
                    if (advisorErrors.length > 0) setAdvisorErrors([]);
                  }}
                />
              </div>
            </div>
          </div>

          {/* Bank Information */}
          <div>
            <h3 className="text-base font-semibold mb-3 flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-green-600" />
              {text.bankInfo}
            </h3>
            {bankErrors.length > 0 && (
              <Alert variant="destructive" className="mb-3">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  {bankErrors.map((e, i) => (
                    <div key={i}>{e}</div>
                  ))}
                </AlertDescription>
              </Alert>
            )}
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="account_number">
                  {text.accountNumber} <span className="text-red-500">*</span>
                </Label>
                <Input
                  id="account_number"
                  placeholder={text.accountNumberPlaceholder}
                  value={accountNumber}
                  onChange={e => {
                    setAccountNumber(e.target.value);
                    setPersonalInfoSaved(false);
                    if (bankErrors.length > 0) setBankErrors([]);
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label>{text.bankDocument}</Label>
                {existingBankDocument && (
                  <div className="p-3 border rounded-lg bg-green-50 border-green-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <CheckCircle className="w-5 h-5 text-green-600" />
                        <span className="text-sm font-medium text-green-800">
                          {text.documentUploaded}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handlePreviewBankDocument}
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          {text.preview}
                        </Button>
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={handleDeleteBankDocument}
                        >
                          <X className="w-4 h-4 mr-1" />
                          {text.deleteBankDoc}
                        </Button>
                      </div>
                    </div>
                  </div>
                )}
                <FileUpload
                  onFilesChange={files => {
                    setBankDocumentFiles(files);
                    setPersonalInfoSaved(false);
                  }}
                  acceptedTypes={[".jpg", ".jpeg", ".png", ".webp", ".pdf"]}
                  maxSize={10 * 1024 * 1024}
                  maxFiles={1}
                  initialFiles={bankDocumentFiles}
                  fileType="bank_document"
                  locale={locale}
                />
                <div className="text-xs text-muted-foreground space-y-1">
                  <p>{text.fileFormats}</p>
                  <p>{text.fileSizeLimit}</p>
                </div>
              </div>
            </div>
          </div>

          {/* Save Personal Info Button */}
          <div className="flex justify-end">
            <Button
              onClick={handleSavePersonalInfo}
              disabled={savingPersonalInfo || personalInfoSaved}
              variant={personalInfoSaved ? "outline" : "default"}
              className={personalInfoSaved ? "" : "nycu-gradient text-white"}
            >
              {savingPersonalInfo ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {text.saving}
                </>
              ) : personalInfoSaved ? (
                <>
                  <CheckCircle className="h-4 w-4 mr-2" />
                  {locale === "zh" ? "已儲存" : "Saved"}
                </>
              ) : (
                <>
                  <Save className="h-4 w-4 mr-2" />
                  {text.savePersonalInfo}
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Scholarship Application Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-amber-100 rounded-lg">
              <Award className="h-6 w-6 text-amber-600" />
            </div>
            <div>
              <CardTitle className="text-2xl">
                {locale === "zh" ? "申請獎學金" : "Apply for Scholarship"}
              </CardTitle>
              <CardDescription>
                {locale === "zh"
                  ? "選擇獎學金類型並填寫申請資料"
                  : "Select scholarship type and fill in application details"}
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Scholarship Selection */}
          <div className="space-y-2">
            <Label htmlFor="scholarship_type">
              {text.selectScholarship} <span className="text-red-500">*</span>
            </Label>
            <Select
              value={selectedScholarship?.code || ""}
              onValueChange={handleScholarshipChange}
            >
              <SelectTrigger>
                <SelectValue placeholder={text.selectScholarshipPlaceholder} />
              </SelectTrigger>
              <SelectContent>
                {eligibleScholarships.length === 0 ? (
                  <SelectItem value="no-eligible" disabled>
                    {text.noEligibleScholarships}
                  </SelectItem>
                ) : (
                  eligibleScholarships.map(scholarship => (
                    <SelectItem key={scholarship.id} value={scholarship.code}>
                      {locale === "zh"
                        ? scholarship.name
                        : scholarship.name_en || scholarship.name}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          {/* Sub-type Selection */}
          {selectedScholarship && hasSpecialSubTypes && (
            <div className="space-y-2">
              <Label>
                <span className="font-semibold">1. {text.selectPrograms}</span>{" "}
                <span className="text-red-500">*</span>
              </Label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {eligibleSubTypes.map((subType, index) => {
                  const subTypeValue = subType.value;
                  const isSelected = subTypeValue
                    ? selectedSubTypes.includes(subTypeValue)
                    : false;

                  const isSelectable = (() => {
                    if (!subTypeValue) return false;

                    if (selectionMode === "hierarchical") {
                      const validSubTypes = eligibleSubTypes.filter(
                        st => st.value && st.value !== "general"
                      );
                      const expectedIndex = selectedSubTypes.length;
                      return isSelected || index === expectedIndex;
                    }

                    return true;
                  })();

                  return (
                    <Card
                      key={subType.value || subType.label}
                      className={clsx(
                        "relative cursor-pointer transition-all duration-200",
                        isSelectable && "hover:border-primary/50",
                        isSelected && "border-primary bg-primary/5",
                        !isSelectable &&
                          "opacity-50 cursor-not-allowed bg-gray-50"
                      )}
                      onClick={() => {
                        if (isSelectable && subTypeValue) {
                          handleSubTypeSelection(subTypeValue);
                        }
                      }}
                    >
                      <div className="absolute top-2 right-2 w-4 h-4 rounded-full border-2 flex items-center justify-center">
                        {isSelected && (
                          <div className="w-2 h-2 rounded-full bg-primary" />
                        )}
                      </div>
                      <CardContent className="p-4">
                        <p className="text-sm font-medium">
                          {locale === "zh" ? subType.label : subType.label_en}
                        </p>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>

              {/* Selection mode description */}
              <div className="text-xs text-gray-600">
                {selectionMode === "single"
                  ? text.singleSelection
                  : selectionMode === "hierarchical"
                    ? text.hierarchicalSelection
                    : text.multipleSelection}
              </div>

              {hasSpecialSubTypes && selectedSubTypes.length === 0 && (
                <p className="text-sm text-destructive">
                  {text.programsRequired}
                </p>
              )}

              {/* Sub-type preference ordering */}
              {selectedSubTypes.length >= 2 && (
                <div className="mt-4">
                  <h4 className="text-sm font-semibold mb-2">
                    <span>2. </span>
                    <span className="text-red-600">
                      {locale === "zh"
                        ? "選擇志願序（請按 ▲▼ 箭頭調整志願序）"
                        : "Set Preference Order (use ▲▼ arrows to reorder)"}
                    </span>
                  </h4>
                  <div className="space-y-2">
                    {subTypePreferences.map((subType, index) => {
                      const config = eligibleSubTypes.find(
                        c => c.value === subType
                      );
                      return (
                        <div
                          key={subType}
                          className="flex items-center gap-2 p-2 bg-gray-50 rounded"
                        >
                          <div className="flex flex-col">
                            <button
                              type="button"
                              disabled={index === 0}
                              onClick={() => handleMovePreference(index, "up")}
                              className="p-0.5 text-gray-500 hover:text-gray-700 disabled:opacity-30"
                            >
                              ▲
                            </button>
                            <button
                              type="button"
                              disabled={index === subTypePreferences.length - 1}
                              onClick={() =>
                                handleMovePreference(index, "down")
                              }
                              className="p-0.5 text-gray-500 hover:text-gray-700 disabled:opacity-30"
                            >
                              ▼
                            </button>
                          </div>
                          <span className="text-sm font-medium w-6">
                            {index + 1}.
                          </span>
                          <span className="flex-1 text-sm">
                            {locale === "zh"
                              ? config?.label || subType
                              : config?.label_en || config?.label || subType}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Dynamic Application Form */}
          {selectedScholarship && (
            <DynamicApplicationForm
              scholarshipType={selectedScholarship.code}
              locale={locale}
              onFieldChange={(fieldName, value) => {
                setDynamicFormData(prev => ({
                  ...prev,
                  [fieldName]: value,
                }));
              }}
              onFileChange={(documentType, files) => {
                setDynamicFileData(prev => ({
                  ...prev,
                  [documentType]: files,
                }));
              }}
              initialValues={dynamicFormData}
              initialFiles={dynamicFileData}
              selectedSubTypes={selectedSubTypes}
              currentUserId={userId}
            />
          )}

          {/* Progress indicator */}
          {selectedScholarship && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="font-medium">{text.formProgress}</span>
                <span className="font-semibold text-nycu-blue-700">
                  {formProgress}%
                </span>
              </div>
              <Progress value={formProgress} className="h-2" />
              {formProgress < 100 && (
                <p className="text-sm text-amber-600">
                  {text.completeAllRequired} ({formProgress}%)
                </p>
              )}
            </div>
          )}

          {/* Application Terms Agreement */}
          {selectedScholarship && selectedScholarship.terms_document_url && (
            <div className="space-y-3">
              <Alert className="border-blue-200 bg-blue-50">
                <FileText className="h-5 w-5 text-blue-600" />
                <AlertDescription>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-blue-900 mb-1">
                        {text.termsAvailable}
                      </p>
                      <p className="text-sm text-blue-700">
                        {text.mustAgreeTerms}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handlePreviewTerms}
                      className="ml-4 border-blue-300 text-blue-700 hover:bg-blue-100"
                    >
                      <Eye className="h-4 w-4 mr-2" />
                      {text.viewTerms}
                    </Button>
                  </div>
                </AlertDescription>
              </Alert>

              <div className="flex items-center space-x-3 p-4 bg-gray-50 rounded-lg border-2 border-gray-200">
                <Checkbox
                  id="agree-terms"
                  checked={agreedToTerms}
                  onCheckedChange={checked =>
                    setAgreedToTerms(checked === true)
                  }
                  className="h-5 w-5"
                />
                <Label
                  htmlFor="agree-terms"
                  className="text-base font-medium leading-relaxed cursor-pointer flex-1"
                >
                  {text.agreeTerms}
                </Label>
              </div>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex justify-between pt-4">
            <Button variant="outline" onClick={onBack} size="lg">
              <ChevronLeft className="h-5 w-5 mr-2" />
              {text.backButton}
            </Button>
            <div className="flex gap-3">
              <Button
                variant="outline"
                onClick={handleSaveDraft}
                disabled={submitting || !selectedScholarship}
                size="lg"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                    {text.saving}
                  </>
                ) : (
                  <>
                    <Save className="h-5 w-5 mr-2" />
                    {text.saveDraft}
                  </>
                )}
              </Button>
              <Button
                onClick={() => setShowSubmitPreview(true)}
                disabled={
                  submitting ||
                  !personalInfoSaved ||
                  formProgress < 100 ||
                  Boolean(
                    selectedScholarship?.terms_document_url && !agreedToTerms
                  )
                }
                size="lg"
                className="nycu-gradient text-white px-8"
              >
                {submitting ? (
                  <>
                    <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                    {text.submitting}
                  </>
                ) : (
                  <>
                    <Send className="h-5 w-5 mr-2" />
                    {text.submitApplication}
                  </>
                )}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Terms Preview Dialog */}
      <FilePreviewDialog
        isOpen={showTermsPreview}
        onClose={handleCloseTermsPreview}
        file={termsPreviewFile}
        locale={locale}
      />

      {/* Bank Document Preview Dialog */}
      <FilePreviewDialog
        isOpen={showBankDocPreview}
        onClose={() => setShowBankDocPreview(false)}
        file={bankDocPreviewFile}
        locale={locale}
      />

      {/* Submit Preview Dialog */}
      <Dialog open={showSubmitPreview} onOpenChange={setShowSubmitPreview}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center gap-2">
              <Eye className="h-5 w-5" />
              {locale === "zh" ? "申請資料預覽" : "Application Preview"}
            </DialogTitle>
            <DialogDescription>
              {locale === "zh"
                ? "請確認以下資料無誤後再送出申請"
                : "Please verify the following information before submitting"}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Student Info */}
            {userInfo && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 mb-2">
                  {locale === "zh" ? "學籍資料" : "Student Information"}
                </h3>
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-gray-50 rounded-lg p-4">
                  <div>
                    <span className="text-gray-500">
                      {locale === "zh" ? "姓名" : "Name"}
                    </span>
                    <p className="font-medium">{userInfo.name || "-"}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">
                      {locale === "zh" ? "學號" : "Student ID"}
                    </span>
                    <p className="font-medium">{userInfo.nycu_id || "-"}</p>
                  </div>
                  <div>
                    <span className="text-gray-500">
                      {locale === "zh" ? "系所" : "Department"}
                    </span>
                    <p className="font-medium">{userInfo.dept_name || "-"}</p>
                  </div>
                  {studentInfo && (
                    <>
                      <div>
                        <span className="text-gray-500">
                          {locale === "zh" ? "學位" : "Degree"}
                        </span>
                        <p className="font-medium">
                          {(() => {
                            const degreeMap: Record<string, string> = {
                              "1": "博士",
                              "2": "碩士",
                              "3": "學士",
                            };
                            const val = String(studentInfo.std_degree || "");
                            return degreeMap[val] || val || "-";
                          })()}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-500">
                          {locale === "zh" ? "入學年度學期" : "Enrollment"}
                        </span>
                        <p className="font-medium">
                          {studentInfo.std_enrollyear
                            ? `${studentInfo.std_enrollyear} 學年度第 ${studentInfo.std_enrollterm || "?"} 學期`
                            : "-"}
                        </p>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}

            <Separator />

            {/* Personal Info */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 mb-2">
                {locale === "zh" ? "個人資料" : "Personal Information"}
              </h3>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-gray-50 rounded-lg p-4">
                <div>
                  <span className="text-gray-500">
                    {locale === "zh" ? "指導教授" : "Advisor"}
                  </span>
                  <p className="font-medium">{advisorName || "-"}</p>
                </div>
                <div>
                  <span className="text-gray-500">
                    {locale === "zh" ? "教授 Email" : "Advisor Email"}
                  </span>
                  <p className="font-medium">{advisorEmail || "-"}</p>
                </div>
                <div>
                  <span className="text-gray-500">
                    {locale === "zh"
                      ? "指導教授本校人事編號"
                      : "Advisor NYCU ID"}
                  </span>
                  <p className="font-medium">{advisorNycuId || "-"}</p>
                </div>
                <div className="col-span-2">
                  <span className="text-gray-500">
                    {locale === "zh"
                      ? "郵局局號加帳號共 14 碼"
                      : "Post Office Account"}
                  </span>
                  <p className="font-medium">{accountNumber || "-"}</p>
                </div>
              </div>
            </div>

            <Separator />

            {/* Scholarship Info */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 mb-2">
                {locale === "zh" ? "申請獎學金" : "Scholarship Application"}
              </h3>
              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm bg-gray-50 rounded-lg p-4">
                <div className="col-span-2">
                  <span className="text-gray-500">
                    {locale === "zh" ? "獎學金" : "Scholarship"}
                  </span>
                  <p className="font-medium">
                    {selectedScholarship
                      ? locale === "zh"
                        ? selectedScholarship.name
                        : selectedScholarship.name_en ||
                          selectedScholarship.name
                      : "-"}
                  </p>
                </div>
                {hasSpecialSubTypes && selectedSubTypes.length > 0 && (
                  <>
                    <div className="col-span-2">
                      <span className="text-gray-500">
                        {locale === "zh" ? "申請項目" : "Programs"}
                      </span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {selectedSubTypes.map(st => {
                          const config = eligibleSubTypes.find(
                            c => c.value === st
                          );
                          return (
                            <Badge key={st} variant="secondary">
                              {locale === "zh"
                                ? config?.label || st
                                : config?.label_en || config?.label || st}
                            </Badge>
                          );
                        })}
                      </div>
                    </div>
                    {subTypePreferences.length >= 2 && (
                      <div className="col-span-2">
                        <span className="text-gray-500">
                          {locale === "zh" ? "志願序" : "Preference Order"}
                        </span>
                        <div className="mt-1 space-y-1">
                          {subTypePreferences.map((st, i) => {
                            const config = eligibleSubTypes.find(
                              c => c.value === st
                            );
                            return (
                              <div key={st} className="flex items-center gap-2">
                                <span className="text-sm font-semibold text-nycu-blue-700 w-6">
                                  {i + 1}.
                                </span>
                                <span className="text-sm font-medium">
                                  {locale === "zh"
                                    ? config?.label || st
                                    : config?.label_en || config?.label || st}
                                </span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Warning */}
          <Alert className="border-amber-200 bg-amber-50">
            <AlertCircle className="h-4 w-4 text-amber-600" />
            <AlertDescription className="text-amber-800 font-medium">
              {locale === "zh"
                ? "送出後將無法修改申請內容，請確認資料無誤。"
                : "You cannot modify the application after submission. Please verify all information is correct."}
            </AlertDescription>
          </Alert>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowSubmitPreview(false)}
            >
              {locale === "zh" ? "返回修改" : "Go Back"}
            </Button>
            <Button
              onClick={() => {
                setShowSubmitPreview(false);
                handleSubmit();
              }}
              disabled={submitting}
              className="nycu-gradient text-white"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {text.submitting}
                </>
              ) : (
                <>
                  <Send className="h-4 w-4 mr-2" />
                  {locale === "zh" ? "確認送出" : "Confirm Submit"}
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
