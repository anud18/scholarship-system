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
  Eye,
  GripVertical,
  Loader2,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  buildSuppDocFileProxyUrl,
  type SupplementaryDoc,
} from "@/lib/api/modules/system-settings";
import { previewMimeType } from "@/lib/utils";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { AddSupplementaryDocDialog } from "./AddSupplementaryDocDialog";

interface SortableRowProps {
  doc: SupplementaryDoc;
  disabled: boolean;
  onPreview: (doc: SupplementaryDoc) => void;
  onEdit: (doc: SupplementaryDoc) => void;
  onDelete: (doc: SupplementaryDoc) => void;
}

function SortableRow({
  doc,
  disabled,
  onPreview,
  onEdit,
  onDelete,
}: SortableRowProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: doc.id, disabled });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="flex items-center gap-3 rounded-md border border-gray-200 bg-white px-3 py-2"
      data-testid={`supp-row-${doc.id}`}
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
      <div className="flex-1 min-w-0">
        <p
          className="text-sm font-medium text-nycu-navy-900 truncate"
          title={doc.title}
        >
          {doc.title}
        </p>
        <p className="text-xs text-gray-500 truncate" title={doc.original_filename}>
          {doc.original_filename}
        </p>
      </div>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onPreview(doc)}
        aria-label="預覽"
      >
        <Eye className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onEdit(doc)}
        aria-label="編輯標題"
      >
        <Pencil className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(doc)}
        aria-label="刪除"
        className="text-red-600 hover:bg-red-50"
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

export function SupplementaryDocsList() {
  const [docs, setDocs] = useState<SupplementaryDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const [reordering, setReordering] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [editingDoc, setEditingDoc] = useState<SupplementaryDoc | null>(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [deletingDoc, setDeletingDoc] = useState<SupplementaryDoc | null>(null);
  const [preview, setPreview] = useState<
    { url: string; filename: string; type: string } | null
  >(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } })
  );

  useEffect(() => {
    apiClient.systemSettings.supplementaryDocs
      .list()
      .then((res) => {
        if (res.success && res.data) setDocs(res.data);
      })
      .catch(() => toast.error("載入補充參考文件失敗"))
      .finally(() => setLoading(false));
  }, []);

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = docs.findIndex((d) => d.id === active.id);
    const newIndex = docs.findIndex((d) => d.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const previous = docs;
    const next = arrayMove(docs, oldIndex, newIndex);
    setDocs(next);
    setReordering(true);

    try {
      const items = next.map((d, idx) => ({ id: d.id, sort_order: idx }));
      const res = await apiClient.systemSettings.supplementaryDocs.reorder(
        items
      );
      if (!res.success) {
        setDocs(previous);
        toast.error(res.message || "排序失敗");
      } else {
        setDocs(
          next.map((d, idx) => ({ ...d, sort_order: idx }))
        );
      }
    } catch {
      setDocs(previous);
      toast.error("排序失敗");
    } finally {
      setReordering(false);
    }
  };

  const handlePreview = (doc: SupplementaryDoc) => {
    const url = buildSuppDocFileProxyUrl(doc.id, doc.object_name);
    setPreview({
      url,
      filename: doc.original_filename,
      type: previewMimeType(doc.original_filename),
    });
  };

  const openEdit = (doc: SupplementaryDoc) => {
    setEditingDoc(doc);
    setEditingTitle(doc.title);
  };

  const saveEdit = async () => {
    if (!editingDoc) return;
    const trimmed = editingTitle.trim();
    if (!trimmed) {
      toast.error("標題不得為空");
      return;
    }
    if (trimmed.length > 200) {
      toast.error("標題不得超過 200 字");
      return;
    }
    const res = await apiClient.systemSettings.supplementaryDocs.updateTitle(
      editingDoc.id,
      trimmed
    );
    if (res.success && res.data) {
      setDocs((prev) =>
        prev.map((d) => (d.id === editingDoc.id ? res.data! : d))
      );
      setEditingDoc(null);
      toast.success("已更新");
    } else {
      toast.error(res.message || "更新失敗");
    }
  };

  const confirmDelete = async () => {
    if (!deletingDoc) return;
    const target = deletingDoc;
    setDeletingDoc(null);
    const previous = docs;
    setDocs((prev) => prev.filter((d) => d.id !== target.id));
    try {
      const res = await apiClient.systemSettings.supplementaryDocs.delete(
        target.id
      );
      if (!res.success) {
        setDocs(previous);
        toast.error(res.message || "刪除失敗");
      } else {
        toast.success("已刪除");
      }
    } catch {
      setDocs(previous);
      toast.error("刪除失敗");
    }
  };

  return (
    <section className="rounded-xl border border-gray-200 bg-white p-5 mt-6">
      <header className="flex items-center justify-between mb-4">
        <div>
          <h3 className="font-semibold text-nycu-navy-900">補充參考文件</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            學生在申請須知頁面會看到此處列出的檔案，可拖曳排序。
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
      ) : docs.length === 0 ? (
        <p className="text-sm text-gray-500 py-4">
          目前尚無補充參考文件，點擊「新增」上傳。
        </p>
      ) : (
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={docs.map((d) => d.id)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {docs.map((doc) => (
                <SortableRow
                  key={doc.id}
                  doc={doc}
                  disabled={reordering}
                  onPreview={handlePreview}
                  onEdit={openEdit}
                  onDelete={(d) => setDeletingDoc(d)}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      <AddSupplementaryDocDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onCreated={(doc) => setDocs((prev) => [...prev, doc])}
      />

      {editingDoc && (
        <Dialog
          open
          onOpenChange={(next) => !next && setEditingDoc(null)}
        >
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>編輯標題</DialogTitle>
              <DialogDescription>
                修改此補充參考文件的顯示標題。
              </DialogDescription>
            </DialogHeader>
            <Input
              value={editingTitle}
              onChange={(e) => setEditingTitle(e.target.value)}
              maxLength={200}
            />
            <DialogFooter>
              <Button variant="outline" onClick={() => setEditingDoc(null)}>
                取消
              </Button>
              <Button onClick={saveEdit}>儲存</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {deletingDoc && (
        <Dialog open onOpenChange={(next) => !next && setDeletingDoc(null)}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>確認刪除</DialogTitle>
              <DialogDescription>
                刪除後學生將無法看到「{deletingDoc.title}」這份檔案，確定要刪除嗎？
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setDeletingDoc(null)}
              >
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
