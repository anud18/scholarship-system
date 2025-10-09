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
          locale === "zh"
            ? `成功上傳 ${files.length} 個檔案`
            : `Successfully uploaded ${files.length} file(s)`
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
        setUploadMessage(
          locale === "zh" ? "部分檔案上傳失敗" : "Some files failed to upload"
        );
      }
    } catch (err: any) {
      setUploadStatus("error");
      setUploadMessage(
        err.message || (locale === "zh" ? "上傳失敗" : "Upload failed")
      );
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
          <DialogTitle>
            {locale === "zh" ? "上傳申請文件" : "Upload Application Documents"}
          </DialogTitle>
          <DialogDescription>
            {locale === "zh" ? "學號" : "Student ID"}: {application.student_id} |{" "}
            {locale === "zh" ? "申請 ID" : "Application ID"}: {applicationId}
            {application.form_data?.name && ` | ${application.form_data.name}`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Document Type Selection */}
          {scholarshipDocuments.length > 0 ? (
            <div className="space-y-2">
              <label className="text-sm font-medium">
                {locale === "zh" ? "文件類型" : "Document Type"}
              </label>
              <Select
                value={selectedDocumentType}
                onValueChange={setSelectedDocumentType}
                disabled={uploading}
              >
                <SelectTrigger>
                  <SelectValue
                    placeholder={
                      locale === "zh" ? "選擇文件類型" : "Select document type"
                    }
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
                {locale === "zh"
                  ? "此獎學金類型尚未設定文件需求，請聯繫管理員"
                  : "No document requirements configured for this scholarship type"}
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
                {locale === "zh" ? "上傳中..." : "Uploading..."}
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
            {locale === "zh" ? "取消" : "Cancel"}
          </Button>
          <Button
            onClick={handleUpload}
            disabled={!selectedDocumentType || files.length === 0 || uploading}
          >
            {uploading ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {locale === "zh" ? "上傳中..." : "Uploading..."}
              </>
            ) : (
              <>
                <Upload className="h-4 w-4 mr-2" />
                {locale === "zh" ? "上傳" : "Upload"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
