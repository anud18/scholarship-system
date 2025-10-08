/**
 * Base API Client for making HTTP requests
 *
 * This client handles:
 * - URL construction (relative paths in browser, internal URLs for SSR)
 * - Authentication token management
 * - Request/response transformation
 * - Error handling
 */

import type { ApiResponse } from '../api'; // Import from main api.ts for now

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
   * Make an authenticated API request
   * @param endpoint - API endpoint (e.g., "/auth/login")
   * @param options - Fetch options with optional params
   */
  async request<T = any>(
    endpoint: string,
    options: RequestInit & { params?: Record<string, any> } = {}
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

    // Remove params from options before passing to fetch
    const { params, ...fetchOptions } = options;
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
          console.error("Authentication failed - clearing token");
          this.clearToken();
        } else if (response.status === 403) {
          console.error(
            "Authorization denied - user may not have proper permissions"
          );
        } else if (response.status === 429) {
          console.warn("Rate limit exceeded - request throttled");
        }

        const msg =
          (data && (data.detail || data.error || data.message || data.title)) ||
          (typeof data === "string" ? data : "") ||
          response.statusText ||
          `HTTP ${response.status}`;
        throw new Error(msg);
      }

      // Handle different response formats from backend
      if (data && typeof data === "object") {
        // If response already has success/message structure, return as-is
        if ("success" in data && "message" in data) {
          return data as ApiResponse<T>;
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
      console.error("API request failed:", error);
      throw error;
    }
  }
}
