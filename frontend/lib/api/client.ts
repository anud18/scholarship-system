/**
 * Base API Client for making HTTP requests
 *
 * This client handles:
 * - URL construction (relative paths in browser, internal URLs for SSR)
 * - Authentication token management
 * - Request/response transformation
 * - Error handling
 * - Runtime validation with Zod (optional)
 */

import type { ApiResponse } from '../api'; // Import from main api.ts for now
import { z, type ZodType } from 'zod';
import { logger } from '../utils/logger';

/**
 * API validation error with detailed information
 */
export class ApiValidationError extends Error {
  constructor(
    message: string,
    public readonly zodError: z.ZodError,
    public readonly endpoint: string,
    public readonly responseData: unknown
  ) {
    super(message);
    this.name = 'ApiValidationError';
  }
}

export class ApiClient {
  private baseURL: string;
  private token: string | null = null;

  constructor() {
    // Use relative path in browser (Nginx will proxy /api/ to backend)
    // Use internal Docker network URL for server-side rendering
    if (typeof window !== "undefined") {
      // Browser environment - always use relative path
      // Nginx reverse proxy will handle routing /api/* to backend
      this.baseURL = "";
      console.log("🌐 API Client Browser mode - using relative path (Nginx proxy)");
    } else {
      // Server-side environment - use internal Docker network or localhost
      this.baseURL = process.env.INTERNAL_API_URL || "http://localhost:8000";
      console.log("🖥️ API Client Server-side mode - using:", this.baseURL);
    }

    // Try to get token from localStorage on client side with safe access
    if (typeof window !== "undefined") {
      this.token = window.localStorage?.getItem?.("auth_token") ?? null;
    }
  }

  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("auth_token", token);
    }
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
    }
  }

  hasToken(): boolean {
    return !!this.token;
  }

  getToken(): string | null {
    return this.token;
  }

  private getContentType(res: any): string {
    const h: any = res?.headers;
    if (h?.get) return h.get("content-type") || "";
    if (h && typeof h === "object") {
      return h["content-type"] || h["Content-Type"] || h["Content-type"] || "";
    }
    return "";
  }

  private async readTextSafe(res: any): Promise<string> {
    try {
      if (typeof res?.text === "function") return await res.text();
    } catch {}
    if (typeof res?.json === "function") {
      try {
        return JSON.stringify(await res.json());
      } catch {}
    }
    if (typeof res?.body === "string") return res.body;
    if (typeof (res as any)?._bodyInit === "string")
      return (res as any)._bodyInit;
    return "";
  }

  /**
   * Make an authenticated API request with optional runtime validation
   * @param endpoint - API endpoint (e.g., "/auth/login")
   * @param options - Fetch options with optional params and schema
   */
  async request<T = any>(
    endpoint: string,
    options: RequestInit & {
      params?: Record<string, any>;
      schema?: ZodType<T>;
      validateResponse?: boolean;
    } = {}
  ): Promise<ApiResponse<T>> {
    // Handle query parameters
    let url = `${this.baseURL}/api/v1${endpoint}`;
    if (options.params) {
      const searchParams = new URLSearchParams();
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== "") {
          searchParams.append(key, String(value));
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        url += `?${queryString}`;
      }
    }

    // Normalize headers so .get/.set always exist
    const headers = new Headers(options.headers ?? {});

    // Only set Content-Type if it's not FormData
    const isFormData = options.body instanceof FormData;
    if (!isFormData && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    headers.set("Accept", "application/json");

    if (this.token) {
      headers.set("Authorization", `Bearer ${this.token}`);
    }

    // Remove params and schema from options before passing to fetch
    const { params, schema, validateResponse = false, ...fetchOptions } = options;
    const config: RequestInit = {
      ...fetchOptions,
      headers,
    };

    try {
      const response: any = await fetch(url, config);

      const contentType = this.getContentType(response);
      const canJson =
        contentType.includes("application/json") ||
        typeof response?.json === "function";

      let data: any;
      if (canJson) {
        try {
          data = await response.json();
        } catch {
          const t = await this.readTextSafe(response);
          try {
            data = JSON.parse(t);
          } catch {
            data = t;
          }
        }
      } else {
        const t = await this.readTextSafe(response);
        try {
          data = JSON.parse(t);
        } catch {
          data = t;
        }
      }

      if (!response.ok) {
        // Handle specific error codes
        if (response.status === 401) {
          logger.error("Authentication failed", { status: 401, endpoint });
          this.clearToken();

          // Emit session expired event for global handling
          if (typeof window !== "undefined") {
            window.dispatchEvent(
              new CustomEvent("session-expired", {
                detail: { type: "token_expired", status: 401, endpoint }
              })
            );
          }
        } else if (response.status === 403) {
          logger.error("Authorization denied", { status: 403, endpoint });

          // Emit unauthorized event
          if (typeof window !== "undefined") {
            window.dispatchEvent(
              new CustomEvent("session-expired", {
                detail: { type: "forbidden", status: 403, endpoint }
              })
            );
          }
        } else if (response.status === 429) {
          logger.warn("Rate limit exceeded", { endpoint });
        }

        const msg =
          (data && (data.detail || data.error || data.message || data.title)) ||
          (typeof data === "string" ? data : "") ||
          response.statusText ||
          `HTTP ${response.status}`;
        throw new Error(msg);
      }

      // Runtime validation if schema provided
      if (schema && (validateResponse || process.env.NODE_ENV === 'development')) {
        try {
          // Validate the entire ApiResponse structure if data has success/message
          if (data && typeof data === "object" && "success" in data && "data" in data) {
            schema.parse(data.data);
          } else {
            // Validate raw data
            schema.parse(data);
          }
        } catch (error) {
          if (error instanceof z.ZodError) {
            logger.error("API Response Validation Failed", {
              endpoint,
              errorCount: error.errors.length,
            });

            // Only throw in development to prevent breaking production
            if (process.env.NODE_ENV === 'development' || validateResponse) {
              throw new ApiValidationError(
                `API response validation failed for ${endpoint}`,
                error,
                endpoint,
                data
              );
            }
          }
        }
      }

      // Handle different response formats from backend
      if (data && typeof data === "object") {
        // If response already has success structure (with message or data), return as-is
        if ("success" in data && ("message" in data || "data" in data)) {
          // Ensure message property exists for consistency
          const message = data.message || "Request completed successfully";

          // Log warning in development if message was missing
          if (!data.message && process.env.NODE_ENV === 'development') {
            logger.warn('API Response missing message field', {
              endpoint,
              success: data.success,
              hasData: !!data.data,
            });
          }

          return {
            success: data.success,
            message,
            data: data.data,
          } as ApiResponse<T>;
        }
        // If it's a PaginatedResponse, wrap it
        else if (
          "items" in data &&
          "total" in data &&
          "page" in data &&
          "size" in data &&
          "pages" in data
        ) {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
        // If it's a direct object, wrap it
        else if ("id" in data) {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
        // If it's an array, wrap it
        else if (Array.isArray(data)) {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
        // Unknown object format, wrap anyway
        else {
          return {
            success: true,
            message: "Request completed successfully",
            data: data as T,
          } as ApiResponse<T>;
        }
      }

      // Primitive or unknown response
      return {
        success: true,
        message: "Request completed successfully",
        data: data as T,
      } as ApiResponse<T>;
    } catch (error) {
      logger.error("API request failed", { endpoint });
      throw error;
    }
  }
}
