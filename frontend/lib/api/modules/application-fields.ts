/**
 * Application Fields API Module (OpenAPI-typed)
 *
 * Manages dynamic form fields and documents for scholarship applications:
 * - Form configuration
 * - Custom field definitions
 * - Document requirements
 * - Example file uploads
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

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

export function createApplicationFieldsApi() {
  return {
    /**
     * Get form configuration for a scholarship type
     * Type-safe: Path parameter and query parameters validated against OpenAPI
     */
    getFormConfig: async (
      scholarshipType: string,
      includeInactive: boolean = false
    ): Promise<ApiResponse<ScholarshipFormConfig>> => {
      const response = await typedClient.raw.GET('/api/v1/application-fields/form-config/{scholarship_type}', {
        params: {
          path: { scholarship_type: scholarshipType },
          query: { include_inactive: includeInactive },
        },
      });
      return toApiResponse<ScholarshipFormConfig>(response);
    },

    /**
     * Save form configuration for a scholarship type
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    saveFormConfig: async (
      scholarshipType: string,
      config: FormConfigSaveRequest
    ): Promise<ApiResponse<ScholarshipFormConfig>> => {
      const response = await typedClient.raw.POST('/api/v1/application-fields/form-config/{scholarship_type}', {
        params: { path: { scholarship_type: scholarshipType } },
        body: config,
      });
      return toApiResponse<ScholarshipFormConfig>(response);
    },

    /**
     * Get all fields for a scholarship type
     * Type-safe: Path parameter validated against OpenAPI
     */
    getFields: async (
      scholarshipType: string
    ): Promise<ApiResponse<ApplicationField[]>> => {
      const response = await typedClient.raw.GET('/api/v1/application-fields/fields/{scholarship_type}', {
        params: { path: { scholarship_type: scholarshipType } },
      });
      return toApiResponse<ApplicationField[]>(response);
    },

    /**
     * Create a new field
     * Type-safe: Request body validated against OpenAPI
     */
    createField: async (
      fieldData: ApplicationFieldCreate
    ): Promise<ApiResponse<ApplicationField>> => {
      const response = await typedClient.raw.POST('/api/v1/application-fields/fields', {
        body: fieldData as any, // Frontend includes additional optional fields not in OpenAPI schema
      });
      return toApiResponse<ApplicationField>(response);
    },

    /**
     * Update an existing field
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateField: async (
      fieldId: number,
      fieldData: ApplicationFieldUpdate
    ): Promise<ApiResponse<ApplicationField>> => {
      const response = await typedClient.raw.PUT('/api/v1/application-fields/fields/{field_id}', {
        params: { path: { field_id: fieldId } },
        body: fieldData,
      });
      return toApiResponse<ApplicationField>(response);
    },

    /**
     * Delete a field
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteField: async (fieldId: number): Promise<ApiResponse<boolean>> => {
      const response = await typedClient.raw.DELETE('/api/v1/application-fields/fields/{field_id}', {
        params: { path: { field_id: fieldId } },
      });
      return toApiResponse<boolean>(response);
    },

    /**
     * Get all documents for a scholarship type
     * Type-safe: Path parameter validated against OpenAPI
     */
    getDocuments: async (
      scholarshipType: string
    ): Promise<ApiResponse<ApplicationDocument[]>> => {
      const response = await typedClient.raw.GET('/api/v1/application-fields/documents/{scholarship_type}', {
        params: { path: { scholarship_type: scholarshipType } },
      });
      return toApiResponse<ApplicationDocument[]>(response);
    },

    /**
     * Create a new document requirement
     * Type-safe: Request body validated against OpenAPI
     */
    createDocument: async (
      documentData: ApplicationDocumentCreate
    ): Promise<ApiResponse<ApplicationDocument>> => {
      const response = await typedClient.raw.POST('/api/v1/application-fields/documents', {
        body: documentData as any, // Frontend includes additional optional fields not in OpenAPI schema
      });
      return toApiResponse<ApplicationDocument>(response);
    },

    /**
     * Update an existing document requirement
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateDocument: async (
      documentId: number,
      documentData: ApplicationDocumentUpdate
    ): Promise<ApiResponse<ApplicationDocument>> => {
      const response = await typedClient.raw.PUT('/api/v1/application-fields/documents/{document_id}', {
        params: { path: { document_id: documentId } },
        body: documentData,
      });
      return toApiResponse<ApplicationDocument>(response);
    },

    /**
     * Delete a document requirement
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteDocument: async (documentId: number): Promise<ApiResponse<boolean>> => {
      const response = await typedClient.raw.DELETE('/api/v1/application-fields/documents/{document_id}', {
        params: { path: { document_id: documentId } },
      });
      return toApiResponse<boolean>(response);
    },

    /**
     * Upload example file for a document
     * Type-safe: FormData upload with path parameter
     */
    uploadDocumentExample: async (
      documentId: number,
      file: File
    ): Promise<any> => {
      const formData = new FormData();
      formData.append("file", file);

      const token = typedClient.getToken();
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
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteDocumentExample: async (
      documentId: number
    ): Promise<ApiResponse<boolean>> => {
      const response = await typedClient.raw.DELETE('/api/v1/application-fields/documents/{document_id}/example', {
        params: { path: { document_id: documentId } },
      });
      return toApiResponse<boolean>(response);
    },
  };
}
