import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const documentId = searchParams.get("documentId");

    // Get token from query params, Authorization header, or cookie
    const queryToken = searchParams.get("token");
    const authHeader = request.headers.get("authorization");
    const cookieToken = request.cookies.get("access_token")?.value || request.cookies.get("auth_token")?.value;
    const token = queryToken || authHeader?.replace("Bearer ", "") || cookieToken;

    if (!documentId) {
      return NextResponse.json(
        { error: "Document ID is required" },
        { status: 400 }
      );
    }

    // Validate documentId to prevent injection attacks
    if (!documentId.match(/^\d+$/)) {
      return NextResponse.json(
        { error: "Invalid document ID format" },
        { status: 400 }
      );
    }

    if (!token) {
      return NextResponse.json(
        { error: "Access token is required" },
        { status: 401 }
      );
    }

    // Use only trusted internal backend URL with validated path
    const baseUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;

    // Validate base URL is trusted (must be our backend)
    if (!baseUrl) {
      return NextResponse.json(
        { error: "Invalid backend configuration" },
        { status: 500 }
      );
    }

    // Parse URL and validate hostname to prevent URL bypass attacks
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(baseUrl);
    } catch (error) {
      return NextResponse.json(
        { error: "Invalid backend URL format" },
        { status: 500 }
      );
    }

    // Allowlist of trusted hostnames
    const allowedHostnames = ['backend', 'ss.test.nycu.edu.tw'];
    if (!allowedHostnames.includes(parsedUrl.hostname)) {
      return NextResponse.json(
        { error: "Untrusted backend hostname" },
        { status: 500 }
      );
    }

    // Construct URL with validated components only
    const backendUrl = new URL(`/api/v1/application-fields/documents/${documentId}/example`, baseUrl).toString();

    console.log("Document example preview API called:", {
      documentId,
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
        { error: "Failed to fetch document example" },
        { status: response.status }
      );
    }

    // 獲取文件數據
    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/pdf";

    // 從 backend 獲取完整的 Content-Disposition 標頭（包含 filename）
    const contentDisposition = response.headers.get("content-disposition") || "inline";

    // 返回文件給用戶
    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600", // 1小時緩存
      },
    });
  } catch (error) {
    console.error("Document example preview error:", error);
    return NextResponse.json(
      { error: "Failed to preview document example" },
      { status: 500 }
    );
  }
}
