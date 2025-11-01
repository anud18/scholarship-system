/**
 * Compatibility layer between openapi-fetch and ApiResponse format
 *
 * Converts openapi-fetch responses to the standard ApiResponse format
 * used throughout the application, maintaining backward compatibility.
 */

import type { ApiResponse } from './types';

/**
 * openapi-fetch response type
 * Flexible definition to handle various error structures from FastAPI
 */
export interface FetchResponse<T> {
  data?: T;
  error?: {
    detail?: string | any[] | any; // FastAPI can return string, validation errors array, or other structures
    message?: string;
    [key: string]: any;
  };
  response: Response;
}

/**
 * Helper function to safely convert any value to a string message
 */
function safeStringify(value: any): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value && typeof value === 'object') {
    // Handle Error objects
    if (value.message && typeof value.message === 'string') {
      return value.message;
    }
    // Handle arrays
    if (Array.isArray(value)) {
      return value.map(v => safeStringify(v)).join(', ');
    }
    // Handle objects with detail field
    if (value.detail) {
      return safeStringify(value.detail);
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
 * @param response - openapi-fetch response object (uses any to accept full OpenAPI types)
 * @returns ApiResponse<T> in standard format
 */
export function toApiResponse<T>(
  response: any
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
        .map((err: any) => `${err.loc?.join('.')}: ${err.msg}`)
        .join(', ');
    } else if (response.error.detail) {
      // Handle object detail - use safeStringify
      errorMessage = safeStringify(response.error.detail);
    } else if (response.error.message) {
      // Handle message field - ensure it's a string
      errorMessage = safeStringify(response.error.message);
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
    const data = response.data as any;

    // If backend returns ApiResponse format, use it directly
    if ('success' in data && 'data' in data) {
      // Ensure message is always a string
      const message = typeof data.message === 'string'
        ? data.message
        : safeStringify(data.message) || 'Request completed successfully';

      return {
        success: data.success,
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
export function extractErrorMessage(response: FetchResponse<any>): string {
  if (response.error) {
    // Handle different error detail formats
    if (typeof response.error.detail === 'string') {
      return response.error.detail;
    } else if (Array.isArray(response.error.detail)) {
      // FastAPI validation errors
      return response.error.detail
        .map((err: any) => `${err.loc?.join('.')}: ${err.msg}`)
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
