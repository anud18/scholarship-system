"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import apiClient from "@/lib/api";
import type { ScholarshipConfiguration } from "@/lib/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { logger } from "@/lib/utils/logger";
import { roundLabel } from "@/lib/utils/application-round";
import {
  nextRoundDraft,
  toggleSubType,
  toRoundDrafts,
  toRoundInputs,
  validateRoundDrafts,
  type RoundDraft,
} from "./application-rounds-form";

interface ApplicationRoundsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  configuration: ScholarshipConfiguration | null;
  onSaved?: () => void;
}

type DateField = Exclude<keyof RoundDraft, "round_number" | "open_sub_types">;

const REVIEW_FIELDS: Array<{ label: string; start: DateField; end: DateField }> = [
  { label: "教授審查期間", start: "professor_review_start", end: "professor_review_end" },
  { label: "學院審查期間", start: "college_review_start", end: "college_review_end" },
];

const formatWindow = (start: string | null, end: string | null) => {
  if (!start || !end) return "未設定";
  const format = (value: string) =>
    new Date(value).toLocaleString("zh-TW", { dateStyle: "short", timeStyle: "short" });
  return `${format(start)} ~ ${format(end)}`;
};

/**
 * 多梯次申請 editor: the configuration's own window is 第一梯次 (every sub-type);
 * the admin adds 第二梯次起 with a window, the sub-types it opens and optional
 * review windows (blank → the configuration's general review windows).
 */
