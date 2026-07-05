/**
 * Type-safe API client generated from OpenAPI schema
 *
 * This client provides:
 * - Automatic type inference from backend OpenAPI schema
 * - Auth token management (localStorage-based)
 * - Browser/SSR URL routing
 * - Request/response interceptors
 * - Full TypeScript type safety
 *
 * Based on openapi-fetch for lightweight, zero-runtime overhead
 */

import createClient from 'openapi-fetch';
import type { paths } from './generated/schema';
import { logger } from '../utils/logger';

/**
 * Credential-submission endpoints: a 401 from these means the SUBMITTED
 * credentials were wrong, not that the stored session expired. Don't clear
 * the stored token or announce session expiry for them.
 */
const CREDENTIAL_ENDPOINTS = [
  '/api/v1/auth/login',
  '/api/v1/auth/mock-sso/login',
  '/api/v1/auth/portal-sso/verify',
];

/**
 * Type-safe API client with authentication and environment-aware routing
 */
class TypedApiClient {
  private client: ReturnType<typeof createClient<paths>>;
  private token: string | null = null;

  constructor() {
    // Environment-aware base URL
    // Browser: Use relative path (Nginx proxy handles /api/* routing)
    // Server: Use internal Docker network URL
    const baseUrl = typeof window !== 'undefined'
      ? '' // Browser: relative path
      : process.env.INTERNAL_API_URL || 'http://localhost:8000';

    logger.debug('Typed API Client initialized', {
      mode: typeof window !== 'undefined' ? 'browser' : 'server',
      baseUrl,
    });

    // Create typed client
    this.client = createClient<paths>({ baseUrl });

    // Load token from localStorage (client-side only)
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('auth_token');
    }

    // Add authentication interceptor
    this.client.use({
      onRequest: ({ request }) => {
        if (!this.token) {
          return undefined; // No modification needed
        }

        const headers = new Headers(request.headers);
        headers.set('Authorization', `Bearer ${this.token}`);

        return new Request(request, {
          headers,
        });
      },
      onResponse: ({ request, response }) => {
        // Clear token on 401 Unauthorized
        if (response.status === 401) {
          let endpoint = request.url;
          try {
            endpoint = new URL(request.url, 'http://localhost').pathname;
          } catch {}

          // Failed credential submission — leave any stored session alone.
          if (CREDENTIAL_ENDPOINTS.includes(endpoint)) {
            return undefined;
          }

          logger.error('Authentication failed - clearing token');
          this.clearToken();

          // Announce session expiry so SessionExpiredModal prompts a
          // re-login (same contract as the legacy ApiClient in client.ts).
          // Without this, the app looks logged-in but every request from
          // this client goes out WITHOUT an Authorization header, and
          // panels surface the raw backend error ("Authorization header
          // missing") with no way to recover.
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('session-expired', {
                detail: { type: 'token_expired', status: 401, endpoint },
              })
            );
          }
        }
        return undefined; // No modification needed
      },
    });
  }

  /**
   * Set authentication token
   * Stores in localStorage and updates Authorization header
   */
  setToken(token: string): void {
    this.token = token;
    if (typeof window !== 'undefined') {
      localStorage.setItem('auth_token', token);
    }
  }

  /**
   * Clear authentication token
   * Removes from localStorage
   */
  clearToken(): void {
    this.token = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('auth_token');
    }
  }

  /**
   * Check if user has authentication token
   */
  hasToken(): boolean {
    return !!this.token;
  }

  /**
   * Get current authentication token
   */
  getToken(): string | null {
    return this.token;
  }

  /**
   * Get the raw typed client for direct API calls
   *
   * Usage:
   *   const response = await typedClient.raw.GET('/auth/me');
   *   const response = await typedClient.raw.POST('/auth/login', {
   *     body: { username, password }
   *   });
   */
  get raw() {
    return this.client;
  }
}

/**
 * Singleton typed API client instance
 *
 * Usage:
 *   import { typedClient } from '@/lib/api/typed-client';
 *   const response = await typedClient.raw.GET('/api/v1/auth/me');
 */
export const typedClient = new TypedApiClient();

/**
 * Export the class for advanced use cases
 */
export { TypedApiClient };
