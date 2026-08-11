/**
 * Issue #1223 section B — the middleware and the nginx configs BOTH emit
 * Permissions-Policy / Cross-Origin-Opener-Policy / Cross-Origin-Resource-Policy.
 *
 * nginx `add_header` APPENDS to the upstream (Next.js) response, so a page served
 * through nginx carries each of these headers TWICE. Permissions-Policy is an
 * RFC 8941 Structured Dictionary: duplicate field lines are comma-joined and
 * duplicate keys are last-wins. Two IDENTICAL values are therefore idempotent —
 * but two DIVERGENT values silently union, with nginx (which appends last)
 * winning every overlapping key. That failure is invisible in both codebases.
 *
 * This test is the thing that makes the duplication safe: it reads the actual
 * nginx configs off disk and pins every declaration to the shared TS constant.
 */

import { readFileSync } from "fs";
import path from "path";

import { middleware } from "@/middleware";
import {
  CROSS_ORIGIN_OPENER_POLICY,
  CROSS_ORIGIN_RESOURCE_POLICY,
  PERMISSIONS_POLICY,
} from "@/lib/security-headers";

function mockRequest(url: string) {
  return {
    headers: new Headers(),
    nextUrl: new URL(url),
  } as unknown as Parameters<typeof middleware>[0];
}

const NGINX_CONFIGS = ["nginx/nginx.prod.conf", "nginx/nginx.staging.conf"] as const;

function readConf(relPath: string): string {
  return readFileSync(path.resolve(__dirname, "../..", relPath), "utf8");
}

/** Every `add_header <name> "<value>" always;` value declared in a config. */
function declaredValues(conf: string, header: string): string[] {
  const re = new RegExp(`add_header\\s+${header}\\s+"([^"]*)"`, "g");
  return [...conf.matchAll(re)].map((m) => m[1]);
}

describe("nginx <-> middleware security-header parity (issue #1223 B)", () => {
  const HEADERS = [
    ["Permissions-Policy", PERMISSIONS_POLICY],
    ["Cross-Origin-Opener-Policy", CROSS_ORIGIN_OPENER_POLICY],
    ["Cross-Origin-Resource-Policy", CROSS_ORIGIN_RESOURCE_POLICY],
  ] as const;

  describe.each(NGINX_CONFIGS)("%s", (relPath) => {
    const conf = readConf(relPath);

    it.each(HEADERS)("declares %s at least once", (header) => {
      expect(declaredValues(conf, header).length).toBeGreaterThan(0);
    });

    it.each(HEADERS)("every %s declaration matches the shared TS constant", (header, expected) => {
      for (const value of declaredValues(conf, header)) {
        expect(value).toBe(expected);
      }
    });

    /**
     * nginx drops ALL inherited add_headers in any block that declares one of its
     * own. Both configs have a `/api/v1/preview` block and an `/api/email/` block
     * that re-declare X-Frame-Options SAMEORIGIN — each MUST also re-declare the
     * three new headers or they silently vanish for exactly the routes that serve
     * framed file/email previews.
     */
    it("re-declares all three in every block that re-declares X-Frame-Options SAMEORIGIN", () => {
      const sameOriginBlocks = conf.split("add_header X-Frame-Options SAMEORIGIN").length - 1;
      expect(sameOriginBlocks).toBeGreaterThan(0);

      for (const [header] of ["Permissions-Policy", "Cross-Origin-Opener-Policy"].map(
        (h) => [h] as const
      )) {
        // one server-level declaration + one per SAMEORIGIN block
        expect(declaredValues(conf, header)).toHaveLength(sameOriginBlocks + 1);
      }
    });

    /**
     * Static-asset blocks declare their own Cache-Control, which drops every
     * inherited add_header — and frontend/middleware.ts's matcher EXCLUDES those
     * same paths (`_next/static`, `.js`/`.css`/image extensions). Without an
     * explicit re-declaration they are covered by NEITHER layer.
     *
     * Only CORP is required there: it is the header that governs no-cors
     * SUBRESOURCE embedding. Permissions-Policy and COOP are document-scoped and
     * inert on a JS/CSS response, so they are deliberately not repeated onto
     * every cached asset.
     */
    it("re-declares CORP in every block that declares its own Cache-Control", () => {
      const cacheControlBlocks = conf.split('add_header Cache-Control "public, immutable"').length - 1;
      expect(cacheControlBlocks).toBeGreaterThan(0);

      const sameOriginBlocks = conf.split("add_header X-Frame-Options SAMEORIGIN").length - 1;
      expect(declaredValues(conf, "Cross-Origin-Resource-Policy")).toHaveLength(
        1 + sameOriginBlocks + cacheControlBlocks
      );
    });

    it("does NOT set Cross-Origin-Embedder-Policy", () => {
      // require-corp would break the same-origin /api/v1/preview iframes (the
      // caveat raised in #1223) and buys nothing: no SharedArrayBuffer anywhere.
      // Match the DIRECTIVE, not the bare name — the configs mention the header
      // in a comment explaining precisely why it is absent.
      expect(declaredValues(conf, "Cross-Origin-Embedder-Policy")).toHaveLength(0);
    });
  });

  /**
   * The nginx assertions above are worthless if the OTHER layer stops emitting
   * these headers — nginx only covers requests that actually traverse it, so
   * localhost dev and any non-nginx path depend on the middleware.
   */
  describe("frontend/middleware.ts emits the same values", () => {
    const URLS = [
      "https://ss.test.nycu.edu.tw/student/apply",
      // The framable-preview branch must not fork a different set.
      "https://ss.test.nycu.edu.tw/api/v1/preview?fileId=1&type=pdf",
    ];

    it.each(URLS)("%s carries all three headers with the shared values", (url) => {
      const headers = middleware(mockRequest(url)).headers;
      expect(headers.get("Permissions-Policy")).toBe(PERMISSIONS_POLICY);
      expect(headers.get("Cross-Origin-Opener-Policy")).toBe(CROSS_ORIGIN_OPENER_POLICY);
      expect(headers.get("Cross-Origin-Resource-Policy")).toBe(CROSS_ORIGIN_RESOURCE_POLICY);
    });

    it("does NOT emit Cross-Origin-Embedder-Policy", () => {
      const headers = middleware(mockRequest("https://ss.test.nycu.edu.tw/student/apply")).headers;
      expect(headers.get("Cross-Origin-Embedder-Policy")).toBeNull();
    });
  });

  it("Permissions-Policy uses the bare `self` token, never CSP's quoted 'self'", () => {
    // `clipboard-write=('self')` is invalid and the whole entry is silently
    // dropped — the classic Permissions-Policy footgun.
    expect(PERMISSIONS_POLICY).not.toContain("'self'");
    expect(PERMISSIONS_POLICY).toContain("clipboard-write=(self)");
  });

  it("keeps clipboard-write enabled for the debug panel's copy buttons", () => {
    // components/debug-panel.tsx calls navigator.clipboard.writeText, and it is
    // rendered on localhost AND ss.test.nycu.edu.tw. clipboard-write=() would
    // break it silently (production strips console).
    expect(PERMISSIONS_POLICY).toContain("clipboard-write=(self)");
    expect(PERMISSIONS_POLICY).not.toContain("clipboard-write=()");
    // Paste events are not gated by clipboard-read, so it stays denied.
    expect(PERMISSIONS_POLICY).toContain("clipboard-read=()");
  });
});
