/**
 * Bank Verification API Module (OpenAPI-typed)
 *
 * Handles bank account verification for scholarship applications:
 * - Single and batch verification
 * - Verification status tracking
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

type BankVerificationResult = {
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

type BankVerificationBatchResult = {
  total: number;
  verified: number;
  failed: number;
  results: BankVerificationResult[];
};

type ManualBankReviewRequest = {
  application_id: number;
  account_number_approved?: boolean;
  account_number_corrected?: string;
  account_holder_approved?: boolean;
  account_holder_corrected?: string;
  review_notes?: string;
};

type ManualBankReviewResult = {
  success: boolean;
  application_id: number;
  account_number_status: string;
  account_holder_status: string;
  updated_form_data: { [key: string]: string };
  review_timestamp: string;
  reviewed_by: string;
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
  };
}
