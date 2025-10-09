"use client";

import React, { useState, useCallback } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Upload,
  FileArchive,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Info,
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface BatchDocumentUploadProps {
  batchId: number;
  onUploadComplete?: () => void;
  locale?: "zh" | "en";
}

interface UploadResult {
  student_id: string;
  file_name: string;
  document_type: string;
  status: string;
  message?: string;
  application_id?: number;
}

export function BatchDocumentUpload({
  batchId,
  onUploadComplete,
  locale = "zh",
}: BatchDocumentUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResults, setUploadResults] = useState<{
    total_files: number;
    matched_count: number;
    unmatched_count: number;
    error_count: number;
    results: UploadResult[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const handleFileSelect = (file: File) => {
    // Validate file extension
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError(locale === "zh" ? "請選擇 ZIP 檔案" : "Please select a ZIP file");
      return;
    }

    // Validate file size (100MB max)
    if (file.size > 100 * 1024 * 1024) {
      setError(
        locale === "zh"
          ? "檔案大小不能超過 100MB"
          : "File size cannot exceed 100MB"
      );
      return;
    }

    setSelectedFile(file);
    setError(null);
    setUploadResults(null);
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect(file);
    }
  }, []);

  const handleUpload = async () => {
    if (!selectedFile) {
      setError(locale === "zh" ? "請選擇檔案" : "Please select a file");
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      const response = await apiClient.batchImport.uploadDocuments(
        batchId,
        selectedFile
      );

      if (response.success && response.data) {
        setUploadResults(response.data);
        setSelectedFile(null);

        if (response.data.error_count === 0) {
          onUploadComplete?.();
        }
      } else {
        setError(
          response.message ||
            (locale === "zh" ? "上傳失敗" : "Upload failed")
        );
      }
    } catch (error: any) {
      setError(
        error.message ||
          (locale === "zh"
            ? "上傳時發生錯誤"
            : "Error during upload")
      );
    } finally {
      setIsUploading(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "success":
        return <CheckCircle className="h-4 w-4 text-green-600" />;
      case "error":
        return <XCircle className="h-4 w-4 text-red-600" />;
      default:
        return <AlertTriangle className="h-4 w-4 text-yellow-600" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const baseClasses = "px-2 py-1 rounded text-xs font-medium";
    switch (status) {
      case "success":
        return (
          <span className={`${baseClasses} bg-green-100 text-green-800`}>
            {locale === "zh" ? "成功" : "Success"}
          </span>
        );
      case "error":
        return (
          <span className={`${baseClasses} bg-red-100 text-red-800`}>
            {locale === "zh" ? "失敗" : "Failed"}
          </span>
        );
      default:
        return (
          <span className={`${baseClasses} bg-yellow-100 text-yellow-800`}>
            {locale === "zh" ? "警告" : "Warning"}
          </span>
        );
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileArchive className="h-5 w-5" />
          {locale === "zh" ? "批次上傳文件" : "Batch Document Upload"}
        </CardTitle>
        <CardDescription>
          {locale === "zh"
            ? "上傳包含所有學生文件的 ZIP 檔案"
            : "Upload a ZIP file containing all student documents"}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Instructions */}
        <Alert>
          <Info className="h-4 w-4" />
          <AlertDescription>
            <div className="space-y-2">
              <p className="font-semibold">
                {locale === "zh" ? "檔案命名規則：" : "File naming convention:"}
              </p>
              <code className="block bg-gray-100 px-3 py-2 rounded">
                {"{"}學號{"}"}_文件類型.pdf
              </code>
              <p className="text-sm">
                {locale === "zh" ? "範例：" : "Examples:"}
              </p>
              <ul className="text-sm list-disc list-inside space-y-1">
                <li>
                  <code>111111111_transcript.pdf</code> (
                  {locale === "zh" ? "成績單" : "Transcript"})
                </li>
                <li>
                  <code>111111111_id_card.pdf</code> (
                  {locale === "zh" ? "身份證" : "ID Card"})
                </li>
                <li>
                  <code>222222222_bank_book.pdf</code> (
                  {locale === "zh" ? "存摺封面" : "Bank Book"})
                </li>
              </ul>
              <p className="text-sm text-gray-600">
                {locale === "zh"
                  ? "支援格式：PDF, JPG, PNG"
                  : "Supported formats: PDF, JPG, PNG"}
              </p>
            </div>
          </AlertDescription>
        </Alert>

        {/* Error message */}
        {error && (
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Upload results summary */}
        {uploadResults && (
          <Alert
            variant={uploadResults.error_count === 0 ? "default" : "destructive"}
          >
            <Info className="h-4 w-4" />
            <AlertDescription>
              <div className="space-y-1">
                <p className="font-semibold">
                  {locale === "zh" ? "上傳結果摘要：" : "Upload Summary:"}
                </p>
                <p>
                  {locale === "zh" ? "總檔案數" : "Total files"}:{" "}
                  {uploadResults.total_files}
                </p>
                <p className="text-green-600">
                  {locale === "zh" ? "成功" : "Success"}:{" "}
                  {uploadResults.matched_count}
                </p>
                <p className="text-red-600">
                  {locale === "zh" ? "失敗" : "Failed"}:{" "}
                  {uploadResults.error_count + uploadResults.unmatched_count}
                </p>
              </div>
            </AlertDescription>
          </Alert>
        )}

        {/* File upload area */}
        {!uploadResults && (
          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              isDragging
                ? "border-nycu-blue-500 bg-nycu-blue-50"
                : "border-gray-300 hover:border-gray-400"
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <Upload className="h-12 w-12 mx-auto mb-4 text-gray-400" />
            <p className="text-lg font-medium mb-2">
              {locale === "zh"
                ? "拖放 ZIP 檔案到此處"
                : "Drag and drop ZIP file here"}
            </p>
            <p className="text-sm text-gray-500 mb-4">
              {locale === "zh" ? "或" : "or"}
            </p>
            <label>
              <input
                type="file"
                accept=".zip"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) handleFileSelect(file);
                }}
                className="hidden"
              />
              <Button type="button" variant="outline" asChild>
                <span>{locale === "zh" ? "選擇檔案" : "Select File"}</span>
              </Button>
            </label>
            {selectedFile && (
              <div className="mt-4 flex items-center justify-center gap-2 text-sm text-gray-600">
                <FileArchive className="h-4 w-4" />
                <span>{selectedFile.name}</span>
                <span className="text-gray-400">
                  ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)
                </span>
              </div>
            )}
          </div>
        )}

        {/* Upload button */}
        {!uploadResults && selectedFile && (
          <Button
            onClick={handleUpload}
            disabled={isUploading}
            className="w-full"
          >
            {isUploading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {locale === "zh" ? "上傳中..." : "Uploading..."}
              </>
            ) : (
              <>
                <Upload className="mr-2 h-4 w-4" />
                {locale === "zh" ? "開始上傳" : "Start Upload"}
              </>
            )}
          </Button>
        )}

        {/* Upload results table */}
        {uploadResults && uploadResults.results.length > 0 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="font-semibold">
                {locale === "zh" ? "詳細結果" : "Detailed Results"}
              </h4>
              <Button
                onClick={() => {
                  setUploadResults(null);
                  setSelectedFile(null);
                }}
                variant="outline"
                size="sm"
              >
                {locale === "zh" ? "上傳更多" : "Upload More"}
              </Button>
            </div>
            <div className="overflow-x-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{locale === "zh" ? "學號" : "Student ID"}</TableHead>
                    <TableHead>{locale === "zh" ? "檔案名稱" : "File Name"}</TableHead>
                    <TableHead>{locale === "zh" ? "文件類型" : "Document Type"}</TableHead>
                    <TableHead>{locale === "zh" ? "狀態" : "Status"}</TableHead>
                    <TableHead>{locale === "zh" ? "訊息" : "Message"}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {uploadResults.results.map((result, idx) => (
                    <TableRow
                      key={idx}
                      className={
                        result.status === "error" ? "bg-red-50" : undefined
                      }
                    >
                      <TableCell className="font-mono">
                        {result.student_id || "-"}
                      </TableCell>
                      <TableCell className="text-sm">
                        {result.file_name}
                      </TableCell>
                      <TableCell>{result.document_type}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {getStatusIcon(result.status)}
                          {getStatusBadge(result.status)}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">
                        {result.message || "-"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
