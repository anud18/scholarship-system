/**
 * Static-asset headers from the middleware (release ZAP baseline, 2026-10-14).
 *
 * The baseline scan hits `next start` directly — no nginx — so asset URLs the
 * page matcher skipped were served bare: /favicon.ico (Next's HTML 404) filed
 * "CSP Header Not Set" (Medium), and chunks / public SVGs filed missing CORP,
 * nosniff and Permissions-Policy (Low).
 */
import { unstable_doesMiddlewareMatch } from "next/experimental/testing/server";

import { config, middleware } from "@/middleware";
import {
  CROSS_ORIGIN_EMBEDDER_POLICY,
  CROSS_ORIGIN_OPENER_POLICY,
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
  "/_next/static/media/font.woff2",
];

function headersFor(path: string): Headers {
  return middleware(mockRequest(`${ORIGIN}${path}`)).headers;
}

function expectCommonAssetHeaders(headers: Headers) {
  expect(headers.get("X-Content-Type-Options")).toBe("nosniff");
  expect(headers.get("Permissions-Policy")).toBe(PERMISSIONS_POLICY);
  expect(headers.get("Cross-Origin-Opener-Policy")).toBe(CROSS_ORIGIN_OPENER_POLICY);
  expect(headers.get("Cross-Origin-Resource-Policy")).toBe(CROSS_ORIGIN_RESOURCE_POLICY);
  expect(headers.get("Cross-Origin-Embedder-Policy")).toBe(CROSS_ORIGIN_EMBEDDER_POLICY);
  // no per-request nonce machinery on assets
  expect(headers.get("X-CSP-Nonce")).toBeNull();
}

describe("middleware matcher", () => {
  // Including the shapes an unanchored extension lookahead used to drop.
  it.each([
    ...PUBLIC_ASSETS,
    ...CHUNKS,
    "/",
    "/student/apply",
    "/api/v1/preview",
    "/api/v1/files/1/photo.png",
    "/a.png.bak",
    "/favicon.ico/x",
    "/pdf.worker.min.mjs",
  ])("runs the middleware for %s", (path) => {
    expect(unstable_doesMiddlewareMatch({ config, url: `${ORIGIN}${path}` })).toBe(true);
  });
});

describe("middleware static-asset headers", () => {
  it.each(PUBLIC_ASSETS)("%s gets STATIC_ASSET_CSP and the shared headers", (path) => {
    const headers = headersFor(path);
    expect(headers.get("Content-Security-Policy")).toBe(STATIC_ASSET_CSP);
    expectCommonAssetHeaders(headers);
  });

  it.each(CHUNKS)("%s gets the shared headers but NO CSP (a worker obeys its own)", (path) => {
    const headers = headersFor(path);
    expect(headers.get("Content-Security-Policy")).toBeNull();
    expectCommonAssetHeaders(headers);
  });

  it("classifies case-insensitively, like Next's matcher", () => {
    expect(headersFor("/_NEXT/STATIC/chunks/a.js").get("Content-Security-Policy")).toBeNull();
    expect(headersFor("/ICON.SVG").get("Content-Security-Policy")).toBe(STATIC_ASSET_CSP);
  });

  it.each(["/api/v1/files/1/photo.png", "/API/x.png"])(
    "%s is an API route: page policy, never the asset branch",
    (path) => {
      const headers = headersFor(path);
      expect(headers.get("Content-Security-Policy")).toContain("nonce-");
      expect(headers.get("X-CSP-Nonce")).not.toBeNull();
    }
  );

  it.each(["/pdf.worker.min.mjs", "/a.png.bak", "/student/apply"])(
    "%s keeps the page branch (never default-src 'none')",
    (path) => {
      expect(headersFor(path).get("Content-Security-Policy")).toContain("nonce-");
    }
  );
});
