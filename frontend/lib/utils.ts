import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export { clsx };

/**
 * Format date string to localized date-time format
 */
export function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return "-";

  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return "-";

    return new Intl.DateTimeFormat("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(date);
  } catch {
    return "-";
  }
}

/**
 * Map a filename's extension to a preview MIME type used by FilePreviewDialog
 * and similar viewers. Falls back to `application/octet-stream`.
 */
export function previewMimeType(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".doc")) return "application/msword";
  if (lower.endsWith(".docx"))
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if (lower.endsWith(".odt"))
    return "application/vnd.oasis.opendocument.text";
  if (lower.endsWith(".ods"))
    return "application/vnd.oasis.opendocument.spreadsheet";
  if (lower.endsWith(".odp"))
    return "application/vnd.oasis.opendocument.presentation";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".png")) return "image/png";
  return "application/octet-stream";
}

/**
 * Get badge variant based on status
 */
export function getStatusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  const statusLower = status.toLowerCase();

  // Success states
  if (["completed", "active", "approved", "verified", "locked"].includes(statusLower)) {
    return "default";
  }

  // Partial approval state
  if (statusLower === "partial_approved") {
    return "outline";
  }

  // Warning/pending states
  if (["draft", "pending", "processing", "paused", "under_review"].includes(statusLower)) {
    return "secondary";
  }

  // Error/failed states
  if (["failed", "rejected", "error", "cancelled", "disabled"].includes(statusLower)) {
    return "destructive";
  }

  return "outline";
}
