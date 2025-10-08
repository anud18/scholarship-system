/**
 * Applications API Module
 *
 * Handles scholarship application operations including:
 * - Application CRUD operations
 * - File uploads and document management
 * - Application status management
 * - Review and recommendation workflows
 */

import type { ApiClient } from '../client';
import type { ApiResponse, Application, ApplicationFile } from '../../api';

// Import types from main api.ts for now
type ApplicationCreate = {
  scholarship_type: string;
  personal_statement?: string;
  expected_graduation_date?: string;
  research_topic?: string;
  gpa?: number;
  [key: string]: any;
};

export function createApplicationsApi(client: ApiClient) {
  return {
    /**
     * Get current user's applications with optional status filter
     */
    getMyApplications: async (
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = status ? `?status=${encodeURIComponent(status)}` : "";
      return client.request(`/applications${params}`);
    },

    /**
     * Get applications for college review
     */
    getCollegeReview: async (
      status?: string,
      scholarshipType?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams();
      if (status) params.append("status", status);
      if (scholarshipType) params.append("scholarship_type", scholarshipType);

      const queryString = params.toString();
      return client.request(
        `/applications/college/review${queryString ? `?${queryString}` : ""}`
      );
    },

    /**
     * Get applications by scholarship type
     */
    getByScholarshipType: async (
      scholarshipType: string,
      status?: string
    ): Promise<ApiResponse<Application[]>> => {
      const params = new URLSearchParams();
      params.append("scholarship_type", scholarshipType);
      if (status) params.append("status", status);

      const queryString = params.toString();
      return client.request(
        `/applications/review/list${queryString ? `?${queryString}` : ""}`
      );
    },

    /**
     * Create new application
     */
    createApplication: async (
      applicationData: ApplicationCreate,
      isDraft: boolean = false
    ): Promise<ApiResponse<Application>> => {
      const url = isDraft ? "/applications?is_draft=true" : "/applications";
      return client.request(url, {
        method: "POST",
        body: JSON.stringify(applicationData),
      });
    },

    /**
     * Get application by ID
     */
    getApplicationById: async (
      id: number
    ): Promise<ApiResponse<Application>> => {
      return client.request(`/applications/${id}`);
    },

    /**
     * Update application
     */
    updateApplication: async (
      id: number,
      applicationData: Partial<ApplicationCreate>
    ): Promise<ApiResponse<Application>> => {
      return client.request(`/applications/${id}`, {
        method: "PUT",
        body: JSON.stringify(applicationData),
      });
    },

    /**
     * Update application status
     */
    updateStatus: async (
      id: number,
      statusData: { status: string; comments?: string }
    ): Promise<ApiResponse<Application>> => {
      return client.request(`/applications/${id}/status`, {
        method: "PATCH",
        body: JSON.stringify(statusData),
      });
    },

    /**
     * Upload file to application
     */
    uploadFile: async (
      applicationId: number,
      file: File,
      fileType: string
    ): Promise<ApiResponse<any>> => {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("file_type", fileType);

      return client.request(`/applications/${applicationId}/files`, {
        method: "POST",
        body: formData,
      });
    },

    /**
     * Submit application for review
     */
    submitApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      return client.request(`/applications/${applicationId}/submit`, {
        method: "POST",
      });
    },

    /**
     * Delete application
     */
    deleteApplication: async (
      applicationId: number
    ): Promise<ApiResponse<{ success: boolean; message: string }>> => {
      return client.request(`/applications/${applicationId}`, {
        method: "DELETE",
      });
    },

    /**
     * Withdraw application
     */
    withdrawApplication: async (
      applicationId: number
    ): Promise<ApiResponse<Application>> => {
      return client.request(`/applications/${applicationId}/withdraw`, {
        method: "POST",
      });
    },

    /**
     * Upload document to application
     */
    uploadDocument: async (
      applicationId: number,
      file: File,
      fileType: string = "other"
    ): Promise<ApiResponse<any>> => {
      const formData = new FormData();
      formData.append("file", file);

      return client.request(
        `/applications/${applicationId}/files/upload?file_type=${encodeURIComponent(fileType)}`,
        {
          method: "POST",
          body: formData,
          headers: {}, // Remove Content-Type to let browser set it for FormData
        }
      );
    },

    /**
     * Get application files
     */
    getApplicationFiles: async (
      applicationId: number
    ): Promise<ApiResponse<ApplicationFile[]>> => {
      return client.request(`/applications/${applicationId}/files`);
    },

    /**
     * Save application as draft
     */
    saveApplicationDraft: async (
      applicationData: ApplicationCreate
    ): Promise<ApiResponse<Application>> => {
      const response = await client.request("/applications?is_draft=true", {
        method: "POST",
        body: JSON.stringify(applicationData),
      });

      // Handle direct Application response vs wrapped ApiResponse
      if (
        response &&
        typeof response === "object" &&
        "id" in response &&
        !("success" in response)
      ) {
        // Direct Application object - wrap it in ApiResponse format
        return {
          success: true,
          message: "Draft saved successfully",
          data: response as unknown as Application,
        };
      }

      // Already in ApiResponse format
      return response as ApiResponse<Application>;
    },

    /**
     * Submit recommendation for application
     */
    submitRecommendation: async (
      applicationId: number,
      reviewStage: string,
      recommendation: string,
      selectedAwards?: string[]
    ): Promise<ApiResponse<Application>> => {
      return client.request(`/applications/${applicationId}/review`, {
        method: "POST",
        body: JSON.stringify({
          application_id: applicationId,
          review_stage: reviewStage,
          recommendation,
          ...(selectedAwards ? { selected_awards: selectedAwards } : {}),
        }),
      });
    },
  };
}
