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
import { SONNER_EMPTY_STYLE_HASH, SONNER_STYLE_HASH } from "@/lib/security-headers";

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
    expect(csp).toContain("img-src 'self' data: blob:");
    // ...but NOT via a wildcard scheme (issue #1223 finding B)
    expect(csp).not.toContain("img-src 'self' data: blob: https:");
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

  // ---------------------------------------------------------------------------
  // Issue #1273 (ZAP 10055 "CSP: style-src unsafe-inline", Medium).
  // `style-src 'self' 'unsafe-inline'` was commit bc2019f0's blunt fix for
  // shadcn/ui. The narrow form keeps `'unsafe-inline'` for style ATTRIBUTES only
  // (Radix/floating-ui positioning) while ELEMENT styles stay nonce-gated.
  // `toContain` would not catch a regression that appends ' unsafe-inline' back
  // onto style-src, so assert on the PARSED directive.
  // ---------------------------------------------------------------------------

  function directiveOf(csp: string, name: string): string {
    return csp.split("; ").find((d) => d === name || d.startsWith(`${name} `)) ?? "";
  }

  it("prod style-src is nonce-gated with NO unsafe-inline", () => {
    setNodeEnv("production");
    const res = middleware(mockRequest("https://ss.test.nycu.edu.tw/student/apply"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    const nonce = res.headers.get("X-CSP-Nonce");

    expect(directiveOf(csp, "style-src")).toBe(
      `style-src 'self' 'nonce-${nonce}' ${SONNER_STYLE_HASH} ${SONNER_EMPTY_STYLE_HASH}`,
    );
    // the regression this test exists for
    expect(directiveOf(csp, "style-src")).not.toContain("unsafe-inline");
    // and no unsafe-* survives anywhere in the production policy
    expect(csp).not.toContain("'unsafe-eval'");
  });

  it("prod keeps style-src-attr 'unsafe-inline' so Radix inline positioning still works", () => {
    setNodeEnv("production");
    const res = middleware(mockRequest("https://ss.test.nycu.edu.tw/student/apply"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    // Dropping this re-breaks every Popover/Dropdown/Dialog (bc2019f0's symptom).
    expect(directiveOf(csp, "style-src-attr")).toBe("style-src-attr 'unsafe-inline'");
  });

  it("the framable-preview branch does not fork a stale style-src", () => {
    setNodeEnv("production");
    const res = middleware(mockRequest("https://ss.test.nycu.edu.tw/api/v1/preview?fileId=1&type=pdf"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    const nonce = res.headers.get("X-CSP-Nonce");
    expect(directiveOf(csp, "style-src")).toBe(
      `style-src 'self' 'nonce-${nonce}' ${SONNER_STYLE_HASH} ${SONNER_EMPTY_STYLE_HASH}`,
    );
    expect(directiveOf(csp, "style-src-attr")).toBe("style-src-attr 'unsafe-inline'");
  });

  it("dev style-src stays relaxed (React Fast Refresh injects unnonced styles)", () => {
    setNodeEnv("development");
    const csp = middleware(mockRequest("http://localhost:3000/student/apply")).headers.get(
      "Content-Security-Policy",
    ) ?? "";
    // Deliberate dev/prod split: nonce-gating styles locally buys nothing and
    // fights HMR. The prod branch is the one under test above.
    expect(directiveOf(csp, "style-src")).toBe("style-src 'self' 'unsafe-inline'");
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
  // prefix. system-docs / supp-docs are the routes that previously sat outside
  // the prefix and recurred the "refused to connect" bug — they are the core
  // regression guard for the unification.
  const PREVIEW_ROUTES = [
    "https://ss.test.nycu.edu.tw/api/v1/preview?fileId=1&applicationId=1&type=pdf",
    "https://ss.test.nycu.edu.tw/api/v1/preview/terms?scholarshipType=phd",
    "https://ss.test.nycu.edu.tw/api/v1/preview/examples?documentId=1",
    "https://ss.test.nycu.edu.tw/api/v1/preview/system-docs?key=regulations_url",
    "https://ss.test.nycu.edu.tw/api/v1/preview/supp-docs?id=1",
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
      // String-prefix footgun guard: a `/api/v1/preview-*` SIBLING must NOT be
      // framable. The predicate matches exactly /api/v1/preview and /preview/<child>,
      // so this hypothetical sibling must keep the strict DENY posture.
      "https://ss.test.nycu.edu.tw/api/v1/preview-export?id=1",
    ]) {
      const res = middleware(mockRequest(url));
      const csp = res.headers.get("Content-Security-Policy") ?? "";
      expect(res.headers.get("X-Frame-Options")).toBe("DENY");
      expect(csp).toContain("frame-ancestors 'none'");
      expect(csp).not.toContain("frame-ancestors 'self'");
    }
  });

  // -------------------------------------------------------------------------
  // img-src wildcard (issue #1223 finding B). `toContain` is not enough here —
  // it still passes if someone appends ` https:` back on, which is exactly the
  // regression being guarded. Assert on the PARSED directive instead.
  // -------------------------------------------------------------------------

  function imgSrcOf(url: string): string {
    const csp = middleware(mockRequest(url)).headers.get("Content-Security-Policy") ?? "";
    return csp.split("; ").find((d) => d.startsWith("img-src ")) ?? "";
  }

  it("prod CSP img-src allows no wildcard scheme or host", () => {
    setNodeEnv("production");
    expect(imgSrcOf("https://ss.test.nycu.edu.tw/student/apply")).toBe("img-src 'self' data: blob:");
  });

  it("dev CSP img-src is byte-identical to prod img-src", () => {
    setNodeEnv("development");
    const dev = imgSrcOf("http://localhost:3000/student/apply");
    setNodeEnv("production");
    const prod = imgSrcOf("https://ss.test.nycu.edu.tw/student/apply");
    // A looser dev policy is what lets a remote <img> pass locally and break
    // only after deploy.
    expect(dev).toBe(prod);
  });

  it("img-src still permits blob: and data: so local file preview keeps working", () => {
    setNodeEnv("production");
    const imgSrc = imgSrcOf("https://ss.test.nycu.edu.tw/student/apply");
    // URL.createObjectURL previews (lib/file-preview.ts) and inline SVG.
    expect(imgSrc).toContain("blob:");
    expect(imgSrc).toContain("data:");
  });

  it("the framable-preview branch does not fork a stale img-src", () => {
    setNodeEnv("production");
    const res = middleware(mockRequest("https://ss.test.nycu.edu.tw/api/v1/preview?fileId=1&type=pdf"));
    const csp = res.headers.get("Content-Security-Policy") ?? "";
    expect(csp.split("; ").find((d) => d.startsWith("img-src "))).toBe("img-src 'self' data: blob:");
    expect(csp).toContain("frame-ancestors 'self'");
  });
});
