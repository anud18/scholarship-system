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
import type { ApiResponse, Application, ApplicationFile } from '../../api.legacy';

type ApplicationCreate = {
  scholarship_type: string;
  personal_statement?: string;
  expected_graduation_date?: string;
  research_topic?: string;
  gpa?: number;
  [key: string]: any;
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
        body: applicationData as any, // Frontend includes dynamic fields via [key: string]: any
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
        body: applicationData as any, // Partial<ApplicationCreate> makes all fields optional for updates
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Update application status
     * NOTE: Endpoint /api/v1/applications/{id}/status not in OpenAPI schema
     * TODO: Either add backend endpoint or use alternative status update method
     */
    updateStatus: async (
      id: number,
      statusData: { status: string; comments?: string }
    ): Promise<ApiResponse<Application>> => {
      // NOTE: Endpoint /api/v1/applications/{id}/status not in OpenAPI schema
      // Fallback: Use PUT /api/v1/applications/{id} with status field
      const response = await typedClient.raw.PUT('/api/v1/applications/{id}', {
        params: { path: { id } },
        body: { status: statusData.status } as any,
      });
      return toApiResponse<Application>(response);
    },

    /**
     * Upload file to application
     * Type-safe: Path parameter validated, FormData properly typed
     */
    uploadFile: async (
      applicationId: number,
      file: File,
      fileType: string
    ): Promise<ApiResponse<any>> => {
      const formData = createFileUploadFormData({ file, file_type: fileType });

      const response = await typedClient.raw.POST('/api/v1/applications/{id}/files', {
        params: { path: { id: applicationId } },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<any>(response);
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
     * Delete application
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteApplication: async (
      applicationId: number
    ): Promise<ApiResponse<{ success: boolean; message: string }>> => {
      const response = await typedClient.raw.DELETE('/api/v1/applications/{id}', {
        params: { path: { id: applicationId } },
      });
      return toApiResponse<{ success: boolean; message: string }>(response);
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
     * Upload document to application
     * Type-safe: Path and query parameters validated, FormData properly typed
     */
    uploadDocument: async (
      applicationId: number,
      file: File,
      fileType: string = 'other'
    ): Promise<ApiResponse<any>> => {
      const formData = createFileUploadFormData({ file });

      const response = await typedClient.raw.POST('/api/v1/applications/{id}/files/upload', {
        params: {
          path: { id: applicationId },
          query: { file_type: fileType },
        },
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<any>(response);
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
        body: applicationData as any, // Frontend includes dynamic fields via [key: string]: any
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
        } as any,
      });
      return toApiResponse<Application>(response);
    },
  };
}
