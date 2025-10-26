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
 * Validate backend URL to prevent SSRF attacks
 * Ensures the URL hostname is from a trusted allowlist
 */
function validateBackendUrl(envUrl: string | undefined): string {
  if (!envUrl) {
    throw new Error("Invalid backend configuration: URL not set");
  }

  // Parse URL to extract hostname
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(envUrl);
  } catch (error) {
    throw new Error("Invalid backend URL format");
  }

  // Allowlist of trusted hostnames
  const allowedHostnames = [
    'backend',                  // Docker internal network
    'localhost',                // Local development
    'host.docker.internal',     // Docker host gateway
    'ss.test.nycu.edu.tw'       // Production server
  ];

  if (!allowedHostnames.includes(parsedUrl.hostname)) {
    throw new Error(`Untrusted backend hostname: ${parsedUrl.hostname}`);
  }

  return envUrl;
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

    // Security: Validate backend URL to prevent SSRF attacks
    let baseUrl: string;
    try {
      baseUrl = validateBackendUrl(
        process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL
      );
    } catch (error: any) {
      console.error("Backend URL validation error:", error.message);
      return NextResponse.json(
        { error: "Invalid backend configuration" },
        { status: 500 }
      );
    }

    // Construct backend URL using safe URL constructor
    let backendUrl: string;
    if (applicationId) {
      // Application file download
      const url = new URL(`/api/v1/files/applications/${applicationId}/files/${fileId}/download`, baseUrl);
      url.searchParams.set("token", token);
      backendUrl = url.toString();
    } else if (userId) {
      // User profile file download (e.g., bank document)
      const url = new URL(`/api/v1/user-profiles/files/bank_documents/${fileId}`, baseUrl);
      url.searchParams.set("token", token);
      backendUrl = url.toString();
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
