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
} from "lucide-react";
import api, { ScholarshipType, ApplicationCreate, Application } from "@/lib/api";
import { clsx } from "@/lib/utils";
import { useApplications } from "@/hooks/use-applications";

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
  const [eligibleScholarships, setEligibleScholarships] = useState<ScholarshipType[]>([]);
  const [selectedScholarship, setSelectedScholarship] = useState<ScholarshipType | null>(null);
  const [selectedSubTypes, setSelectedSubTypes] = useState<string[]>([]);
  const [dynamicFormData, setDynamicFormData] = useState<Record<string, any>>({});
  const [dynamicFileData, setDynamicFileData] = useState<Record<string, File[]>>({});
  const [formProgress, setFormProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

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
      title: "申請獎學金",
      subtitle: "選擇獎學金類型並填寫申請資料",
      selectScholarship: "選擇獎學金",
      selectScholarshipPlaceholder: "請選擇要申請的獎學金",
      noEligibleScholarships: "目前沒有符合資格的獎學金",
      selectPrograms: "選擇申請項目",
      programsRequired: "請至少選擇一個申請項目",
      formProgress: "表單完成度",
      completeAllRequired: "請完成所有必填項目",
      saveDraft: "儲存草稿",
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
      title: "Apply for Scholarship",
      subtitle: "Select scholarship type and fill in application details",
      selectScholarship: "Select Scholarship",
      selectScholarshipPlaceholder: "Please select a scholarship to apply",
      noEligibleScholarships: "No eligible scholarships available",
      selectPrograms: "Select Programs",
      programsRequired: "Please select at least one program",
      formProgress: "Form Completion",
      completeAllRequired: "Please complete all required fields",
      saveDraft: "Save Draft",
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
      hierarchicalSelection: "Please select items in order (sequential selection required)",
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

  useEffect(() => {
    loadEligibleScholarships();
  }, []);

  useEffect(() => {
    calculateProgress();
  }, [selectedScholarship, selectedSubTypes, dynamicFormData, dynamicFileData]);

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
      if (editingApplication.scholarship_subtype_list && editingApplication.scholarship_subtype_list.length > 0) {
        const validSubTypes = editingApplication.scholarship_subtype_list.filter(
          st => st !== "general"
        );
        setSelectedSubTypes(validSubTypes);
      }

      // Load form data
      const formData = editingApplication.submitted_form_data || editingApplication.form_data || {};
      if (formData.fields) {
        const existingFormData: Record<string, any> = {};
        Object.entries(formData.fields).forEach(([fieldId, fieldData]: [string, any]) => {
          if (fieldData && typeof fieldData === "object" && "value" in fieldData) {
            existingFormData[fieldId] = fieldData.value;
          }
        });
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
        const eligible = response.data.filter((scholarship: ScholarshipType) => {
          const hasCommonErrors = scholarship.errors?.some(rule => !rule.sub_type) || false;
          return Array.isArray(scholarship.eligible_sub_types) &&
            scholarship.eligible_sub_types.length > 0 &&
            !hasCommonErrors;
        });
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
      const response = await api.applicationFields.getFormConfig(selectedScholarship.code);
      if (!response.success || !response.data) {
        setFormProgress(0);
        return;
      }

      const { fields, documents } = response.data;
      const requiredFields = fields.filter(f => f.is_active && f.is_required);
      const requiredDocuments = documents.filter(d => d.is_active && d.is_required);

      let totalRequired = requiredFields.length + requiredDocuments.length;

      // Add sub-type selection as required if applicable
      const hasSpecialSubTypes = selectedScholarship.eligible_sub_types &&
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
        const hasPrefillValue = field.prefill_value !== undefined &&
          field.prefill_value !== null &&
          field.prefill_value !== "";

        if ((isFixed && hasPrefillValue) || (fieldValue !== undefined && fieldValue !== null && fieldValue !== "")) {
          completedItems++;
        }
      });

      // Check required documents
      requiredDocuments.forEach(doc => {
        const docFiles = dynamicFileData[doc.document_name];
        const isFixedDocument = doc.is_fixed === true;

        if ((isFixedDocument && doc.existing_file_url) || (docFiles && docFiles.length > 0)) {
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
    const scholarship = eligibleScholarships.find(s => s.code === scholarshipCode);
    setSelectedScholarship(scholarship || null);
    setSelectedSubTypes([]);
    setDynamicFormData({});
    setDynamicFileData({});
    setAgreedToTerms(false); // Reset terms agreement when scholarship changes
  };

  const handlePreviewTerms = () => {
    if (!selectedScholarship || !selectedScholarship.terms_document_url) return;

    // Get token from localStorage for authentication
    const token = typeof window !== 'undefined'
      ? localStorage.getItem('auth_token')
      : null;

    // Append token as query parameter for iframe authentication
    const previewUrl = `/api/v1/preview-terms?scholarshipType=${selectedScholarship.code}${token ? `&token=${encodeURIComponent(token)}` : ''}`;

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

    const selectionMode = selectedScholarship.sub_type_selection_mode || "multiple";
    let newSelected: string[] = [];

    switch (selectionMode) {
      case "single":
        newSelected = selectedSubTypes.includes(subTypeValue) ? [] : [subTypeValue];
        break;
      case "hierarchical":
        const validSubTypes = selectedScholarship.eligible_sub_types?.filter(
          st => st.value && st.value !== "general"
        ) || [];
        const orderedValues = validSubTypes.map(st => st.value!).filter(Boolean);

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

      const documents = Object.entries(dynamicFileData).map(([docType, files]) => {
        const file = files[0];
        return {
          document_id: docType,
          document_type: docType,
          file_path: file.name,
          original_filename: file.name,
          upload_time: new Date().toISOString(),
        };
      });

      const applicationData: ApplicationCreate = {
        scholarship_type: selectedScholarship.code,
        configuration_id: selectedScholarship.configuration_id || 0,
        scholarship_subtype_list: selectedSubTypes.length > 0 ? selectedSubTypes : ["general"],
        agree_terms: agreedToTerms,
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

      const documents = Object.entries(dynamicFileData).map(([docType, files]) => {
        const file = files[0];
        return {
          document_id: docType,
          document_type: docType,
          file_path: file.name,
          original_filename: file.name,
          upload_time: new Date().toISOString(),
        };
      });

      const applicationData: ApplicationCreate = {
        scholarship_type: selectedScholarship.code,
        configuration_id: selectedScholarship.configuration_id || 0,
        scholarship_subtype_list: selectedSubTypes.length > 0 ? selectedSubTypes : ["general"],
        agree_terms: agreedToTerms,
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
  const selectionMode = selectedScholarship?.sub_type_selection_mode ?? "multiple";
  const hasSpecialSubTypes = eligibleSubTypes.length > 0 &&
    eligibleSubTypes[0]?.value !== "general" &&
    eligibleSubTypes[0]?.value !== null;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-amber-100 rounded-lg">
              <Award className="h-6 w-6 text-amber-600" />
            </div>
            <div>
              <CardTitle className="text-2xl">{text.title}</CardTitle>
              <CardDescription>{text.subtitle}</CardDescription>
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
                      {locale === "zh" ? scholarship.name : scholarship.name_en || scholarship.name}
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
                {text.selectPrograms} <span className="text-red-500">*</span>
              </Label>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {eligibleSubTypes.map((subType, index) => {
                  const subTypeValue = subType.value;
                  const isSelected = subTypeValue ? selectedSubTypes.includes(subTypeValue) : false;

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
                        !isSelectable && "opacity-50 cursor-not-allowed bg-gray-50"
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
                <span className="font-semibold text-nycu-blue-700">{formProgress}%</span>
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
                  onCheckedChange={(checked) => setAgreedToTerms(checked === true)}
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
                onClick={handleSubmit}
                disabled={
                  submitting ||
                  formProgress < 100 ||
                  Boolean(selectedScholarship?.terms_document_url && !agreedToTerms)
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
    </div>
  );
}
