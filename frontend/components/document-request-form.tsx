"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { FileText, Loader2, X } from "lucide-react";
import { apiClient } from "@/lib/api";
import { toast } from "sonner";

interface DocumentRequestFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  applicationId: number;
  applicationName: string;
  onSuccess?: () => void;
  locale?: "zh" | "en";
}

export function DocumentRequestForm({
  open,
  onOpenChange,
  applicationId,
  applicationName,
  onSuccess,
  locale = "zh",
}: DocumentRequestFormProps) {
  const [requestedDocuments, setRequestedDocuments] = useState<string[]>([]);
  const [currentDocument, setCurrentDocument] = useState("");
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAddDocument = () => {
    const trimmedDoc = currentDocument.trim();
    if (trimmedDoc && !requestedDocuments.includes(trimmedDoc)) {
      setRequestedDocuments([...requestedDocuments, trimmedDoc]);
      setCurrentDocument("");
    }
  };

  const handleRemoveDocument = (index: number) => {
    setRequestedDocuments(requestedDocuments.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAddDocument();
    }
  };

  const handleSubmit = async () => {
    // Validation
    if (requestedDocuments.length === 0) {
      toast.error(locale === "zh" ? "請至少新增一項文件" : "Please add at least one document");
      return;
    }

    if (!reason.trim()) {
      toast.error(locale === "zh" ? "請輸入補件原因" : "Please enter a reason");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await apiClient.applications.createDocumentRequest(
        applicationId,
        {
          requested_documents: requestedDocuments,
          reason: reason.trim(),
          notes: notes.trim() || undefined,
        }
      );

      if (response.success) {
        toast.success(
          locale === "zh" ? "文件補件要求已送出" : "Document request sent successfully"
        );
        // Reset form
        setRequestedDocuments([]);
        setCurrentDocument("");
        setReason("");
        setNotes("");
        onOpenChange(false);
        onSuccess?.();
      } else {
        toast.error(
          response.message ||
            (locale === "zh" ? "送出失敗" : "Failed to send request")
        );
      }
    } catch (error: any) {
      console.error("Failed to create document request:", error);
      toast.error(
        error?.response?.data?.message ||
          (locale === "zh" ? "建立文件要求時發生錯誤" : "Error creating document request")
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = () => {
    // Reset form when canceling
    setRequestedDocuments([]);
    setCurrentDocument("");
    setReason("");
    setNotes("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2 text-orange-600 mb-2">
            <FileText className="h-5 w-5" />
            <DialogTitle>
              {locale === "zh" ? "要求補件" : "Request Documents"}
            </DialogTitle>
          </div>
          <DialogDescription>
            {locale === "zh"
              ? `向學生要求補充申請「${applicationName}」所需的文件`
              : `Request additional documents from student for application "${applicationName}"`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Requested Documents */}
          <div className="space-y-2">
            <Label htmlFor="document-input" className="text-gray-900">
              {locale === "zh" ? "需補文件 *" : "Required Documents *"}
            </Label>
            <div className="flex gap-2">
              <Input
                id="document-input"
                placeholder={
                  locale === "zh"
                    ? "輸入文件名稱，按 Enter 新增"
                    : "Enter document name, press Enter to add"
                }
                value={currentDocument}
                onChange={(e) => setCurrentDocument(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isSubmitting}
              />
              <Button
                type="button"
                onClick={handleAddDocument}
                disabled={!currentDocument.trim() || isSubmitting}
                variant="outline"
              >
                {locale === "zh" ? "新增" : "Add"}
              </Button>
            </div>

            {/* Document badges */}
            {requestedDocuments.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-3">
                {requestedDocuments.map((doc, index) => (
                  <Badge
                    key={index}
                    variant="secondary"
                    className="pr-1 text-sm"
                  >
                    {doc}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-4 w-4 p-0 ml-1"
                      onClick={() => handleRemoveDocument(index)}
                      disabled={isSubmitting}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </Badge>
                ))}
              </div>
            )}

            <p className="text-xs text-gray-500">
              {locale === "zh"
                ? "例如：成績單、推薦信、研究計畫等"
                : "e.g., transcript, recommendation letter, research plan"}
            </p>
          </div>

          {/* Reason */}
          <div className="space-y-2">
            <Label htmlFor="reason-input" className="text-gray-900">
              {locale === "zh" ? "補件原因 *" : "Reason *"}
            </Label>
            <Textarea
              id="reason-input"
              placeholder={
                locale === "zh"
                  ? "說明為何需要這些文件..."
                  : "Explain why these documents are needed..."
              }
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="min-h-[100px]"
              disabled={isSubmitting}
            />
            <p className="text-xs text-gray-500">
              {locale === "zh"
                ? "學生會在通知郵件中看到此說明"
                : "Students will see this explanation in the notification email"}
            </p>
          </div>

          {/* Notes (optional) */}
          <div className="space-y-2">
            <Label htmlFor="notes-input" className="text-gray-900">
              {locale === "zh" ? "補充說明（選填）" : "Additional Notes (Optional)"}
            </Label>
            <Textarea
              id="notes-input"
              placeholder={
                locale === "zh"
                  ? "額外的提醒或說明..."
                  : "Additional reminders or instructions..."
              }
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="min-h-[80px]"
              disabled={isSubmitting}
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={handleCancel}
            disabled={isSubmitting}
          >
            {locale === "zh" ? "取消" : "Cancel"}
          </Button>
          <Button
            type="button"
            onClick={handleSubmit}
            disabled={
              isSubmitting ||
              requestedDocuments.length === 0 ||
              !reason.trim()
            }
            className="bg-orange-600 hover:bg-orange-700"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                {locale === "zh" ? "送出中..." : "Submitting..."}
              </>
            ) : (
              <>{locale === "zh" ? "送出要求" : "Submit Request"}</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
