import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const scholarshipType = searchParams.get("scholarshipType");

    // Get token from Authorization header or cookie (for iframe/img requests)
    const authHeader = request.headers.get("authorization");
    const cookieToken = request.cookies.get("access_token")?.value;
    const token = authHeader?.replace("Bearer ", "") || cookieToken;

    if (!scholarshipType) {
      return NextResponse.json(
        { error: "Scholarship type is required" },
        { status: 400 }
      );
    }

    // Validate scholarshipType to prevent SSRF attacks
    if (!scholarshipType.match(/^[a-zA-Z0-9_-]+$/)) {
      return NextResponse.json(
        { error: "Invalid scholarship type format" },
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
    const backendUrl = new URL(`/api/v1/scholarships/${scholarshipType}/terms`, baseUrl).toString();

    console.log("Terms preview API called:", {
      scholarshipType,
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
        { error: "Failed to fetch terms document" },
        { status: response.status }
      );
    }

    // 獲取文件數據
    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/pdf";

    // 返回文件給用戶
    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": "inline",
        "Cache-Control": "private, max-age=3600", // 1小時緩存
      },
    });
  } catch (error) {
    console.error("Terms preview error:", error);
    return NextResponse.json(
      { error: "Failed to preview terms document" },
      { status: 500 }
    );
  }
}
