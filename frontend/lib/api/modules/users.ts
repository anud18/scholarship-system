/**
 * Users API Module (OpenAPI-typed)
 *
 * Handles user-related operations including:
 * - Profile management
 * - Student information
 * - User CRUD operations (admin)
 * - User statistics
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse, User, Student, StudentInfoResponse } from '../../api.legacy';

// Import types from main api.ts for now
// TODO: Move these to a shared types file
type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
};

type UserListResponse = {
  id: number;
  nycu_id: string;
  email: string;
  name: string;
  role: string;
  user_type?: string;
  status?: string;
  dept_code?: string;
  dept_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
};

type UserResponse = {
  id: number;
  nycu_id: string;
  email: string;
  name: string;
  role: string;
  user_type?: string;
  status?: string;
  dept_code?: string;
  dept_name?: string;
  comment?: string;
  last_login_at?: string;
  created_at: string;
  updated_at: string;
  raw_data?: any;
};

type UserCreate = {
  nycu_id: string;
  email: string;
  name: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  user_type?: "student" | "employee";
  status?: "在學" | "畢業" | "在職" | "退休";
  dept_code?: string;
  dept_name?: string;
  college_code?: string;
  comment?: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
    [key: string]: any;
  };
  // Backward compatibility fields
  username?: string;
  full_name?: string;
  chinese_name?: string;
  english_name?: string;
};

type UserUpdate = Partial<UserCreate>;

type UserStats = {
  total_users: number;
  role_distribution: Record<string, number>;
  user_type_distribution: Record<string, number>;
  status_distribution: Record<string, number>;
  recent_registrations: number;
};

export function createUsersApi() {
  return {
    /**
     * Get current user's profile
     * Type-safe: Response type inferred from OpenAPI
     */
    getProfile: async (): Promise<ApiResponse<User>> => {
      const response = await typedClient.raw.GET('/api/v1/users/me');
      return toApiResponse<User>(response);
    },

    /**
     * Update current user's profile
     * Type-safe: Request body validated against OpenAPI
     */
    updateProfile: async (
      userData: Partial<User>
    ): Promise<ApiResponse<User>> => {
      const response = await typedClient.raw.PUT('/api/v1/users/me', {
        body: userData,
      });
      return toApiResponse<User>(response);
    },

    /**
     * Get current student's detailed information
     * Type-safe: Response type inferred from OpenAPI
     */
    getStudentInfo: async (): Promise<ApiResponse<StudentInfoResponse>> => {
      const response = await typedClient.raw.GET('/api/v1/users/student-info');
      return toApiResponse<StudentInfoResponse>(response);
    },

    /**
     * Update current student's information
     * Type-safe: Request body validated against OpenAPI
     */
    updateStudentInfo: async (
      studentData: Partial<Student>
    ): Promise<ApiResponse<Student>> => {
      const response = await typedClient.raw.PUT('/api/v1/users/student-info', {
        body: studentData as any, // Partial<Student> makes all fields optional for PATCH updates
      });
      return toApiResponse<Student>(response);
    },

    /**
     * Get all users with pagination and filters (admin)
     * Type-safe: Query parameters validated against OpenAPI
     */
    getAll: async (params?: {
      page?: number;
      size?: number;
      role?: string;
      search?: string;
    }) => {
      const response = await typedClient.raw.GET('/api/v1/users', {
        params: { query: params },
      });
      return toApiResponse<PaginatedResponse<UserListResponse>>(response);
    },

    /**
     * Get user by ID (admin)
     * Type-safe: Path parameter validated against OpenAPI
     */
    getById: async (userId: number) => {
      const response = await typedClient.raw.GET('/api/v1/users/{id}', {
        params: { path: { id: userId } },
      });
      return toApiResponse<UserResponse>(response);
    },

    /**
     * Create new user (admin)
     * Type-safe: Request body validated against OpenAPI
     */
    create: async (userData: UserCreate) => {
      const response = await typedClient.raw.POST('/api/v1/users', {
        body: userData as any, // TypeScript undefined vs Python None/null handling difference
      });
      return toApiResponse<UserResponse>(response);
    },

    /**
     * Update user (admin)
     * Type-safe: Request body and path parameter validated
     */
    update: async (userId: number, userData: UserUpdate) => {
      const response = await typedClient.raw.PUT('/api/v1/users/{id}', {
        params: { path: { id: userId } },
        body: userData,
      });
      return toApiResponse<UserResponse>(response);
    },

    /**
     * Delete user - hard delete (admin)
     * Type-safe: Path parameter validated against OpenAPI
     */
    delete: async (userId: number) => {
      const response = await typedClient.raw.DELETE('/api/v1/users/{id}', {
        params: { path: { id: userId } },
      });
      return toApiResponse<{
        success: boolean;
        message: string;
        data: { user_id: number };
      }>(response);
    },

    /**
     * Reset user password (not supported in SSO model)
     * Type-safe: Path parameter validated against OpenAPI
     */
    resetPassword: async (userId: number) => {
      const response = await typedClient.raw.POST('/api/v1/users/{id}/reset-password', {
        params: { path: { id: userId } },
      });
      return toApiResponse<{
        success: boolean;
        message: string;
        data: { user_id: number };
      }>(response);
    },

    /**
     * Get user statistics overview (admin)
     * Type-safe: Response type inferred from OpenAPI
     */
    getStats: async () => {
      const response = await typedClient.raw.GET('/api/v1/users/stats/overview');
      return toApiResponse<UserStats>(response);
    },
  };
}
