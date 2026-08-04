/**
 * Renewal API Module
 *
 * Endpoints for the scholarship renewal + challenge flow.
 *
 * Backed by `backend/app/api/v1/endpoints/renewal.py`:
 *   - GET  /api/v1/renewals/eligible             — student-side, list renewable prior apps
 *   - POST /api/v1/renewals/                     — student-side, create renewal from prior
 *   - POST /api/v1/renewals/challenge            — student-side, create challenge from renewal
 *   - GET  /api/v1/renewals/distribution-result  — admin-side, finalised renewal distribution
 *
 * All endpoints return the standard ApiResponse `{ success, message, data }`
 * shape; we normalise via `toApiResponse`.
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";

// ---------------------------------------------------------------------------
// Eligible renewals (student-side)
// ---------------------------------------------------------------------------

export interface EligibleRenewal {
  previous_application_id: number;
  scholarship_type_id: number;
  scholarship_type_name: string | null;
  sub_scholarship_type: string | null;
  target_academic_year: number;
  renewal_year: number;
  /** ISO 8601 UTC string of the renewal application end date, if configured */
  renewal_deadline: string | null;
}

// ---------------------------------------------------------------------------
// Create renewal / challenge (student-side)
// ---------------------------------------------------------------------------

export interface CreateRenewalRequest {
  previous_application_id: number;
}

export interface CreateRenewalResult {
  id: number;
  app_id: string;
  is_renewal: boolean;
  sub_scholarship_type: string | null;
  previous_application_id: number | null;
  academic_year: number;
  renewal_year: number | null;
  status: string;
}

export interface CreateChallengeRequest {
  renewal_application_id: number;
  target_sub_type: string;
}

export interface CreateChallengeResult {
  id: number;
  app_id: string;
  is_renewal: boolean;
  sub_scholarship_type: string | null;
  challenges_application_id: number | null;
  academic_year: number;
  status: string;
}

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
     * List the current user's prior-year approved applications that are
     * currently within an open renewal window.
     */
    listEligible: async (): Promise<ApiResponse<EligibleRenewal[]>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/renewals/eligible" as any,
        {}
      );
      return toApiResponse(response) as ApiResponse<EligibleRenewal[]>;
    },

    /**
     * Create a renewal application from a prior approved application.
     */
    createRenewal: async (
      previous_application_id: number
    ): Promise<ApiResponse<CreateRenewalResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/renewals/" as any,
        { body: { previous_application_id } as any }
      );
      return toApiResponse(response) as ApiResponse<CreateRenewalResult>;
    },

    /**
     * Create a challenge application from an approved renewal application,
     * targeting a different sub_scholarship_type.
     */
    createChallenge: async (
      renewal_application_id: number,
      target_sub_type: string
    ): Promise<ApiResponse<CreateChallengeResult>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/renewals/challenge" as any,
        { body: { renewal_application_id, target_sub_type } as any }
      );
      return toApiResponse(response) as ApiResponse<CreateChallengeResult>;
    },

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
