"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type {
  KnownCollege,
  KnownSubType,
  QuotaMatrix,
  QuotaParseResult,
} from "@/lib/quota/parse-quota-sheet";

interface QuotaImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  result: QuotaParseResult | null;
  currentQuotas: QuotaMatrix;
  knownColleges: KnownCollege[];
  knownSubTypes: KnownSubType[];
  onConfirm: (quotas: QuotaMatrix) => void;
}

export function QuotaImportDialog({
  open,
  onOpenChange,
  result,
  currentQuotas,
  knownColleges,
  knownSubTypes,
  onConfirm,
}: QuotaImportDialogProps) {
  if (!result) return null;
  const hasErrors = result.errors.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>匯入配額預覽</DialogTitle>
          <DialogDescription className="sr-only">預覽 Excel 匯入的配額矩陣，確認後套用至配額設定。</DialogDescription>
        </DialogHeader>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th scope="col" className="border p-1 text-left">子類型＼學院</th>
                {knownColleges.map(c => (
                  <th key={c.code} scope="col" className="border p-1">{c.name || c.code}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {knownSubTypes.map(s => (
                <tr key={s.code}>
                  <th scope="row" className="border p-1 font-medium text-left">{s.label || s.code}</th>
                  {knownColleges.map(c => {
                    const before = currentQuotas?.[s.code]?.[c.code] ?? 0;
                    const after = result.quotas?.[s.code]?.[c.code] ?? 0;
                    const changed = before !== after;
                    return (
                      <td
                        key={c.code}
                        className={cn("border p-1 text-center", changed && "bg-amber-50 font-semibold")}
                      >
                        {changed ? `${before}→${after}` : after}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {result.errors.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm text-red-600">
            {result.errors.map((e, i) => <li key={i}><span aria-hidden="true">⛔</span> {e.message}</li>)}
          </ul>
        )}
        {result.warnings.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm text-amber-600">
            {result.warnings.map((w, i) => <li key={i}><span aria-hidden="true">⚠</span> {w.message}</li>)}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button
            disabled={hasErrors}
            onClick={() => {
              onConfirm(result.quotas);
              onOpenChange(false);
            }}
          >
            確認套用
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
