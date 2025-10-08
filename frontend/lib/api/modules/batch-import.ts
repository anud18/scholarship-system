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
  batch_id: string;
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

type BatchHistoryItem = {
  id: string;
  file_name: string;
  uploaded_by: number;
  uploaded_at: string;
  total_records: number;
  success_count: number;
  failed_count: number;
  status: "pending" | "completed" | "failed";
  scholarship_type: string;
  academic_year: number;
  semester: string;
};

type BatchHistoryResponse = {
  items: BatchHistoryItem[];
  total: number;
};

type BatchDetails = BatchHistoryItem & {
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
      batchId: string,
      confirm: boolean = true
    ): Promise<ApiResponse<BatchConfirmResult>> => {
      return client.request(`/college/batch-import/${batchId}/confirm`, {
        method: "POST",
        body: JSON.stringify({ batch_id: batchId, confirm }),
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
      batchId: string
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
  };
}
