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
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import apiClient from "@/lib/api";
import type { SupplementaryDoc } from "@/lib/api/modules/system-settings";

const ACCEPTED = ".pdf,.doc,.docx";
const ACCEPTED_LABEL = "PDF · DOC · DOCX";
const MAX_SIZE_MB = 10;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (doc: SupplementaryDoc) => void;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function AddSupplementaryDocDialog({
  open,
  onOpenChange,
  onCreated,
}: Props) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dragActive, setDragActive] = useState(false);

  const reset = () => {
    setTitle("");
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
    const trimmed = title.trim();
    if (!trimmed) {
      toast.error("請輸入標題");
      return;
    }
    if (trimmed.length > 200) {
      toast.error("標題不得超過 200 字");
      return;
    }
    if (!file) {
      toast.error("請選擇檔案");
      return;
    }
    setSubmitting(true);
    try {
      const res = await apiClient.systemSettings.supplementaryDocs.upload(
        file,
        trimmed
      );
      if (res.success && res.data) {
        toast.success("已新增補充參考文件");
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
          <DialogTitle>新增補充參考文件</DialogTitle>
          <DialogDescription>
            上傳後學生即可在申請須知頁面看到此檔案。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label htmlFor="supp-doc-title">標題</Label>
            <Input
              id="supp-doc-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：FAQ"
              maxLength={200}
              disabled={submitting}
            />
            <p className="text-xs text-gray-500 mt-1">
              {title.length}/200
            </p>
          </div>

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
                onChange={(e) =>
                  validateAndSet(e.target.files?.[0] || null)
                }
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
                <p
                  className="text-sm font-medium truncate"
                  title={file.name}
                >
                  {file.name}
                </p>
                <p className="text-xs text-gray-500">{formatBytes(file.size)}</p>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setFile(null)}
                disabled={submitting}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          )}

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
              {submitting && (
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
              )}
              {submitting ? "上傳中..." : "上傳"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
