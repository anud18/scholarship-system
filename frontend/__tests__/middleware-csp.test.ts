/**
 * Unit tests for the CSP middleware (frontend/middleware.ts).
 *
 * Regression guard for PR #885: document preview iframes (a same-origin
 * /api/v1/preview proxy, and a blob: URL for a just-selected local PDF) are
 * only allowed to render if the CSP carries `frame-src 'self' blob:`. With no
 * frame-src directive the browser falls back to `default-src 'self'`, which
 * blocks blob: frames and silently renders a blank preview. These tests pin
 * the directive in BOTH the dev and prod CSP branches and confirm the
 * clickjacking protections were not loosened in the process.
 */
import { middleware } from "@/middleware";

// The middleware only reads request.headers and request.nextUrl.hostname, so a
// minimal stand-in is enough (NextResponse is the real one from next/server).
function mockRequest(url: string) {
  return {
    headers: new Headers(),
    nextUrl: new URL(url),
  } as unknown as Parameters<typeof middleware>[0];
}

describe("middleware Content-Security-Policy", () => {
  const originalEnv = process.env.NODE_ENV;

  afterEach(() => {
    Object.defineProperty(process.env, "NODE_ENV", { value: originalEnv, configurable: true });
  });

  function setNodeEnv(value: string) {
    Object.defineProperty(process.env, "NODE_ENV", { value, configurable: true });
  }

  it("dev CSP allows frame-src 'self' blob: for blob/same-origin PDF preview", () => {
    setNodeEnv("development");
    const res = middleware(mockRequest("http://localhost:3000/student/apply"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain("frame-src 'self' blob:");
    // blob: images must still be allowed (the preview dialog renders images via <img>)
    expect(csp).toContain("img-src 'self' data: blob: https:");
  });

  it("prod CSP allows frame-src 'self' blob: and keeps clickjacking protections", () => {
    setNodeEnv("production");
    const res = middleware(mockRequest("https://ss.test.nycu.edu.tw/student/apply"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    // the #885 fix
    expect(csp).toContain("frame-src 'self' blob:");
    // and it must NOT have loosened the directive to anything wider than blob:
    expect(csp).not.toContain("frame-src 'self' blob: https:");
    expect(csp).not.toContain("frame-src *");
    // clickjacking / object protections intact
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
    expect(res.headers.get("X-Frame-Options")).toBe("DENY");
  });

  it("emits a per-request nonce and exposes it for nginx", () => {
    setNodeEnv("production");
    const res = middleware(mockRequest("https://ss.test.nycu.edu.tw/"));
    const nonce = res.headers.get("X-CSP-Nonce");
    expect(nonce).toBeTruthy();
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp).toContain(`'nonce-${nonce}'`);
  });
});
