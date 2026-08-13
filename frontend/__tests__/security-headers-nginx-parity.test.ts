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
  CROSS_ORIGIN_EMBEDDER_POLICY,
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
    ["Cross-Origin-Embedder-Policy", CROSS_ORIGIN_EMBEDDER_POLICY],
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
     * document-scoped headers or they silently vanish for exactly the routes that
     * serve framed file/email previews. COEP is the sharpest of these: a
     * require-corp parent page refuses to frame any response that does not
     * itself declare COEP, so a missing re-declaration = blank preview iframes.
     */
    it("re-declares the document-scoped headers in every block that re-declares X-Frame-Options SAMEORIGIN", () => {
      const sameOriginBlocks = conf.split("add_header X-Frame-Options SAMEORIGIN").length - 1;
      const monitoringBlocks = conf.split("location ^~ /monitoring").length - 1;
      const healthBlocks = conf.split("location /health").length - 1;
      expect(sameOriginBlocks).toBeGreaterThan(0);
      expect(monitoringBlocks).toBe(1);
      expect(healthBlocks).toBe(1);

      // server level + each SAMEORIGIN block + /monitoring + /health
      for (const [header] of ["Permissions-Policy", "Cross-Origin-Opener-Policy"].map(
        (h) => [h] as const
      )) {
        expect(declaredValues(conf, header)).toHaveLength(
          1 + sameOriginBlocks + monitoringBlocks + healthBlocks
        );
      }

      // COEP is deliberately ABSENT from /monitoring: Grafana loads
      // cross-origin no-cors images (gravatars, grafana.com panels) that an
      // enforced require-corp would block, and it is the one document prefix
      // where nginx's COEP is not deduplicated against the Next.js middleware.
      expect(declaredValues(conf, "Cross-Origin-Embedder-Policy")).toHaveLength(
        1 + sameOriginBlocks + healthBlocks
      );
    });

    /**
     * Static-asset blocks declare their own Cache-Control, which drops every
     * inherited add_header — and frontend/middleware.ts's matcher EXCLUDES those
     * same paths (`_next/static`, `.js`/`.css`/image extensions). Without an
     * explicit re-declaration they are covered by NEITHER layer. The same holds
     * for the bare `/pdf.worker.min.mjs` block.
     *
     * Each such block re-declares CORP (governs no-cors SUBRESOURCE embedding),
     * HSTS and Referrer-Policy (AppScan 2026-08-13 flagged static chunks missing
     * both). Permissions-Policy and COOP/COEP are document-scoped and inert on a
     * JS/CSS response, so they are deliberately not repeated onto cached assets.
     *
     * The Cache-Control string is pinned to the SINGLE-declaration form — the
     * old `expires 1y` + `"public, immutable"` pair emitted two Cache-Control
     * headers on every asset (an AppScan unnecessary-header finding).
     */
    it("re-declares CORP/HSTS/Referrer-Policy in every subresource block", () => {
      expect(conf).not.toContain('add_header Cache-Control "public, immutable"');
      // Directive form only — comments explaining the removal may say "expires".
      expect(conf).not.toMatch(/^\s*expires\s/m);
      const cacheControlBlocks =
        conf.split('add_header Cache-Control "public, max-age=31536000, immutable"').length - 1;
      expect(cacheControlBlocks).toBeGreaterThan(0);

      const sameOriginBlocks = conf.split("add_header X-Frame-Options SAMEORIGIN").length - 1;
      const workerBlocks = conf.split("location = /pdf.worker.min.mjs").length - 1;
      const monitoringBlocks = conf.split("location ^~ /monitoring").length - 1;
      const healthBlocks = conf.split("location /health").length - 1;
      expect(workerBlocks).toBe(1);

      const expected =
        1 + sameOriginBlocks + cacheControlBlocks + workerBlocks + monitoringBlocks + healthBlocks;
      expect(declaredValues(conf, "Cross-Origin-Resource-Policy")).toHaveLength(expected);
      expect(declaredValues(conf, "Strict-Transport-Security")).toHaveLength(expected);
      expect(declaredValues(conf, "Referrer-Policy")).toHaveLength(expected);
    });

    /**
     * COOP/COEP/CORP are RFC 8941 sf-item headers: when nginx add_header
     * APPENDS to the identical header the Next.js middleware already set, the
     * duplicated value ("same-origin, same-origin") is a parse FAILURE that
     * browsers treat as unsafe-none — crossOriginIsolated was observed false
     * behind nginx. The upstream copy must therefore be hidden wherever nginx
     * emits its own: once at server level, and re-declared in the pdf.worker
     * block (whose own proxy_hide_header lines stop inheritance).
     */
    it("hides the upstream copy of every sf-item header nginx re-emits", () => {
      for (const header of [
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Embedder-Policy",
        "Cross-Origin-Resource-Policy",
      ]) {
        expect(conf.split(`proxy_hide_header ${header};`).length - 1).toBe(2);
      }

      // Next.js sets its own Cache-Control on every static path nginx caches
      // (immutable for /_next/static, max-age=0 for /public) — each block that
      // declares the immutable value must hide the upstream copy or the
      // response carries two Cache-Control lines (the AppScan finding) with
      // the upstream max-age=0 winning for /public assets.
      const cacheControlBlocks =
        conf.split('add_header Cache-Control "public, max-age=31536000, immutable"').length - 1;
      expect(conf.split("proxy_hide_header Cache-Control;").length - 1).toBe(cacheControlBlocks);
    });

    it("pins HSTS to the preload form everywhere it is declared", () => {
      const values = declaredValues(conf, "Strict-Transport-Security");
      expect(values.length).toBeGreaterThan(0);
      for (const value of values) {
        expect(value).toBe("max-age=31536000; includeSubDomains; preload");
      }
    });

    it("answers hidden-path probes with 404, never a 403 that confirms existence", () => {
      // AppScan 2026-08-13: 55 "Hidden Directory Detected" findings — `deny all`
      // (403) on dotfile paths reveals they exist. Both probe blocks must
      // `return 404` and no location may use `deny all` outside /nginx_status.
      expect(conf).toContain("location ~ /\\.");
      const denyAlls = conf.split("deny all;").length - 1;
      const statusBlocks = conf.split("location /nginx_status").length - 1;
      expect(denyAlls).toBe(statusBlocks);
    });

    it("rejects rate-limited requests with 429, not the default 503", () => {
      // AppScan files any 5xx as an "Application Error" (23 findings).
      expect(conf).toContain("limit_req_status 429;");
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

    it.each(URLS)("%s carries all four headers with the shared values", (url) => {
      const headers = middleware(mockRequest(url)).headers;
      expect(headers.get("Permissions-Policy")).toBe(PERMISSIONS_POLICY);
      expect(headers.get("Cross-Origin-Opener-Policy")).toBe(CROSS_ORIGIN_OPENER_POLICY);
      expect(headers.get("Cross-Origin-Resource-Policy")).toBe(CROSS_ORIGIN_RESOURCE_POLICY);
      expect(headers.get("Cross-Origin-Embedder-Policy")).toBe(CROSS_ORIGIN_EMBEDDER_POLICY);
    });

    it("marks every /api response no-store, and leaves pages alone", () => {
      // AppScan 2026-08-13 "Cacheable SSL Page Found": authenticated JSON/file
      // responses must never be cacheable. Framed preview responses included —
      // they are auth-gated documents, not static assets.
      const api = middleware(
        mockRequest("https://ss.test.nycu.edu.tw/api/v1/preview?fileId=1&type=pdf")
      ).headers;
      expect(api.get("Cache-Control")).toBe("no-store, no-cache, must-revalidate");
      expect(api.get("Pragma")).toBe("no-cache");

      const page = middleware(mockRequest("https://ss.test.nycu.edu.tw/student/apply")).headers;
      expect(page.get("Cache-Control")).toBeNull();
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
