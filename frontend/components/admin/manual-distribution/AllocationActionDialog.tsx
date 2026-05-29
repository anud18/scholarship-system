"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api";
import { logger } from "@/lib/utils/logger";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";

export type AllocationMode = "revoke" | "suspend" | "restore";

export interface AllocationActionTarget {
  applicationId: number;
  studentName: string;
}

interface AllocationActionDialogProps {
  mode: AllocationMode;
  target: AllocationActionTarget | null;
  onClose: () => void;
  /** Parent runs fetchData + success messaging. */
  onConfirmed: (studentName: string) => void;
}

const SUSPEND_OPTIONS = ["休學", "退學", "畢業", "其他"] as const;

export function AllocationActionDialog({
  mode,
  target,
  onClose,
  onConfirmed,
}: AllocationActionDialogProps) {
  const isRevoke = mode === "revoke";
  const isRestore = mode === "restore";
  const [revokeReason, setRevokeReason] = useState("");
  const [suspendOption, setSuspendOption] =
    useState<(typeof SUSPEND_OPTIONS)[number]>("休學");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setRevokeReason("");
    setSuspendOption("休學");
    setNote("");
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const composedReason = isRevoke
    ? revokeReason.trim()
    : note.trim()
      ? `${suspendOption}：${note.trim()}`
      : suspendOption;

  const confirmDisabled =
    submitting ||
    (isRevoke
      ? revokeReason.trim().length === 0
      : isRestore
        ? false
        : suspendOption === "其他" && note.trim().length === 0);

  const handleConfirm = async () => {
    if (!target || confirmDisabled) return;
    setSubmitting(true);
    try {
      const resp = isRevoke
        ? await apiClient.manualDistribution.revokeAllocation(
            target.applicationId,
            composedReason
          )
        : isRestore
          ? await apiClient.manualDistribution.restoreAllocation(
              target.applicationId
            )
          : await apiClient.manualDistribution.suspendAllocation(
              target.applicationId,
              composedReason
            );
      if (resp.success) {
        const name = target.studentName;
        reset();
        onConfirmed(name);
      } else {
        logger.error(`${mode} failed`, { message: resp.message });
        alert(
          resp.message ||
            (isRevoke ? "撤銷失敗" : isRestore ? "恢復失敗" : "停發失敗")
        );
      }
    } catch (err) {
      logger.error(`${mode} error`, { err });
      alert(
        isRevoke
          ? "撤銷時發生錯誤"
          : isRestore
            ? "恢復時發生錯誤"
            : "停發時發生錯誤"
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={open => !open && handleClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>
            {isRevoke
              ? "撤銷獎學金分發"
              : isRestore
                ? "恢復為正常分發"
                : "停發獎學金分發"}
          </DialogTitle>
          <DialogDescription>
            {target &&
              (isRestore ? (
                <>
                  確定要將 <strong>{target.studentName}</strong>{" "}
                  恢復為正常分發嗎？申請狀態將改回「核准（已分配）」。已從鎖定造冊移除的項目不會自動還原，請重新生成造冊。
                </>
              ) : (
                <>
                  {isRevoke ? "確定要撤銷 " : "確定要停發 "}
                  <strong>{target.studentName}</strong>
                  {" 的獎學金分發嗎？此操作將從未鎖定造冊中移除該學生，並標記申請為"}
                  {isRevoke ? "已撤銷。" : "已停發。"}
                </>
              ))}
          </DialogDescription>
        </DialogHeader>

        {!isRestore && (
        <div className="space-y-4">
          {isRevoke ? (
            <div className="space-y-2">
              <Label htmlFor="revoke-reason">撤銷原因</Label>
              <Textarea
                id="revoke-reason"
                value={revokeReason}
                onChange={e => setRevokeReason(e.target.value)}
                placeholder="違反獎學金要點"
                rows={3}
                maxLength={500}
                disabled={submitting}
              />
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="suspend-option">停發原因</Label>
                <Select
                  value={suspendOption}
                  onValueChange={v => setSuspendOption(v as (typeof SUSPEND_OPTIONS)[number])}
                  disabled={submitting}
                >
                  <SelectTrigger id="suspend-option">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUSPEND_OPTIONS.map(o => (
                      <SelectItem key={o} value={o}>
                        {o}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="suspend-note">
                  補充說明
                  {suspendOption === "其他" && (
                    <span className="text-red-500 ml-1">*</span>
                  )}
                </Label>
                {/* maxLength=400: the composed reason "label：note" must stay within
                    the backend SuspendRequest.reason max_length=500, leaving
                    100 chars for the longest label prefix "其他：". */}
                <Textarea
                  id="suspend-note"
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder={
                    suspendOption === "其他"
                      ? "選擇「其他」時必填，請說明原因"
                      : "選填"
                  }
                  rows={3}
                  maxLength={400}
                  disabled={submitting}
                />
              </div>
            </>
          )}
        </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={submitting}>
            取消
          </Button>
          <Button
            variant={isRestore ? "default" : "destructive"}
            onClick={handleConfirm}
            disabled={confirmDisabled}
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            {isRevoke ? "確認撤銷" : isRestore ? "確認恢復" : "確認停發"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
