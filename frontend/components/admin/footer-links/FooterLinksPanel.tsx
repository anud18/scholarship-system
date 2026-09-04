"use client";

import { useEffect, useState } from "react";
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  ExternalLink,
  Eye,
  EyeOff,
  FileText,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import apiClient from "@/lib/api";
import {
  buildFooterLinkFileProxyUrl,
  notifyFooterLinksChanged,
  type FooterLink,
} from "@/lib/api/modules/footer-links";
import { previewMimeType } from "@/lib/utils";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { AddFooterLinkDialog } from "./AddFooterLinkDialog";

const MAX_TITLE_LENGTH = 200;

interface SortableRowProps {
  link: FooterLink;
  disabled: boolean;
  onPreview: (link: FooterLink) => void;
  onEdit: (link: FooterLink) => void;
  onToggleActive: (link: FooterLink) => void;
  onDelete: (link: FooterLink) => void;
}

function SortableRow({
  link,
  disabled,
  onPreview,
  onEdit,
  onToggleActive,
  onDelete,
}: SortableRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: link.id, disabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const isFile = link.link_type === "file";
  const Icon = isFile ? FileText : ExternalLink;
  const subtitle = isFile ? link.original_filename : link.url;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-3 rounded-md border border-gray-200 px-3 py-2 ${
        link.is_active ? "bg-white" : "bg-gray-50"
      }`}
      data-testid={`footer-link-row-${link.id}`}
    >
      <button
        type="button"
        aria-label="拖曳排序"
        className="cursor-grab text-gray-400 hover:text-gray-600 disabled:cursor-not-allowed"
        disabled={disabled}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>

      <Icon
        className={`h-4 w-4 flex-shrink-0 ${
          isFile ? "text-nycu-blue-600" : "text-gray-500"
        }`}
      />

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-nycu-navy-900 truncate">
          {link.title_zh}
          {link.title_en && (
            <span className="ml-2 text-xs font-normal text-gray-400">
              {link.title_en}
            </span>
          )}
          {!link.is_active && (
            <span className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 text-xs font-normal text-gray-600">
              已隱藏
            </span>
          )}
        </p>
        <p
          className="text-xs text-gray-500 truncate"
          title={subtitle ?? undefined}
        >
          {subtitle}
        </p>
      </div>

      {isFile && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onPreview(link)}
          aria-label="預覽"
        >
          <Eye className="h-4 w-4" />
        </Button>
      )}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onToggleActive(link)}
        aria-label={link.is_active ? "隱藏" : "顯示"}
        title={link.is_active ? "隱藏此連結" : "顯示此連結"}
      >
        {link.is_active ? (
          <EyeOff className="h-4 w-4" />
        ) : (
          <Eye className="h-4 w-4 text-green-600" />
        )}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onEdit(link)}
        aria-label="編輯"
      >
        <Pencil className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(link)}
        aria-label="刪除"
        className="text-red-600 hover:bg-red-50"
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function FooterLinksPanel() {
  const [links, setLinks] = useState<FooterLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [reordering, setReordering] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editingLink, setEditingLink] = useState<FooterLink | null>(null);
  const [editTitleZh, setEditTitleZh] = useState("");
  const [editTitleEn, setEditTitleEn] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [deletingLink, setDeletingLink] = useState<FooterLink | null>(null);
  const [preview, setPreview] = useState<
    { url: string; filename: string; type: string } | null
  >(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  useEffect(() => {
    // include_inactive: admins manage hidden links too.
    apiClient.footerLinks
      .list(true)
      .then((res) => {
        if (res.success && res.data) setLinks(res.data);
      })
      .catch(() => toast.error("載入相關連結失敗"))
      .finally(() => setLoading(false));
  }, []);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = links.findIndex((l) => l.id === active.id);
    const newIndex = links.findIndex((l) => l.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const previous = links;
    const next = arrayMove(links, oldIndex, newIndex);
    setLinks(next);
    setReordering(true);

    try {
      const items = next.map((l, idx) => ({ id: l.id, sort_order: idx }));
      const res = await apiClient.footerLinks.reorder(items);
      if (!res.success) {
        setLinks(previous);
        toast.error(res.message || "排序失敗");
      } else {
        setLinks(next.map((l, idx) => ({ ...l, sort_order: idx })));
        notifyFooterLinksChanged();
      }
    } catch {
      setLinks(previous);
      toast.error("排序失敗");
    } finally {
      setReordering(false);
    }
  };

  const handlePreview = (link: FooterLink) => {
    const filename = link.original_filename || "";
    setPreview({
      url: buildFooterLinkFileProxyUrl(link.id, link.object_name),
      filename,
      type: previewMimeType(filename),
    });
  };

  const openEdit = (link: FooterLink) => {
    setEditingLink(link);
    setEditTitleZh(link.title_zh);
    setEditTitleEn(link.title_en || "");
    setEditUrl(link.url || "");
  };

  const saveEdit = async () => {
    if (!editingLink) return;
    const trimmedZh = editTitleZh.trim();
    if (!trimmedZh) {
      toast.error("中文名稱不得為空");
      return;
    }
    if (trimmedZh.length > MAX_TITLE_LENGTH) {
      toast.error(`名稱不得超過 ${MAX_TITLE_LENGTH} 字`);
      return;
    }

    const payload: {
      title_zh: string;
      title_en: string | null;
      url?: string;
    } = {
      title_zh: trimmedZh,
      title_en: editTitleEn.trim() || null,
    };

    if (editingLink.link_type === "url") {
      const trimmedUrl = editUrl.trim();
      if (!/^https?:\/\/.+/i.test(trimmedUrl)) {
        toast.error("網址必須以 http:// 或 https:// 開頭");
        return;
      }
      payload.url = trimmedUrl;
    }

    try {
      const res = await apiClient.footerLinks.update(editingLink.id, payload);
      if (res.success && res.data) {
        setLinks((prev) =>
          prev.map((l) => (l.id === editingLink.id ? res.data! : l))
        );
        setEditingLink(null);
        notifyFooterLinksChanged();
        toast.success("已更新");
      } else {
        toast.error(res.message || "更新失敗");
      }
    } catch {
      toast.error("更新失敗");
    }
  };

  const toggleActive = async (link: FooterLink) => {
    const previous = links;
    const nextActive = !link.is_active;
    setLinks((prev) =>
      prev.map((l) => (l.id === link.id ? { ...l, is_active: nextActive } : l))
    );
    try {
      const res = await apiClient.footerLinks.update(link.id, {
        is_active: nextActive,
      });
      if (!res.success) {
        setLinks(previous);
        toast.error(res.message || "更新失敗");
      } else {
        notifyFooterLinksChanged();
        toast.success(nextActive ? "已顯示" : "已隱藏");
      }
    } catch {
      setLinks(previous);
      toast.error("更新失敗");
    }
  };

  const confirmDelete = async () => {
    if (!deletingLink) return;
    const target = deletingLink;
    setDeletingLink(null);
    const previous = links;
    setLinks((prev) => prev.filter((l) => l.id !== target.id));
    try {
      const res = await apiClient.footerLinks.delete(target.id);
      if (!res.success) {
        setLinks(previous);
        toast.error(res.message || "刪除失敗");
      } else {
        notifyFooterLinksChanged();
        toast.success("已刪除");
      }
    } catch {
      setLinks(previous);
      toast.error("刪除失敗");
    }
  };

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 mt-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-nycu-navy-900">相關連結</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            顯示在網頁最下方的連結，可放外部網址或上傳檔案（PDF 等），並可拖曳排序。
          </p>
        </div>
        <Button onClick={() => setAddOpen(true)} size="sm">
          <Plus className="h-4 w-4 mr-1.5" /> 新增
        </Button>
      </header>

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> 載入中…
        </div>
      ) : links.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">
          目前尚無相關連結，點擊「新增」建立。
        </p>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={links.map((l) => l.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {links.map((link) => (
                <SortableRow
                  key={link.id}
                  link={link}
                  disabled={reordering}
                  onPreview={handlePreview}
                  onEdit={openEdit}
                  onToggleActive={toggleActive}
                  onDelete={(l) => setDeletingLink(l)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <AddFooterLinkDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onCreated={(link) => {
          setLinks((prev) => [...prev, link]);
          notifyFooterLinksChanged();
        }}
      />

      {editingLink && (
        <Dialog open onOpenChange={(next) => !next && setEditingLink(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>編輯相關連結</DialogTitle>
              <DialogDescription>
                {editingLink.link_type === "file"
                  ? "檔案內容無法直接替換，如需更換請刪除後重新上傳。"
                  : "修改此連結的顯示名稱與網址。"}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div>
                <Label htmlFor="edit-footer-title-zh">名稱（中文）</Label>
                <Input
                  id="edit-footer-title-zh"
                  value={editTitleZh}
                  onChange={(e) => setEditTitleZh(e.target.value)}
                  maxLength={MAX_TITLE_LENGTH}
                />
              </div>
              <div>
                <Label htmlFor="edit-footer-title-en">
                  名稱（英文，選填）
                </Label>
                <Input
                  id="edit-footer-title-en"
                  value={editTitleEn}
                  onChange={(e) => setEditTitleEn(e.target.value)}
                  maxLength={MAX_TITLE_LENGTH}
                />
              </div>
              {editingLink.link_type === "url" ? (
                <div>
                  <Label htmlFor="edit-footer-url">網址</Label>
                  <Input
                    id="edit-footer-url"
                    value={editUrl}
                    onChange={(e) => setEditUrl(e.target.value)}
                    placeholder="https://www.nycu.edu.tw"
                  />
                </div>
              ) : (
                <div className="rounded-md border bg-gray-50 px-3 py-2">
                  <p className="text-xs text-gray-500">目前檔案</p>
                  <p className="text-sm truncate">
                    {editingLink.original_filename}
                  </p>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingLink(null)}>
                取消
              </Button>
              <Button onClick={saveEdit}>儲存</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {deletingLink && (
        <Dialog open onOpenChange={(next) => !next && setDeletingLink(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>確認刪除</DialogTitle>
              <DialogDescription>
                刪除後「{deletingLink.title_zh}」將不再顯示於網頁下方
                {deletingLink.link_type === "file" && "，且上傳的檔案會一併移除"}
                ，確定要刪除嗎？
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDeletingLink(null)}>
                取消
              </Button>
              <Button
                onClick={confirmDelete}
                className="bg-red-600 hover:bg-red-700 text-white"
              >
                刪除
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      <FilePreviewDialog
        isOpen={preview !== null}
        onClose={() => setPreview(null)}
        file={preview}
        locale="zh"
      />
    </section>
  );
}
