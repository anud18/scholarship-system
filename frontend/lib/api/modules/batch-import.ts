/**
 * Batch Import API Module
 *
 * Handles bulk application data import for college administrators:
 * - Upload and validate Excel/CSV files
 * - Preview data before confirmation
 * - Confirm batch imports
 * - View import history and details
 * - Download import templates
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

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

export function createBatchImportApi(client: ApiClient) {
  return {
    /**
     * Upload and validate batch import data file
     */
    uploadData: async (
      file: File,
      scholarshipType: string,
      academicYear: number,
      semester: string
    ): Promise<ApiResponse<BatchUploadResult>> => {
      const formData = new FormData();
      formData.append("file", file);

      return client.request("/college/batch-import/upload-data", {
        method: "POST",
        body: formData,
        headers: {}, // Let browser set Content-Type for FormData
        params: {
          scholarship_type: scholarshipType,
          academic_year: academicYear,
          semester: semester,
        },
      });
    },

    /**
     * Confirm batch import after validation
     */
    confirm: async (
      batchId: number,
      confirm: boolean = true
    ): Promise<ApiResponse<BatchConfirmResult>> => {
      return client.request(`/college/batch-import/${batchId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ batch_id: batchId, confirm }),
      });
    },

    /**
     * Update a single record in the batch import
     */
    updateRecord: async (
      batchId: number,
      recordIndex: number,
      updates: Record<string, any>
    ): Promise<ApiResponse<BatchUpdateRecordResult>> => {
      return client.request(`/college/batch-import/${batchId}/records`, {
        method: "PATCH",
        body: JSON.stringify({ record_index: recordIndex, updates }),
      });
    },

    /**
     * Re-validate all records in the batch import
     */
    revalidate: async (
      batchId: number
    ): Promise<ApiResponse<BatchRevalidateResult>> => {
      return client.request(`/college/batch-import/${batchId}/validate`, {
        method: "POST",
      });
    },

    /**
     * Delete a single record from the batch import
     */
    deleteRecord: async (
      batchId: number,
      recordIndex: number
    ): Promise<ApiResponse<BatchDeleteRecordResult>> => {
      return client.request(
        `/college/batch-import/${batchId}/records/${recordIndex}`,
        {
          method: "DELETE",
        }
      );
    },

    /**
     * Upload documents in bulk for batch import (ZIP file)
     */
    uploadDocuments: async (
      batchId: number,
      zipFile: File
    ): Promise<ApiResponse<BatchDocumentUploadResponse>> => {
      const formData = new FormData();
      formData.append("file", zipFile);

      return client.request(`/college/batch-import/${batchId}/documents`, {
        method: "POST",
        body: formData,
        headers: {}, // Let browser set Content-Type for FormData
      });
    },

    /**
     * Get batch import history with optional filtering
     */
    getHistory: async (params?: {
      skip?: number;
      limit?: number;
      status?: string;
    }): Promise<ApiResponse<BatchHistoryResponse>> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return client.request(
        `/college/batch-import/history${query ? `?${query}` : ""}`
      );
    },

    /**
     * Get detailed information about a specific batch import
     */
    getDetails: async (
      batchId: number
    ): Promise<ApiResponse<BatchDetails>> => {
      return client.request(`/college/batch-import/${batchId}/details`);
    },

    /**
     * Download batch import template for a scholarship type
     */
    downloadTemplate: async (scholarshipType: string): Promise<void> => {
      const token = client.getToken();
      const baseURL = typeof window !== "undefined" ? "" : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/college/batch-import/template?scholarship_type=${encodeURIComponent(scholarshipType)}`,
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
     */
    deleteBatch: async (batchId: number): Promise<ApiResponse<{ batch_id: number; deleted_applications: number }>> => {
      return client.request(`/college/batch-import/${batchId}`, {
        method: "DELETE",
      });
    },

    /**
     * Download original file for a batch import
     */
    downloadFile: async (batchId: number): Promise<void> => {
      const token = client.getToken();
      const baseURL =
        typeof window !== "undefined"
          ? ""
          : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/college/batch-import/${batchId}/download`,
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
