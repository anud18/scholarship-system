"use client";

import { useEffect, useRef, useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  BookOpen,
  CheckCircle2,
  CloudUpload,
  Eye,
  FileArchive,
  FileText,
  FileType2,
  Loader2,
  RotateCcw,
  X,
} from "lucide-react";
import apiClient from "@/lib/api";
import { toast } from "sonner";
import { FilePreviewDialog } from "@/components/file-preview-dialog";

type DocKey = "regulations_url" | "sample_document_url";

interface DocSlot {
  key: DocKey;
  title: string;
  subtitle: string;
  Icon: React.ComponentType<{ className?: string }>;
  accent: {
    ring: string;
    tile: string;
    iconColor: string;
    pillBg: string;
    dropHover: string;
    dropActive: string;
  };
}

const SLOTS: DocSlot[] = [
  {
    key: "regulations_url",
    title: "獎學金要點",
    subtitle: "提供學生、教授與學院審核時參閱的法規文件",
    Icon: BookOpen,
    accent: {
      ring: "ring-nycu-blue-200",
      tile: "bg-nycu-blue-50",
      iconColor: "text-nycu-blue-600",
      pillBg: "bg-nycu-blue-100 text-nycu-blue-700",
      dropHover: "hover:border-nycu-blue-400 hover:bg-nycu-blue-50/40",
      dropActive:
        "border-nycu-blue-500 bg-nycu-blue-50 ring-4 ring-nycu-blue-100",
    },
  },
  {
    key: "sample_document_url",
    title: "申請文件範例檔",
    subtitle: "提供學生填寫申請文件時的參考範例",
    Icon: FileArchive,
    accent: {
      ring: "ring-amber-200",
      tile: "bg-amber-50",
      iconColor: "text-amber-600",
      pillBg: "bg-amber-100 text-amber-700",
      dropHover: "hover:border-amber-400 hover:bg-amber-50/40",
      dropActive: "border-amber-500 bg-amber-50 ring-4 ring-amber-100",
    },
  },
];

const ACCEPTED = ".pdf,.doc,.docx";
const MAX_SIZE_MB = 10;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function fileTypeBadge(name: string): string {
  const ext = name.toLowerCase().split(".").pop() || "";
  if (ext === "pdf") return "PDF";
  if (ext === "docx") return "DOCX";
  if (ext === "doc") return "DOC";
  return ext.toUpperCase() || "檔案";
}

function previewMimeType(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".doc")) return "application/msword";
  if (lower.endsWith(".docx"))
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  return "application/octet-stream";
}

