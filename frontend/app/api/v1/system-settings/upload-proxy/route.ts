import { NextRequest, NextResponse } from "next/server";

const ALLOWED_KEYS = new Set(["regulations_url", "sample_document_url"]);

export async function POST(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const key = searchParams.get("key");

    if (!key || !ALLOWED_KEYS.has(key)) {
      return NextResponse.json({ error: "Invalid key" }, { status: 400 });
    }

    const authHeader = request.headers.get("authorization");
    if (!authHeader) {
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
      `/api/v1/system-settings/upload/${key}`,
      baseUrl
    ).toString();

    const formData = await request.formData();

    const response = await fetch(backendUrl, {
      method: "POST",
      headers: { Authorization: authHeader },
      body: formData,
    });

    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to proxy upload" },
      { status: 500 }
    );
  }
}
