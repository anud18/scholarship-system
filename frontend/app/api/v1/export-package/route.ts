import { NextRequest, NextResponse } from "next/server";
import { logger } from "@/lib/utils/logger";

/**
 * Sanitizes backend URL by validating hostname and reconstructing a clean URL.
 * Prevents SSRF attacks via hostname allowlist.
 */
function getSafeBackendUrl(): URL {
  const envUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;

  if (!envUrl) {
    throw new Error("Backend URL not configured");
  }

  let parsed: URL;
  try {
    parsed = new URL(envUrl);
  } catch {
    throw new Error("Invalid backend URL format");
  }

  const allowedHosts = [
    "backend",
    "localhost",
    "host.docker.internal",
    "ss.test.nycu.edu.tw",
  ];
  if (!allowedHosts.includes(parsed.hostname)) {
    throw new Error(`Untrusted hostname: ${parsed.hostname}`);
  }

  const protocol = parsed.protocol === "https:" ? "https:" : "http:";
  const port = parsed.port || (protocol === "https:" ? "443" : "8000");

  return new URL(`${protocol}//${parsed.hostname}:${port}`);
}

/**
 * Pull a human-readable message out of a backend error body. The backend
 * wraps HTTPException into ApiResponse `{ success, message, trace_id }`;
 * bare FastAPI errors carry `detail`. Falls back to the raw text.
 */
function extractBackendError(text: string): string {
  try {
    const parsed = JSON.parse(text);
    const message = parsed?.message ?? parsed?.detail;
    return typeof message === "string" && message ? message : text;
  } catch {
    return text;
  }
}

/**
 * Proxies the college export-package download to the backend, turning the
 * `token` query param into a Bearer header.
 *
 * The archive can run into the gigabytes (issue #1376), so the backend body
 * is piped straight through: never buffered with arrayBuffer(), no invented
 * Content-Length, and the client's abort signal is forwarded so a cancelled
 * download stops the backend from building the rest of the ZIP.
 * `dry_run=true` is forwarded as-is; the backend then answers with a small
 * JSON precheck instead of the archive.
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const token = searchParams.get("token");
    const scholarshipTypeId = searchParams.get("scholarship_type_id");
    const academicYear = searchParams.get("academic_year");
    const semester = searchParams.get("semester");
    const dryRun = searchParams.get("dry_run");

    if (!token) {
      return NextResponse.json(
        { error: "Access token is required" },
        { status: 400 }
      );
    }

    if (!scholarshipTypeId || !academicYear) {
      return NextResponse.json(
        { error: "scholarship_type_id and academic_year are required" },
        { status: 400 }
      );
    }

    // Validate numeric parameters
    if (!/^\d+$/.test(scholarshipTypeId) || !/^\d+$/.test(academicYear)) {
      return NextResponse.json(
        { error: "Invalid parameter format" },
        { status: 400 }
      );
    }

    // Validate semester if provided
    if (semester && !["first", "second", "annual"].includes(semester)) {
      return NextResponse.json(
        { error: "Invalid semester value" },
        { status: 400 }
      );
    }

    if (dryRun !== null && !["true", "false"].includes(dryRun)) {
      return NextResponse.json(
        { error: "Invalid dry_run value" },
        { status: 400 }
      );
    }

    let backendUrl: URL;
    try {
      backendUrl = getSafeBackendUrl();
    } catch {
      return NextResponse.json(
        { error: "Invalid backend configuration" },
        { status: 500 }
      );
    }

    backendUrl.pathname = "/api/v1/college-review/export-package";
    backendUrl.searchParams.set("scholarship_type_id", scholarshipTypeId);
    backendUrl.searchParams.set("academic_year", academicYear);
    if (semester) {
      backendUrl.searchParams.set("semester", semester);
    }
    if (dryRun === "true") {
      backendUrl.searchParams.set("dry_run", "true");
    }

    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      signal: request.signal,
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Export package backend error", {
        status: response.status,
      });
      return NextResponse.json(
        {
          error:
            extractBackendError(errorText) ||
            "Failed to generate export package",
        },
        { status: response.status }
      );
    }

    if (!response.body) {
      logger.error("Export package backend returned no body", {
        status: response.status,
      });
      return NextResponse.json(
        { error: "Failed to download export package" },
        { status: 502 }
      );
    }

    // Stream the backend body through untouched. Content-Length is not
    // forwarded: the ZIP has none (chunked), and Next may re-encode the
    // small dry_run JSON.
    const headers = new Headers({
      "Content-Type":
        response.headers.get("content-type") || "application/zip",
      "Cache-Control": "no-cache, no-store, must-revalidate",
    });
    const contentDisposition = response.headers.get("content-disposition");
    if (contentDisposition) {
      headers.set("Content-Disposition", contentDisposition);
    }

    return new NextResponse(response.body, { status: 200, headers });
  } catch (error) {
    if (request.signal.aborted) {
      // The browser cancelled the download; nothing to repair on our side.
      logger.info("Export package download aborted by client", {});
      return new NextResponse(null, { status: 499 });
    }
    logger.error("Export package proxy error", {});
    return NextResponse.json(
      { error: "Failed to download export package" },
      { status: 500 }
    );
  }
}
