/**
 * Authentication API Module (OpenAPI-typed)
 *
 * Handles user authentication including:
 * - Login/logout
 * - User registration
 * - Token management
 * - Mock SSO for development
 *
 * Now using openapi-fetch for full type safety from backend OpenAPI schema
 */

import { typedClient } from '../typed-client';
import { toApiResponse } from '../compat';
import type { ApiResponse } from '../types';
import type { User } from '../types';

export function createAuthApi() {
  return {
    /**
     * Login with username and password
     *
     * Type-safe: Parameters and response types inferred from OpenAPI schema
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
      const response = await typedClient.raw.POST('/api/v1/auth/login', {
        body: { username, password },
      });

      const apiResponse = toApiResponse<{
        access_token: string;
        token_type: string;
        expires_in: number;
        user: User;
      }>(response);

      // Store token after successful login
      if (apiResponse.success && apiResponse.data?.access_token) {
        typedClient.setToken(apiResponse.data.access_token);
      }

      return apiResponse;
    },

    /**
     * Logout current user
     */
    logout: async (): Promise<ApiResponse<void>> => {
      // Optional: call backend logout endpoint if needed
      // const response = await typedClient.raw.POST('/api/v1/auth/logout', {});

      // Clear local token
      typedClient.clearToken();

      return {
        success: true,
        message: 'Logged out successfully',
        data: undefined,
      };
    },

    /**
     * Register a new user
     *
     * Type-safe: Request body validated against OpenAPI schema
     */
    register: async (userData: {
      username: string;
      email: string;
      password: string;
      full_name: string;
    }): Promise<ApiResponse<User>> => {
      const response = await typedClient.raw.POST('/api/v1/auth/register', {
        body: userData as any, // TODO: Update OpenAPI schema for registration endpoint
      });

      return toApiResponse<User>(response);
    },

    /**
     * Get current authenticated user
     *
     * Type-safe: Response type inferred from OpenAPI schema
     */
    getCurrentUser: async (): Promise<ApiResponse<User>> => {
      const response = await typedClient.raw.GET('/api/v1/auth/me');
      return toApiResponse<User>(response);
    },

    /**
     * Refresh authentication token
     *
     * Type-safe: Response includes access_token and token_type
     */
    refreshToken: async (): Promise<
      ApiResponse<{ access_token: string; token_type: string }>
    > => {
      const response = await typedClient.raw.POST('/api/v1/auth/refresh', {});

      const apiResponse = toApiResponse<{ access_token: string; token_type: string }>(response);

      // Update token after successful refresh
      if (apiResponse.success && apiResponse.data?.access_token) {
        typedClient.setToken(apiResponse.data.access_token);
      }

      return apiResponse;
    },

    /**
     * Get list of mock SSO users (development only)
     *
     * Type-safe: Response array type inferred from OpenAPI
     */
    getMockUsers: async (): Promise<ApiResponse<any[]>> => {
      const response = await typedClient.raw.GET('/api/v1/auth/mock-sso/users');
      return toApiResponse<any[]>(response);
    },

    /**
     * Login using mock SSO (development only)
     *
     * Type-safe: Request body and response validated
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
      const response = await typedClient.raw.POST('/api/v1/auth/mock-sso/login', {
        body: { nycu_id },
      });

      const apiResponse = toApiResponse<{
        access_token: string;
        token_type: string;
        expires_in: number;
        user: User;
      }>(response);

      // Store token after successful mock login
      if (apiResponse.success && apiResponse.data?.access_token) {
        typedClient.setToken(apiResponse.data.access_token);
      }

      return apiResponse;
    },
  };
}