export function SystemDocsPanel() {
  const [currentFiles, setCurrentFiles] = useState<
    Record<DocKey, { objectName: string; displayName: string } | null>
  >({
    regulations_url: null,
    sample_document_url: null,
  });
  const [pendingFiles, setPendingFiles] = useState<Record<DocKey, File | null>>(
    { regulations_url: null, sample_document_url: null }
  );
  const [uploading, setUploading] = useState<Record<DocKey, boolean>>({
    regulations_url: false,
    sample_document_url: false,
  });
  const [dragActive, setDragActive] = useState<Record<DocKey, boolean>>({
    regulations_url: false,
    sample_document_url: false,
  });
  const [preview, setPreview] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);
  const inputRefs = {
    regulations_url: useRef<HTMLInputElement>(null),
    sample_document_url: useRef<HTMLInputElement>(null),
  };

  useEffect(() => {
    apiClient.systemSettings.getPublicDocs().then((res) => {
      if (!res.success || !res.data) return;
      const next: typeof currentFiles = {
        regulations_url: null,
        sample_document_url: null,
      };
      if (res.data.regulations_url) {
        next.regulations_url = {
          objectName: res.data.regulations_url,
          displayName:
            res.data.regulations_url_filename ||
            res.data.regulations_url.split("/").pop() ||
            "",
        };
      }
      if (res.data.sample_document_url) {
        next.sample_document_url = {
          objectName: res.data.sample_document_url,
          displayName:
            res.data.sample_document_url_filename ||
            res.data.sample_document_url.split("/").pop() ||
            "",
        };
      }
      setCurrentFiles(next);
    });
  }, []);

  const validateAndSet = (key: DocKey, file: File | null) => {
    if (!file) return;
    const ext = "." + (file.name.toLowerCase().split(".").pop() || "");
    if (!ACCEPTED.split(",").includes(ext)) {
      toast.error("僅接受 PDF / DOC / DOCX");
      return;
    }
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`檔案大小超過 ${MAX_SIZE_MB} MB`);
      return;
    }
    setPendingFiles((p) => ({ ...p, [key]: file }));
  };

  const doUpload = async (key: DocKey) => {
    const file = pendingFiles[key];
    if (!file) return;
    setUploading((u) => ({ ...u, [key]: true }));
    try {
      const res =
        key === "regulations_url"
          ? await apiClient.systemSettings.uploadRegulations(file)
          : await apiClient.systemSettings.uploadSampleDocument(file);
      if (res.success) {
        toast.success(
          key === "regulations_url" ? "獎學金要點已更新" : "申請文件範例檔已更新"
        );
        setCurrentFiles((c) => ({
          ...c,
          [key]: {
            objectName: res.data?.object_name || "",
            displayName: res.data?.original_filename || file.name,
          },
        }));
        setPendingFiles((p) => ({ ...p, [key]: null }));
      } else {
        toast.error(res.message || "上傳失敗");
      }
    } catch {
      toast.error("上傳失敗");
    } finally {
      setUploading((u) => ({ ...u, [key]: false }));
    }
  };

  const openPreview = (key: DocKey) => {
    const current = currentFiles[key];
    if (!current) return;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("auth_token") || ""
        : "";
    const cacheBuster = encodeURIComponent(
      current.objectName.split("/").pop() || ""
    );
    const url = `/api/v1/system-settings/file-proxy?key=${key}&token=${encodeURIComponent(
      token
    )}&v=${cacheBuster}`;
    setPreview({
      url,
      filename: current.displayName,
      type: previewMimeType(current.displayName),
    });
  };

  const onDrop = (key: DocKey, e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive((d) => ({ ...d, [key]: false }));
    const file = e.dataTransfer.files?.[0];
    validateAndSet(key, file || null);
  };

  return (
    <>
      <Card className="overflow-hidden border-gray-200/80 shadow-sm">
        <CardHeader className="bg-gradient-to-br from-gray-50 to-white border-b">
          <div className="flex items-start gap-4">
            <div className="rounded-xl bg-nycu-navy-900 p-3 shadow-sm">
              <FileText className="h-6 w-6 text-white" />
            </div>
            <div className="flex-1">
              <CardTitle className="text-xl text-nycu-navy-900">
                系統文件管理
              </CardTitle>
              <CardDescription className="mt-1">
                上傳供學生、教授及學院端參閱的全域文件。更新後，所有使用者下次開啟頁面即可看到最新版本。
              </CardDescription>
            </div>
          </div>
        </CardHeader>

        <CardContent className="grid gap-6 p-6 lg:grid-cols-2">
          {SLOTS.map((slot) => {
            const current = currentFiles[slot.key];
            const pending = pendingFiles[slot.key];
            const isUploading = uploading[slot.key];
            const isDragging = dragActive[slot.key];
            const Icon = slot.Icon;

            return (
              <section
                key={slot.key}
                className={`rounded-xl bg-white border border-gray-200 ring-1 ring-transparent transition-all ${slot.accent.ring} hover:shadow-sm`}
              >
                {/* Slot header */}
                <header className="flex items-start gap-4 p-5 border-b border-gray-100">
                  <div
                    className={`rounded-lg p-2.5 ${slot.accent.tile} flex-shrink-0`}
                  >
                    <Icon className={`h-6 w-6 ${slot.accent.iconColor}`} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3 className="font-semibold text-nycu-navy-900">
                        {slot.title}
                      </h3>
                      {current && (
                        <Badge
                          variant="outline"
                          className="gap-1 border-green-200 bg-green-50 text-green-700"
                        >
                          <CheckCircle2 className="h-3 w-3" />
                          已上傳
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-gray-500 mt-0.5 leading-relaxed">
                      {slot.subtitle}
                    </p>
                  </div>
                </header>

                {/* Body */}
                <div className="p-5 space-y-4">
                  {/* Existing file card */}
                  {current && !pending && (
                    <div className="rounded-lg border border-gray-200 bg-gradient-to-br from-gray-50/60 to-white p-4">
                      <div className="flex items-start gap-3">
                        <div
                          className={`rounded-md ${slot.accent.tile} p-2 flex-shrink-0`}
                        >
                          <FileType2
                            className={`h-5 w-5 ${slot.accent.iconColor}`}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span
                              className={`text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded ${slot.accent.pillBg}`}
                            >
                              {fileTypeBadge(current.displayName)}
                            </span>
                            <p
                              className="text-sm font-medium text-nycu-navy-900 truncate"
                              title={current.displayName}
                            >
                              {current.displayName}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 mt-4 pt-3 border-t border-gray-100">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openPreview(slot.key)}
                          className="text-nycu-blue-600 hover:bg-nycu-blue-50"
                        >
                          <Eye className="h-4 w-4 mr-1.5" />
                          預覽
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => inputRefs[slot.key].current?.click()}
                          className="text-gray-600 hover:bg-gray-100"
                        >
                          <RotateCcw className="h-4 w-4 mr-1.5" />
                          替換
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Pending file card */}
                  {pending && (
                    <div className="rounded-lg border-2 border-dashed border-nycu-blue-300 bg-nycu-blue-50/40 p-4">
                      <div className="flex items-start gap-3">
                        <div className="rounded-md bg-white p-2 border border-nycu-blue-200 flex-shrink-0">
                          <FileType2 className="h-5 w-5 text-nycu-blue-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span
                              className={`text-[10px] font-semibold tracking-wider px-1.5 py-0.5 rounded ${slot.accent.pillBg}`}
                            >
                              {fileTypeBadge(pending.name)}
                            </span>
                            <p
                              className="text-sm font-medium text-nycu-navy-900 truncate"
                              title={pending.name}
                            >
                              {pending.name}
                            </p>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            {formatBytes(pending.size)} · 待上傳
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 mt-4 pt-3 border-t border-nycu-blue-100">
                        <Button
                          size="sm"
                          onClick={() => doUpload(slot.key)}
                          disabled={isUploading}
                          className="nycu-gradient text-white"
                        >
                          {isUploading ? (
                            <>
                              <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                              上傳中...
                            </>
                          ) : (
                            <>
                              <CloudUpload className="h-4 w-4 mr-1.5" />
                              {current ? "確認替換" : "確認上傳"}
                            </>
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setPendingFiles((p) => ({
                              ...p,
                              [slot.key]: null,
                            }))
                          }
                          disabled={isUploading}
                          className="text-gray-600"
                        >
                          <X className="h-4 w-4 mr-1.5" />
                          取消
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Drop zone (empty state, or minimal CTA when file exists) */}
                  {!pending && (
                    <label
                      onDragOver={(e) => {
                        e.preventDefault();
                        setDragActive((d) => ({ ...d, [slot.key]: true }));
                      }}
                      onDragLeave={() =>
                        setDragActive((d) => ({ ...d, [slot.key]: false }))
                      }
                      onDrop={(e) => onDrop(slot.key, e)}
                      className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed cursor-pointer transition-all ${
                        isDragging
                          ? slot.accent.dropActive
                          : `border-gray-300 ${slot.accent.dropHover}`
                      } ${current ? "py-6" : "py-10"}`}
                    >
                      <input
                        ref={inputRefs[slot.key]}
                        type="file"
                        accept={ACCEPTED}
                        onChange={(e) =>
                          validateAndSet(slot.key, e.target.files?.[0] || null)
                        }
                        className="sr-only"
                      />
                      <div
                        className={`rounded-full p-3 mb-3 ${slot.accent.tile}`}
                      >
                        <CloudUpload
                          className={`h-6 w-6 ${slot.accent.iconColor}`}
                        />
                      </div>
                      <p className="text-sm font-medium text-nycu-navy-800">
                        {current
                          ? "上傳新檔案以替換"
                          : "拖曳檔案至此或點擊選擇"}
                      </p>
                      <p className="text-xs text-gray-500 mt-1.5">
                        支援 PDF · DOC · DOCX · 上限 {MAX_SIZE_MB} MB
                      </p>
                    </label>
                  )}
                </div>
              </section>
            );
          })}
        </CardContent>
      </Card>

      <FilePreviewDialog
        isOpen={preview !== null}
        onClose={() => setPreview(null)}
        file={preview}
        locale="zh"
      />
    </>
  );
}
