"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Download, Loader2, Upload, XCircle } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { apiClient } from "@/lib/api";
import type { ReceivedMonthsPreview } from "@/lib/api/modules/received-months";

interface ScholarshipTypeOption {
  id: number;
  name: string;
}

interface ImportReceivedMonthsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called after a successful confirm, so the caller can refresh its view. */
  onImported: () => void;
}

export function ImportReceivedMonthsDialog({
  open,
  onOpenChange,
  onImported,
}: ImportReceivedMonthsDialogProps) {
  const [types, setTypes] = useState<ScholarshipTypeOption[]>([]);
  const [typeId, setTypeId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ReceivedMonthsPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset every time the dialog opens so a previous run never leaks through.
  useEffect(() => {
    if (!open) return;
    setTypeId("");
    setFile(null);
    setPreview(null);
    setError(null);

    let cancelled = false;
    apiClient.admin
      .getScholarshipConfigTypes()
      .then((response) => {
        if (cancelled) return;
        const rows = Array.isArray(response.data) ? response.data : [];
        setTypes(
          rows
            .map((row) => row as { id?: number; name?: string })
            .filter((row): row is ScholarshipTypeOption =>
              typeof row.id === "number" && typeof row.name === "string",
            ),
        );
      })
      .catch(() => {
        if (!cancelled) setError("無法載入獎學金類型");
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  const handleDownloadTemplate = async () => {
    setError(null);
    try {
      await apiClient.receivedMonths.downloadTemplate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "下載範例失敗");
    }
  };

  const handlePreview = async () => {
    if (!file || !typeId) return;
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      const response = await apiClient.receivedMonths.preview(
        Number(typeId),
        file,
      );
      if (response.success && response.data) setPreview(response.data);
      else setError(response.message || "解析失敗");
    } catch {
      setError("解析失敗，請確認檔案格式");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiClient.receivedMonths.confirm(preview.import_id);
      if (response.success) {
        onImported();
        onOpenChange(false);
      } else {
        setError(response.message || "匯入失敗");
      }
    } catch {
      setError("匯入失敗");
    } finally {
      setBusy(false);
    }
  };

  const handleCancel = async () => {
    // Discard the staged rows server-side rather than leaving them pending.
    if (preview) {
      try {
        await apiClient.receivedMonths.cancel(preview.import_id);
      } catch {
        // Best-effort: staged data expires on its own after 7 days.
      }
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? onOpenChange(true) : handleCancel())}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>匯入已領月份數</DialogTitle>
          <DialogDescription>
            上傳國科會「獲獎生已領月份統計表」。月份數依「領獎起始月份」至「目前領獎月份」推算，
            不採用檔案中的「合計目前領獎月份數」。確認前不會寫入任何資料。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1">
            <Label htmlFor="received-months-type">獎學金</Label>
            <Select value={typeId} onValueChange={setTypeId} disabled={busy}>
              <SelectTrigger id="received-months-type">
                <SelectValue placeholder="選擇獎學金類型" />
              </SelectTrigger>
              <SelectContent>
                {types.map((type) => (
                  <SelectItem key={type.id} value={String(type.id)}>
                    {type.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="received-months-file">檔案 (.xlsx)</Label>
            <input
              id="received-months-file"
              type="file"
              accept=".xlsx"
              disabled={busy}
              className="block w-full text-sm file:mr-3 file:rounded-md file:border file:bg-muted file:px-3 file:py-1.5 file:text-sm"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setPreview(null);
              }}
            />
          </div>
        </div>

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {preview && (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-4 text-sm">
              <span>可匯入 {preview.valid_rows}</span>
              <span className="text-amber-600">警告 {preview.warning_rows}</span>
              <span className="text-destructive">錯誤 {preview.error_rows}</span>
            </div>

            <div className="max-h-72 overflow-auto rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>列</TableHead>
                    <TableHead>學號</TableHead>
                    <TableHead>領獎起始</TableHead>
                    <TableHead>目前領獎</TableHead>
                    <TableHead className="text-right">月份數</TableHead>
                    <TableHead>狀態</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.rows.map((row) => (
                    <TableRow key={row.row_number}>
                      <TableCell className="font-mono text-xs">
                        {row.row_number}
                      </TableCell>
                      <TableCell className="font-mono">
                        {row.student_number}
                      </TableCell>
                      <TableCell>{row.award_start_label ?? "—"}</TableCell>
                      <TableCell>{row.award_current_label ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {row.months ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {row.error ? (
                          <span className="inline-flex items-center gap-1 text-destructive">
                            <XCircle className="h-3.5 w-3.5" />
                            {row.error}
                          </span>
                        ) : row.warning ? (
                          <span className="inline-flex items-center gap-1 text-amber-600">
                            <AlertTriangle className="h-3.5 w-3.5" />
                            {row.warning}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">正常</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        <DialogFooter className="sm:justify-between">
          <Button
            variant="ghost"
            onClick={handleDownloadTemplate}
            disabled={busy}
            className="sm:mr-auto"
          >
            <Download className="mr-2 h-4 w-4" />
            下載範例
          </Button>
          <Button variant="outline" onClick={handleCancel} disabled={busy}>
            取消
          </Button>
          {preview ? (
            <Button
              onClick={handleConfirm}
              disabled={busy || preview.valid_rows === 0}
            >
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              確認匯入 ({preview.valid_rows})
            </Button>
          ) : (
            <Button onClick={handlePreview} disabled={busy || !file || !typeId}>
              {busy ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-2 h-4 w-4" />
              )}
              預覽
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
