import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

const INTERNAL_API_URL = process.env.INTERNAL_API_URL || "http://backend:8000";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const fileId = searchParams.get("fileId");
    const filename = searchParams.get("filename");
    const type = searchParams.get("type");
    const applicationId = searchParams.get("applicationId");
    const userId = searchParams.get("userId");
    const rosterId = searchParams.get("rosterId");
    let token = searchParams.get("token");

    // 如果沒有提供 token，嘗試從 cookies 獲取
    if (!token) {
      const cookieStore = await cookies();
      token = cookieStore.get("token")?.value || null;
    }

    // 處理造冊預覽
    if (type === "roster") {
      return handleRosterPreview(rosterId, token, searchParams);
    }

    if (!fileId) {
      return NextResponse.json(
        { error: "File ID is required" },
        { status: 400 }
      );
    }

    // For user profile documents, userId can be used instead of applicationId
    if (!applicationId && !userId) {
      return NextResponse.json(
        { error: "Application ID or User ID is required" },
        { status: 400 }
      );
    }

    if (!token) {
      return NextResponse.json(
        { error: "Access token is required" },
        { status: 400 }
      );
    }

    // 預設使用內部 Docker 網路地址來訪問後端，如果沒有設定則使用 NEXT_PUBLIC_API_URL
    let backendUrl;
    if (applicationId) {
      // Application file preview
      backendUrl = `${process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/files/applications/${applicationId}/files/${fileId}?token=${token}`;
    } else if (userId) {
      // User profile file preview (e.g., bank document)
      backendUrl = `${process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/user-profiles/files/bank_documents/${fileId}?token=${token}`;
    } else {
      return NextResponse.json(
        { error: "Invalid file context" },
        { status: 400 }
      );
    }

    console.log("Preview API called:", {
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

    // 根據文件類型設置適當的 Content-Type
    let finalContentType = contentType;
    if (type === "pdf") {
      finalContentType = "application/pdf";
    } else if (type === "image") {
      finalContentType = contentType.startsWith("image/")
        ? contentType
        : "image/jpeg";
    }

    // 處理中文文件名編碼
    let contentDisposition = "inline";
    if (filename) {
      // 使用 encodeURIComponent 來正確編碼中文文件名
      const encodedFilename = encodeURIComponent(filename);
      contentDisposition = `inline; filename*=UTF-8''${encodedFilename}`;
    }

    // 返回文件給用戶
    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": finalContentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600", // 1小時緩存
      },
    });
  } catch (error) {
    console.error("File preview error:", error);
    return NextResponse.json(
      { error: "Failed to preview file" },
      { status: 500 }
    );
  }
}

