/**
 * Application Fields API Module
 *
 * Manages dynamic form fields and documents for scholarship applications:
 * - Form configuration
 * - Custom field definitions
 * - Document requirements
 * - Example file uploads
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

type ScholarshipFormConfig = {
  scholarship_type: string;
  fields: any[];
  documents: any[];
};

type FormConfigSaveRequest = {
  fields: any[];
  documents: any[];
};

type ApplicationField = {
  id: number;
  scholarship_type: string;
  field_name: string;
  field_label: string;
  field_type: string;
  required: boolean;
  display_order: number;
  is_active: boolean;
  options?: any;
};

type ApplicationFieldCreate = Omit<ApplicationField, 'id'>;
type ApplicationFieldUpdate = Partial<ApplicationFieldCreate>;

type ApplicationDocument = {
  id: number;
  scholarship_type: string;
  document_name: string;
  document_label: string;
  required: boolean;
  display_order: number;
  is_active: boolean;
  example_file_path?: string;
  description?: string;
};

type ApplicationDocumentCreate = Omit<ApplicationDocument, 'id'>;
type ApplicationDocumentUpdate = Partial<ApplicationDocumentCreate>;

export function createApplicationFieldsApi(client: ApiClient) {
  return {
    /**
     * Get form configuration for a scholarship type
     */
    getFormConfig: async (
      scholarshipType: string,
      includeInactive: boolean = false
    ): Promise<ApiResponse<ScholarshipFormConfig>> => {
      return client.request(
        `/application-fields/form-config/${scholarshipType}?include_inactive=${includeInactive}`
      );
    },

    /**
     * Save form configuration for a scholarship type
     */
    saveFormConfig: async (
      scholarshipType: string,
      config: FormConfigSaveRequest
    ): Promise<ApiResponse<ScholarshipFormConfig>> => {
      return client.request(
        `/application-fields/form-config/${scholarshipType}`,
        {
          method: "POST",
          body: JSON.stringify(config),
        }
      );
    },

    /**
     * Get all fields for a scholarship type
     */
    getFields: async (
      scholarshipType: string
    ): Promise<ApiResponse<ApplicationField[]>> => {
      return client.request(`/application-fields/fields/${scholarshipType}`);
    },

    /**
     * Create a new field
     */
    createField: async (
      fieldData: ApplicationFieldCreate
    ): Promise<ApiResponse<ApplicationField>> => {
      return client.request("/application-fields/fields", {
        method: "POST",
        body: JSON.stringify(fieldData),
      });
    },

    /**
     * Update an existing field
     */
    updateField: async (
      fieldId: number,
      fieldData: ApplicationFieldUpdate
    ): Promise<ApiResponse<ApplicationField>> => {
      return client.request(`/application-fields/fields/${fieldId}`, {
        method: "PUT",
        body: JSON.stringify(fieldData),
      });
    },

    /**
     * Delete a field
     */
    deleteField: async (fieldId: number): Promise<ApiResponse<boolean>> => {
      return client.request(`/application-fields/fields/${fieldId}`, {
        method: "DELETE",
      });
    },

    /**
     * Get all documents for a scholarship type
     */
    getDocuments: async (
      scholarshipType: string
    ): Promise<ApiResponse<ApplicationDocument[]>> => {
      return client.request(`/application-fields/documents/${scholarshipType}`);
    },

    /**
     * Create a new document requirement
     */
    createDocument: async (
      documentData: ApplicationDocumentCreate
    ): Promise<ApiResponse<ApplicationDocument>> => {
      return client.request("/application-fields/documents", {
        method: "POST",
        body: JSON.stringify(documentData),
      });
    },

    /**
     * Update an existing document requirement
     */
    updateDocument: async (
      documentId: number,
      documentData: ApplicationDocumentUpdate
    ): Promise<ApiResponse<ApplicationDocument>> => {
      return client.request(`/application-fields/documents/${documentId}`, {
        method: "PUT",
        body: JSON.stringify(documentData),
      });
    },

    /**
     * Delete a document requirement
     */
    deleteDocument: async (documentId: number): Promise<ApiResponse<boolean>> => {
      return client.request(`/application-fields/documents/${documentId}`, {
        method: "DELETE",
      });
    },

    /**
     * Upload example file for a document
     */
    uploadDocumentExample: async (
      documentId: number,
      file: File
    ): Promise<any> => {
      const formData = new FormData();
      formData.append("file", file);

      const token = client.getToken();
      const baseURL =
        typeof window !== "undefined"
          ? ""
          : process.env.INTERNAL_API_URL || "http://localhost:8000";

      const response = await fetch(
        `${baseURL}/api/v1/application-fields/documents/${documentId}/upload-example`,
        {
          method: "POST",
          body: formData,
          credentials: "include",
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "Failed to upload example file");
      }

      return response.json();
    },

    /**
     * Delete example file for a document
     */
    deleteDocumentExample: async (
      documentId: number
    ): Promise<ApiResponse<boolean>> => {
      return client.request(
        `/application-fields/documents/${documentId}/example`,
        {
          method: "DELETE",
        }
      );
    },
  };
}
