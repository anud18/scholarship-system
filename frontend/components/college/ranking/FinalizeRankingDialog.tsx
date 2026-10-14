"use client";

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { isUndeletableRanking, type RankingScopeFields } from "./ranking-scope";

export interface FinalizeCandidate {
  id: number;
  name: string;
  siblings: RankingScopeFields[];
}

interface FinalizeRankingDialogProps {
  locale: "zh" | "en";
  /** The ranking about to be locked and the drafts beside it; null = closed. */
  candidate: FinalizeCandidate | null;
  isFinalizing: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

// Why a listed sibling survives the lock (and so blocks it), or null.
function undeletableNote(
  sibling: RankingScopeFields,
  locale: "zh" | "en"
): string | null {
  if (!isUndeletableRanking(sibling)) return null;
  if (sibling.is_finalized) {
    return locale === "zh" ? "（已鎖定，無法刪除）" : " (locked; cannot be deleted)";
  }
  return locale === "zh"
    ? "（已執行分發或已用於造冊，無法刪除）"
    : " (distributed or used by a roster; cannot be deleted)";
}

/**
 * 確認排名 with drafts beside it: the lock deletes them for good. A locked,
 * settled or roster-referenced sibling is never deleted (the backend answers
 * 409), so confirm stays disabled while one is listed instead of inviting a
 * certain failure.
 */
export function FinalizeRankingDialog({
  locale,
  candidate,
  isFinalizing,
  onCancel,
  onConfirm,
}: FinalizeRankingDialogProps) {
  const siblings = candidate?.siblings ?? [];
  const hasUndeletableSibling = siblings.some(isUndeletableRanking);

  return (
    <Dialog
      open={candidate !== null}
      onOpenChange={open => {
        if (!open && !isFinalizing) onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{locale === "zh" ? "確認排名" : "Confirm ranking"}</DialogTitle>
          <DialogDescription>
            {locale === "zh"
              ? `確認「${candidate?.name ?? ""}」後，本學院同一學年度／學期的以下 ${siblings.length} 份排名將被永久刪除，只保留這一份；鎖定期間無法再新增排名。此操作無法復原。`
              : `Confirming "${candidate?.name ?? ""}" permanently deletes the ${siblings.length} ranking(s) below for the same period; no new ranking can be created while it is locked. This cannot be undone.`}
          </DialogDescription>
        </DialogHeader>
        <ul className="max-h-48 overflow-y-auto list-disc pl-5 text-sm">
          {siblings.map(sibling => (
            <li key={sibling.id}>
              {sibling.ranking_name}
              {undeletableNote(sibling, locale)}
            </li>
          ))}
        </ul>
        {hasUndeletableSibling && (
          <p className="text-sm text-destructive">
            {locale === "zh"
              ? "標示無法刪除的排名不會被刪除，請聯絡管理員處理後再確認排名。"
              : "A ranking marked as undeletable blocks the lock; ask an administrator to resolve it first."}
          </p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={isFinalizing}>
            {locale === "zh" ? "取消" : "Cancel"}
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={isFinalizing || hasUndeletableSibling}
          >
            {isFinalizing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            {locale === "zh" ? "確認並刪除其他排名" : "Confirm and delete the others"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
