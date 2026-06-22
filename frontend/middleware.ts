import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Next.js Middleware for Content Security Policy (CSP)
 * Generates a unique nonce for each request and injects it into CSP headers
 */

export function middleware(request: NextRequest) {
  // Generate a cryptographically secure nonce using Web Crypto API (Edge Runtime compatible)
  const nonceArray = new Uint8Array(16);
  crypto.getRandomValues(nonceArray);
  const nonce = Buffer.from(nonceArray).toString("base64");

  // Clone the request headers
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  // Create response with updated headers
  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  // Determine environment-specific CSP policy
  const isDevelopment = process.env.NODE_ENV === "development";

  // ALL same-origin file-preview proxies live under the single `/api/v1/preview`
  // namespace (the multiplexer at `/api/v1/preview` plus `/api/v1/preview/terms`,
  // `/api/v1/preview/examples`, `/api/v1/preview/system-docs`,
  // `/api/v1/preview/supp-docs`, `/api/v1/preview/application-document`). They are
  // rendered INSIDE an <iframe> by the app (file-preview-dialog,
  // application-detail-dialog, review dialogs, the student wizard, …). The global
  // clickjacking posture (`frame-ancestors 'none'` + `X-Frame-Options: DENY`)
  // would make the browser refuse to frame these responses
  // ("<host> refused to connect") — so for this prefix ONLY we relax framing to
  // same-origin. `frame-src 'self'` on the parent page is not enough: the CHILD
  // response must also permit being framed, AND browsers honor CSP
  // `frame-ancestors` OVER `X-Frame-Options`, so nginx re-declaring SAMEORIGIN is
  // not sufficient without this matching CSP relaxation.
  //
  // INVARIANT: this is why every framable file proxy MUST live under
  // `/api/v1/preview/` — both this predicate and the nginx preview block then cover
  // it correct-by-construction, with no per-endpoint edits. A framable proxy placed
  // outside this prefix recurs the "refused to connect" bug in BOTH layers.
  //
  // Match the multiplexer EXACTLY (`/api/v1/preview`) plus its child paths
  // (`/api/v1/preview/...`) — NOT a bare `startsWith`, which would also relax a
  // `/api/v1/preview-export`-style sibling and silently make it framable. The nginx
  // configs mirror this with `location ~ ^/api/v1/preview(/|$)`; the two layers MUST
  // stay in lock-step (a tight-here / loose-there split itself breaks framing).
  const { pathname } = request.nextUrl;
  const isFramablePreview =
    pathname === "/api/v1/preview" || pathname.startsWith("/api/v1/preview/");
  const frameAncestors = isFramablePreview ? "frame-ancestors 'self'" : "frame-ancestors 'none'";

  if (isDevelopment) {
    // Development CSP: Relaxed for HMR and debugging
    const csp = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-eval' 'unsafe-inline'", // HMR requires unsafe-eval
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "frame-src 'self' blob:", // inline file preview: same-origin /api proxy + just-selected blob: PDFs
      "font-src 'self'",
      "connect-src 'self' ws: wss:", // WebSocket for HMR
      frameAncestors,
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; ");

    response.headers.set("Content-Security-Policy", csp);
  } else {
    // Production CSP: Strict with nonce-based script/style loading
    const portalHost =
      request.nextUrl.hostname.includes("test") ||
      request.nextUrl.hostname.includes("staging")
        ? "https://portal.test.nycu.edu.tw"
        : "https://portal.nycu.edu.tw";
    const csp = [
      "default-src 'self'",
      `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`, // strict-dynamic for bundled scripts
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data: blob: https:",
      "frame-src 'self' blob:", // inline file preview: same-origin /api proxy + just-selected blob: PDFs
      "font-src 'self'",
      "connect-src 'self' https://*.nycu.edu.tw",
      "base-uri 'self'",
      `form-action 'self' ${portalHost}`,
      frameAncestors,
      "object-src 'none'",
      "upgrade-insecure-requests",
    ].join("; ");

    response.headers.set("Content-Security-Policy", csp);
  }

  // Additional security headers (defense in depth). Same-origin preview proxies
  // must stay framable by the app itself, so SAMEORIGIN (not DENY) for those —
  // a mixed DENY/SAMEORIGIN pair across nginx + middleware is treated as invalid
  // and still blocks, so both layers must agree (see nginx /api/v1/preview block).
  response.headers.set("X-Frame-Options", isFramablePreview ? "SAMEORIGIN" : "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

  // Expose nonce to response headers for Nginx to read (if needed)
  response.headers.set("X-CSP-Nonce", nonce);

  return response;
}

// Configure which routes should trigger this middleware
export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder files
     * - api/email/preview/ (serves email HTML with its own CSP; middleware nonce would block inline styles)
     */
    "/((?!_next/static|_next/image|favicon.ico|api/email/preview/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|woff|woff2|ttf|eot)).*)",
  ],
};
