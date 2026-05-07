"use client";

import React, { useState } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import {
  Upload,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { FileUpload } from "@/components/file-upload";
import type { Application } from "@/lib/api";
import { getTranslation } from "@/lib/i18n";

interface DocumentType {
  value: string;
  label_zh: string;
  label_en: string;
}

interface ApplicationFileUploadDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  application: Application | null;
  applicationId: number | null;
  scholarshipDocuments: DocumentType[];
  onUploadComplete: () => void;
  locale?: "zh" | "en";
}

export function ApplicationFileUploadDialog({
  open,
  onOpenChange,
  application,
  applicationId,
  scholarshipDocuments,
  onUploadComplete,
  locale = "zh",
}: ApplicationFileUploadDialogProps) {
  const t = (key: string) => getTranslation(locale, key);
  const [selectedDocumentType, setSelectedDocumentType] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<"idle" | "success" | "error">("idle");
  const [uploadMessage, setUploadMessage] = useState("");

  const handleUpload = async () => {
    if (!applicationId || files.length === 0 || !selectedDocumentType) {
      return;
    }

    setUploading(true);
    setUploadStatus("idle");
    setUploadMessage("");

    try {
      const uploadPromises = files.map((file) =>
        apiClient.applications.uploadDocument(applicationId, file, selectedDocumentType)
      );

      const results = await Promise.allSettled(uploadPromises);
      const allSuccess = results.every((result) => result.status === "fulfilled");

      if (allSuccess) {
        setUploadStatus("success");
        setUploadMessage(
          `${t("form_dialog.upload_success_prefix")} ${files.length} ${t("form_dialog.upload_success_suffix")}`
        );
        setFiles([]);
        setSelectedDocumentType("");

        // Delay to show success message
        setTimeout(() => {
          onUploadComplete();
          onOpenChange(false);
        }, 1500);
      } else {
        setUploadStatus("error");
        setUploadMessage(t("form_dialog.partial_upload_failed"));
      }
    } catch (err: any) {
      setUploadStatus("error");
      setUploadMessage(err.message || t("form_dialog.upload_failed"));
    } finally {
      setUploading(false);
    }
  };

  const handleClose = () => {
    setSelectedDocumentType("");
    setFiles([]);
    setUploading(false);
    setUploadStatus("idle");
    setUploadMessage("");
    onOpenChange(false);
  };

  if (!application || !applicationId) {
    return null;
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("form_dialog.upload_application_documents")}</DialogTitle>
          <DialogDescription>
            {t("profile_management.id_number")}: {application.student_id} |{" "}
            {t("form_dialog.application_id")}: {applicationId}
            {application.form_data?.name && ` | ${application.form_data.name}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Document Type Selection */}
          {scholarshipDocuments.length > 0 ? (
            <div className="space-y-2">
              <label className="text-sm font-medium">
                {t("form_dialog.document_type")}
              </label>
              <Select
                value={selectedDocumentType}
                onValueChange={setSelectedDocumentType}
                disabled={uploading}
              >
                <SelectTrigger>
                  <SelectValue
                    placeholder={t("form_dialog.select_document_type")}
                  />
                </SelectTrigger>
                <SelectContent>
                  {scholarshipDocuments.map((doc) => (
                    <SelectItem key={doc.value} value={doc.value}>
                      {locale === "zh" ? doc.label_zh : doc.label_en}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                {t("form_dialog.no_document_requirements")}
              </AlertDescription>
            </Alert>
          )}

          {/* File Upload */}
          {selectedDocumentType && (
            <FileUpload
              onFilesChange={setFiles}
              acceptedTypes={[".pdf", ".jpg", ".jpeg", ".png"]}
              maxSize={10 * 1024 * 1024}
              maxFiles={3}
              fileType={selectedDocumentType}
              locale={locale}
              initialFiles={files}
            />
          )}

          {/* Upload Progress */}
          {uploading && (
            <div className="space-y-2">
              <Progress value={75} className="h-2" />
              <p className="text-sm text-center text-muted-foreground">
                {t("form_dialog.uploading")}
              </p>
            </div>
          )}

          {/* Upload Status */}
          {uploadMessage && (
            <Alert variant={uploadStatus === "success" ? "default" : "destructive"}>
              <AlertDescription>{uploadMessage}</AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={uploading}>
            {t("form_dialog.cancel")}
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!selectedDocumentType || files.length === 0 || uploading}
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {t("form_dialog.uploading")}
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                {t("form_dialog.upload")}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
