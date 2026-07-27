/**
 * 匯入已領月份數 API Module
 *
 * Two-phase import of 國科會's 獲獎生已領月份統計表, driven by the dialog on the
 * 學生領獎紀錄查詢 page: `preview` parses and stages, `confirm` commits.
 *
 * Uses raw fetch rather than typedClient because the upload is multipart.
 */

import { typedClient } from "../typed-client";
import type { ApiResponse } from "../types";

/** One parsed row as staged by the preview endpoint. */
export interface ReceivedMonthsPreviewRow {
  row_number: number;
  student_number: string;
  /** Inclusive 領獎起始月份 → 目前領獎月份 span. Null when `error` is set. */
  months: number | null;
  award_start_month: number | null;
  award_current_month: number | null;
  award_start_label: string | null;
  award_current_label: string | null;
  /** Every column of the source row, keyed by the file's own header text. */
  raw_row: Record<string, string>;
  /** Set when 合計目前領獎月份數 disagrees with the derived span — still imports. */
  warning: string | null;
  /** Set when the row cannot be imported at all. */
  error: string | null;
}

export interface ReceivedMonthsPreview {
  import_id: number;
  file_name: string;
  scholarship_type_id: number;
  total_rows: number;
  valid_rows: number;
  warning_rows: number;
  error_rows: number;
  headers: string[];
  rows: ReceivedMonthsPreviewRow[];
}

export interface ReceivedMonthsConfirmResult {
  import_id: number;
  created: number;
  updated: number;
}

async function readApiResponse<T>(
  response: Response,
): Promise<ApiResponse<T>> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON response — fall through to the HTTP-status error shape below.
  }

  if (!response.ok) {
    const bodyObj =
      body && typeof body === "object"
        ? (body as { message?: unknown; detail?: unknown })
        : null;
    const message =
      (typeof bodyObj?.message === "string" && bodyObj.message) ||
      (typeof bodyObj?.detail === "string" && bodyObj.detail) ||
      `匯入失敗 (HTTP ${response.status})`;
    return { success: false, message, data: undefined } as ApiResponse<T>;
  }

  return body as ApiResponse<T>;
}

function authHeaders(): Record<string, string> {
  const token = typedClient.getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function createReceivedMonthsApi() {
  return {
    /**
     * Download the example workbook — 國科會's blank 獲獎生已領月份統計表.
     * Triggers a browser download; resolves once the click is dispatched.
     */
    downloadTemplate: async (): Promise<void> => {
      const response = await fetch("/api/v1/admin/received-months/template", {
        method: "GET",
        headers: authHeaders(),
      });

      if (!response.ok) {
        let detail = "";
        try {
          const body = await response.clone().json();
          detail = body?.message || body?.detail || "";
        } catch {
          // Non-JSON error body — surface the status alone.
        }
        throw new Error(
          `下載範例失敗 (${response.status}${detail ? `: ${detail}` : ""})`,
        );
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;

      // filename*=UTF-8''… (RFC 5987) — the name is Chinese.
      const disposition = response.headers.get("content-disposition");
      let filename = "received-months-template.xlsx";
      const match = disposition?.match(/filename\*=UTF-8''([^;]+)/);
      if (match) filename = decodeURIComponent(match[1].trim());

      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },

    /** Parse and stage an upload. Writes nothing to the ledger. */
    preview: async (
      scholarshipTypeId: number,
      file: File,
    ): Promise<ApiResponse<ReceivedMonthsPreview>> => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("scholarship_type_id", String(scholarshipTypeId));

      const response = await fetch("/api/v1/admin/received-months/preview", {
        method: "POST",
        body: formData,
        headers: authHeaders(),
      });
      return readApiResponse<ReceivedMonthsPreview>(response);
    },

    /** Commit a staged import into the ledger. */
    confirm: async (
      importId: number,
    ): Promise<ApiResponse<ReceivedMonthsConfirmResult>> => {
      const response = await fetch(
        `/api/v1/admin/received-months/${importId}/confirm`,
        { method: "POST", headers: authHeaders() },
      );
      return readApiResponse<ReceivedMonthsConfirmResult>(response);
    },

    /** Discard a staged import without touching the ledger. */
    cancel: async (
      importId: number,
    ): Promise<ApiResponse<{ import_id: number }>> => {
      const response = await fetch(
        `/api/v1/admin/received-months/${importId}/cancel`,
        { method: "POST", headers: authHeaders() },
      );
      return readApiResponse<{ import_id: number }>(response);
    },
  };
}
