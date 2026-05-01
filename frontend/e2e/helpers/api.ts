const API_V1 = "http://localhost:8000/api/v1";

export interface ApiResult<T> {
  status: number;
  ok: boolean;
  body: T;
  traceId: string | null;
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
