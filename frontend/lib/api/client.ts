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

/**
 * Minimal structural type for non-standard fetch responses (e.g. the React
 * Native whatwg-fetch polyfill, or test mocks). Real production code receives
 * a full `Response`; this type only exists so the defensive paths in
 * `getContentType` / `readTextSafe` can be reached under a non-`any` annotation.
 */
interface FetchResponseLike {
  headers?: Headers | Record<string, string>;
  text?: () => Promise<string> | string;
  json?: () => Promise<unknown>;
  body?: string | ReadableStream<Uint8Array> | null;
  ok?: boolean;
  status?: number;
  statusText?: string;
}

/**
 * Shape of a typical error/status payload coming back from the backend. The
 * fields are checked in order so the client surfaces the most specific message
 * available. Backed by FastAPI's HTTPException (`.detail`), our ApiResponse
 * envelope (`.message`), and a few legacy shapes (`.error`, `.title`).
 */
interface ApiErrorPayload {
  detail?: string;
  error?: string;
  message?: string;
  title?: string;
  success?: boolean;
  data?: unknown;
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

  /**
   * Extract the content-type header from a fetch Response, tolerating test
   * mocks that pass a plain-object `headers` map instead of a real Headers
   * instance.
   */
  private getContentType(res: Response | FetchResponseLike): string {
    const h = res?.headers as Headers | Record<string, string> | undefined;
    if (h && typeof (h as Headers).get === "function") {
      return (h as Headers).get("content-type") || "";
    }
    if (h && typeof h === "object") {
      const dict = h as Record<string, string>;
      return (
        dict["content-type"] || dict["Content-Type"] || dict["Content-type"] || ""
      );
    }
    return "";
  }

  /**
   * Read response body as text, tolerating non-standard fetch implementations
   * (e.g. React Native's whatwg-fetch polyfill exposes `_bodyInit` rather than
   * a working `text()`).
   */
  private async readTextSafe(res: Response | FetchResponseLike): Promise<string> {
    try {
      if (typeof res?.text === "function") return await res.text();
    } catch {}
    if (typeof res?.json === "function") {
      try {
        return JSON.stringify(await res.json());
      } catch {}
    }
    if (typeof (res as FetchResponseLike)?.body === "string") {
      return (res as FetchResponseLike).body as string;
    }
    const rnPolyfillBody = (res as { _bodyInit?: unknown })?._bodyInit;
    if (typeof rnPolyfillBody === "string") return rnPolyfillBody;
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
      const response: Response = await fetch(url, config);

      const contentType = this.getContentType(response);
      const canJson =
        contentType.includes("application/json") ||
        typeof (response as Response & { json?: unknown })?.json === "function";

      // `data` is genuinely unknown here — the network response could be JSON
      // matching ApiResponse, an error payload with `.detail`/`.message`, a
      // bare string, or something else. Narrow at each access site below.
      let data: unknown;
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

        const errPayload =
          data && typeof data === "object" ? (data as ApiErrorPayload) : null;
        const msg =
          errPayload?.detail ||
          errPayload?.error ||
          errPayload?.message ||
          errPayload?.title ||
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
            schema.parse((data as ApiErrorPayload).data);
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
        const obj = data as ApiErrorPayload & Record<string, unknown>;
        // If response already has success structure (with message or data), return as-is
        if ("success" in obj && ("message" in obj || "data" in obj)) {
          // Ensure message property exists for consistency
          const message = obj.message || "Request completed successfully";

          // Log warning in development if message was missing
          if (!obj.message && process.env.NODE_ENV === 'development') {
            logger.warn('API Response missing message field', {
              endpoint,
              success: obj.success,
              hasData: !!obj.data,
            });
          }

          return {
            success: obj.success,
            message,
            data: obj.data,
          } as ApiResponse<T>;
        }
        // If it's a PaginatedResponse, wrap it
        else if (
          "items" in obj &&
          "total" in obj &&
          "page" in obj &&
          "size" in obj &&
          "pages" in obj
        ) {
          return {
            success: true,
            message: "Request completed successfully",
            data: obj as T,
          } as ApiResponse<T>;
        }
        // If it's a direct object, wrap it
        else if ("id" in obj) {
          return {
            success: true,
            message: "Request completed successfully",
            data: obj as T,
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
