import type { Browser, BrowserContext } from "@playwright/test";
import { BACKEND_URL, FRONTEND_URL } from "./env";

const API_BASE = BACKEND_URL;

export interface AuthSession {
  token: string;
  userId: number;
  user: Record<string, unknown>;
  traceId: string | null;
}

export interface LoginResult extends AuthSession {
  context: BrowserContext;
}

async function fetchMockSsoSession(nycuId: string): Promise<AuthSession> {
  const r = await fetch(`${API_BASE}/api/v1/auth/mock-sso/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nycu_id: nycuId }),
  });
  const body = (await r.json()) as {
    success?: boolean;
    message?: string;
    data?: {
      access_token?: string;
      user?: Record<string, unknown> & { id?: number };
    };
  };
  if (!r.ok || !body.success || !body.data?.access_token || !body.data?.user) {
    throw new Error(
      `mock-sso login failed for ${nycuId}: HTTP ${r.status} ${body.message ?? "(no message)"}`
    );
  }
  const token = body.data.access_token;
  const user = body.data.user;
  const userId = typeof user.id === "number" ? user.id : Number(user.id);
  if (!Number.isFinite(userId)) {
    throw new Error(`mock-sso login for ${nycuId}: missing numeric user.id`);
  }
  return { token, userId, user, traceId: r.headers.get("x-trace-id") };
}

/**
 * Inject an authenticated mock-SSO session into an EXISTING context.
 *
 * Use this with the built-in `context`/`page` test fixtures (which the runner
 * owns) when you need Playwright to record + attach video/trace — manually
 * created `browser.newContext()` contexts (see {@link loginAs}) only get trace,
 * never video, because `recordVideo` is a creation-time-only option the runner
 * does not retrofit onto contexts it did not create.
 */
export async function authContext(
  context: BrowserContext,
  nycuId: string
): Promise<AuthSession> {
  const session = await fetchMockSsoSession(nycuId);
  // useAuth (frontend/hooks/use-auth.tsx:38-62) reads BOTH 'auth_token' and 'user'.
  await context.addInitScript(
    ({ t, u }: { t: string; u: string }) => {
      localStorage.setItem("auth_token", t);
      localStorage.setItem("user", u);
    },
    { t: session.token, u: JSON.stringify(session.user) }
  );
  await context.setExtraHTTPHeaders({
    Authorization: `Bearer ${session.token}`,
  });
  return session;
}

export async function loginAs(
  browser: Browser,
  nycuId: string
): Promise<LoginResult> {
  const context = await browser.newContext({ baseURL: FRONTEND_URL });
  const session = await authContext(context, nycuId);
  return { context, ...session };
}
