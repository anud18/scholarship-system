/**
 * Renewal API Module
 *
 * Admin-side renewal distribution result.
 *
 * Backed by `backend/app/api/v1/endpoints/renewal.py`:
 *   - GET  /api/v1/renewals/distribution-result  — admin-side, finalised renewal distribution
 *
 * All endpoints return the standard ApiResponse `{ success, message, data }`
 * shape; we normalise via `toApiResponse`.
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";

// ---------------------------------------------------------------------------
// Distribution result (admin-side)
// ---------------------------------------------------------------------------

export interface RenewalDistributionApplication {
  id: number;
  app_id: string;
  student_name: string | null;
  previous_application_id: number | null;
  /** True when a downstream challenge application points at this renewal */
  has_challenge: boolean;
}

export interface RenewalDistributionGroup {
  sub_type: string | null;
  renewal_year: number | null;
  applications: RenewalDistributionApplication[];
}

export interface RenewalDistributionRejected {
  id: number;
  student_name: string | null;
}

export interface RenewalDistributionSummary {
  approved: number;
  rejected: number;
}

export interface RenewalDistributionResult {
  groups: RenewalDistributionGroup[];
  rejected: RenewalDistributionRejected[];
  summary: RenewalDistributionSummary;
}

// ---------------------------------------------------------------------------
// API client factory
// ---------------------------------------------------------------------------

export function createRenewalApi() {
  return {
    /**
     * Admin-only: read the finalised renewal distribution for a given
     * scholarship type + academic year, grouped by (sub_type, renewal_year).
     *
     * @param scholarship_type_id ID of the scholarship type to inspect.
     * @param academic_year       Target application academic year (e.g. 114).
     */
    getDistributionResult: async (
      scholarship_type_id: number,
      academic_year: number
    ): Promise<ApiResponse<RenewalDistributionResult>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/renewals/distribution-result" as any,
        {
          params: {
            query: { scholarship_type_id, academic_year } as any,
          },
        }
      );
      return toApiResponse(
        response
      ) as ApiResponse<RenewalDistributionResult>;
    },
  };
}
