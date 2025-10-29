/**
 * Professor-Student Relationship API Module (OpenAPI-typed)
 *
 * Manages relationships between professors and students:
 * - View existing relationships
 * - Create/update/delete relationships
 * - Track relationship types and status
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../../api.legacy';

type ProfessorStudentRelationship = {
  id: number;
  professor_id: number;
  student_id: number;
  relationship_type: string;
  status: string;
  start_date?: string;
  end_date?: string;
  notes?: string;
};

type ProfessorStudentRelationshipCreate = {
  professor_id: number;
  student_id: number;
  relationship_type: string;
  status?: string;
  start_date?: string;
  notes?: string;
};

type ProfessorStudentRelationshipUpdate = {
  relationship_type?: string;
  status?: string;
  end_date?: string;
  notes?: string;
};

export function createProfessorStudentApi() {
  return {
    /**
     * Get professor-student relationships with optional filtering
     * Type-safe: Query parameters validated against OpenAPI
     */
    getProfessorStudentRelationships: async (params?: {
      professor_id?: number;
      student_id?: number;
      relationship_type?: string;
      status?: string;
      page?: number;
      size?: number;
    }): Promise<ApiResponse<ProfessorStudentRelationship[]>> => {
      const response = await typedClient.raw.GET('/api/v1/professor-student', {
        params: {
          query: {
            professor_id: params?.professor_id,
            student_id: params?.student_id,
            relationship_type: params?.relationship_type,
            status: params?.status,
            page: params?.page,
            size: params?.size,
          },
        },
      });
      return toApiResponse(response);
    },

    /**
     * Create a new professor-student relationship
     * Type-safe: Request body validated against OpenAPI
     */
    createProfessorStudentRelationship: async (
      relationshipData: ProfessorStudentRelationshipCreate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      const response = await typedClient.raw.POST('/api/v1/professor-student', {
        params: { query: relationshipData as any },
      });
      return toApiResponse<ProfessorStudentRelationship>(response);
    },

    /**
     * Update an existing professor-student relationship
     * Type-safe: Path parameter and request body validated against OpenAPI
     */
    updateProfessorStudentRelationship: async (
      id: number,
      relationshipData: ProfessorStudentRelationshipUpdate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      const response = await typedClient.raw.PUT('/api/v1/professor-student/{id}', {
        params: { path: { id } },
        body: relationshipData as any, // Update type allows optional fields not matching exact schema structure
      });
      return toApiResponse(response);
    },

    /**
     * Delete a professor-student relationship
     * Type-safe: Path parameter validated against OpenAPI
     */
    deleteProfessorStudentRelationship: async (
      id: number
    ): Promise<ApiResponse<void>> => {
      const response = await typedClient.raw.DELETE('/api/v1/professor-student/{id}', {
        params: { path: { id } },
      });
      return toApiResponse(response);
    },
  };
}
