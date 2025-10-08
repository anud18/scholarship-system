/**
 * Authentication API Module
 *
 * Handles user authentication including:
 * - Login/logout
 * - User registration
 * - Token management
 * - Mock SSO for development
 */

import type { ApiClient } from '../client';
import type { ApiResponse, User } from '../../api'; // Import from main api.ts for now

export function createAuthApi(client: ApiClient) {
  return {
    /**
     * Login with username and password
     */
    login: async (
      username: string,
      password: string
    ): Promise<
      ApiResponse<{
        access_token: string;
        token_type: string;
        expires_in: number;
        user: User;
      }>
    > => {
      const response = await client.request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });

      // Store token after successful login
      if (response.success && response.data?.access_token) {
        client.setToken(response.data.access_token);
      }

      return response;
    },

    /**
     * Logout current user
     */
    logout: async (): Promise<ApiResponse<void>> => {
      // Optional: call backend logout endpoint if needed
      // await client.request("/auth/logout", { method: "POST" });

      // Clear local token
      client.clearToken();

      return {
        success: true,
        message: "Logged out successfully",
        data: undefined,
      };
    },

    /**
     * Register a new user
     */
    register: async (userData: {
      username: string;
      email: string;
      password: string;
      full_name: string;
    }): Promise<ApiResponse<User>> => {
      return client.request("/auth/register", {
        method: "POST",
        body: JSON.stringify(userData),
      });
    },

    /**
     * Get current authenticated user
     */
    getCurrentUser: async (): Promise<ApiResponse<User>> => {
      return client.request("/auth/me");
    },

    /**
     * Refresh authentication token
     */
    refreshToken: async (): Promise<
      ApiResponse<{ access_token: string; token_type: string }>
    > => {
      const response = await client.request("/auth/refresh", {
        method: "POST",
      });

      // Update token after successful refresh
      if (response.success && response.data?.access_token) {
        client.setToken(response.data.access_token);
      }

      return response;
    },

    /**
     * Get list of mock SSO users (development only)
     */
    getMockUsers: async (): Promise<ApiResponse<any[]>> => {
      return client.request("/auth/mock-sso/users");
    },

    /**
     * Login using mock SSO (development only)
     */
    mockSSOLogin: async (
      nycu_id: string
    ): Promise<
      ApiResponse<{
        access_token: string;
        token_type: string;
        expires_in: number;
        user: User;
      }>
    > => {
      const response = await client.request("/auth/mock-sso/login", {
        method: "POST",
        body: JSON.stringify({ nycu_id }),
      });

      // Store token after successful mock login
      if (response.success && response.data?.access_token) {
        client.setToken(response.data.access_token);
      }

      return response;
    },
  };
}
