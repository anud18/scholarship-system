import type { Browser, BrowserContext } from "@playwright/test";

const API_BASE = "http://localhost:8000";

export interface LoginResult {
  context: BrowserContext;
  token: string;
  userId: number;
  user: Record<string, unknown>;
  traceId: string | null;
}

export async function loginAs(browser: Browser, nycuId: string): Promise<LoginResult> {
  const r = await fetch(`${API_BASE}/api/v1/auth/mock-sso/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nycu_id: nycuId }),
  });
  const body = (await r.json()) as {
    success?: boolean;
    message?: string;
    data?: { access_token?: string; user?: Record<string, unknown> & { id?: number } };
  };
  if (!r.ok || !body.success || !body.data?.access_token || !body.data?.user) {
    throw new Error(
      `mock-sso login failed for ${nycuId}: HTTP ${r.status} ${body.message ?? "(no message)"}`,
    );
  }
  const token = body.data.access_token;
  const user = body.data.user;
  const userId = typeof user.id === "number" ? user.id : Number(user.id);
  if (!Number.isFinite(userId)) {
    throw new Error(`mock-sso login for ${nycuId}: missing numeric user.id`);
  }

  const context = await browser.newContext({ baseURL: "http://localhost:3000" });
  // useAuth (frontend/hooks/use-auth.tsx:38-62) reads BOTH 'auth_token' and 'user'.
  await context.addInitScript(
    ({ t, u }: { t: string; u: string }) => {
      localStorage.setItem("auth_token", t);
      localStorage.setItem("user", u);
    },
    { t: token, u: JSON.stringify(user) },
  );
  await context.setExtraHTTPHeaders({ Authorization: `Bearer ${token}` });

  return { context, token, userId, user, traceId: r.headers.get("x-trace-id") };
}
