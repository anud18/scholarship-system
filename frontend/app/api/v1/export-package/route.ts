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

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const token = searchParams.get("token");
    const scholarshipTypeId = searchParams.get("scholarship_type_id");
    const academicYear = searchParams.get("academic_year");
    const semester = searchParams.get("semester");

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

    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Export package backend error", {
        status: response.status,
      });
      return NextResponse.json(
        { error: errorText || "Failed to generate export package" },
        { status: response.status }
      );
    }

    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/zip";
    const contentDisposition =
      response.headers.get("content-disposition") || "attachment";

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Cache-Control": "no-cache, no-store, must-revalidate",
      },
    });
  } catch (error) {
    logger.error("Export package proxy error", {});
    return NextResponse.json(
      { error: "Failed to download export package" },
      { status: 500 }
    );
  }
}
