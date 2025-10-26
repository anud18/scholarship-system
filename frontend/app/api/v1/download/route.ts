import { NextRequest, NextResponse } from "next/server";

// ============================================================================
// Security: Input Validation Utility
// ============================================================================
// Prevents SSRF attacks by validating user-controlled inputs

/**
 * Validate ID parameters (fileId, applicationId, userId)
 * Only allows alphanumeric characters, hyphens, and underscores
 * Prevents path traversal (..), injection (/), and other attacks
 */
function validateId(id: string | null, paramName: string): void {
  if (!id) {
    throw new Error(`${paramName} is required`);
  }

  // Check for path traversal attempts
  if (id.includes("..") || id.includes("/") || id.includes("\\")) {
    throw new Error(`Invalid ${paramName}: path traversal detected`);
  }

  // Only allow safe characters: letters, numbers, hyphens, underscores
  const idPattern = /^[a-zA-Z0-9_-]+$/;
  if (!idPattern.test(id)) {
    throw new Error(`Invalid ${paramName}: contains illegal characters`);
  }

  // Reasonable length limit (prevent DoS)
  if (id.length > 100) {
    throw new Error(`Invalid ${paramName}: too long`);
  }
}

/**
 * Sanitizes backend URL by validating hostname and reconstructing a clean URL
 * Returns a new URL object with validated components (CodeQL sanitizer pattern)
 *
 * This function prevents SSRF attacks by:
 * 1. Validating the hostname against an allowlist
 * 2. Reconstructing a new URL from validated components
 * 3. Breaking the taint chain for static analysis tools
 */
function getSafeBackendUrl(): URL {
  const envUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;

  if (!envUrl) {
    throw new Error("Backend URL not configured");
  }

  // Parse and validate the environment URL
  let parsed: URL;
  try {
    parsed = new URL(envUrl);
  } catch (error) {
    throw new Error("Invalid backend URL format");
  }

  // Explicit allowlist check
  const allowedHosts = ['backend', 'localhost', 'host.docker.internal', 'ss.test.nycu.edu.tw'];
  if (!allowedHosts.includes(parsed.hostname)) {
    throw new Error(`Untrusted hostname: ${parsed.hostname}`);
  }

  // CRITICAL: Reconstruct URL from validated components
  // This creates a new, untainted value for CodeQL's data flow analysis
  const protocol = parsed.protocol === 'https:' ? 'https:' : 'http:';
  const port = parsed.port || (protocol === 'https:' ? '443' : '8000');

  return new URL(`${protocol}//${parsed.hostname}:${port}`);
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const fileId = searchParams.get("fileId");
    const filename = searchParams.get("filename");
    const type = searchParams.get("type");
    const applicationId = searchParams.get("applicationId");
    const userId = searchParams.get("userId");
    const token = searchParams.get("token");

    // Security: Validate all ID parameters to prevent SSRF
    try {
      validateId(fileId, "fileId");

      // For user profile documents, userId can be used instead of applicationId
      if (applicationId) {
        validateId(applicationId, "applicationId");
      } else if (userId) {
        validateId(userId, "userId");
      } else {
        return NextResponse.json(
          { error: "Application ID or User ID is required" },
          { status: 400 }
        );
      }
    } catch (validationError: any) {
      console.error("Input validation error:", validationError.message);
      return NextResponse.json(
        { error: validationError.message },
        { status: 400 }
      );
    }

    if (!token) {
      return NextResponse.json(
        { error: "Access token is required" },
        { status: 400 }
      );
    }

    // Security: Get safe backend URL to prevent SSRF attacks
    let backendUrl: URL;
    try {
      backendUrl = getSafeBackendUrl();
    } catch (error: any) {
      console.error("Backend URL validation error:", error.message);
      return NextResponse.json(
        { error: "Invalid backend configuration" },
        { status: 500 }
      );
    }

    // Construct URL path and query parameters using URL object methods
    if (applicationId) {
      // Application file download
      backendUrl.pathname = `/api/v1/files/applications/${applicationId}/files/${fileId}/download`;
      backendUrl.searchParams.set("token", token);
    } else if (userId) {
      // User profile file download (e.g., bank document)
      backendUrl.pathname = `/api/v1/user-profiles/files/bank_documents/${fileId}`;
      backendUrl.searchParams.set("token", token);
    } else {
      return NextResponse.json(
        { error: "Invalid file context" },
        { status: 400 }
      );
    }

    console.log("Download API called:", {
      fileId,
      applicationId,
      userId,
      backendUrl,
    });

    // 從後端獲取文件
    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      console.error(
        "Backend response error:",
        response.status,
        response.statusText
      );
      return NextResponse.json(
        { error: "Failed to fetch file from backend" },
        { status: response.status }
      );
    }

    // 獲取文件數據
    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/octet-stream";

    // 處理中文文件名編碼
    let contentDisposition = "attachment";
    if (filename) {
      // 使用 encodeURIComponent 來正確編碼中文文件名
      const encodedFilename = encodeURIComponent(filename);
      contentDisposition = `attachment; filename*=UTF-8''${encodedFilename}`;
    }

    // 返回文件給用戶
    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Cache-Control": "no-cache",
      },
    });
  } catch (error) {
    console.error("File download error:", error);
    return NextResponse.json(
      { error: "Failed to download file" },
      { status: 500 }
    );
  }
}
