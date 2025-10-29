"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Eye, FileText } from "lucide-react";
import { Locale } from "@/lib/validators";

interface FilePreviewDialogProps {
  isOpen: boolean;
  onClose: () => void;
  file: {
    url: string;
    filename: string;
    type: string;
    downloadUrl?: string; // 添加下載URL
  } | null;
  locale: Locale;
}

export function FilePreviewDialog({
  isOpen,
  onClose,
  file,
  locale,
}: FilePreviewDialogProps) {
  const [isLoading, setIsLoading] = useState(true);

  // Reset loading state when dialog opens or file changes
  useEffect(() => {
    if (isOpen && file) {
      setIsLoading(true);
    }
  }, [isOpen, file?.url]);

  const handleOpenInNewWindow = () => {
    if (!file) return;

    // 使用前端URL在新視窗開啟，確保包含token
    const frontendUrl = file.url.startsWith("/api/v1/preview")
      ? file.url
      : file.url; // 如果已經是前端URL就直接使用

    window.open(frontendUrl, "_blank");
  };

  const handleDownload = () => {
    if (!file) return;

    // 如果有專門的下載URL，使用它；否則使用預覽URL
    const downloadUrl = file.downloadUrl || file.url;

    // 創建一個隱藏的 a 標籤來下載文件
    const link = document.createElement("a");
    link.href = downloadUrl;
    link.download = file.filename;
    link.target = "_blank";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (!file) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            {locale === "zh" ? "文件預覽" : "File Preview"}
          </DialogTitle>
          <DialogDescription>{file.filename}</DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-hidden relative">
          {file.type.includes("pdf") ? (
            <>
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-background p-8">
                  <div className="w-full max-w-2xl space-y-4">
                    <div className="space-y-3">
                      <Skeleton className="h-6 w-full" />
                      <Skeleton className="h-6 w-[90%]" />
                      <Skeleton className="h-6 w-[85%]" />
                      <Skeleton className="h-6 w-[95%]" />
                      <Skeleton className="h-6 w-[80%]" />
                    </div>
                    <div className="space-y-3 pt-4">
                      <Skeleton className="h-6 w-full" />
                      <Skeleton className="h-6 w-[88%]" />
                      <Skeleton className="h-6 w-[92%]" />
                    </div>
                    <p className="text-sm text-muted-foreground text-center pt-4">
                      {locale === "zh" ? "載入中..." : "Loading..."}
                    </p>
                  </div>
                </div>
              )}
              <iframe
                src={file.url}
                className={`w-full h-[70vh] border rounded transition-opacity duration-300 ${
                  isLoading ? "opacity-0" : "opacity-100"
                }`}
                title={file.filename}
                onLoad={() => setIsLoading(false)}
                onError={() => setIsLoading(false)}
              />
            </>
          ) : file.type.includes("image") ? (
            <div className="flex justify-center items-center h-[70vh] bg-muted rounded relative">
              {isLoading && (
                <div className="absolute inset-0 flex items-center justify-center p-8">
                  <Skeleton className="w-full h-full max-w-3xl max-h-[60vh] rounded-lg" />
                </div>
              )}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={file.url}
                alt={file.filename}
                className={`max-w-full max-h-full object-contain transition-opacity duration-300 ${
                  isLoading ? "opacity-0" : "opacity-100"
                }`}
                onLoad={() => setIsLoading(false)}
                onError={() => setIsLoading(false)}
              />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-[70vh] bg-muted rounded">
              <FileText className="h-16 w-16 text-muted-foreground mb-4" />
              <p className="text-lg font-medium mb-2">{file.filename}</p>
              <p className="text-sm text-muted-foreground mb-4">
                {locale === "zh"
                  ? "此文件類型無法預覽"
                  : "This file type cannot be previewed"}
              </p>
              <Button onClick={handleOpenInNewWindow} variant="outline">
                <Eye className="h-4 w-4 mr-2" />
                {locale === "zh" ? "在新視窗開啟" : "Open in New Window"}
              </Button>
            </div>
          )}

          <div className="flex justify-between items-center mt-4">
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleOpenInNewWindow}>
                <Eye className="h-4 w-4 mr-2" />
                {locale === "zh" ? "在新視窗開啟" : "Open in New Window"}
              </Button>
              <Button variant="outline" onClick={handleDownload}>
                <FileText className="h-4 w-4 mr-2" />
                {locale === "zh" ? "下載" : "Download"}
              </Button>
            </div>
            <Button variant="outline" onClick={onClose}>
              {locale === "zh" ? "關閉" : "Close"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
