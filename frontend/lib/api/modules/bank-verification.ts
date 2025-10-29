/**
 * Bank Verification API Module (OpenAPI-typed)
 *
 * Handles bank account verification for scholarship applications:
 * - Single and batch verification
 * - Verification status tracking
 * - Async batch verification with task monitoring
 * - Student verified account management
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

export type BankVerificationResult = {
  application_id: number;
  verification_status: string;
  account_number_status?: string;
  account_holder_status?: string;
  requires_manual_review?: boolean;
  comparisons?: {
    [key: string]: {
      field_name: string;
      form_value: string;
      ocr_value: string;
      similarity_score: number;
      is_match: boolean;
      confidence: string;
      needs_manual_review?: boolean;
    };
  };
  form_data?: { [key: string]: string };
  ocr_data?: { [key: string]: any };
  passbook_document?: {
    file_path: string;
    original_filename: string;
    file_id?: number;
    object_name?: string;
  };
  recommendations?: string[];
};

export type BankVerificationBatchResult = {
  total: number;
  verified: number;
  failed: number;
  results: BankVerificationResult[];
};

export type ManualBankReviewRequest = {
  application_id: number;
  account_number_approved?: boolean;
  account_number_corrected?: string;
  account_holder_approved?: boolean;
  account_holder_corrected?: string;
  review_notes?: string;
};

export type ManualBankReviewResult = {
  success: boolean;
  application_id: number;
  account_number_status: string;
  account_holder_status: string;
  updated_form_data: { [key: string]: string };
  review_timestamp: string;
  reviewed_by: string;
};

export type BankVerificationTask = {
  task_id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  total_count: number;
  processed_count: number;
  verified_count: number;
  needs_review_count: number;
  failed_count: number;
  skipped_count?: number;
  progress_percentage?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  is_completed: boolean;
  is_running: boolean;
  error_message?: string;
  results?: { [appId: number]: any };
};

export type BatchVerificationAsyncResponse = {
  task_id: string;
  total_count: number;
  status: string;
  created_at: string;
};

export type VerifiedAccountResponse = {
  has_verified_account: boolean;
  account?: {
    id: number;
    account_number: string;
    account_holder: string;
    verified_at: string;
    verification_method?: string;
    verification_notes?: string;
    passbook_cover_url?: string;
  };
  message: string;
};

export function createBankVerificationApi() {
  return {
    /**
     * Get bank verification initial data without performing OCR
     * Used for direct manual review mode
     */
    getBankVerificationInitData: async (
      applicationId: number
    ): Promise<ApiResponse<BankVerificationResult>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/bank-verification/{application_id}/init', {
        params: { path: { application_id: applicationId } },
      });
      return toApiResponse<BankVerificationResult>(response);
    },

    /**
     * Verify bank account for a single application
     * Type-safe: Request body validated against OpenAPI
     */
    verifyBankAccount: async (
      applicationId: number,
      forceRecheck: boolean = false
    ): Promise<ApiResponse<BankVerificationResult>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/bank-verification', {
        body: { application_id: applicationId, force_recheck: forceRecheck } as any,
      });
      return toApiResponse<BankVerificationResult>(response);
    },

    /**
     * Verify bank accounts for multiple applications in batch
     * Type-safe: Request body validated against OpenAPI
     */
    verifyBankAccountsBatch: async (
      applicationIds: number[],
      forceRecheck: boolean = false
    ): Promise<ApiResponse<BankVerificationBatchResult>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/bank-verification/batch', {
        body: { application_ids: applicationIds, force_recheck: forceRecheck } as any,
      });
      return toApiResponse<BankVerificationBatchResult>(response);
    },

    /**
     * Submit manual review of bank account information
     * Allows administrators to approve/correct account number and holder name
     */
    submitManualReview: async (
      reviewData: ManualBankReviewRequest
    ): Promise<ApiResponse<ManualBankReviewResult>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/bank-verification/manual-review', {
        body: reviewData as any,
      });
      return toApiResponse<ManualBankReviewResult>(response);
    },

    /**
     * Start async batch verification task
     * Returns immediately with task_id for progress tracking
     */
    startBatchVerificationAsync: async (
      applicationIds: number[]
    ): Promise<ApiResponse<BatchVerificationAsyncResponse>> => {
      const response = await typedClient.raw.POST('/api/v1/admin/bank-verification/batch-async', {
        body: { application_ids: applicationIds } as any,
      });
      return toApiResponse<BatchVerificationAsyncResponse>(response);
    },

    /**
     * Get verification task status and progress
     */
    getVerificationTaskStatus: async (taskId: string): Promise<ApiResponse<BankVerificationTask>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/bank-verification/tasks/{task_id}', {
        params: { path: { task_id: taskId } },
      });
      return toApiResponse<BankVerificationTask>(response);
    },

    /**
     * List verification tasks with optional status filter
     */
    listVerificationTasks: async (
      status?: string,
      limit: number = 50,
      offset: number = 0
    ): Promise<ApiResponse<{ tasks: BankVerificationTask[]; pagination: any }>> => {
      const response = await typedClient.raw.GET('/api/v1/admin/bank-verification/tasks', {
        params: {
          query: {
            status,
            limit,
            offset,
          },
        },
      });
      return toApiResponse<{ tasks: BankVerificationTask[]; pagination: any }>(response);
    },

    /**
     * Get student's verified bank account (student endpoint)
     */
    getMyVerifiedAccount: async (): Promise<ApiResponse<VerifiedAccountResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/student-bank-accounts/my-verified-account');
      return toApiResponse<VerifiedAccountResponse>(response);
    },
  };
}
