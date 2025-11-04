/**
 * Batch Import API Module (OpenAPI-typed)
 *
 * Handles bulk application data import for college administrators:
 * - Upload and validate Excel/CSV files
 * - Preview data before confirmation
 * - Confirm batch imports
 * - View import history and details
 * - Download import templates
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import { createFileUploadFormData, type MultipartFormData } from '../form-data-helpers';
import type { ApiResponse } from '../types';

type BatchUploadResult = {
  batch_id: number;
  file_name: string;
  total_records: number;
  preview_data: Array<Record<string, any>>;
  validation_summary: {
    valid_count: number;
    invalid_count: number;
    warnings: string[];
    errors: Array<{
      row: number;
      field?: string;
      message: string;
    }>;
  };
};

type BatchConfirmResult = {
  success_count: number;
  failed_count: number;
  errors: Array<{
    row: number;
    student_id: string;
    error: string;
  }>;
  created_application_ids: number[];
};

type BatchUpdateRecordResult = {
  updated_record: Record<string, any>;
};

type BatchRevalidateResult = {
  batch_id: number;
  total_records: number;
  valid_count: number;
  invalid_count: number;
  warnings: Array<{
    row: number;
    field?: string;
    message: string;
  }>;
  errors: Array<{
    row: number;
    field: string;
    message: string;
  }>;
};

type BatchDeleteRecordResult = {
  deleted_record: Record<string, any>;
  remaining_records: number;
};

type BatchDocumentUploadResult = {
  student_id: string;
  file_name: string;
  document_type: string;
  status: string;
  message?: string;
  application_id?: number;
};

type BatchDocumentUploadResponse = {
  batch_id: number;
  total_files: number;
  matched_count: number;
  unmatched_count: number;
  error_count: number;
  results: BatchDocumentUploadResult[];
};

type BatchHistoryItem = {
  id: number;
  file_name: string;
  importer_name?: string;
  created_at: string;
  total_records: number;
  success_count: number;
  failed_count: number;
  import_status: string;
  scholarship_type_id?: number;
  college_code: string;
  academic_year: number;
  semester: string | null;
};

type BatchHistoryResponse = {
  items: BatchHistoryItem[];
  total: number;
};

type BatchDetails = BatchHistoryItem & {
  created_applications?: number[];
  validation_summary: {
    valid_count: number;
    invalid_count: number;
    warnings: string[];
    errors: Array<{
      row: number;
      field?: string;
      message: string;
    }>;
  };
  preview_data: Array<Record<string, any>>;
  processing_errors: Array<{
    row: number;
    student_id: string;
    error: string;
  }>;
};

export function createBatchImportApi() {
  return {
    /**
     * Upload and validate batch import data file
     * Type-safe: FormData upload with query parameters validated
     */
    uploadData: async (
      file: File,
      scholarshipType: string,
      academicYear: number,
      semester: string
    ): Promise<ApiResponse<BatchUploadResult>> => {
      const formData = createFileUploadFormData({ file });

      const response = await typedClient.raw.POST('/api/v1/college-review/batch-import/upload-data', {
        params: {
          query: {
            scholarship_type: scholarshipType,
            academic_year: academicYear,
            semester: semester,
          },
        },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<BatchUploadResult>(response);
    },

    /**
     * Confirm batch import after validation
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    confirm: async (
      batchId: number,
      confirm: boolean = true
    ): Promise<ApiResponse<BatchConfirmResult>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/batch-import/{batch_id}/confirm', {
        params: { path: { batch_id: batchId } },
        body: { batch_id: batchId, confirm },
      });
      return toApiResponse<BatchConfirmResult>(response);
    },

    /**
     * Update a single record in the batch import
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateRecord: async (
      batchId: number,
      recordIndex: number,
      updates: Record<string, any>
    ): Promise<ApiResponse<BatchUpdateRecordResult>> => {
      const response = await typedClient.raw.PATCH('/api/v1/college-review/batch-import/{batch_id}/records', {
        params: { path: { batch_id: batchId } },
        body: { record_index: recordIndex, updates } as any,
      });
      return toApiResponse<BatchUpdateRecordResult>(response);
    },

    /**
     * Re-validate all records in the batch import
     * Type-safe: Path parameter validated against OpenAPI
     */
    revalidate: async (
      batchId: number
    ): Promise<ApiResponse<BatchRevalidateResult>> => {
      const response = await typedClient.raw.POST('/api/v1/college-review/batch-import/{batch_id}/validate', {
        params: { path: { batch_id: batchId } },
      });
      return toApiResponse<BatchRevalidateResult>(response);
    },

    /**
     * Delete a single record from the batch import
     * Type-safe: Path parameters validated against OpenAPI
     */
    deleteRecord: async (
      batchId: number,
      recordIndex: number
    ): Promise<ApiResponse<BatchDeleteRecordResult>> => {
      const response = await typedClient.raw.DELETE('/api/v1/college-review/batch-import/{batch_id}/records/{record_index}', {
        params: { path: { batch_id: batchId, record_index: recordIndex } },
      });
      return toApiResponse<BatchDeleteRecordResult>(response);
    },

    /**
     * Upload documents in bulk for batch import (ZIP file)
     * Type-safe: Path parameter and FormData body properly typed
     */
    uploadDocuments: async (
      batchId: number,
      zipFile: File
    ): Promise<ApiResponse<BatchDocumentUploadResponse>> => {
      const formData = createFileUploadFormData({ file: zipFile });

      const response = await typedClient.raw.POST('/api/v1/college-review/batch-import/{batch_id}/documents', {
        params: { path: { batch_id: batchId } },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<BatchDocumentUploadResponse>(response);
    },

    /**
     * Get batch import history with optional filtering
     * Type-safe: Query parameters validated against OpenAPI
     */
    getHistory: async (params?: {
      skip?: number;
      limit?: number;
      status?: string;
    }): Promise<ApiResponse<BatchHistoryResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/batch-import/history', {
        params: {
          query: {
            skip: params?.skip,
            limit: params?.limit,
            status: params?.status,
          },
        },
      });
      return toApiResponse<BatchHistoryResponse>(response);
    },

    /**
     * Get detailed information about a specific batch import
     * Type-safe: Path parameter validated against OpenAPI
     */
    getDetails: async (
      batchId: number
    ): Promise<ApiResponse<BatchDetails>> => {
      const response = await typedClient.raw.GET('/api/v1/college-review/batch-import/{batch_id}/details', {
        params: { path: { batch_id: batchId } },
      });
      return toApiResponse<BatchDetails>(response);
    },

    /**
     * Download batch import template for a scholarship type
     * Type-safe: Returns blob for file download
     */
    downloadTemplate: async (scholarshipType: string): Promise<void> => {
      const token = typedClient.getToken();
      const baseURL = typeof window !== "undefined" ? "" : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/college-review/batch-import/template?scholarship_type=${encodeURIComponent(scholarshipType)}`,
        {
          method: "GET",
          headers: {
            ...(token && { Authorization: `Bearer ${token}` }),
          },
        }
      );

      if (!response.ok) {
        throw new Error("Failed to download template");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;

      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers.get("content-disposition");
      let filename = `batch_import_template_${scholarshipType}.xlsx`;
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

    /**
     * Delete a batch import and all its related applications
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteBatch: async (batchId: number): Promise<ApiResponse<{ batch_id: number; deleted_applications: number }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/college-review/batch-import/{batch_id}', {
        params: { path: { batch_id: batchId } },
      });
      return toApiResponse<{ batch_id: number; deleted_applications: number }>(response);
    },

    /**
     * Download original file for a batch import
     * Type-safe: Returns blob for file download
     */
    downloadFile: async (batchId: number): Promise<void> => {
      const token = typedClient.getToken();
      const baseURL =
        typeof window !== "undefined"
          ? ""
          : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/college-review/batch-import/${batchId}/download`,
        {
          method: "GET",
          headers: {
            ...(token && { Authorization: `Bearer ${token}` }),
          },
        }
      );

      if (!response.ok) {
        throw new Error("Failed to download file");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;

      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers.get("content-disposition");
      let filename = `batch_import_${batchId}.xlsx`;
      if (contentDisposition) {
        // Match filename*=UTF-8''encoded_name (RFC 5987)
        const filenameMatch = contentDisposition.match(
          /filename\*=UTF-8''([^;]+)/
        );
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
