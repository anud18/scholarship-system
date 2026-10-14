/**
 * URL Validation Utilities
 *
 * Provides secure URL construction and validation to prevent open redirect vulnerabilities.
 * CodeQL recognizes these patterns as sanitization barriers.
 *
 * @see https://codeql.github.com/codeql-query-help/javascript/js-client-side-unvalidated-url-redirection/
 */

/**
 * Validates that a URL path is same-origin
 *
 * This function uses the URL API with origin validation, which CodeQL recognizes
 * as a sanitization barrier against open redirect vulnerabilities.
 *
 * @param path - The URL path to validate (must be relative)
 * @returns The validated path
 * @throws {Error} if URL is not same-origin or is absolute
 */
export function validateSameOriginUrl(path: string): string {
  // Ensure it's a relative path
  if (!path.startsWith('/')) {
    throw new Error('Only relative URLs are allowed');
  }

  // Parse relative to current origin (CodeQL sanitization pattern)
  const url = new URL(path, window.location.origin);

  // Verify origin hasn't changed - this is the key check CodeQL recognizes
  if (url.origin !== window.location.origin) {
    throw new Error('Cross-origin navigation blocked');
  }

  // Return only the pathname and search (no origin)
  return url.pathname + url.search;
}

export type SafeNavigation =
  | { kind: "internal"; path: string }
  | { kind: "external"; url: string };

const NAVIGABLE_PROTOCOLS = new Set(["http:", "https:"]);

/**
 * Resolves a server-supplied link (e.g. a notification's action_url) into a
 * navigation target that cannot execute script.
 *
 * Unlike validateSameOriginUrl this also accepts external http(s) links, which
 * callers must open in a new tab. Same-origin results use the same
 * URL-API origin comparison CodeQL recognizes as a sanitization barrier.
 *
 * @param raw - The stored link; may be relative or absolute
 * @param origin - The current origin, or null during server rendering
 * @returns The target, or null when the link is empty, unparsable or uses a
 *          non-http(s) scheme (javascript:, data:, vbscript:, ...)
 */
export function resolveSafeNavigation(
  raw: string | null | undefined,
  origin: string | null
): SafeNavigation | null {
  if (!origin || !raw || !raw.trim()) return null;

  let url: URL;
  try {
    url = new URL(raw.trim(), origin);
  } catch {
    return null;
  }

  if (!NAVIGABLE_PROTOCOLS.has(url.protocol)) return null;

  if (url.origin === new URL(origin).origin) {
    return { kind: "internal", path: url.pathname + url.search + url.hash };
  }
  return { kind: "external", url: url.href };
}

/**
 * Safely constructs API preview URLs with authentication token
 *
 * Uses an allowlist approach to ensure only authorized endpoints can be accessed.
 * All constructed URLs are validated to be same-origin before being returned.
 *
 * @param endpoint - The API endpoint path (must be in allowlist)
 * @param params - Query parameters to append
 * @returns A validated same-origin URL string
 * @throws {Error} if endpoint is not in allowlist or URL validation fails
 */
export function buildSecurePreviewUrl(
  endpoint: string,
  params: Record<string, string | number | undefined>
): string {
  // Allowlist of permitted preview/download endpoints
  const allowedEndpoints = [
    '/api/v1/preview',
    '/api/v1/preview/examples',
    '/api/v1/download'
  ];

  if (!allowedEndpoints.includes(endpoint)) {
    throw new Error(`Endpoint ${endpoint} not in allowlist`);
  }

  // Use URL API for safe construction (prevents injection)
  const url = new URL(endpoint, window.location.origin);

  // Add query parameters using URLSearchParams (automatic encoding)
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, String(value));
    }
  });

  // Final validation using CodeQL-recognized pattern
  return validateSameOriginUrl(url.pathname + url.search);
}

/**
 * Gets authentication token from storage with fallback
 *
 * Centralizes token retrieval logic to maintain consistency across the application.
 * Checks multiple storage locations for backward compatibility.
 *
 * @returns The authentication token or empty string if not found
 */
export function getAuthToken(): string {
  return (
    localStorage.getItem("auth_token") ||
    localStorage.getItem("token") ||
    sessionStorage.getItem("auth_token") ||
    sessionStorage.getItem("token") ||
    ""
  );
}
