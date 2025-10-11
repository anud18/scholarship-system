"use client";

import { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { AlertTriangle, Loader2 } from "lucide-react";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";

interface DeleteApplicationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  applicationId: number;
  applicationName: string;
  onSuccess?: () => void;
  locale?: "zh" | "en";
  requireReason?: boolean;
}

export function DeleteApplicationDialog({
  open,
  onOpenChange,
  applicationId,
  applicationName,
  onSuccess,
  locale = "zh",
  requireReason = true,
}: DeleteApplicationDialogProps) {
  const [reason, setReason] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    // Validate reason if required
    if (requireReason && !reason.trim()) {
      toast.error(locale === "zh" ? "請輸入刪除原因" : "Deletion reason is required");
      return;
    }

    setIsDeleting(true);
    try {
      const response = await apiClient.applications.deleteApplication(
        applicationId,
        requireReason ? reason : undefined
      );

      if (response.success) {
        toast.success(
          locale === "zh" ? "申請已成功刪除" : "Application deleted successfully"
        );
        onOpenChange(false);
        setReason(""); // Reset reason
        onSuccess?.();
      } else {
        toast.error(
          response.message ||
            (locale === "zh" ? "刪除失敗" : "Failed to delete application")
        );
      }
    } catch (error: any) {
      console.error("Failed to delete application:", error);
      toast.error(
        error?.response?.data?.message ||
          (locale === "zh" ? "刪除申請時發生錯誤" : "Error deleting application")
      );
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <div className="flex items-center gap-2 text-red-600 mb-2">
            <AlertTriangle className="h-5 w-5" />
            <AlertDialogTitle>
              {locale === "zh" ? "確認刪除申請" : "Confirm Delete Application"}
            </AlertDialogTitle>
          </div>
          <AlertDialogDescription className="space-y-3">
            <p>
              {locale === "zh"
                ? `確定要刪除申請「${applicationName}」嗎？`
                : `Are you sure you want to delete application "${applicationName}"?`}
            </p>
            <p className="text-sm font-medium text-gray-700">
              {locale === "zh"
                ? "此操作將標記申請為「已刪除」狀態，可在操作紀錄中查看。"
                : "This action will mark the application as 'deleted' and can be viewed in the audit trail."}
            </p>

            {requireReason && (
              <div className="space-y-2 pt-2">
                <Label htmlFor="deletion-reason" className="text-gray-900">
                  {locale === "zh" ? "刪除原因 *" : "Deletion Reason *"}
                </Label>
                <Textarea
                  id="deletion-reason"
                  placeholder={
                    locale === "zh"
                      ? "請輸入刪除原因..."
                      : "Enter deletion reason..."
                  }
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="min-h-[80px]"
                  disabled={isDeleting}
                />
                <p className="text-xs text-gray-500">
                  {locale === "zh"
                    ? "刪除原因將記錄在操作紀錄中"
                    : "The reason will be recorded in the audit trail"}
                </p>
              </div>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>
            {locale === "zh" ? "取消" : "Cancel"}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleDelete();
            }}
            disabled={isDeleting || (requireReason && !reason.trim())}
            className="bg-red-600 hover:bg-red-700 focus:ring-red-600"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {locale === "zh" ? "刪除中..." : "Deleting..."}
              </>
            ) : (
              <>{locale === "zh" ? "確認刪除" : "Confirm Delete"}</>
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
