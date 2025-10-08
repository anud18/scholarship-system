/**
 * Professor-Student Relationship API Module
 *
 * Manages relationships between professors and students:
 * - View existing relationships
 * - Create/update/delete relationships
 * - Track relationship types and status
 */

import type { ApiClient } from '../client';
import type { ApiResponse } from '../../api';

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

export function createProfessorStudentApi(client: ApiClient) {
  return {
    /**
     * Get professor-student relationships with optional filtering
     */
    getProfessorStudentRelationships: async (params?: {
      professor_id?: number;
      student_id?: number;
      relationship_type?: string;
      status?: string;
      page?: number;
      size?: number;
    }): Promise<ApiResponse<ProfessorStudentRelationship[]>> => {
      const queryParams = new URLSearchParams();
      if (params) {
        Object.entries(params).forEach(([key, value]) => {
          if (value !== undefined) {
            queryParams.append(key, value.toString());
          }
        });
      }
      const query = queryParams.toString();
      return client.request(`/professor-student${query ? `?${query}` : ""}`);
    },

    /**
     * Create a new professor-student relationship
     */
    createProfessorStudentRelationship: async (
      relationshipData: ProfessorStudentRelationshipCreate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      return client.request("/professor-student", {
        method: "POST",
        body: JSON.stringify(relationshipData),
      });
    },

    /**
     * Update an existing professor-student relationship
     */
    updateProfessorStudentRelationship: async (
      id: number,
      relationshipData: ProfessorStudentRelationshipUpdate
    ): Promise<ApiResponse<ProfessorStudentRelationship>> => {
      return client.request(`/professor-student/${id}`, {
        method: "PUT",
        body: JSON.stringify(relationshipData),
      });
    },

    /**
     * Delete a professor-student relationship
     */
    deleteProfessorStudentRelationship: async (
      id: number
    ): Promise<ApiResponse<void>> => {
      return client.request(`/professor-student/${id}`, {
        method: "DELETE",
      });
    },
  };
}
