/**
 * Compatibility layer between openapi-fetch and ApiResponse format
 *
 * Converts openapi-fetch responses to the standard ApiResponse format
 * used throughout the application, maintaining backward compatibility.
 */

import type { ApiResponse } from './types';

// FastAPI validation error row — emitted in error.detail arrays.
interface FastApiValidationErrorRow {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
  [key: string]: unknown;
}

/**
 * openapi-fetch response type
 * Flexible definition to handle various error structures from FastAPI
 */
export interface FetchResponse<T> {
  data?: T;
  error?: {
    // FastAPI can return string, validation errors array, or other structures
    detail?: string | FastApiValidationErrorRow[] | Record<string, unknown>;
    message?: string;
    [key: string]: unknown;
  };
  response: Response;
}

/**
 * Helper function to safely convert any value to a string message
 */
function safeStringify(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    // Handle Error objects
    if (typeof obj.message === 'string') {
      return obj.message;
    }
    // Handle arrays
    if (Array.isArray(value)) {
      return value.map(v => safeStringify(v)).join(', ');
    }
    // Handle objects with detail field
    if (obj.detail) {
      return safeStringify(obj.detail);
    }
    // Fallback: stringify the object
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value || 'Unknown error');
}

/**
 * Convert openapi-fetch response to ApiResponse format
 *
 * Handles:
 * - Success responses (data present)
 * - Error responses (error present)
 * - HTTP status codes
 * - Error message extraction
 *
 * @param response - openapi-fetch response object. Typed as
 *   ``FetchResponse<unknown>`` so callers can pass any openapi-fetch
 *   response without forcing the caller's `T` to flow through the
 *   typed-client's generated union (which is often
 *   `Record<string, never>` for nested body schemas the backend doesn't
 *   fully emit). The wrapper inspects ``response.data`` and re-narrows
 *   to ``T`` at the return boundary.
 * @returns ApiResponse<T> in standard format
 */
export function toApiResponse<T>(
  response: FetchResponse<unknown>
): ApiResponse<T> {
  // Handle error responses
  if (response.error) {
    let errorMessage: string;

    // Handle different error detail formats
    if (typeof response.error.detail === 'string') {
      errorMessage = response.error.detail;
    } else if (Array.isArray(response.error.detail)) {
      // FastAPI validation errors
      errorMessage = response.error.detail
        .map(
          (err: FastApiValidationErrorRow) =>
            `${err.loc?.join('.')}: ${err.msg}`
        )
        .join(', ');
    } else if (response.error.detail) {
      // Handle object detail - use safeStringify
      errorMessage = safeStringify(response.error.detail);
    } else if (response.error.message) {
      // Handle message field - ensure it's a string
      errorMessage = safeStringify(response.error.message);
      // The backend's validation handler puts the generic text in `message`
      // ("Validation failed") and the actual per-field reasons in `errors` —
      // without them the user sees no reason at all.
      const errorList = (response.error as { errors?: unknown }).errors;
      if (Array.isArray(errorList) && errorList.length > 0) {
        errorMessage += `: ${errorList.map((e) => safeStringify(e)).join('; ')}`;
      }
    } else {
      errorMessage = `Request failed with status ${response.response.status}`;
    }

    return {
      success: false,
      message: errorMessage,
      data: undefined,
    };
  }

  // Handle success responses
  // Backend already returns ApiResponse format {success, message, data}
  if (response.data && typeof response.data === 'object') {
    // Narrow to dict for the field-presence check below; payload shape is
    // generic across endpoints so structural access is the safe minimum.
    const data = response.data as Record<string, unknown>;

    // If backend returns ApiResponse format, use it directly
    if ('success' in data && 'data' in data) {
      // Ensure message is always a string
      const message = typeof data.message === 'string'
        ? data.message
        : safeStringify(data.message) || 'Request completed successfully';

      return {
        // `data` is `Record<string, unknown>` from the structural narrow above;
        // backend ApiResponse format guarantees `success: boolean`. Coerce
        // explicitly so the strict prod build (Next.js TS) accepts the
        // assignment.
        success: Boolean(data.success),
        message: message,
        data: data.data as T,
      };
    }
  }

  // Fallback: wrap raw data in ApiResponse format
  return {
    success: true,
    message: 'Request completed successfully',
    data: response.data as T,
  };
}

/**
 * Extract error message from openapi-fetch response
 *
 * @param response - openapi-fetch response object
 * @returns Error message string
 */
export function extractErrorMessage(response: FetchResponse<unknown>): string {
  if (response.error) {
    // Handle different error detail formats
    if (typeof response.error.detail === 'string') {
      return response.error.detail;
    } else if (Array.isArray(response.error.detail)) {
      // FastAPI validation errors
      return response.error.detail
        .map(
          (err: FastApiValidationErrorRow) =>
            `${err.loc?.join('.')}: ${err.msg}`
        )
        .join(', ');
    } else if (response.error.detail) {
      // Handle object detail - use safeStringify
      return safeStringify(response.error.detail);
    } else if (response.error.message) {
      // Handle message field - ensure it's a string
      return safeStringify(response.error.message);
    } else {
      return `Request failed with status ${response.response.status}`;
    }
  }

  if (!response.response.ok) {
    return `Request failed with status ${response.response.status}`;
  }

  return 'Unknown error occurred';
}

/**
 * Check if response is successful
 *
 * @param response - openapi-fetch response object
 * @returns true if response is successful
 */
export function isSuccessResponse<T>(
  response: FetchResponse<T>
): response is FetchResponse<T> & { data: T } {
  return !response.error && response.response.ok && response.data !== undefined;
}

/**
 * Type guard for error responses
 *
 * @param response - openapi-fetch response object
 * @returns true if response is an error
 */
export function isErrorResponse<T>(
  response: FetchResponse<T>
): response is FetchResponse<T> & { error: NonNullable<FetchResponse<T>['error']> } {
  return !!response.error || !response.response.ok;
}
