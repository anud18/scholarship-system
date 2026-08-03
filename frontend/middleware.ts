import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import {
  CROSS_ORIGIN_OPENER_POLICY,
  CROSS_ORIGIN_RESOURCE_POLICY,
  PERMISSIONS_POLICY,
  SONNER_EMPTY_STYLE_HASH,
  SONNER_STYLE_HASH,
} from "@/lib/security-headers";

/**
 * Next.js Middleware for Content Security Policy (CSP)
 * Generates a unique nonce for each request and injects it into CSP headers
 */

export function middleware(request: NextRequest) {
  // Generate a cryptographically secure nonce using Web Crypto API (Edge Runtime compatible)
  const nonceArray = new Uint8Array(16);
  crypto.getRandomValues(nonceArray);
  const nonce = Buffer.from(nonceArray).toString("base64");

  // Determine environment-specific CSP policy
  const isDevelopment = process.env.NODE_ENV === "development";

  // ALL same-origin file-preview proxies live under the single `/api/v1/preview`
  // namespace (the multiplexer at `/api/v1/preview` plus `/api/v1/preview/terms`,
  // `/api/v1/preview/examples`, `/api/v1/preview/system-docs`,
  // `/api/v1/preview/supp-docs`). They are
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

  let csp: string;

  if (isDevelopment) {
    // Development CSP: Relaxed for HMR and debugging
    csp = [
      "default-src 'self'",
      "script-src 'self' 'unsafe-eval' 'unsafe-inline'", // HMR requires unsafe-eval
      "style-src 'self' 'unsafe-inline'",
      // Kept byte-identical to the production directive on purpose: a looser dev
      // img-src lets an accidental remote <img> pass locally and break only in
      // production. Turbopack HMR needs no image source — its channel is the
      // ws:/wss: connect-src below, its overlay is inline data:/same-origin.
      "img-src 'self' data: blob:",
      "frame-src 'self' blob:", // inline file preview: same-origin /api proxy + just-selected blob: PDFs
      "font-src 'self'",
      "connect-src 'self' ws: wss:", // WebSocket for HMR
      frameAncestors,
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; ");
  } else {
    // Production CSP: Strict with nonce-based script/style loading
    const portalHost =
      request.nextUrl.hostname.includes("test") ||
      request.nextUrl.hostname.includes("staging")
        ? "https://portal.test.nycu.edu.tw"
        : "https://portal.nycu.edu.tw";
    csp = [
      "default-src 'self'",
      `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`, // strict-dynamic for bundled scripts
      // Issue #1273 / ZAP 10055. `style-src 'self' 'unsafe-inline'` (commit bc2019f0)
      // was the blunt fix for shadcn/ui: Radix + floating-ui write inline style
      // ATTRIBUTES at runtime (Popover/Dropdown/Dialog positioning, animation vars)
      // and a nonce cannot be attached to a `style=` attribute. But that one keyword
      // also re-permitted injected `<style>` ELEMENTS, which nothing in this app needs.
      //
      // CSP Level 3 splits the two. Keep the half the UI actually requires and drop
      // the half that only helps an attacker:
      //   style-src      -> ELEMENTS (<style>, <link rel=stylesheet>): nonce-gated
      //   style-src-attr -> ATTRIBUTES (style="..."): 'unsafe-inline', for Radix
      //
      // ACCEPTED RESIDUAL RISK: an HTML-injection point can still set a `style=`
      // attribute. Closing that would mean replacing Radix's positioning engine —
      // disproportionate. Injected <style> blocks are now blocked by the browser.
      //
      // The two sonner hashes cover the <Toaster/> stylesheet, which the library
      // injects imperatively with no nonce hook — see lib/security-headers.ts.
      `style-src 'self' 'nonce-${nonce}' ${SONNER_STYLE_HASH} ${SONNER_EMPTY_STYLE_HASH}`,
      "style-src-attr 'unsafe-inline'",
      // NO bare `https:` — that allowed images from ANY HTTPS origin (issue #1223
      // finding B, flagged by ZAP) and nothing in the app needs it. Every <img>
      // render site uses a same-origin or blob: source:
      //   - file-preview-dialog.tsx             -> /api/v1/preview… or createObjectURL
      //   - bank-verification-review-dialog.tsx -> /api/v1/preview…
      // There is no next/image (images.unoptimized) and no remotePatterns, so any
      // future remote image MUST be added here by explicit origin, never as a scheme.
      // data: covers inline SVG; blob: covers just-selected local files.
      "img-src 'self' data: blob:",
      "frame-src 'self' blob:", // inline file preview: same-origin /api proxy + just-selected blob: PDFs
      "font-src 'self'",
      "connect-src 'self' https://*.nycu.edu.tw",
      "base-uri 'self'",
      `form-action 'self' ${portalHost}`,
      frameAncestors,
      "object-src 'none'",
      "upgrade-insecure-requests",
    ].join("; ");
  }

  // Clone the request headers.
  //
  // BOTH of these must be forwarded on the REQUEST, not just the response:
  //   x-nonce                  -> read by app/layout.tsx via getNonce()
  //   Content-Security-Policy  -> read by Next.js itself
  //
  // Next.js only auto-attaches the nonce to the <style>/<script> tags it injects
  // when it can parse a nonce out of the REQUEST's CSP header. With the header set
  // on the response only (the pre-#1273 shape), Next emitted two un-nonced inline
  // <style> elements on every page — invisible while `style-src` still carried
  // 'unsafe-inline', but an instant style-src-elem block the moment it was removed.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  // Create response with updated headers
  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  response.headers.set("Content-Security-Policy", csp);

  // Additional security headers (defense in depth). Same-origin preview proxies
  // must stay framable by the app itself, so SAMEORIGIN (not DENY) for those —
  // a mixed DENY/SAMEORIGIN pair across nginx + middleware is treated as invalid
  // and still blocks, so both layers must agree (see nginx /api/v1/preview block).
  response.headers.set("X-Frame-Options", isFramablePreview ? "SAMEORIGIN" : "DENY");
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

  // Issue #1223 section B. These three are mirrored VERBATIM at the server level
  // and in every re-declaring location block of nginx.prod.conf /
  // nginx.staging.conf — see lib/security-headers.ts for why the layers must not
  // drift, and __tests__/security-headers-nginx-parity.test.ts which pins it.
  response.headers.set("Permissions-Policy", PERMISSIONS_POLICY);
  response.headers.set("Cross-Origin-Opener-Policy", CROSS_ORIGIN_OPENER_POLICY);
  response.headers.set("Cross-Origin-Resource-Policy", CROSS_ORIGIN_RESOURCE_POLICY);
  // Cross-Origin-Embedder-Policy is DELIBERATELY NOT SET. `require-corp` would
  // demand a CORP header on every subresource the same-origin /api/v1/preview
  // iframes pull, breaking file preview — the exact caveat raised in #1223 — and
  // it buys nothing: nothing in this app uses SharedArrayBuffer or needs
  // `crossOriginIsolated`. Do not add it without re-testing every preview route.

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
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|woff|woff2|ttf|eot)).*)",
  ],
};
