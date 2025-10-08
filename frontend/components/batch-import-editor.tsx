"use client";

import React, { useState, useEffect } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Edit2,
  Trash2,
  Save,
  X,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Loader2,
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

interface BatchImportEditorProps {
  batchId: string;
  previewData: Array<Record<string, any>>;
  validationErrors: Array<{
    row: number;
    field?: string;
    message: string;
  }>;
  onDataChange?: (newData: Array<Record<string, any>>) => void;
  onValidationChange?: (errors: Array<any>) => void;
  locale?: "zh" | "en";
}

interface EditingCell {
  rowIndex: number;
  field: string;
  value: any;
}

export function BatchImportEditor({
  batchId,
  previewData: initialData,
  validationErrors: initialErrors,
  onDataChange,
  onValidationChange,
  locale = "zh",
}: BatchImportEditorProps) {
  const [data, setData] = useState(initialData);
  const [errors, setErrors] = useState(initialErrors);
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState<number | null>(null);
  const [isRevalidating, setIsRevalidating] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    setData(initialData);
  }, [initialData]);

  useEffect(() => {
    setErrors(initialErrors);
  }, [initialErrors]);

  const getErrorsForRow = (rowIndex: number) => {
    return errors.filter((e) => e.row === rowIndex + 2);
  };

  const getErrorForCell = (rowIndex: number, field: string) => {
    return errors.find((e) => e.row === rowIndex + 2 && e.field === field);
  };

  const handleStartEdit = (rowIndex: number, field: string, value: any) => {
    setEditingCell({ rowIndex, field, value });
  };

  const handleCancelEdit = () => {
    setEditingCell(null);
  };

  const handleSaveEdit = async () => {
    if (!editingCell) return;

    setIsSaving(true);
    setMessage(null);

    try {
      const response = await apiClient.batchImport.updateRecord(
        batchId,
        editingCell.rowIndex,
        { [editingCell.field]: editingCell.value }
      );

      if (response.success && response.data) {
        // Update local data
        const newData = [...data];
        newData[editingCell.rowIndex] = response.data.updated_record;
        setData(newData);
        onDataChange?.(newData);

        setMessage({
          type: "success",
          text: locale === "zh" ? "記錄更新成功" : "Record updated successfully",
        });
        setEditingCell(null);

        // Auto-clear message after 3 seconds
        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({
          type: "error",
          text: response.message || (locale === "zh" ? "更新失敗" : "Update failed"),
        });
      }
    } catch (error: any) {
      setMessage({
        type: "error",
        text: error.message || (locale === "zh" ? "更新時發生錯誤" : "Error during update"),
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteRecord = async (rowIndex: number) => {
    if (!confirm(locale === "zh" ? "確定要刪除此筆記錄嗎？" : "Confirm delete this record?")) {
      return;
    }

    setIsDeleting(rowIndex);
    setMessage(null);

    try {
      const response = await apiClient.batchImport.deleteRecord(batchId, rowIndex);

      if (response.success && response.data) {
        // Update local data
        const newData = data.filter((_, idx) => idx !== rowIndex);
        setData(newData);
        onDataChange?.(newData);

        // Remove errors for this row and adjust row numbers
        const newErrors = errors
          .filter((e) => e.row !== rowIndex + 2)
          .map((e) => ({
            ...e,
            row: e.row > rowIndex + 2 ? e.row - 1 : e.row,
          }));
        setErrors(newErrors);
        onValidationChange?.(newErrors);

        setMessage({
          type: "success",
          text:
            locale === "zh"
              ? `記錄刪除成功，剩餘 ${response.data.remaining_records} 筆`
              : `Record deleted, ${response.data.remaining_records} remaining`,
        });

        setTimeout(() => setMessage(null), 3000);
      } else {
        setMessage({
          type: "error",
          text: response.message || (locale === "zh" ? "刪除失敗" : "Delete failed"),
        });
      }
    } catch (error: any) {
      setMessage({
        type: "error",
        text: error.message || (locale === "zh" ? "刪除時發生錯誤" : "Error during deletion"),
      });
    } finally {
      setIsDeleting(null);
    }
  };

  const handleRevalidate = async () => {
    setIsRevalidating(true);
    setMessage(null);

    try {
      const response = await apiClient.batchImport.revalidate(batchId);

      if (response.success && response.data) {
        setErrors(response.data.errors);
        onValidationChange?.(response.data.errors);

        setMessage({
          type: response.data.invalid_count === 0 ? "success" : "error",
          text:
            locale === "zh"
              ? `驗證完成：有效 ${response.data.valid_count} 筆，錯誤 ${response.data.invalid_count} 筆`
              : `Validation complete: ${response.data.valid_count} valid, ${response.data.invalid_count} errors`,
        });

        setTimeout(() => setMessage(null), 5000);
      } else {
        setMessage({
          type: "error",
          text: response.message || (locale === "zh" ? "驗證失敗" : "Validation failed"),
        });
      }
    } catch (error: any) {
      setMessage({
        type: "error",
        text: error.message || (locale === "zh" ? "驗證時發生錯誤" : "Error during validation"),
      });
    } finally {
      setIsRevalidating(false);
    }
  };

  if (data.length === 0) {
    return (
      <Alert>
        <AlertDescription>
          {locale === "zh" ? "沒有資料可顯示" : "No data to display"}
        </AlertDescription>
      </Alert>
    );
  }

  const columns = Object.keys(data[0]);

  return (
    <div className="space-y-4">
      {/* Header with actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold">
            {locale === "zh" ? "批次資料編輯" : "Batch Data Editor"}
          </h3>
          <span className="text-sm text-gray-500">
            ({data.length} {locale === "zh" ? "筆記錄" : "records"})
          </span>
        </div>
        <Button
          onClick={handleRevalidate}
          disabled={isRevalidating}
          variant="outline"
          size="sm"
        >
          {isRevalidating ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          {locale === "zh" ? "重新驗證" : "Revalidate"}
        </Button>
      </div>

      {/* Status message */}
      {message && (
        <Alert variant={message.type === "error" ? "destructive" : "default"}>
          {message.type === "success" ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <AlertTriangle className="h-4 w-4" />
          )}
          <AlertDescription>{message.text}</AlertDescription>
        </Alert>
      )}

      {/* Validation summary */}
      {errors.length > 0 && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            {locale === "zh"
              ? `發現 ${errors.length} 個驗證錯誤，請修正後再匯入`
              : `Found ${errors.length} validation errors, please correct before importing`}
          </AlertDescription>
        </Alert>
      )}

      {/* Editable table */}
      <div className="overflow-x-auto rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">#</TableHead>
              {columns.map((col) => (
                <TableHead key={col}>{col}</TableHead>
              ))}
              <TableHead className="w-24">
                {locale === "zh" ? "操作" : "Actions"}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((row, rowIndex) => {
              const rowErrors = getErrorsForRow(rowIndex);
              const hasError = rowErrors.length > 0;

              return (
                <TableRow
                  key={rowIndex}
                  className={hasError ? "bg-red-50" : undefined}
                >
                  <TableCell className="font-medium">{rowIndex + 1}</TableCell>
                  {columns.map((col) => {
                    const cellError = getErrorForCell(rowIndex, col);
                    const isEditing =
                      editingCell?.rowIndex === rowIndex &&
                      editingCell?.field === col;

                    return (
                      <TableCell
                        key={col}
                        className={
                          cellError
                            ? "border-2 border-red-300 bg-red-100"
                            : undefined
                        }
                      >
                        {isEditing ? (
                          <div className="flex items-center gap-2">
                            <Input
                              value={editingCell.value}
                              onChange={(e) =>
                                setEditingCell({
                                  ...editingCell,
                                  value: e.target.value,
                                })
                              }
                              className="h-8"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  handleSaveEdit();
                                } else if (e.key === "Escape") {
                                  handleCancelEdit();
                                }
                              }}
                            />
                            <Button
                              size="sm"
                              onClick={handleSaveEdit}
                              disabled={isSaving}
                            >
                              {isSaving ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Save className="h-3 w-3" />
                              )}
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={handleCancelEdit}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </div>
                        ) : (
                          <div
                            className="group relative cursor-pointer hover:bg-gray-100 px-2 py-1 rounded"
                            onClick={() =>
                              handleStartEdit(rowIndex, col, row[col])
                            }
                          >
                            <div className="flex items-center gap-2">
                              <span>
                                {typeof row[col] === "object" && row[col] !== null
                                  ? JSON.stringify(row[col])
                                  : String(row[col] ?? "")}
                              </span>
                              <Edit2 className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                            </div>
                            {cellError && (
                              <div className="absolute left-0 top-full mt-1 z-10 bg-red-600 text-white text-xs px-2 py-1 rounded shadow-lg whitespace-nowrap">
                                {cellError.message}
                              </div>
                            )}
                          </div>
                        )}
                      </TableCell>
                    );
                  })}
                  <TableCell>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDeleteRecord(rowIndex)}
                      disabled={isDeleting === rowIndex}
                      className="text-red-600 hover:text-red-700 hover:bg-red-50"
                    >
                      {isDeleting === rowIndex ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {/* Error details */}
      {errors.length > 0 && (
        <div className="space-y-2">
          <h4 className="font-semibold text-sm">
            {locale === "zh" ? "錯誤詳情" : "Error Details"}
          </h4>
          <div className="max-h-48 overflow-y-auto space-y-1">
            {errors.map((error, idx) => (
              <div
                key={idx}
                className="text-sm text-red-600 bg-red-50 px-3 py-2 rounded"
              >
                {locale === "zh" ? "第" : "Row"} {error.row} {locale === "zh" ? "行" : ""}
                {error.field && ` - ${error.field}`}: {error.message}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
