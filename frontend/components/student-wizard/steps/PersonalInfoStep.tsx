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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { FileUpload } from "@/components/file-upload";
import {
  User,
  CreditCard,
  Mail,
  Save,
  CheckCircle,
  ChevronRight,
  ChevronLeft,
  AlertCircle,
  Loader2,
  Eye,
  X,
} from "lucide-react";
import api from "@/lib/api";
import { useStudentProfile } from "@/hooks/use-student-profile";
import {
  validateAdvisorInfo,
  validateBankInfo,
  validateAdvisorEmail,
  sanitizeAdvisorInfo,
  sanitizeBankInfo,
} from "@/lib/validations/user-profile";
import { toast } from "sonner";
import { FilePreviewDialog } from "@/components/file-preview-dialog";

interface PersonalInfoStepProps {
  onNext: () => void;
  onBack: () => void;
  onComplete: (completed: boolean) => void;
  locale: "zh" | "en";
}

export function PersonalInfoStep({
  onNext,
  onBack,
  onComplete,
  locale,
}: PersonalInfoStepProps) {
  const [saving, setSaving] = useState(false);

  // Use SWR hook for student profile data
  const { profile, isLoading, error, refresh } = useStudentProfile();

  // Form data
  const [advisorName, setAdvisorName] = useState("");
  const [advisorEmail, setAdvisorEmail] = useState("");
  const [advisorNycuId, setAdvisorNycuId] = useState("");
  const [accountNumber, setAccountNumber] = useState("");
  const [bankDocumentFiles, setBankDocumentFiles] = useState<File[]>([]);
  const [existingBankDocument, setExistingBankDocument] = useState<string | null>(null);

  // Validation states
  const [advisorErrors, setAdvisorErrors] = useState<string[]>([]);
  const [bankErrors, setBankErrors] = useState<string[]>([]);
  const [emailValidationError, setEmailValidationError] = useState<string>("");

  // File preview
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);
  const [showPreview, setShowPreview] = useState(false);  const t = {
    zh: {
      title: "填寫個人資料",
      subtitle: "請填寫指導教授資訊與郵局帳號資料",
      advisorInfo: "指導教授資訊",
      advisorName: "教授姓名",
      advisorNamePlaceholder: "請輸入指導教授姓名",
      advisorEmail: "教授 Email",
      advisorEmailPlaceholder: "professor@nycu.edu.tw",
      advisorId: "指導教授本校人事編號",
      advisorIdPlaceholder: "請輸入指導教授本校人事編號",
      bankInfo: "郵局帳號資訊",
      accountNumber: "郵局帳號",
      accountNumberPlaceholder: "請輸入完整郵局帳號",
      bankDocument: "存摺封面照片",
      uploadBankDocument: "上傳存摺封面",
      documentUploaded: "已上傳文件",
      preview: "預覽",
      delete: "刪除",
      fileFormats: "支援格式：JPG, JPEG, PNG, PDF",
      fileSizeLimit: "檔案大小限制：10MB",
      uploadSuggestion: "建議上傳存摺封面照片或帳戶資料截圖",
      saveButton: "儲存並繼續",
      backButton: "返回上一步",
      skipButton: "暫時跳過",
      loading: "正在載入資料...",
      saving: "儲存中...",
      validationFailed: "驗證失敗",
      validationFailedDesc: "請檢查並修正表單中的錯誤",
      updateSuccess: "更新成功",
      profileUpdated: "個人資料已更新",
      updateFailed: "更新失敗",
      uploadingDocument: "正在上傳文件...",
      documentUploadSuccess: "文件上傳成功",
      completionPercentage: "完成度",
      requiredFields: "必填欄位",
      optionalFields: "選填欄位",
      advisorInfoDesc: "請提供您的指導教授資訊",
      bankInfoDesc: "請提供用於獎學金撥款的郵局帳號資訊",
    },
    en: {
      title: "Fill Personal Information",
      subtitle: "Please provide advisor information and bank account details",
      advisorInfo: "Advisor Information",
      advisorName: "Advisor Name",
      advisorNamePlaceholder: "Enter advisor's name",
      advisorEmail: "Advisor Email",
      advisorEmailPlaceholder: "professor@nycu.edu.tw",
      advisorId: "Advisor ID",
      advisorIdPlaceholder: "Enter advisor's NYCU ID",
      bankInfo: "Post Office Account Information",
      accountNumber: "Post Office Account Number",
      accountNumberPlaceholder: "Enter complete post office account number",
      bankDocument: "Passbook Cover Photo",
      uploadBankDocument: "Upload Passbook Cover",
      documentUploaded: "Document Uploaded",
      preview: "Preview",
      delete: "Delete",
      fileFormats: "Supported formats: JPG, JPEG, PNG, PDF",
      fileSizeLimit: "File size limit: 10MB",
      uploadSuggestion: "Recommend uploading passbook cover photo or account details screenshot",
      saveButton: "Save and Continue",
      backButton: "Back",
      skipButton: "Skip for Now",
      loading: "Loading...",
      saving: "Saving...",
      validationFailed: "Validation Failed",
      validationFailedDesc: "Please check and correct errors in the form",
      updateSuccess: "Update Success",
      profileUpdated: "Profile updated successfully",
      updateFailed: "Update Failed",
      uploadingDocument: "Uploading document...",
      documentUploadSuccess: "Document uploaded successfully",
      completionPercentage: "Completion",
      requiredFields: "Required Fields",
      optionalFields: "Optional Fields",
      advisorInfoDesc: "Please provide your advisor's information",
      bankInfoDesc: "Please provide post office account for scholarship disbursement",
    },
  };

  const text = t[locale];

  // Populate form fields when profile data loads
  useEffect(() => {
    if (profile) {
      setAdvisorName(profile.advisor_name || "");
      setAdvisorEmail(profile.advisor_email || "");
      setAdvisorNycuId(profile.advisor_nycu_id || "");
      setAccountNumber(profile.account_number || "");
      setExistingBankDocument(profile.bank_document_photo_url || null);
    }
  }, [profile]);

  const validateAdvisorData = () => {
    const advisorData = {
      advisor_name: advisorName,
      advisor_email: advisorEmail,
      advisor_nycu_id: advisorNycuId,
    };

    const validation = validateAdvisorInfo(advisorData);
    setAdvisorErrors(validation.errors);
    return validation.isValid;
  };

  const validateBankData = () => {
    const bankData = {
      account_number: accountNumber,
    };

    const validation = validateBankInfo(bankData);
    setBankErrors(validation.errors);
    return validation.isValid;
  };

  const handleAdvisorEmailChange = (email: string) => {
    setAdvisorEmail(email);
    setEmailValidationError("");
    if (advisorErrors.length > 0) {
      setAdvisorErrors([]);
    }

    if (email.trim() !== "") {
      const validation = validateAdvisorEmail(email);
      if (!validation.isValid) {
        setEmailValidationError(validation.errors[0] || "");
      }
    }
  };

  const handleSave = async () => {
    setSaving(true);

    try {
      // Validate advisor info
      const advisorValid = validateAdvisorData();
      const bankValid = validateBankData();

      if (!advisorValid || !bankValid) {
        toast.error(text.validationFailedDesc);
        setSaving(false);
        return;
      }

      // Save advisor info
      const advisorData = sanitizeAdvisorInfo({
        advisor_name: advisorName,
        advisor_email: advisorEmail,
        advisor_nycu_id: advisorNycuId,
      });

      const advisorResponse = await api.userProfiles.updateAdvisorInfo({
        ...advisorData,
        change_reason: "Advisor information updated by user in wizard",
      });

      if (!advisorResponse.success) {
        throw new Error(advisorResponse.message || "Failed to update advisor info");
      }

      // Save bank info
      const bankData = sanitizeBankInfo({
        account_number: accountNumber,
      });

      const bankResponse = await api.userProfiles.updateBankInfo({
        ...bankData,
        change_reason: "Bank information updated by user in wizard",
      });

      if (!bankResponse.success) {
        throw new Error(bankResponse.message || "Failed to update bank info");
      }

      // Upload bank document if new file is selected
      if (bankDocumentFiles.length > 0) {
        const file = bankDocumentFiles[0];
        const uploadResponse = await api.userProfiles.uploadBankDocumentFile(file);

        if (!uploadResponse.success) {
          throw new Error(uploadResponse.message || "Failed to upload document");
        }

        toast.success(text.documentUploadSuccess);
      }

      toast.success(text.profileUpdated);

      // Refresh SWR cache to sync changes across components
      await refresh();

      onComplete(true);
      onNext();
    } catch (error: any) {
      toast.error(error.message || text.updateFailed);
    } finally {
      setSaving(false);
    }
  };

  const handlePreviewBankDocument = () => {
    if (!existingBankDocument) return;

    const filename = existingBankDocument.split("/").pop()?.split("?")[0] || "bank_document";
    const token = localStorage.getItem("auth_token") || "";

    const fileId = filename;
    const fileType = encodeURIComponent("bank_document");
    const previewUrl = `/api/v1/preview?fileId=${fileId}&filename=${encodeURIComponent(filename)}&type=${fileType}&token=${token}`;

    let fileTypeDisplay = "other";
    if (filename.toLowerCase().endsWith(".pdf")) {
      fileTypeDisplay = "application/pdf";
    } else if ([".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"].some(ext => filename.toLowerCase().endsWith(ext))) {
      fileTypeDisplay = "image";
    }

    setPreviewFile({
      url: previewUrl,
      filename: filename,
      type: fileTypeDisplay,
    });

    setShowPreview(true);
  };

  const handleDeleteBankDocument = async () => {
    try {
      const response = await api.userProfiles.deleteBankDocument();

      if (response.success) {
        toast.success("文件已刪除");
        setExistingBankDocument(null);
        // Refresh SWR cache to sync changes
        await refresh();
      } else {
        throw new Error(response.message || "Delete failed");
      }
    } catch (error: any) {
      toast.error(error.message || "刪除失敗");
    }
  };

  // Calculate completion percentage
  const calculateCompletion = () => {
    const total = 5; // advisor_name, advisor_email, advisor_nycu_id, account_number, bank_document
    let completed = 0;

    if (advisorName) completed++;
    if (advisorEmail) completed++;
    if (advisorNycuId) completed++;
    if (accountNumber) completed++;
    if (existingBankDocument || bankDocumentFiles.length > 0) completed++;

    return Math.round((completed / total) * 100);
  };

  // Loading state from SWR
  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <Loader2 className="h-12 w-12 animate-spin mx-auto mb-4 text-nycu-blue-600" />
          <p className="text-lg text-gray-600">{text.loading}</p>
        </CardContent>
      </Card>
    );
  }

  // Error state from SWR
  if (error) {
    return (
      <Card>
        <CardContent className="p-12 text-center">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 text-red-500" />
          <p className="text-lg text-red-600 mb-4">載入資料時發生錯誤</p>
          <p className="text-sm text-gray-600 mb-6">{error.message}</p>
          <Button onClick={() => refresh()}>重新載入</Button>
        </CardContent>
      </Card>
    );
  }

  const completionPercentage = calculateCompletion();

  return (
    <div className="space-y-6">
      {/* Progress indicator */}
      <Card>
        <CardContent className="p-6">
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="font-medium">{text.completionPercentage}</span>
              <span className="font-semibold text-nycu-blue-700">{completionPercentage}%</span>
            </div>
            <Progress value={completionPercentage} className="h-2" />
          </div>
        </CardContent>
      </Card>

      {/* Advisor Information */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-violet-100 rounded-lg">
              <User className="h-6 w-6 text-violet-600" />
            </div>
            <div>
              <CardTitle className="text-xl">{text.advisorInfo}</CardTitle>
              <CardDescription>{text.advisorInfoDesc}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Advisor validation errors */}
          {advisorErrors.length > 0 && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <div className="space-y-1">
                  {advisorErrors.map((error, index) => (
                    <div key={index}>{error}</div>
                  ))}
                </div>
              </AlertDescription>
            </Alert>
          )}

          <div className="grid md:grid-cols-2 gap-4">
            {/* Advisor Name */}
            <div className="space-y-2">
              <Label htmlFor="advisor_name">
                {text.advisorName} <span className="text-red-500">*</span>
              </Label>
              <Input
                id="advisor_name"
                placeholder={text.advisorNamePlaceholder}
                value={advisorName}
                onChange={(e) => {
                  setAdvisorName(e.target.value);
                  if (advisorErrors.length > 0) setAdvisorErrors([]);
                }}
                className={advisorErrors.some(e => e.includes("姓名") || e.includes("name")) ? "border-red-500" : ""}
              />
            </div>

            {/* Advisor Email */}
            <div className="space-y-2">
              <Label htmlFor="advisor_email">
                {text.advisorEmail} <span className="text-red-500">*</span>
              </Label>
              <Input
                id="advisor_email"
                type="email"
                placeholder={text.advisorEmailPlaceholder}
                value={advisorEmail}
                onChange={(e) => handleAdvisorEmailChange(e.target.value)}
                className={emailValidationError || advisorErrors.some(e => e.includes("Email")) ? "border-red-500" : ""}
              />
              {emailValidationError && (
                <div className="text-sm text-red-600 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {emailValidationError}
                </div>
              )}
            </div>

            {/* Advisor NYCU ID */}
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="advisor_nycu_id">
                {text.advisorId} <span className="text-red-500">*</span>
              </Label>
              <Input
                id="advisor_nycu_id"
                placeholder={text.advisorIdPlaceholder}
                value={advisorNycuId}
                onChange={(e) => {
                  setAdvisorNycuId(e.target.value);
                  if (advisorErrors.length > 0) setAdvisorErrors([]);
                }}
                className={advisorErrors.some(e => e.includes("工號") || e.includes("ID")) ? "border-red-500" : ""}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Bank Information */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-100 rounded-lg">
              <CreditCard className="h-6 w-6 text-green-600" />
            </div>
            <div>
              <CardTitle className="text-xl">{text.bankInfo}</CardTitle>
              <CardDescription>{text.bankInfoDesc}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Bank validation errors */}
          {bankErrors.length > 0 && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <div className="space-y-1">
                  {bankErrors.map((error, index) => (
                    <div key={index}>{error}</div>
                  ))}
                </div>
              </AlertDescription>
            </Alert>
          )}

          {/* Post Office Account Number */}
          <div className="space-y-2">
            <Label htmlFor="account_number">
              {text.accountNumber} <span className="text-red-500">*</span>
            </Label>
            <Input
              id="account_number"
              placeholder={text.accountNumberPlaceholder}
              value={accountNumber}
              onChange={(e) => {
                setAccountNumber(e.target.value);
                if (bankErrors.length > 0) setBankErrors([]);
              }}
              className={bankErrors.some(e => e.includes("帳") || e.includes("account")) ? "border-red-500" : ""}
            />
          </div>

          {/* Bank Document Upload */}
          <div className="space-y-4">
            <Label>{text.bankDocument}</Label>

            {/* Display current uploaded document */}
            {existingBankDocument && (
              <div className="mb-4 p-4 border rounded-lg bg-green-50 border-green-200">
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
                      {text.delete}
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* File Upload Component */}
            <FileUpload
              onFilesChange={setBankDocumentFiles}
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
              <p>{text.uploadSuggestion}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Action buttons */}
      <div className="flex justify-between pt-4">
        <Button variant="outline" onClick={onBack} size="lg">
          <ChevronLeft className="h-5 w-5 mr-2" />
          {text.backButton}
        </Button>
        <div className="flex gap-3">
          <Button
            variant="outline"
            onClick={() => {
              onComplete(false);
              onNext();
            }}
            size="lg"
          >
            {text.skipButton}
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || completionPercentage < 100}
            size="lg"
            className="nycu-gradient text-white px-8"
          >
            {saving ? (
              <>
                <Loader2 className="h-5 w-5 mr-2 animate-spin" />
                {text.saving}
              </>
            ) : (
              <>
                <Save className="h-5 w-5 mr-2" />
                {text.saveButton}
                <ChevronRight className="h-5 w-5 ml-2" />
              </>
            )}
          </Button>
        </div>
      </div>

      {/* File Preview Dialog */}
      <FilePreviewDialog
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        file={previewFile}
        locale={locale}
      />
    </div>
  );
}
