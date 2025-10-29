"use client";

import type React from "react";

import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Upload, File, X, CheckCircle, AlertCircle, Eye } from "lucide-react";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { Locale } from "@/lib/validators";

interface FileUploadProps {
  onFilesChange: (files: File[]) => void;
  acceptedTypes?: string[];
  maxSize?: number;
  maxFiles?: number;
  initialFiles?: File[]; // 支持初始文件
  fileType?: string; // 文件類型標識符
  locale?: Locale; // 添加語言支持
}

export function FileUpload({
  onFilesChange,
  acceptedTypes = [".pdf", ".jpg", ".jpeg", ".png"],
  maxSize = 10 * 1024 * 1024, // 10MB
  maxFiles = 5,
  initialFiles = [],
  fileType = "",
  locale = "zh",
}: FileUploadProps) {
  const [files, setFiles] = useState<File[]>(initialFiles);
  const [dragActive, setDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{
    [key: string]: number;
  }>({});
  const [uploadStatus, setUploadStatus] = useState<{
    [key: string]: "uploading" | "success" | "error";
  }>({});
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);
  const [isPreviewDialogOpen, setIsPreviewDialogOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  // 為每個組件生成穩定的唯一 ID
  const inputId = useMemo(
    () =>
      `file-upload-${fileType || "default"}-${Math.random().toString(36).substr(2, 9)}`,
    [fileType]
  );

  // 檢查文件是否為已上傳的文件
  const isUploadedFile = (file: File) => {
    return (file as any).id || (file as any).file_path || (file as any).url;
  };

  // 初始化和同步外部文件
  useEffect(() => {
    setFiles([...initialFiles]);
  }, [initialFiles]);

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFiles(Array.from(e.dataTransfer.files));
    }
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFiles(Array.from(e.target.files));
    }
  };

  const handleFiles = (newFiles: File[]) => {
    const validFiles = newFiles.filter(file => {
      // Check file type
      const fileExtension = "." + file.name.split(".").pop()?.toLowerCase();
      if (!acceptedTypes.includes(fileExtension)) {
        return false;
      }

      // Check file size
      if (file.size > maxSize) {
        return false;
      }

      return true;
    });

    const updatedFiles = [...files, ...validFiles].slice(0, maxFiles);
    setFiles(updatedFiles);
    onFilesChange(updatedFiles);

    // Simulate upload progress for new files only
    validFiles.forEach(file => {
      // 跳過已上傳的文件
      if (isUploadedFile(file)) return;

      const fileName = `${fileType}_${file.name}`; // Add fileType prefix to avoid conflicts
      setUploadStatus(prev => ({ ...prev, [fileName]: "uploading" }));

      let progress = 0;
      const interval = setInterval(() => {
        progress += Math.random() * 30;
        if (progress >= 100) {
          progress = 100;
          setUploadStatus(prev => ({ ...prev, [fileName]: "success" }));
          clearInterval(interval);
        }
        setUploadProgress(prev => ({ ...prev, [fileName]: progress }));
      }, 200);
    });
  };

  const removeFile = (index: number) => {
    const fileToRemove = files[index];
    const updatedFiles = files.filter((_, i) => i !== index);
    setFiles(updatedFiles);
    onFilesChange(updatedFiles);

    // Clean up progress and status for removed file
    if (fileToRemove) {
      const fileName = `${fileType}_${fileToRemove.name}`;
      setUploadProgress(prev => {
        const newProgress = { ...prev };
        delete newProgress[fileName];
        return newProgress;
      });
      setUploadStatus(prev => {
        const newStatus = { ...prev };
        delete newStatus[fileName];
        return newStatus;
      });
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (
      Number.parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i]
    );
  };

  // 獲取文件的顯示大小
  const getFileDisplaySize = (file: File) => {
    // 如果是已上傳的文件，優先使用 originalSize
    if (isUploadedFile(file) && (file as any).originalSize) {
      return formatFileSize((file as any).originalSize);
    }
    return formatFileSize(file.size);
  };

  // 獲取文件的預覽URL
  const getFilePreviewUrl = (file: File) => {
    if (isUploadedFile(file)) {
      // 如果是已上傳的文件，使用其URL
      return (
        (file as any).url ||
        (file as any).file_path ||
        URL.createObjectURL(file)
      );
    }
    // 如果是本地文件，創建臨時URL
    return URL.createObjectURL(file);
  };

  // 獲取文件類型
  const getFileType = (file: File) => {
    const filename = file.name.toLowerCase();
    if (filename.endsWith(".pdf")) {
      return "application/pdf";
    } else if (
      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"].some(ext =>
        filename.endsWith(ext)
      )
    ) {
      return "image";
    }
    return "other";
  };

  // 處理文件預覽
  const handleFilePreview = (file: File) => {
    const previewUrl = getFilePreviewUrl(file);
    const fileType = getFileType(file);

    setPreviewFile({
      url: previewUrl,
      filename: file.name,
      type: fileType,
    });
    setIsPreviewDialogOpen(true);
  };

  // 清理臨時URL
  const cleanupTempUrl = useCallback((url: string) => {
    if (url.startsWith("blob:")) {
      URL.revokeObjectURL(url);
    }
  }, []);

  // 組件卸載時清理臨時URL
  useState(() => {
    return () => {
      files.forEach(file => {
        if (!isUploadedFile(file)) {
          cleanupTempUrl(URL.createObjectURL(file));
        }
      });
    };
  });

  return (
    <div className="space-y-4">
      <Card
        className={`border-2 border-dashed transition-colors ${
          dragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/25"
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <CardContent className="flex flex-col items-center justify-center p-6 text-center">
          <Upload className="h-10 w-10 text-muted-foreground mb-4" />
          <div className="space-y-2">
            <p className="text-sm font-medium">拖放檔案到此處或點擊上傳</p>
            <p className="text-xs text-muted-foreground">
              支援格式: {acceptedTypes.join(", ")} | 最大檔案大小:{" "}
              {formatFileSize(maxSize)}
            </p>
          </div>

          <input
            type="file"
            multiple
            accept={acceptedTypes.join(",")}
            onChange={handleChange}
            className="hidden"
            id={inputId}
          />
          <Button asChild className="mt-4">
            <label htmlFor={inputId} className="cursor-pointer">
              選擇檔案
            </label>
          </Button>
        </CardContent>
      </Card>

      {files.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">
            已上傳檔案 ({files.length}/{maxFiles}) - {fileType || "未指定類型"}
          </h4>
          {files.map((file, index) => (
            <Card key={index}>
              <CardContent className="flex items-center justify-between p-3">
                <div className="flex items-center space-x-3">
                  <File className="h-4 w-4 text-muted-foreground" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {getFileDisplaySize(file)}
                      {isUploadedFile(file) && (
                        <span className="ml-1 text-blue-600">已上傳</span>
                      )}
                    </p>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  {/* 預覽按鈕 */}
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleFilePreview(file)}
                  >
                    <Eye className="h-4 w-4" />
                  </Button>

                  {(() => {
                    const fileName = `${fileType}_${file.name}`;
                    const isUploaded = isUploadedFile(file);

                    // 如果是已上傳的文件，顯示已上傳狀態
                    if (isUploaded) {
                      return (
                        <Badge variant="outline" className="text-xs">
                          <CheckCircle className="h-3 w-3 mr-1" />
                          已存在
                        </Badge>
                      );
                    }

                    // 新上傳文件的狀態顯示
                    return (
                      <>
                        {uploadStatus[fileName] === "uploading" && (
                          <div className="flex items-center space-x-2">
                            <Progress
                              value={uploadProgress[fileName] || 0}
                              className="w-20 h-2"
                            />
                            <span className="text-xs text-muted-foreground">
                              {Math.round(uploadProgress[fileName] || 0)}%
                            </span>
                          </div>
                        )}

                        {uploadStatus[fileName] === "success" && (
                          <Badge variant="default" className="text-xs">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            完成
                          </Badge>
                        )}

                        {uploadStatus[fileName] === "error" && (
                          <Badge variant="destructive" className="text-xs">
                            <AlertCircle className="h-3 w-3 mr-1" />
                            失敗
                          </Badge>
                        )}
                      </>
                    );
                  })()}

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeFile(index)}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* 文件預覽對話框 */}
      <FilePreviewDialog
        isOpen={isPreviewDialogOpen}
        onClose={() => setIsPreviewDialogOpen(false)}
        file={previewFile}
        locale={locale}
      />
    </div>
  );
}
