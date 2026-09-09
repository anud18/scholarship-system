"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SubTypeLabel, SubTypeLabels } from "@/lib/api/types";

interface SubTypeLabelsEditorProps {
  /** Sub-type codes this scholarship defines (e.g. ["nstc", "moe_1w"]). */
  subTypes: string[];
  /** Current per-year overrides; codes absent from it show the base name. */
  value: SubTypeLabels | undefined;
  onChange: (next: SubTypeLabels) => void;
  /** Prefix for input ids so the create and edit dialogs don't collide. */
  idPrefix?: string;
}

/**
 * Per-configuration (per academic year) sub-type display names.
 *
 * Each row edits one sub-type's 中文 / English label for THIS configuration
 * only. Empty inputs mean "use the base name from 子類型設定", so clearing a
 * row removes its override instead of storing an empty string.
 */
export function SubTypeLabelsEditor({
  subTypes,
  value,
  onChange,
  idPrefix = "sub_type_label",
}: SubTypeLabelsEditorProps) {
  const labels = value ?? {};

  const updateField = (code: string, field: keyof SubTypeLabel, raw: string) => {
    const current: SubTypeLabel = labels[code] ?? { name: "" };
    const nextEntry: SubTypeLabel = { ...current, [field]: raw };
    const isEmpty = !nextEntry.name.trim() && !(nextEntry.name_en ?? "").trim();

    const { [code]: _removed, ...rest } = labels;
    onChange(isEmpty ? rest : { ...rest, [code]: nextEntry });
  };

  if (subTypes.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      <div>
        <Label>本學年度子類型顯示名稱</Label>
        <p className="mt-1 text-sm text-muted-foreground">
          學生申請、教授／學院審核與匯出畫面顯示的獎學金名稱，僅套用於此配置的學年度。留空則沿用子類型的預設名稱。
        </p>
      </div>
      {subTypes.map(code => {
        const entry = labels[code];
        return (
          <div
            key={code}
            className="grid grid-cols-1 gap-2 rounded-lg border p-3 md:grid-cols-[8rem_1fr_1fr] md:items-center"
            data-testid={`${idPrefix}-row-${code}`}
          >
            <span className="font-mono text-sm">{code}</span>
            <div>
              <Label htmlFor={`${idPrefix}_${code}_name`} className="text-xs text-muted-foreground">
                中文名稱
              </Label>
              <Input
                id={`${idPrefix}_${code}_name`}
                value={entry?.name ?? ""}
                onChange={e => updateField(code, "name", e.target.value)}
                placeholder="例：115學年度教育部博士生獎學金"
                maxLength={200}
              />
            </div>
            <div>
              <Label htmlFor={`${idPrefix}_${code}_name_en`} className="text-xs text-muted-foreground">
                英文名稱
              </Label>
              <Input
                id={`${idPrefix}_${code}_name_en`}
                value={entry?.name_en ?? ""}
                onChange={e => updateField(code, "name_en", e.target.value)}
                placeholder="e.g. AY115 MOE PhD Scholarship"
                maxLength={200}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
