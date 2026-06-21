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

describe("middleware framing for same-origin preview proxies", () => {
  // Regression guard for the iframe "refused to connect" bug: a same-origin
  // /api/v1/preview* response rendered inside an <iframe> must NOT carry
  // `frame-ancestors 'none'` / `X-Frame-Options: DENY`, or the browser refuses
  // to frame it. `frame-src 'self'` on the PARENT page (the #885 fix) is not
  // enough — the CHILD response must also permit being framed same-origin.
  // nginx must agree (see nginx /api/v1/preview block); a DENY/SAMEORIGIN split
  // across the two layers is treated as invalid and still blocks.
  const originalEnv = process.env.NODE_ENV;
  afterEach(() => {
    Object.defineProperty(process.env, "NODE_ENV", { value: originalEnv, configurable: true });
  });
  function setNodeEnv(value: string) {
    Object.defineProperty(process.env, "NODE_ENV", { value, configurable: true });
  }

  // ALL framable file-preview proxies now live under the single /api/v1/preview
  // prefix. system-docs / supp-docs / application-document are the routes that
  // previously sat outside the prefix and recurred the "refused to connect" bug —
  // they are the core regression guard for the unification.
  const PREVIEW_ROUTES = [
    "https://ss.test.nycu.edu.tw/api/v1/preview?fileId=1&applicationId=1&type=pdf",
    "https://ss.test.nycu.edu.tw/api/v1/preview/terms?scholarshipType=phd",
    "https://ss.test.nycu.edu.tw/api/v1/preview/examples?documentId=1",
    "https://ss.test.nycu.edu.tw/api/v1/preview/system-docs?key=regulations_url",
    "https://ss.test.nycu.edu.tw/api/v1/preview/supp-docs?id=1",
    "https://ss.test.nycu.edu.tw/api/v1/preview/application-document?id=APP-1",
  ];

  it.each(PREVIEW_ROUTES)("prod: %s is framable same-origin (SAMEORIGIN + frame-ancestors 'self')", (url) => {
    setNodeEnv("production");
    const res = middleware(mockRequest(url));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(res.headers.get("X-Frame-Options")).toBe("SAMEORIGIN");
    expect(csp).toContain("frame-ancestors 'self'");
    expect(csp).not.toContain("frame-ancestors 'none'");
    // the rest of the strict CSP is unchanged
    expect(csp).toContain("object-src 'none'");
  });

  it("dev: /api/v1/preview is framable same-origin", () => {
    setNodeEnv("development");
    const res = middleware(mockRequest("http://localhost:3000/api/v1/preview?fileId=1&type=pdf"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(res.headers.get("X-Frame-Options")).toBe("SAMEORIGIN");
    expect(csp).toContain("frame-ancestors 'self'");
  });

  it("non-preview routes keep the strict DENY / frame-ancestors 'none' posture", () => {
    setNodeEnv("production");
    for (const url of [
      "https://ss.test.nycu.edu.tw/",
      "https://ss.test.nycu.edu.tw/student/apply",
      "https://ss.test.nycu.edu.tw/api/v1/applications/87",
      // /api/v1/download is the closest non-framable sibling of the relaxed
      // /api/v1/preview prefix (attachment download). Guard that the framing
      // relaxation does NOT leak to it.
      "https://ss.test.nycu.edu.tw/api/v1/download?fileId=1&applicationId=1&type=pdf",
    ]) {
      const res = middleware(mockRequest(url));
      const csp = res.headers.get("Content-Security-Policy") ?? "";
      expect(res.headers.get("X-Frame-Options")).toBe("DENY");
      expect(csp).toContain("frame-ancestors 'none'");
      expect(csp).not.toContain("frame-ancestors 'self'");
    }
  });
});
