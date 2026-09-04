"use client";

import { useState } from "react";
import { CloudUpload, FileType2, Loader2, X } from "lucide-react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import apiClient from "@/lib/api";
import type { FooterLink } from "@/lib/api/modules/footer-links";

const ACCEPTED = ".pdf,.doc,.docx,.odt,.ods,.odp";
const ACCEPTED_LABEL = "PDF · DOC · DOCX · ODF";
const MAX_SIZE_MB = 10;
const MAX_TITLE_LENGTH = 200;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (link: FooterLink) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function AddFooterLinkDialog({ open, onOpenChange, onCreated }: Props) {
  const [mode, setMode] = useState<"url" | "file">("url");
  const [titleZh, setTitleZh] = useState("");
  const [titleEn, setTitleEn] = useState("");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const reset = () => {
    setMode("url");
    setTitleZh("");
    setTitleEn("");
    setUrl("");
    setFile(null);
    setDragActive(false);
  };

  const validateAndSet = (f: File | null) => {
    if (!f) return;
    const ext = "." + (f.name.toLowerCase().split(".").pop() || "");
    if (!ACCEPTED.split(",").includes(ext)) {
      toast.error(`僅接受 ${ACCEPTED_LABEL}`);
      return;
    }
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`檔案大小超過 ${MAX_SIZE_MB} MB`);
      return;
    }
    setFile(f);
  };

  const handleSubmit = async () => {
    const trimmedZh = titleZh.trim();
    if (!trimmedZh) {
      toast.error("請輸入中文名稱");
      return;
    }
    if (trimmedZh.length > MAX_TITLE_LENGTH) {
      toast.error(`名稱不得超過 ${MAX_TITLE_LENGTH} 字`);
      return;
    }

    const trimmedEn = titleEn.trim();

    if (mode === "url") {
      const trimmedUrl = url.trim();
      if (!trimmedUrl) {
        toast.error("請輸入網址");
        return;
      }
      // Mirrors the backend guard so the admin sees the problem immediately.
      if (!/^https?:\/\/.+/i.test(trimmedUrl)) {
        toast.error("網址必須以 http:// 或 https:// 開頭");
        return;
      }
      setSubmitting(true);
      try {
        const res = await apiClient.footerLinks.create({
          title_zh: trimmedZh,
          title_en: trimmedEn || null,
          url: trimmedUrl,
        });
        if (res.success && res.data) {
          toast.success("已新增相關連結");
          onCreated(res.data);
          reset();
          onOpenChange(false);
        } else {
          toast.error(res.message || "新增失敗");
        }
      } catch {
        toast.error("新增失敗");
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (!file) {
      toast.error("請選擇檔案");
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiClient.footerLinks.upload(
        file,
        trimmedZh,
        trimmedEn || undefined
      );
      if (res.success && res.data) {
        toast.success("已新增相關連結");
        onCreated(res.data);
        reset();
        onOpenChange(false);
      } else {
        toast.error(res.message || "上傳失敗");
      }
    } catch {
      toast.error("上傳失敗");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!submitting) {
          onOpenChange(next);
          if (!next) reset();
        }
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>新增相關連結</DialogTitle>
          <DialogDescription>
            新增後會顯示在網頁最下方的「相關連結」區塊。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="footer-link-title-zh">名稱（中文）</Label>
            <Input
              id="footer-link-title-zh"
              value={titleZh}
              onChange={(e) => setTitleZh(e.target.value)}
              placeholder="例如：獎學金申請指南"
              maxLength={MAX_TITLE_LENGTH}
              disabled={submitting}
            />
          </div>

          <div>
            <Label htmlFor="footer-link-title-en">名稱（英文，選填）</Label>
            <Input
              id="footer-link-title-en"
              value={titleEn}
              onChange={(e) => setTitleEn(e.target.value)}
              placeholder="Scholarship Guide"
              maxLength={MAX_TITLE_LENGTH}
              disabled={submitting}
            />
            <p className="text-xs text-gray-500 mt-1">
              未填寫時，英文介面會顯示中文名稱。
            </p>
          </div>

          <Tabs
            value={mode}
            onValueChange={(next) => setMode(next as "url" | "file")}
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="url" disabled={submitting}>
                外部網址
              </TabsTrigger>
              <TabsTrigger value="file" disabled={submitting}>
                上傳檔案
              </TabsTrigger>
            </TabsList>

            <TabsContent value="url" className="mt-4">
              <Label htmlFor="footer-link-url">網址</Label>
              <Input
                id="footer-link-url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.nycu.edu.tw"
                disabled={submitting}
              />
            </TabsContent>

            <TabsContent value="file" className="mt-4">
              {!file ? (
                <label
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragActive(true);
                  }}
                  onDragLeave={() => setDragActive(false)}
                  onDrop={(e) => {
                    e.preventDefault();
                    setDragActive(false);
                    validateAndSet(e.dataTransfer.files?.[0] || null);
                  }}
                  className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed cursor-pointer py-8 ${
                    dragActive
                      ? "border-nycu-blue-500 bg-nycu-blue-50"
                      : "border-gray-300 hover:border-nycu-blue-400 hover:bg-nycu-blue-50/40"
                  }`}
                >
                  <input
                    type="file"
                    accept={ACCEPTED}
                    className="sr-only"
                    onChange={(e) => validateAndSet(e.target.files?.[0] || null)}
                  />
                  <CloudUpload className="h-6 w-6 text-nycu-blue-600 mb-2" />
                  <p className="text-sm font-medium text-nycu-navy-800">
                    拖曳檔案或點擊選擇
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    支援 {ACCEPTED_LABEL} · 上限 {MAX_SIZE_MB} MB
                  </p>
                </label>
              ) : (
                <div className="rounded-lg border bg-gray-50 p-3 flex items-center gap-3">
                  <FileType2 className="h-5 w-5 text-nycu-blue-600 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate" title={file.name}>
                      {file.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {formatBytes(file.size)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setFile(null)}
                    disabled={submitting}
                    aria-label="移除檔案"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </TabsContent>
          </Tabs>

          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={() => {
                if (!submitting) {
                  reset();
                  onOpenChange(false);
                }
              }}
              disabled={submitting}
            >
              取消
            </Button>
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />}
              {submitting ? "處理中..." : "新增"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
