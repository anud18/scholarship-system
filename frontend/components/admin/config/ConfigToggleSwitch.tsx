"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface ConfigToggleSwitchProps {
  initialOpen: boolean;
  onToggle: (next: boolean) => Promise<unknown>;
  ariaLabel: string;
  onLabel?: string; // default 開放中
  offLabel?: string; // default 已關閉
  successOn: string;
  successOff: string;
  tooltipOn: string;
  tooltipOff: string;
  onChange?: (open: boolean) => void;
}

export function ConfigToggleSwitch({
  initialOpen,
  onToggle,
  ariaLabel,
  onLabel = "開放中",
  offLabel = "已關閉",
  successOn,
  successOff,
  tooltipOn,
  tooltipOff,
  onChange,
}: ConfigToggleSwitchProps) {
  const [open, setOpen] = useState(initialOpen);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setOpen(initialOpen);
  }, [initialOpen]);

  const handleToggle = async (next: boolean) => {
    const prev = open;
    setOpen(next); // optimistic
    setSaving(true);
    try {
      await onToggle(next);
      toast.success(next ? successOn : successOff);
      onChange?.(next);
    } catch (err) {
      setOpen(prev); // rollback
      toast.error(err instanceof Error ? err.message : "操作失敗");
    } finally {
      setSaving(false);
    }
  };

  return (
    <TooltipProvider delayDuration={250}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="inline-flex items-center gap-2.5">
            <Switch
              checked={open}
              disabled={saving}
              onCheckedChange={handleToggle}
              aria-label={ariaLabel}
              className={
                open ? "data-[state=checked]:bg-emerald-600" : undefined
              }
            />
            <span
              className={[
                "inline-flex items-center gap-1.5 text-xs font-medium tracking-wide tabular-nums transition-colors",
                open ? "text-emerald-700" : "text-muted-foreground",
              ].join(" ")}
            >
              {saving ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <span className="relative inline-flex h-2 w-2">
                  <span
                    className={[
                      "absolute inline-flex h-full w-full rounded-full opacity-60",
                      open ? "animate-ping bg-emerald-400" : "bg-transparent",
                    ].join(" ")}
                  />
                  <span
                    className={[
                      "relative inline-flex h-2 w-2 rounded-full",
                      open ? "bg-emerald-500" : "bg-muted-foreground/40",
                    ].join(" ")}
                  />
                </span>
              )}
              {open ? onLabel : offLabel}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs">
          {open ? tooltipOn : tooltipOff}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
