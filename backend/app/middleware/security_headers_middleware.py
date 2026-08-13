"""
Response-header hardening for every backend API response.

Added for the 2026-08-13 AppScan staging findings:

- "Cacheable SSL Page Found": authenticated JSON responses (e.g.
  /api/v1/auth/me, /api/v1/payment-rosters) carried no Cache-Control header,
  so browsers and shared caches were free to store per-user data. Every
  response now defaults to ``no-store`` unless the endpoint set an explicit
  Cache-Control of its own (a few file endpoints do).

- Missing "Content-Security-Policy": API responses had no CSP at all. JSON
  responses get the strict no-execution policy recommended for APIs. Non-JSON
  responses (Swagger UI HTML in dev, streamed files) are left alone — the
  interactive docs would break under ``default-src 'none'``, and file
  responses that the frontend frames get their CSP from the Next.js proxy
  layer instead.

nginx cannot do either of these safely: ``add_header`` APPENDS, so a
Cache-Control added there would coexist with (not replace) an endpoint's own
value, and a server-level CSP would stack a second, conflicting policy onto
the nonce-based CSP the frontend middleware emits for pages.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Strict no-execution policy for machine-readable responses. frame-ancestors
# 'none' also makes framing a raw API response impossible regardless of the
# X-Frame-Options nginx adds.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"

NO_STORE_CACHE_CONTROL = "no-store, no-cache, must-revalidate"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Default every response to non-cacheable and give JSON a strict CSP."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Endpoint-declared caching wins (e.g. photo/file endpoints that set
        # their own private max-age); everything else must not be stored.
        if "cache-control" not in response.headers:
            response.headers["Cache-Control"] = NO_STORE_CACHE_CONTROL
            response.headers["Pragma"] = "no-cache"

        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json") and "content-security-policy" not in response.headers:
            response.headers["Content-Security-Policy"] = API_CONTENT_SECURITY_POLICY

        return response
