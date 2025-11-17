import { NextRequest, NextResponse } from "next/server";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://backend:8000";

/**
 * Upload scholarship terms document
 *
 * This proxy endpoint handles file uploads for scholarship terms documents.
 * Following CLAUDE.md three-layer architecture:
 * Frontend Component → Next.js Proxy → FastAPI Backend → MinIO
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ type: string }> }
) {
  try {
    const { type } = await params;

    // Validate scholarship type parameter
    if (!type || typeof type !== "string") {
      return NextResponse.json(
        { error: "Scholarship type is required" },
        { status: 400 }
      );
    }

    // Get authorization token from header
    const authHeader = request.headers.get("authorization");
    if (!authHeader) {
      return NextResponse.json(
        { error: "Authentication required" },
        { status: 401 }
      );
    }

    // Get form data from request
    const formData = await request.formData();
    const file = formData.get("file");

    // Validate file exists
    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { success: false, message: "File is required" },
        { status: 400 }
      );
    }

    // Construct backend URL using INTERNAL_API_URL (Docker internal network)
    const backendUrl = `${INTERNAL_API_URL}/api/v1/scholarships/${encodeURIComponent(type)}/upload-terms`;

    console.log(`[Upload Terms Proxy] Forwarding file "${file.name}" to: ${backendUrl}`);

    // Create a fresh FormData instance to avoid stream consumption issues
    const backendFormData = new FormData();
    backendFormData.append("file", file);

    // Forward request to backend
    // IMPORTANT: Don't set Content-Type header - let fetch auto-set with boundary
    const response = await fetch(backendUrl, {
      method: "POST",
      headers: {
        Authorization: authHeader,
      },
      body: backendFormData,
    });

    // Get response data
    const data = await response.json();

    // Return response with same status code
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    console.error("[Upload Terms Proxy] Error:", error);
    return NextResponse.json(
      {
        success: false,
        message: error instanceof Error ? error.message : "Upload failed",
      },
      { status: 500 }
    );
  }
}
