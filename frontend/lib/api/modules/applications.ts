/**
 * Applications API Module (OpenAPI-typed)
 *
 * Handles scholarship application operations including:
 * - Application CRUD operations
 * - File uploads and document management
 * - Application status management
 * - Review and recommendation workflows
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import { createFileUploadFormData, type MultipartFormData } from '../form-data-helpers';
import type { AuditLog } from "@/types/audit";
import type { ApiResponse } from '../types';
import type { Application, ApplicationFile } from '../types';
import type { components } from '../generated/schema';

type ApplicationStatusUpdateResponse = components['schemas']['ApplicationStatusUpdateResponse'];

type ApplicationCreate = {
  scholarship_type: string;
  personal_statement?: string;
  expected_graduation_date?: string;
  research_topic?: string;
  gpa?: number;
  // Dynamic application fields (bank_account, contact_phone, ...) are bag-passed
  // through this index signature. Tightened from `any` to `unknown` so the
  // typed-client `body: applicationData as never` cast at the call site (lines
  // ~85 / ~274) is the only remaining widening — `unknown` here means callers
  // can't accidentally read a dynamic field as a typed value without checking.
  [key: string]: unknown;
};

export function createApplicationsApi() {
  return {
    /**
     * Get current user's applications with optional status filter
     * Type-safe: Query parameters validated against OpenAPI
     */
    getMyApplications: async (
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const response = await typedClient.raw.GET('/api/v1/applications', {
        params: { query: status ? { status } : undefined },
      });
      return toApiResponse<Application[]>(response);
    },

    /**
     * Get applications for college review
     * Type-safe: Query parameters validated against OpenAPI
     */
    getCollegeReview: async (
      status?: string,
      scholarshipType?: string
    ): Promise<ApiResponse<Application[]>> => {
      const response = await typedClient.raw.GET('/api/v1/applications/college/review', {
        params: { query: { status, scholarship_type: scholarshipType } },
      });
      return toApiResponse<Application[]>(response);
    },

    /**
     * Get applications by scholarship type
     * Type-safe: Query parameters validated against OpenAPI
     */
    getByScholarshipType: async (
      scholarshipType: string,
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const response = await typedClient.raw.GET('/api/v1/applications/review/list', {
        params: { query: { scholarship_type: scholarshipType, status } },
      });
      return toApiResponse<Application[]>(response);
    },

    /**
     * Create new application
     * Type-safe: Request body and query params validated
     */
    createApplication: async (
      applicationData: ApplicationCreate,
      isDraft: boolean = false
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.POST('/api/v1/applications', {
        params: { query: isDraft ? { is_draft: true } : undefined },
        body: applicationData as never, // Dynamic fields via [key: string]: unknown bypass strict schema
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Get application by ID
     * Type-safe: Path parameter validated against OpenAPI
     */
    getApplicationById: async (
      id: number
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.GET('/api/v1/applications/{id}', {
        params: { path: { id } },
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Update application
     * Type-safe: Path parameter and body validated
     */
    updateApplication: async (
      id: number,
      applicationData: Partial<ApplicationCreate>
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.PUT('/api/v1/applications/{id}', {
        params: { path: { id } },
        body: applicationData as never, // Partial<ApplicationCreate> makes all fields optional for updates
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Update application status (staff/admin only)
     * Type-safe: Path parameter and body validated against OpenAPI
     *
     * Returns ApplicationStatusUpdateResponse which includes redistribution_info
     * when status changes to approved/rejected.
     *
     * @param id - Application ID
     * @param statusData - Status update data with status and optional comments
     */
    updateApplicationStatus: async (
      id: number,
      statusData: { status: string; comments?: string; rejection_reason?: string }
    ): Promise<ApiResponse<ApplicationStatusUpdateResponse>> => {
      const response = await typedClient.raw.PUT('/api/v1/applications/{id}/status', {
        params: { path: { id } },
        body: statusData,
      });
      return toApiResponse<ApplicationStatusUpdateResponse>(response);
    },

    /**
     * Update application status (backward compatibility)
     * @deprecated Use updateApplicationStatus instead
     */
    updateStatus: async (
      id: number,
      statusData: { status: string; comments?: string }
    ): Promise<ApiResponse<ApplicationStatusUpdateResponse>> => {
      const response = await typedClient.raw.PUT('/api/v1/applications/{id}/status', {
        params: { path: { id } },
        body: statusData,
      });
      return toApiResponse<ApplicationStatusUpdateResponse>(response);
    },

    /**
     * Upload file to application
     * Type-safe: Path parameter validated, FormData properly typed
     */
    uploadFile: async (
      applicationId: number,
      file: File,
      fileType: string
    ): Promise<ApiResponse<unknown>> => {
      const formData = createFileUploadFormData({ file, file_type: fileType });

      const response = await typedClient.raw.POST('/api/v1/applications/{id}/files', {
        params: { path: { id: applicationId } },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<unknown>(response);
    },

    /**
     * Submit application for review
     * Type-safe: Path parameter validated against OpenAPI
     */
    submitApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.POST('/api/v1/applications/{id}/submit', {
        params: { path: { id: applicationId } },
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Delete application (soft delete)
     * Type-safe: Path parameter and query validated against OpenAPI
     *
     * @param applicationId - Application ID to delete
     * @param reason - Optional deletion reason (required for staff users)
     */
    deleteApplication: async (
      applicationId: number,
      reason?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.DELETE('/api/v1/applications/{id}', {
        params: {
          path: { id: applicationId },
          query: reason ? { reason } : undefined,
        },
      });
      return toApiResponse<unknown>(response);
    },

    /**
     * Withdraw application
     * Type-safe: Path parameter validated against OpenAPI
     */
    withdrawApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.POST('/api/v1/applications/{id}/withdraw', {
        params: { path: { id: applicationId } },
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Restore a deleted application to draft status
     * Type-safe: Path parameter validated against OpenAPI
     */
    restoreApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.POST('/api/v1/applications/{id}/restore', {
        params: { path: { id: applicationId } },
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Upload document to application
     * Type-safe: Path and query parameters validated, FormData properly typed
     */
    uploadDocument: async (
      applicationId: number,
      file: File,
      fileType: string = 'other'
    ): Promise<ApiResponse<unknown>> => {
      const formData = createFileUploadFormData({ file });

      const response = await typedClient.raw.POST('/api/v1/applications/{id}/files/upload', {
        params: {
          path: { id: applicationId },
          query: { file_type: fileType },
        },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<unknown>(response);
    },

    /**
     * Get application files
     * Type-safe: Path parameter validated against OpenAPI
     */
    getApplicationFiles: async (
      applicationId: number
    ): Promise<ApiResponse<ApplicationFile[]>> => {
      const response = await typedClient.raw.GET('/api/v1/applications/{id}/files', {
        params: { path: { id: applicationId } },
      });
      return toApiResponse<ApplicationFile[]>(response);
    },

    /**
     * Save application as draft
     * Type-safe: Query parameter and body validated
     */
    saveApplicationDraft: async (
      applicationData: ApplicationCreate
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.POST('/api/v1/applications', {
        params: { query: { is_draft: true } },
        body: applicationData as never, // Dynamic fields via [key: string]: unknown bypass strict schema
      });

      const apiResponse = toApiResponse<Application>(response);

      // Normalize response format
      if (apiResponse.data && typeof apiResponse.data === 'object' && 'id' in apiResponse.data) {
        return {
          success: true,
          message: apiResponse.message || 'Draft saved successfully',
          data: apiResponse.data,
        };
      }

      return apiResponse;
    },

    /**
     * Submit recommendation for application
     * Type-safe: Path parameter and body validated
     */
    submitRecommendation: async (
      applicationId: number,
      reviewStage: string,
      recommendation: string,
      selectedAwards?: string[]
    ): Promise<ApiResponse<Application>> => {
      const response = await typedClient.raw.POST('/api/v1/applications/{id}/review', {
        params: { path: { id: applicationId } },
        body: {
          id: applicationId,
          review_stage: reviewStage,
          recommendation,
          ...(selectedAwards ? { selected_awards: selectedAwards } : {}),
        } as never,
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Get audit trail for application
     * Type-safe: Path and query parameters validated
     */
    getAuditTrail: async (
      applicationId: number,
      limit: number = 50,
      offset: number = 0,
      actionFilter?: string
    ): Promise<ApiResponse<AuditLog[]>> => {
      const response = await typedClient.raw.GET('/api/v1/applications/{id}/audit-trail', {
        params: {
          path: { id: applicationId },
          query: {
            limit,
            offset,
            ...(actionFilter ? { action_filter: actionFilter } : {}),
          },
        },
      });
      return toApiResponse<AuditLog[]>(response);
    },

    /**
     * Create document request for application (staff only)
     * Type-safe: Path parameter and body validated
     */
    createDocumentRequest: async (
      applicationId: number,
      requestData: {
        requested_documents: string[];
        reason: string;
        notes?: string;
      }
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/applications/{application_id}/document-requests',
        {
          params: { path: { application_id: applicationId } },
          body: requestData,
        }
      );
      return toApiResponse<unknown>(response);
    },

    /**
     * List document requests for application (staff only)
     * Type-safe: Path and query parameters validated
     */
    listDocumentRequests: async (
      applicationId: number,
      status?: string
    ): Promise<ApiResponse<unknown[]>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/applications/{application_id}/document-requests',
        {
          params: {
            path: { application_id: applicationId },
            query: status ? { status } : undefined,
          },
        }
      );
      return toApiResponse<unknown[]>(response);
    },

    /**
     * 取得學生儀表板統計資料 (學生專用)
     * GET /api/v1/applications/dashboard/stats
     */
    getStudentDashboardStats: async (): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/applications/dashboard/stats',
        {}
      );
      return toApiResponse(response);
    },

    /**
     * 取得申請的學生相關資料
     * GET /api/v1/applications/{id}/student-data
     */
    getStudentData: async (id: number): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/applications/{id}/student-data',
        { params: { path: { id } } }
      );
      return toApiResponse(response);
    },

    /**
     * 更新申請的學生相關資料 (銀行帳號、指導教授資訊等)
     * PUT /api/v1/applications/{id}/student-data
     */
    updateStudentData: async (
      id: number,
      data: Record<string, unknown>
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.PUT(
        '/api/v1/applications/{id}/student-data',
        {
          params: { path: { id } },
          body: data as never,
        }
      );
      return toApiResponse(response);
    },
  };
}
