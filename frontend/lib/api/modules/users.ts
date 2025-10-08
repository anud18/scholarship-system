/**
 * Users API Module
 *
 * Handles user-related operations including:
 * - Profile management
 * - Student information
 * - User CRUD operations (admin)
 * - User statistics
 */

import type { ApiClient } from '../client';
import type { ApiResponse, User, Student, StudentInfoResponse } from '../../api';

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
  comment?: string;
};

type UserUpdate = Partial<UserCreate>;

type UserStats = {
  total_users: number;
  by_role: Record<string, number>;
  by_user_type: Record<string, number>;
  by_status: Record<string, number>;
  recent_registrations: number;
};

export function createUsersApi(client: ApiClient) {
  return {
    /**
     * Get current user's profile
     */
    getProfile: async (): Promise<ApiResponse<User>> => {
      return client.request("/users/me");
    },

    /**
     * Update current user's profile
     */
    updateProfile: async (
      userData: Partial<User>
    ): Promise<ApiResponse<User>> => {
      return client.request("/users/me", {
        method: "PUT",
        body: JSON.stringify(userData),
      });
    },

    /**
     * Get current student's detailed information
     */
    getStudentInfo: async (): Promise<ApiResponse<StudentInfoResponse>> => {
      return client.request("/users/student-info");
    },

    /**
     * Update current student's information
     */
    updateStudentInfo: async (
      studentData: Partial<Student>
    ): Promise<ApiResponse<Student>> => {
      return client.request("/users/student-info", {
        method: "PUT",
        body: JSON.stringify(studentData),
      });
    },

    /**
     * Get all users with pagination and filters (admin)
     */
    getAll: (params?: {
      page?: number;
      size?: number;
      role?: string;
      search?: string;
    }) =>
      client.request<PaginatedResponse<UserListResponse>>("/users", {
        method: "GET",
        params,
      }),

    /**
     * Get user by ID (admin)
     */
    getById: (userId: number) =>
      client.request<UserResponse>(`/users/${userId}`, {
        method: "GET",
      }),

    /**
     * Create new user (admin)
     */
    create: (userData: UserCreate) =>
      client.request<UserResponse>("/users", {
        method: "POST",
        body: JSON.stringify(userData),
      }),

    /**
     * Update user (admin)
     */
    update: (userId: number, userData: UserUpdate) =>
      client.request<UserResponse>(`/users/${userId}`, {
        method: "PUT",
        body: JSON.stringify(userData),
      }),

    /**
     * Delete user - hard delete (admin)
     */
    delete: (userId: number) =>
      client.request<{
        success: boolean;
        message: string;
        data: { user_id: number };
      }>(`/users/${userId}`, {
        method: "DELETE",
      }),

    /**
     * Reset user password (not supported in SSO model)
     */
    resetPassword: (userId: number) =>
      client.request<{
        success: boolean;
        message: string;
        data: { user_id: number };
      }>(`/users/${userId}/reset-password`, {
        method: "POST",
      }),

    /**
     * Get user statistics overview (admin)
     */
    getStats: () =>
      client.request<UserStats>("/users/stats/overview", {
        method: "GET",
      }),
  };
}
