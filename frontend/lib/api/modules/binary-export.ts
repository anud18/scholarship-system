/**
 * Shared authed binary-download fetcher for backend file exports.
 *
 * openapi-fetch (typedClient.raw) cannot stream blobs, so every binary export
 * goes through plain fetch with the JWT attached. Extracted from
 * lib/api/modules/college.ts when the manual-distribution 分發名單 export became
 * the second module needing it.
 *
 * Returns the file as a Blob plus the filename parsed from the RFC 5987
 * `Content-Disposition: attachment; filename*=UTF-8''<encoded>` header,
 * falling back to `fallbackFilename` when the header is missing.
 */

import { typedClient } from "../typed-client";

export async function fetchBinaryExport(
  path: string,
  params: URLSearchParams,
  fallbackFilename: string,
  errorFallback: string
): Promise<{ blob: Blob; filename: string }> {
  const token = typedClient.getToken();
  const baseURL =
    typeof window !== "undefined"
      ? ""
      : process.env.INTERNAL_API_URL || "http://localhost:8000";

  const query = params.toString();
  const url = `${baseURL}${path}${query ? `?${query}` : ""}`;

  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!response.ok) {
    let message = errorFallback;
    try {
      const errorData = await response.json();
      message = errorData?.detail || errorData?.message || errorData?.error || message;
    } catch {
      // Non-JSON error body — keep default.
    }
    throw new Error(message);
  }

  const disposition = response.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  const filename = filenameMatch
    ? decodeURIComponent(filenameMatch[1].trim())
    : fallbackFilename;

  const blob = await response.blob();
  return { blob, filename };
}
