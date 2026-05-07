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
import { getTranslation } from "@/lib/i18n";

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
  const t = (k: string) => getTranslation(locale, k);

  const resetState = () => {
    setReason("");
    setIsDeleting(false);
  };

  const handleDelete = async () => {
    const trimmedReason = reason.trim();
    if (requireReason && !trimmedReason) {
      toast.error(t("dialogs.delete_application.reason_required"));
      return;
    }

    setIsDeleting(true);
    try {
      const response = await apiClient.admin.deleteApplication(
        applicationId,
        trimmedReason
      );

      if (response.success) {
        toast.success(t("dialogs.delete_application.delete_success"));
        onOpenChange(false);
        resetState();
        onSuccess?.();
      } else {
        toast.error(
          response.message || t("dialogs.delete_application.delete_failed")
        );
      }
    } catch (error: any) {
      console.error("Failed to delete application:", error);
      toast.error(
        error?.response?.data?.message ||
          t("dialogs.delete_application.delete_error")
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
                {t("dialogs.delete_application.confirm_title")}
              </AlertDialogTitle>
              <AlertDialogDescription className="mt-1">
                {t("dialogs.delete_application.confirm_description")}
              </AlertDialogDescription>
            </div>
          </div>
        </AlertDialogHeader>

        <div className="space-y-3 bg-gray-50 border border-gray-200 p-3 rounded-lg">
          <p className="text-sm text-gray-900">
            <span className="text-gray-600">
              {t("dialogs.delete_application.application_label")}{" "}
            </span>
            <span className="font-semibold">{applicationName}</span>
          </p>
          <p className="text-xs text-gray-500">
            {t("dialogs.delete_application.cascade_notice")}
          </p>
        </div>

        {requireReason && (
          <div className="space-y-2">
            <Label htmlFor="deletion-reason" className="text-gray-900">
              {t("dialogs.delete_application.reason_label")}
              <span className="text-red-600 ml-1">*</span>
            </Label>
            <Textarea
              id="deletion-reason"
              placeholder={t("dialogs.delete_application.reason_placeholder")}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="min-h-[80px]"
              maxLength={500}
              disabled={isDeleting}
            />
            <p className="text-xs text-gray-500">
              {t("dialogs.delete_application.reason_recorded_notice")}
            </p>
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={isDeleting}>
            {t("dialogs.delete_application.cancel")}
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
                {t("dialogs.delete_application.deleting")}
              </>
            ) : (
              t("dialogs.delete_application.confirm_delete")
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