export function ApplicationRoundsDialog({
  open,
  onOpenChange,
  configuration,
  onSaved,
}: ApplicationRoundsDialogProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [drafts, setDrafts] = useState<RoundDraft[]>([]);
  const [availableSubTypes, setAvailableSubTypes] = useState<string[]>([]);
  const [subTypeNames, setSubTypeNames] = useState<Record<string, string>>({});
  const [firstRound, setFirstRound] = useState<{ start: string | null; end: string | null }>({
    start: null,
    end: null,
  });

  const configurationId = configuration?.id;

  const load = useCallback(async (id: number) => {
    setLoading(true);
    try {
      const [roundsResponse, translationsResponse] = await Promise.all([
        apiClient.admin.getApplicationRounds(id),
        apiClient.admin.getSubTypeTranslations(),
      ]);
      if (!roundsResponse.success || !roundsResponse.data) {
        throw new Error(roundsResponse.message || "無法載入申請梯次");
      }
      const payload = roundsResponse.data;
      setDrafts(toRoundDrafts(payload.rounds));
      setAvailableSubTypes(payload.available_sub_types);
      setFirstRound({
        start: payload.first_round.application_start_date,
        end: payload.first_round.application_end_date,
      });
      setSubTypeNames(translationsResponse.success ? translationsResponse.data?.zh ?? {} : {});
    } catch (error) {
      logger.error("Failed to load application rounds", { error });
      toast.error(error instanceof Error ? error.message : "無法載入申請梯次");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && configurationId) void load(configurationId);
  }, [open, configurationId, load]);

  const updateDraft = (index: number, next: RoundDraft) =>
    setDrafts(current => current.map((draft, i) => (i === index ? next : draft)));

  const handleAddRound = () =>
    setDrafts(current => [...current, nextRoundDraft(current, firstRound.end, availableSubTypes)]);

  // Only the last round can go, so the round numbers stay consecutive.
  const handleRemoveLastRound = () => setDrafts(current => current.slice(0, -1));

  const handleSave = async () => {
    if (!configurationId) return;
    const problem = validateRoundDrafts(drafts);
    if (problem) {
      toast.error(problem);
      return;
    }
    setSaving(true);
    try {
      const response = await apiClient.admin.updateApplicationRounds(
        configurationId,
        toRoundInputs(drafts)
      );
      if (!response.success) throw new Error(response.message || "儲存失敗");
      toast.success("申請梯次已更新");
      onSaved?.();
      onOpenChange(false);
    } catch (error) {
      logger.error("Failed to save application rounds", { error });
      toast.error(error instanceof Error ? error.message : "儲存失敗");
    } finally {
      setSaving(false);
    }
  };

  const subTypeName = (code: string) => subTypeNames[code] || code;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>多梯次申請 — {configuration?.config_name}</DialogTitle>
          <DialogDescription>
            一般申請期間即第一梯次（開放所有子類別）。之後的梯次可選擇開放的子類別；
            學院排名時，後面梯次的學生一律排在前面梯次之後。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-10">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border bg-muted/30 p-3 text-sm">
              <div className="font-medium">{roundLabel(1)}（一般申請期間）</div>
              <div className="text-muted-foreground">
                {formatWindow(firstRound.start, firstRound.end)}・開放所有子類別
              </div>
            </div>

            {drafts.length === 0 && (
              <p className="text-sm text-muted-foreground">
                目前只有一個梯次。點「新增梯次」開放第二梯次申請。
              </p>
            )}

            {drafts.map((draft, index) => (
              <div key={draft.round_number} className="space-y-3 rounded-md border p-4">
                <div className="flex items-center justify-between">
                  <Badge variant="outline">{roundLabel(draft.round_number)}</Badge>
                  {index === drafts.length - 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-600 hover:text-red-700"
                      onClick={handleRemoveLastRound}
                      aria-label={`刪除${roundLabel(draft.round_number)}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <Label htmlFor={`round-${draft.round_number}-start`}>申請開始時間</Label>
                    <Input
                      id={`round-${draft.round_number}-start`}
                      type="datetime-local"
                      value={draft.application_start_date}
                      onChange={e =>
                        updateDraft(index, { ...draft, application_start_date: e.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`round-${draft.round_number}-end`}>申請截止時間</Label>
                    <Input
                      id={`round-${draft.round_number}-end`}
                      type="datetime-local"
                      value={draft.application_end_date}
                      onChange={e =>
                        updateDraft(index, { ...draft, application_end_date: e.target.value })
                      }
                    />
                  </div>
                </div>

                <div className="space-y-1">
                  <Label>開放申請的子類別</Label>
                  <div className="flex flex-wrap gap-4">
                    {availableSubTypes.map(code => {
                      const id = `round-${draft.round_number}-sub-${code}`;
                      return (
                        <div key={code} className="flex items-center gap-2">
                          <Checkbox
                            id={id}
                            checked={draft.open_sub_types.includes(code)}
                            onCheckedChange={() => updateDraft(index, toggleSubType(draft, code))}
                          />
                          <Label htmlFor={id} className="font-normal">
                            {subTypeName(code)}
                          </Label>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {REVIEW_FIELDS.map(field => (
                  <div key={field.start} className="space-y-1">
                    <Label>
                      {field.label}
                      <span className="ml-1 text-xs font-normal text-muted-foreground">
                        （留空則沿用配置的審查期間）
                      </span>
                    </Label>
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Input
                        type="datetime-local"
                        aria-label={`${roundLabel(draft.round_number)}${field.label}開始`}
                        value={draft[field.start]}
                        onChange={e => updateDraft(index, { ...draft, [field.start]: e.target.value })}
                      />
                      <Input
                        type="datetime-local"
                        aria-label={`${roundLabel(draft.round_number)}${field.label}結束`}
                        value={draft[field.end]}
                        onChange={e => updateDraft(index, { ...draft, [field.end]: e.target.value })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ))}

            <Button
              variant="outline"
              onClick={handleAddRound}
              disabled={!firstRound.end || availableSubTypes.length === 0}
            >
              <Plus className="mr-1 h-4 w-4" />
              新增梯次
            </Button>
            {!firstRound.end && (
              <p className="text-xs text-muted-foreground">
                請先在「編輯配置」設定一般申請期間（第一梯次）。
              </p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            取消
          </Button>
          <Button onClick={handleSave} disabled={loading || saving}>
            {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            儲存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
