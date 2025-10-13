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
  verified: boolean;
  message?: string;
  account_holder?: string;
};

type BankVerificationBatchResult = {
  total: number;
  verified: number;
  failed: number;
  results: BankVerificationResult[];
};

export function createBankVerificationApi() {
  return {
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
  };
}
