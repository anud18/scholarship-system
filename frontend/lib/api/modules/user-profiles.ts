/**
 * User Profiles API Module
 *
 * Manages user profile data including:
 * - Personal information
 * - Bank account details
 * - Advisor information
 * - Profile history
 * - Admin profile management
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

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
};

type AdvisorInfoUpdate = {
  advisor_name?: string;
  advisor_email?: string;
};

type ProfileHistory = {
  id: number;
  user_id: number;
  changed_at: string;
  changed_by: number;
  changes: Record<string, any>;
};

export function createUserProfilesApi(client: ApiClient) {
  return {
    /**
     * Get complete user profile (read-only + editable data)
     */
    getMyProfile: async (): Promise<ApiResponse<CompleteUserProfile>> => {
      return client.request("/user-profiles/me");
    },

    /**
     * Create user profile
     */
    createProfile: async (
      profileData: UserProfileUpdate
    ): Promise<ApiResponse<UserProfile>> => {
      return client.request("/user-profiles/me", {
        method: "POST",
        body: JSON.stringify(profileData),
      });
    },

    /**
     * Update complete profile
     */
    updateProfile: async (
      profileData: UserProfileUpdate
    ): Promise<ApiResponse<UserProfile>> => {
      return client.request("/user-profiles/me", {
        method: "PUT",
        body: JSON.stringify(profileData),
      });
    },

    /**
     * Update bank account information
     */
    updateBankInfo: async (
      bankData: BankInfoUpdate
    ): Promise<ApiResponse<any>> => {
      return client.request("/user-profiles/me/bank-info", {
        method: "PUT",
        body: JSON.stringify(bankData),
      });
    },

    /**
     * Update advisor information
     */
    updateAdvisorInfo: async (
      advisorData: AdvisorInfoUpdate
    ): Promise<ApiResponse<any>> => {
      return client.request("/user-profiles/me/advisor-info", {
        method: "PUT",
        body: JSON.stringify(advisorData),
      });
    },

    /**
     * Upload bank document (base64)
     */
    uploadBankDocument: async (
      photoData: string,
      filename: string,
      contentType: string
    ): Promise<ApiResponse<{ document_url: string }>> => {
      return client.request("/user-profiles/me/bank-document", {
        method: "POST",
        body: JSON.stringify({
          photo_data: photoData,
          filename,
          content_type: contentType,
        }),
      });
    },

    /**
     * Upload bank document (file)
     */
    uploadBankDocumentFile: async (
      file: File
    ): Promise<ApiResponse<{ document_url: string }>> => {
      const formData = new FormData();
      formData.append("file", file);

      return client.request("/user-profiles/me/bank-document/file", {
        method: "POST",
        body: formData,
      });
    },

    /**
     * Delete bank document
     */
    deleteBankDocument: async (): Promise<ApiResponse<any>> => {
      return client.request("/user-profiles/me/bank-document", {
        method: "DELETE",
      });
    },

    /**
     * Get profile change history
     */
    getHistory: async (): Promise<ApiResponse<ProfileHistory[]>> => {
      return client.request("/user-profiles/me/history");
    },

    /**
     * Delete entire profile
     */
    deleteProfile: async (): Promise<ApiResponse<any>> => {
      return client.request("/user-profiles/me", {
        method: "DELETE",
      });
    },

    /**
     * Admin endpoints for profile management
     */
    admin: {
      /**
       * Get incomplete profiles
       */
      getIncompleteProfiles: async (): Promise<ApiResponse<any>> => {
        return client.request("/user-profiles/admin/incomplete");
      },

      /**
       * Get user profile by ID
       */
      getUserProfile: async (
        userId: number
      ): Promise<ApiResponse<CompleteUserProfile>> => {
        return client.request(`/user-profiles/admin/${userId}`);
      },

      /**
       * Get user profile history by ID
       */
      getUserHistory: async (
        userId: number
      ): Promise<ApiResponse<ProfileHistory[]>> => {
        return client.request(`/user-profiles/admin/${userId}/history`);
      },
    },
  };
}
