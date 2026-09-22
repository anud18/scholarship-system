import { BACKEND_URL } from "./env";

const API_V1 = `${BACKEND_URL}/api/v1`;

export interface ApiResult<T> {
  status: number;
  ok: boolean;
  body: T;
  traceId: string | null;
}

// 1x1 transparent PNG — small enough for the base64 query-string endpoint and
// a real image, so the backend's PIL/MIME validation accepts it.
const PASSBOOK_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==";

/**
 * Put a 存摺封面 on the student's profile. `POST /applications/{id}/submit`
 * refuses an application whose profile has none, and the seed never uploads
 * one, so API-driven specs must plant it before submitting.
 */
export async function ensureBankDocument(token: string): Promise<void> {
  const query = new URLSearchParams({
    photo_data: PASSBOOK_PNG_BASE64,
    filename: "e2e-passbook.png",
    content_type: "image/png",
  });
  const res = await apiAs<{ success?: boolean; detail?: string }>(
    token,
    "POST",
    `/user-profiles/me/bank-document?${query.toString()}`,
  );
  if (!res.ok) {
    throw new Error(`ensureBankDocument failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`);
  }
}

export async function apiAs<T = unknown>(
  token: string,
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
  let serialized: string | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    serialized = JSON.stringify(body);
  }
  const r = await fetch(`${API_V1}${path}`, {
    method,
    headers,
    body: serialized,
  });
  let parsed: T;
  const text = await r.text();
  try {
    parsed = (text ? JSON.parse(text) : null) as T;
  } catch {
    parsed = text as unknown as T;
  }
  return {
    status: r.status,
    ok: r.ok,
    body: parsed,
    traceId: r.headers.get("x-trace-id"),
  };
}
