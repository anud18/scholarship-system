/**
 * User Profiles API Module (OpenAPI-typed)
 *
 * Manages user profile data including:
 * - Personal information
 * - Bank account details
 * - Advisor information
 * - Profile history
 * - Admin profile management
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import { createFileUploadFormData, type MultipartFormData } from '../form-data-helpers';
import type { ApiResponse } from '../../api.legacy';

type CompleteUserProfile = {
  user_id: number;
  nycu_id: string;
  full_name: string;
  email: string;
  phone?: string;
  bank_account?: string;
  bank_name?: string;
  bank_branch?: string;
  bank_document_url?: string;
  advisor_name?: string;
  advisor_email?: string;
  [key: string]: any;
};

type UserProfile = {
  id: number;
  user_id: number;
  [key: string]: any;
};

type UserProfileUpdate = {
  phone?: string;
  [key: string]: any;
};

type BankInfoUpdate = {
  bank_account?: string;
  bank_name?: string;
  bank_branch?: string;
  change_reason?: string;
};

type AdvisorInfoUpdate = {
  advisor_name?: string;
  advisor_email?: string;
  change_reason?: string;
};

type ProfileHistory = {
  id: number;
  user_id: number;
  changed_at: string;
  changed_by: number;
  changes: Record<string, any>;
};

export function createUserProfilesApi() {
  return {
    /**
     * Get complete user profile (read-only + editable data)
     * Type-safe: Response type inferred from OpenAPI
     */
    getMyProfile: async (): Promise<ApiResponse<CompleteUserProfile>> => {
      const response = await typedClient.raw.GET('/api/v1/user-profiles/me');
      return toApiResponse<CompleteUserProfile>(response);
    },

    /**
     * Create user profile
     * Type-safe: Request body validated against OpenAPI
     */
    createProfile: async (
      profileData: UserProfileUpdate
    ): Promise<ApiResponse<UserProfile>> => {
      const response = await typedClient.raw.POST('/api/v1/user-profiles/me', {
        body: profileData as any, // Frontend allows [key: string]: any for flexible profile updates
      });
      return toApiResponse<UserProfile>(response);
    },

    /**
     * Update complete profile
     * Type-safe: Request body validated against OpenAPI
     */
    updateProfile: async (
      profileData: UserProfileUpdate
    ): Promise<ApiResponse<UserProfile>> => {
      const response = await typedClient.raw.PUT('/api/v1/user-profiles/me', {
        body: profileData as any, // Frontend allows [key: string]: any for flexible profile updates
      });
      return toApiResponse<UserProfile>(response);
    },

    /**
     * Update bank account information
     * Type-safe: Request body validated against OpenAPI
     */
    updateBankInfo: async (
      bankData: BankInfoUpdate
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PUT('/api/v1/user-profiles/me/bank-info', {
        body: bankData as any, // Frontend allows optional fields that may not match exact schema
      });
      return toApiResponse<any>(response);
    },

    /**
     * Update advisor information
     * Type-safe: Request body validated against OpenAPI
     */
    updateAdvisorInfo: async (
      advisorData: AdvisorInfoUpdate
    ): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.PUT('/api/v1/user-profiles/me/advisor-info', {
        body: advisorData,
      });
      return toApiResponse(response);
    },

    /**
     * Upload bank document (base64)
     * Type-safe: Request body validated against OpenAPI
     */
    uploadBankDocument: async (
      photoData: string,
      filename: string,
      contentType: string
    ): Promise<ApiResponse<{ document_url: string }>> => {
      const response = await typedClient.raw.POST('/api/v1/user-profiles/me/bank-document', {
        params: {
          query: {
            photo_data: photoData,
            filename,
            content_type: contentType,
          },
        },
      });
      return toApiResponse<{ document_url: string }>(response);
    },

    /**
     * Upload bank document (file)
     * Type-safe: FormData properly typed
     */
    uploadBankDocumentFile: async (
      file: File
    ): Promise<ApiResponse<{ document_url: string }>> => {
      const formData = createFileUploadFormData({ file });

      const response = await typedClient.raw.POST('/api/v1/user-profiles/me/bank-document/file', {
        body: formData as MultipartFormData<{ file: string }>,
      });
      return toApiResponse<{ document_url: string }>(response);
    },

    /**
     * Delete bank document
     * Type-safe: Response type inferred from OpenAPI
     */
    deleteBankDocument: async (): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.DELETE('/api/v1/user-profiles/me/bank-document');
      return toApiResponse(response);
    },

    /**
     * Get profile change history
     * Type-safe: Response type inferred from OpenAPI
     */
    getHistory: async (): Promise<ApiResponse<ProfileHistory[]>> => {
      const response = await typedClient.raw.GET('/api/v1/user-profiles/me/history');
      return toApiResponse<ProfileHistory[]>(response);
    },

    /**
     * Delete entire profile
     * Type-safe: Response type inferred from OpenAPI
     */
    deleteProfile: async (): Promise<ApiResponse<any>> => {
      const response = await typedClient.raw.DELETE('/api/v1/user-profiles/me');
      return toApiResponse(response);
    },

    /**
     * Admin endpoints for profile management
     */
    admin: {
      /**
       * Get incomplete profiles
       * Type-safe: Response type inferred from OpenAPI
       */
      getIncompleteProfiles: async (): Promise<ApiResponse<any>> => {
        const response = await typedClient.raw.GET('/api/v1/user-profiles/admin/incomplete');
        return toApiResponse(response);
      },

      /**
       * Get user profile by ID
       * Type-safe: Path parameter validated against OpenAPI
       */
      getUserProfile: async (
        userId: number
      ): Promise<ApiResponse<CompleteUserProfile>> => {
        const response = await typedClient.raw.GET('/api/v1/user-profiles/admin/{user_id}', {
          params: { path: { user_id: userId } },
        });
        return toApiResponse<CompleteUserProfile>(response);
      },

      /**
       * Get user profile history by ID
       * Type-safe: Path parameter validated against OpenAPI
       */
      getUserHistory: async (
        userId: number
      ): Promise<ApiResponse<ProfileHistory[]>> => {
        const response = await typedClient.raw.GET('/api/v1/user-profiles/admin/{user_id}/history', {
          params: { path: { user_id: userId } },
        });
        return toApiResponse<ProfileHistory[]>(response);
      },
    },
  };
}
