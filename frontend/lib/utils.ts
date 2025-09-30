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
 * Get badge variant based on status
 */
export function getStatusBadgeVariant(status: string): "default" | "secondary" | "destructive" | "outline" {
  const statusLower = status.toLowerCase();

  // Success states
  if (["completed", "active", "approved", "verified", "locked"].includes(statusLower)) {
    return "default";
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
