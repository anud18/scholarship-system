/**
 * Bank Verification API Module
 *
 * Handles bank account verification for scholarship applications:
 * - Single and batch verification
 * - Verification status tracking
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

type BankVerificationResult = {
  application_id: number;
  verified: boolean;
  message?: string;
  bank_name?: string;
  account_holder?: string;
};

type BankVerificationBatchResult = {
  total: number;
  verified: number;
  failed: number;
  results: BankVerificationResult[];
};

export function createBankVerificationApi(client: ApiClient) {
  return {
    /**
     * Verify bank account for a single application
     */
    verifyBankAccount: async (
      applicationId: number
    ): Promise<ApiResponse<BankVerificationResult>> => {
      return client.request("/admin/bank-verification", {
        method: "POST",
        body: JSON.stringify({ application_id: applicationId }),
      });
    },

    /**
     * Verify bank accounts for multiple applications in batch
     */
    verifyBankAccountsBatch: async (
      applicationIds: number[]
    ): Promise<ApiResponse<BankVerificationBatchResult>> => {
      return client.request("/admin/bank-verification/batch", {
        method: "POST",
        body: JSON.stringify({ application_ids: applicationIds }),
      });
    },
  };
}
