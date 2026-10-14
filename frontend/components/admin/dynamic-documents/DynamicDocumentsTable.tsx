"use client";

import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Edit, Eye, GripVertical, Loader2, Trash2, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ApplicationDocument } from "@/lib/api";

interface DocumentRowActions {
  uploadingExampleDocId: number | null;
  onToggleActive: (doc: ApplicationDocument, checked: boolean) => void;
  onUploadExample: (
    documentId: number,
    event: React.ChangeEvent<HTMLInputElement>
  ) => void;
  onPreviewExample: (doc: ApplicationDocument) => void;
  onDeleteExample: (documentId: number) => void;
  onEdit: (doc: ApplicationDocument) => void;
  onDelete: (documentId: number) => void;
}

interface SortableDocumentRowProps extends DocumentRowActions {
  doc: ApplicationDocument;
  disabled: boolean;
}

function SortableDocumentRow({
  doc,
  disabled,
  uploadingExampleDocId,
  onToggleActive,
  onUploadExample,
  onPreviewExample,
  onDeleteExample,
  onEdit,
  onDelete,
}: SortableDocumentRowProps) {
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
  const isUploadingExample = uploadingExampleDocId === doc.id;

  return (
    <TableRow
      ref={setNodeRef}
      style={style}
      className="hover:bg-gray-50"
      data-testid={`dynamic-document-row-${doc.id}`}
    >
      <TableCell className="w-8 pr-0">
        <button
          type="button"
          aria-label="拖曳排序"
          className="cursor-grab touch-none text-gray-400 hover:text-gray-600 disabled:cursor-not-allowed"
          disabled={disabled}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-4 w-4" />
        </button>
      </TableCell>
      <TableCell>
        <div>
          <div className="font-medium text-gray-900">{doc.document_name}</div>
          <div className="text-sm text-gray-500">{doc.description}</div>
          {doc.upload_instructions && (
            <div className="text-xs text-gray-400 mt-1">
              {doc.upload_instructions}
            </div>
          )}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant={doc.is_required ? "destructive" : "secondary"}>
          {doc.is_required ? "必要" : "選填"}
        </Badge>
      </TableCell>
      <TableCell>
        <div className="flex gap-1 flex-wrap">
          {doc.accepted_file_types.map(type => (
            <Badge key={type} variant="outline" className="text-xs">
              {type}
            </Badge>
          ))}
        </div>
      </TableCell>
      <TableCell>
        <span className="text-sm font-medium text-gray-700">
          {doc.max_file_size}
        </span>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Switch
            checked={doc.is_active}
            onCheckedChange={checked => onToggleActive(doc, checked)}
          />
          <span className="text-sm text-gray-500">
            {doc.is_active ? "啟用" : "停用"}
          </span>
        </div>
      </TableCell>
      <TableCell>
        <div className="flex gap-2">
          {/* Upload Example Button */}
          <div className="relative">
            <input
              type="file"
              id={`upload-example-${doc.id}`}
              className="hidden"
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
              onChange={e => onUploadExample(doc.id, e)}
              disabled={isUploadingExample}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                document.getElementById(`upload-example-${doc.id}`)?.click()
              }
              disabled={isUploadingExample}
              className="text-green-600 hover:text-green-700"
              title="上傳範例"
            >
              {isUploadingExample ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
            </Button>
          </div>

          {/* Preview Example Button */}
          {doc.example_file_url && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onPreviewExample(doc)}
              className="text-purple-600 hover:text-purple-700"
              title="預覽範例"
            >
              <Eye className="h-4 w-4" />
            </Button>
          )}

          {/* Delete Example Button */}
          {doc.example_file_url && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDeleteExample(doc.id)}
              className="text-orange-600 hover:text-orange-700"
              title="刪除範例"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}

          {/* Edit Document Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => onEdit(doc)}
            className="text-blue-600 hover:text-blue-700"
            title="編輯文件"
          >
            <Edit className="h-4 w-4" />
          </Button>

          {/* Delete Document Button */}
          {doc.id > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onDelete(doc.id)}
              className="text-red-600 hover:text-red-700"
              title="刪除文件"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}

interface DynamicDocumentsTableProps extends DocumentRowActions {
  /** The admin-defined (non-fixed) documents, in display order. */
  documents: ApplicationDocument[];
  /** True while a reorder is being saved; dragging is locked meanwhile. */
  isReordering: boolean;
  /** Called with the documents in their new order after a drop. */
  onReorder: (next: ApplicationDocument[]) => void;
}

export function DynamicDocumentsTable({
  documents,
  isReordering,
  onReorder,
  ...rowActions
}: DynamicDocumentsTableProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    // Space/Enter on the handle lifts a row, arrows move it.
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const oldIndex = documents.findIndex(d => d.id === active.id);
    const newIndex = documents.findIndex(d => d.id === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    onReorder(arrayMove(documents, oldIndex, newIndex));
  };

  return (
    <div className="border rounded-lg overflow-hidden">
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <Table>
          <TableHeader className="bg-gray-50">
            <TableRow>
              <TableHead className="w-8 pr-0">
                <span className="sr-only">排序</span>
              </TableHead>
              <TableHead className="font-semibold">文件資訊</TableHead>
              <TableHead className="font-semibold">必要性</TableHead>
              <TableHead className="font-semibold">支援格式</TableHead>
              <TableHead className="font-semibold">大小限制</TableHead>
              <TableHead className="font-semibold">狀態</TableHead>
              <TableHead className="font-semibold">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <SortableContext
              items={documents.map(d => d.id)}
              strategy={verticalListSortingStrategy}
            >
              {documents.map(doc => (
                <SortableDocumentRow
                  key={doc.id}
                  doc={doc}
                  disabled={isReordering}
                  {...rowActions}
                />
              ))}
            </SortableContext>
          </TableBody>
        </Table>
      </DndContext>
    </div>
  );
}