// 處理造冊預覽
async function handleRosterPreview(
  rosterId: string | null,
  token: string | null,
  searchParams: URLSearchParams
) {
  if (!rosterId) {
    return NextResponse.json(
      { error: "Roster ID is required" },
      { status: 400 }
    );
  }

  if (!token) {
    return NextResponse.json(
      { error: "Authentication required" },
      { status: 401 }
    );
  }

  try {
    // 獲取查詢參數
    const template_name = searchParams.get("template_name") || "STD_UP_MIXLISTA";
    const include_header = searchParams.get("include_header") !== "false";
    const max_preview_rows = searchParams.get("max_preview_rows") || "10";
    const include_excluded = searchParams.get("include_excluded") === "true";

    // 構建後端 URL
    const backendUrl = new URL(
      `/api/v1/payment-rosters/${rosterId}/preview`,
      INTERNAL_API_URL
    );
    backendUrl.searchParams.set("template_name", template_name);
    backendUrl.searchParams.set("include_header", String(include_header));
    backendUrl.searchParams.set("max_preview_rows", max_preview_rows);
    backendUrl.searchParams.set("include_excluded", String(include_excluded));

    console.log(`[Roster Preview] Fetching: ${backendUrl.toString()}`);

    // 調用後端 API
    const response = await fetch(backendUrl.toString(), {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(
        `[Roster Preview] Backend error: ${response.status} - ${errorText}`
      );
      return NextResponse.json(
        {
          success: false,
          message: `Backend error: ${response.status}`,
        },
        { status: response.status }
      );
    }

    const data = await response.json();

    // 返回 HTML 預覽頁面
    if (data.success && data.data) {
      const htmlContent = generateRosterPreviewHTML(data.data);
      return new NextResponse(htmlContent, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
        },
      });
    }

    return NextResponse.json(data);
  } catch (error) {
    console.error("[Roster Preview] Error:", error);
    return NextResponse.json(
      {
        success: false,
        message: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}

// 生成造冊預覽 HTML
function generateRosterPreviewHTML(data: any): string {
  const { roster_code, preview_data, total_rows, column_headers, validation_result } = data;

  return `
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>造冊預覽 - ${roster_code}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans TC", sans-serif;
      background: #f3f4f6;
      padding: 20px;
    }
    .container {
      max-width: 1400px;
      margin: 0 auto;
      background: white;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
      overflow: hidden;
    }
    .header {
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 30px;
    }
    .header h1 {
      font-size: 28px;
      margin-bottom: 8px;
    }
    .header p {
      opacity: 0.9;
      font-size: 14px;
    }
    .info-bar {
      background: #f9fafb;
      padding: 20px 30px;
      border-bottom: 1px solid #e5e7eb;
      display: flex;
      gap: 30px;
      flex-wrap: wrap;
    }
    .info-item {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .info-label {
      color: #6b7280;
      font-size: 14px;
    }
    .info-value {
      color: #111827;
      font-weight: 600;
      font-size: 16px;
    }
    .table-container {
      overflow-x: auto;
      padding: 30px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    thead {
      background: #f9fafb;
    }
    th {
      padding: 12px 16px;
      text-align: left;
      font-weight: 600;
      color: #374151;
      border-bottom: 2px solid #e5e7eb;
      white-space: nowrap;
    }
    td {
      padding: 12px 16px;
      border-bottom: 1px solid #f3f4f6;
      color: #1f2937;
    }
    tbody tr:hover {
      background: #f9fafb;
    }
    .validation {
      margin: 20px 30px;
      padding: 16px;
      background: ${validation_result?.is_valid ? '#d1fae5' : '#fee2e2'};
      border-radius: 6px;
      color: ${validation_result?.is_valid ? '#065f46' : '#991b1b'};
    }
    .validation h3 {
      margin-bottom: 8px;
      font-size: 16px;
    }
    .validation ul {
      margin-left: 20px;
    }
    .validation li {
      margin: 4px 0;
    }
    .footer {
      padding: 20px 30px;
      background: #f9fafb;
      border-top: 1px solid #e5e7eb;
      text-align: center;
      color: #6b7280;
      font-size: 13px;
    }
    .empty-state {
      padding: 60px 30px;
      text-align: center;
      color: #9ca3af;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📋 造冊預覽</h1>
      <p>造冊代碼: ${roster_code}</p>
    </div>

    <div class="info-bar">
      <div class="info-item">
        <span class="info-label">總筆數:</span>
        <span class="info-value">${total_rows || 0}</span>
      </div>
      <div class="info-item">
        <span class="info-label">預覽筆數:</span>
        <span class="info-value">${preview_data?.length || 0}</span>
      </div>
    </div>

    ${validation_result && !validation_result.is_valid ? `
    <div class="validation">
      <h3>⚠️ 驗證警告</h3>
      <ul>
        ${validation_result.errors?.map((error: string) => `<li>${error}</li>`).join('') || ''}
      </ul>
    </div>
    ` : ''}

    <div class="table-container">
      ${preview_data && preview_data.length > 0 ? `
      <table>
        <thead>
          <tr>
            ${column_headers?.map((header: string) => `<th>${header}</th>`).join('') || '<th>無資料</th>'}
          </tr>
        </thead>
        <tbody>
          ${preview_data.map((row: any[]) => `
            <tr>
              ${row.map((cell: any) => `<td>${cell !== null && cell !== undefined ? cell : '-'}</td>`).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
      ` : `
      <div class="empty-state">
        <p style="font-size: 18px; margin-bottom: 8px;">📭 無預覽資料</p>
        <p>此造冊目前沒有任何資料可供預覽</p>
      </div>
      `}
    </div>

    <div class="footer">
      <p>此為預覽資料，僅顯示前 ${preview_data?.length || 0} 筆記錄</p>
      <p style="margin-top: 8px; font-size: 12px;">Generated at ${new Date().toLocaleString('zh-TW')}</p>
    </div>
  </div>
</body>
</html>
  `;
}
