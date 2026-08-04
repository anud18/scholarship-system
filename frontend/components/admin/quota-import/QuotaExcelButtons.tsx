"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Download, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReferenceData } from "@/hooks/use-reference-data";
import {
  parseQuotaSheet,
  type KnownCollege,
  type KnownSubType,
  type QuotaMatrix,
  type QuotaParseResult,
} from "@/lib/quota/parse-quota-sheet";
import { downloadQuotaTemplate } from "@/lib/quota/build-quota-template";
import { QuotaImportDialog } from "@/components/admin/quota-import/QuotaImportDialog";

interface QuotaExcelButtonsProps {
  quotas: QuotaMatrix;
  subTypes: KnownSubType[];
  configCode?: string;
  onApply: (quotas: QuotaMatrix) => void;
}

export function QuotaExcelButtons({ quotas, subTypes, configCode, onApply }: QuotaExcelButtonsProps) {
  const { academies, subTypeTranslations } = useReferenceData();
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<QuotaParseResult | null>(null);
  const [open, setOpen] = useState(false);

  const colleges: KnownCollege[] = academies.map(a => ({ code: a.code, name: a.name }));
  // Enrich sub-types with zh labels so the preview shows names and the parser can
  // match Excel rows by label (parseQuotaSheet supports KnownSubType.label).
  const labeledSubTypes: KnownSubType[] = subTypes.map(s => ({
    code: s.code,
    label: s.label ?? subTypeTranslations?.zh?.[s.code],
  }));

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    try {
      const XLSX = await import("xlsx");
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: "array" });
      const ws = wb.Sheets[wb.SheetNames[0]];
      if (!ws) {
        toast.error("Excel 沒有可用的工作表");
        return;
      }
      const rows = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1 });
      setResult(parseQuotaSheet(rows, colleges, labeledSubTypes, quotas));
      setOpen(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "無法讀取 Excel 檔案");
    }
  };

  const handleTemplate = async () => {
    try {
      await downloadQuotaTemplate(quotas, colleges, labeledSubTypes, configCode);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "無法下載範本");
    }
  };

  return (
    <div className="mt-2 flex gap-2">
      <input ref={fileRef} type="file" accept=".xlsx" hidden onChange={handleFile} />
      <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
        <Upload className="h-4 w-4 mr-1" />
        匯入 Excel
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={handleTemplate}>
        <Download className="h-4 w-4 mr-1" />
        下載範本
      </Button>
      <QuotaImportDialog
        open={open}
        onOpenChange={setOpen}
        result={result}
        currentQuotas={quotas}
        knownColleges={colleges}
        knownSubTypes={labeledSubTypes}
        onConfirm={onApply}
      />
    </div>
  );
}
