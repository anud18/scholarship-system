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

  const resetState = () => {
    setReason("");
    setIsDeleting(false);
  };

  const handleDelete = async () => {
    const trimmedReason = reason.trim();
    if (requireReason && !trimmedReason) {
      toast.error(locale === "zh" ? "請輸入刪除原因" : "Deletion reason is required");
      return;
    }

    setIsDeleting(true);
    try {
      const response = await apiClient.admin.deleteApplication(
        applicationId,
        trimmedReason
      );

      if (response.success) {
        toast.success(
          locale === "zh" ? "申請已成功刪除" : "Application deleted successfully"
        );
        onOpenChange(false);
        resetState();
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
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) resetState();
        onOpenChange(next);
      }}
    >
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100 flex-shrink-0 mt-1">
              <AlertTriangle className="h-5 w-5 text-red-600" />
            </div>
            <div className="flex-1">
              <AlertDialogTitle className="text-red-700">
                {locale === "zh" ? "確認刪除申請" : "Confirm Delete Application"}
              </AlertDialogTitle>
              <AlertDialogDescription className="mt-1">
                {locale === "zh"
                  ? "此操作將永久移除申請資料，且無法撤銷。"
                  : "This action permanently removes the application and cannot be undone."}
              </AlertDialogDescription>
            </div>
          </div>
        </AlertDialogHeader>

        <div className="space-y-3 bg-gray-50 border border-gray-200 p-3 rounded-lg">
          <p className="text-sm text-gray-900">
            <span className="text-gray-600">
              {locale === "zh" ? "申請：" : "Application: "}
            </span>
            <span className="font-semibold">{applicationName}</span>
          </p>
          <p className="text-xs text-gray-500">
            {locale === "zh"
              ? "刪除後相關審查、造冊明細等關聯資料也會一併移除，但操作紀錄會永久保留。"
              : "Related review and roster records will be removed as well; audit logs are preserved."}
          </p>
        </div>

        {requireReason && (
          <div className="space-y-2">
            <Label htmlFor="deletion-reason" className="text-gray-900">
              {locale === "zh" ? "刪除原因" : "Deletion Reason"}
              <span className="text-red-600 ml-1">*</span>
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
              maxLength={500}
              disabled={isDeleting}
            />
            <p className="text-xs text-gray-500">
              {locale === "zh"
                ? "刪除原因將記錄在操作紀錄中"
                : "The reason will be recorded in the audit trail"}
            </p>
          </div>
        )}

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
            ) : locale === "zh" ? (
              "確認刪除"
            ) : (
              "Confirm Delete"
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
