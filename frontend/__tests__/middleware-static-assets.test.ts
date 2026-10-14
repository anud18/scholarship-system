/**
 * Static-asset headers from the middleware (release ZAP baseline, 2026-10-14).
 *
 * The baseline scan hits `next start` directly — no nginx — so asset URLs the
 * page matcher skips were served bare: /favicon.ico (Next's HTML 404) filed
 * "CSP Header Not Set" (Medium), and chunks / public SVGs filed missing CORP,
 * nosniff and Permissions-Policy (Low).
 */
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";

import { config, middleware } from "@/middleware";
import {
  CROSS_ORIGIN_RESOURCE_POLICY,
  PERMISSIONS_POLICY,
  STATIC_ASSET_CSP,
} from "@/lib/security-headers";

function mockRequest(url: string) {
  return {
    headers: new Headers(),
    nextUrl: new URL(url),
  } as unknown as Parameters<typeof middleware>[0];
}

const ORIGIN = "http://localhost:3100";

// The exact URLs the baseline flagged, plus a font.
const PUBLIC_ASSETS = ["/favicon.ico", "/icon.svg", "/nycu-favicon.svg", "/fonts/x.woff2"];
const CHUNKS = [
  "/_next/static/chunks/webpack-d8521aaec7e9ba62.js",
  "/_next/static/css/86498b921adc386d.css",
];

describe("middleware matcher", () => {
  it.each([...PUBLIC_ASSETS, ...CHUNKS])("runs the middleware for %s", (path) => {
    expect(unstable_doesMiddlewareMatch({ config, url: `${ORIGIN}${path}` })).toBe(true);
  });

  it("still runs it for pages and API routes", () => {
    for (const path of ["/", "/student/apply", "/api/v1/preview"]) {
      expect(unstable_doesMiddlewareMatch({ config, url: `${ORIGIN}${path}` })).toBe(true);
    }
  });

  it("never gives the pdf.js worker STATIC_ASSET_CSP (a worker obeys its own CSP)", () => {
    // .mjs was never excluded from the page matcher; it keeps the page branch.
    const headers = middleware(mockRequest(`${ORIGIN}/pdf.worker.min.mjs`)).headers;
    expect(headers.get("Content-Security-Policy")).not.toBe(STATIC_ASSET_CSP);
  });
});

describe("middleware static-asset headers", () => {
  it.each(PUBLIC_ASSETS)("%s gets STATIC_ASSET_CSP, CORP and nosniff", (path) => {
    const headers = middleware(mockRequest(`${ORIGIN}${path}`)).headers;
    expect(headers.get("Content-Security-Policy")).toBe(STATIC_ASSET_CSP);
    expect(headers.get("Cross-Origin-Resource-Policy")).toBe(CROSS_ORIGIN_RESOURCE_POLICY);
    expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
    // no per-request nonce machinery on assets
    expect(headers.get("X-CSP-Nonce")).toBeNull();
  });

  it.each(CHUNKS)("%s gets CORP, nosniff and Permissions-Policy but NO CSP", (path) => {
    const headers = middleware(mockRequest(`${ORIGIN}${path}`)).headers;
    expect(headers.get("Content-Security-Policy")).toBeNull();
    expect(headers.get("Cross-Origin-Resource-Policy")).toBe(CROSS_ORIGIN_RESOURCE_POLICY);
    expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
    expect(headers.get("Permissions-Policy")).toBe(PERMISSIONS_POLICY);
  });

  it("an /api route ending in an image extension keeps the page policy", () => {
    const headers = middleware(mockRequest(`${ORIGIN}/api/v1/files/1/photo.png`)).headers;
    expect(headers.get("Content-Security-Policy")).not.toBe(STATIC_ASSET_CSP);
    expect(headers.get("X-CSP-Nonce")).not.toBeNull();
  });

  it("pages keep the nonce CSP", () => {
    const headers = middleware(mockRequest(`${ORIGIN}/student/apply`)).headers;
    expect(headers.get("Content-Security-Policy")).toContain("nonce-");
  });
});
