/**
 * Document Requests API Module (OpenAPI-typed)
 *
 * Handles student document request operations including:
 * - Viewing pending document requests
 * - Fulfilling document requests
 * - Tracking request status
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';

/**
 * Student-facing document request response
 */
export interface StudentDocumentRequest {
  id: number;
  application_id: number;
  application_app_id: string;
  scholarship_type_name: string;
  academic_year: string;
  semester: string;
  requested_by_name: string;
  requested_at: string;
  requested_documents: string[];
  reason: string;
  notes?: string;
  status: string;
  created_at: string;
  fulfilled_at?: string;
}

export function createDocumentRequestsApi() {
  return {
    /**
     * Get current user's document requests (student only)
     * Type-safe: Query parameters validated against OpenAPI
     */
    getMyDocumentRequests: async (
      status?: string
    ): Promise<ApiResponse<StudentDocumentRequest[]>> => {
      const response = await typedClient.raw.GET('/api/v1/document-requests/my-requests', {
        params: { query: status ? { status } : undefined },
      });
      return toApiResponse<StudentDocumentRequest[]>(response);
    },

    /**
     * Fulfill a document request (student only)
     * Type-safe: Path parameter and body validated against OpenAPI
     */
    fulfillDocumentRequest: async (
      requestId: number,
      notes?: string
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PATCH(
        '/api/v1/document-requests/{request_id}/fulfill',
        {
          params: { path: { request_id: requestId } },
          body: notes ? { notes } : undefined,
        }
      );
      return toApiResponse<any>(response);
    },
  };
}
