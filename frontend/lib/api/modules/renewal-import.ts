/**
 * Renewal Import API Module (OpenAPI-typed)
 *
 * Handles bulk import of renewal ("續領生") students for college administrators:
 * - Upload and validate the renewal roster Excel/CSV file (keeps only
 *   「是 + 通過」 rows; the rest are skipped)
 * - Preview data before confirmation
 * - Confirm the batch, creating pre-approved renewal applications
 * - View import history and details
 * - Download the renewal import template
 *
 * Mirrors batch-import.ts, using openapi-fetch for full type safety from the
 * backend OpenAPI schema.
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import { createFileUploadFormData, type MultipartFormData } from '../form-data-helpers';
import type { ApiResponse } from '../types';

/**
 * Resolve the auth token for direct `fetch()` downloads.
 *
 * The typed client keeps an in-memory copy, but that can be empty on a fresh
 * page load / session restore where the token only lives in localStorage. The
 * rest of the app reads the token straight from storage at call time, so fall
 * back to the same keys here — otherwise these downloads go out without an
 * Authorization header and the backend rejects them with 401
 * ("Authorization header missing").
 */
function resolveAuthToken(): string | null {
  const inMemory = typedClient.getToken();
  if (inMemory) return inMemory;
  if (typeof window === 'undefined') return null;
  return (
    localStorage.getItem('auth_token') ||
    localStorage.getItem('token') ||
    sessionStorage.getItem('auth_token') ||
    null
  );
}

export interface RenewalUploadResult {
  batch_id: number;
  file_name: string;
  total_records: number;
  skipped_records: number;
  preview_data: Array<Record<string, unknown>>;
  validation_summary: {
    valid_count: number;
    invalid_count: number;
    skipped_count: number;
    errors: Array<Record<string, unknown>>;
    warnings: Array<Record<string, unknown>>;
  };
}

export interface RenewalConfirmResult {
  batch_id: number;
  success_count: number;
  failed_count: number;
  created_application_ids: number[];
}

export function createRenewalImportApi() {
  return {
    /**
     * Upload and validate the renewal import data file
     * Type-safe: FormData upload with query parameters validated
     */
    uploadData: async (
      file: File,
      scholarshipType: string,
      academicYear: number,
      semester: string
    ): Promise<ApiResponse<RenewalUploadResult>> => {
      const formData = createFileUploadFormData({ file });

      const response = await typedClient.raw.POST('/api/v1/college-review/renewal-import/upload', {
        params: {
          query: {
            scholarship_type: scholarshipType,
            academic_year: academicYear,
            semester: semester,
          },
        },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<RenewalUploadResult>(response);
    },

    /**
     * Confirm renewal import after validation
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    confirm: async (
      batchId: number,
      confirm: boolean = true
    ): Promise<ApiResponse<RenewalConfirmResult>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/renewal-import/{batch_id}/confirm', {
        params: { path: { batch_id: batchId } },
        body: { batch_id: batchId, confirm },
      });
      return toApiResponse<RenewalConfirmResult>(response);
    },

    /**
     * Get renewal import history with optional pagination
     * Type-safe: Query parameters validated against OpenAPI
     */
    getHistory: async (params?: {
      skip?: number;
      limit?: number;
    }): Promise<ApiResponse<Record<string, unknown>>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/renewal-import/history', {
        params: {
          query: {
            skip: params?.skip,
            limit: params?.limit,
          },
        },
      });
      return toApiResponse<Record<string, unknown>>(response);
    },

    /**
     * Get detailed information about a specific renewal import
     * Type-safe: Path parameter validated against OpenAPI
     */
    getDetails: async (
      batchId: number
    ): Promise<ApiResponse<Record<string, unknown>>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/renewal-import/{batch_id}/details', {
        params: { path: { batch_id: batchId } },
      });
      return toApiResponse<Record<string, unknown>>(response);
    },

    /**
     * Download the renewal import template for a scholarship type
     * Type-safe: Returns blob for file download
     */
    downloadTemplate: async (scholarshipType: string): Promise<void> => {
      const token = resolveAuthToken();
      const baseURL = typeof window !== "undefined" ? "" : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/college-review/renewal-import/template?scholarship_type=${encodeURIComponent(scholarshipType)}`,
        {
          method: "GET",
          headers: {
            ...(token && { Authorization: `Bearer ${token}` }),
          },
        }
      );

      if (!response.ok) {
        let detail = "";
        try {
          const body = await response.clone().json();
          detail = body?.message || body?.detail || "";
        } catch {
          // Non-JSON error body — surface the status alone.
        }
        throw new Error(
          `Failed to download template (${response.status}${detail ? `: ${detail}` : ""})`
        );
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;

      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers.get("content-disposition");
      let filename = `renewal_import_template_${scholarshipType}.xlsx`;
      if (contentDisposition) {
        // Match filename*=UTF-8''encoded_name (RFC 5987)
        const filenameMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/);
        if (filenameMatch) {
          filename = decodeURIComponent(filenameMatch[1].trim());
        }
      }

      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },
  };
}
