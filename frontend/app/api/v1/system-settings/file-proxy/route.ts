import { NextRequest, NextResponse } from "next/server";

const ALLOWED_KEYS = new Set(["regulations_url", "sample_document_url"]);

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const key = searchParams.get("key");

    if (!key || !ALLOWED_KEYS.has(key)) {
      return NextResponse.json({ error: "Invalid key" }, { status: 400 });
    }

    const queryToken = searchParams.get("token");
    const authHeader = request.headers.get("authorization");
    const cookieToken =
      request.cookies.get("access_token")?.value ||
      request.cookies.get("auth_token")?.value;
    const token =
      queryToken || authHeader?.replace("Bearer ", "") || cookieToken;

    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const baseUrl =
      process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      return NextResponse.json(
        { error: "Backend not configured" },
        { status: 500 }
      );
    }

    let parsedUrl: URL;
    try {
      parsedUrl = new URL(baseUrl);
    } catch {
      return NextResponse.json(
        { error: "Invalid backend URL" },
        { status: 500 }
      );
    }

    const allowedHostnames = ["backend", "ss.test.nycu.edu.tw"];
    if (!allowedHostnames.includes(parsedUrl.hostname)) {
      return NextResponse.json(
        { error: "Untrusted backend hostname" },
        { status: 500 }
      );
    }

    const backendUrl = new URL(
      `/api/v1/system-settings/file/${key}`,
      baseUrl
    ).toString();

    const response = await fetch(backendUrl, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: "Failed to fetch document" },
        { status: response.status }
      );
    }

    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/pdf";
    const contentDisposition =
      response.headers.get("content-disposition") || "inline";

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to retrieve document" },
      { status: 500 }
    );
  }
}
