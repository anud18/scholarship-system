"""SecurityHeadersMiddleware contract (AppScan 2026-08-13 staging findings).

Every JSON response must be non-cacheable and carry the strict API CSP;
endpoint-declared Cache-Control must win; non-JSON responses (docs HTML,
files) must not receive the API CSP.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import HTMLResponse, JSONResponse

from app.middleware.security_headers_middleware import (
    API_CONTENT_SECURITY_POLICY,
    NO_STORE_CACHE_CONTROL,
    SecurityHeadersMiddleware,
)


def _build_client() -> TestClient:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/json")
    async def json_endpoint():
        return {"success": True, "message": "ok", "data": None}

    @app.get("/cached-file")
    async def cached_file_endpoint():
        return JSONResponse(
            content={"success": True},
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.get("/docs-like")
    async def docs_like_endpoint():
        return HTMLResponse("<html><body>docs</body></html>")

    return TestClient(app)


def test_json_response_defaults_to_no_store_with_api_csp():
    response = _build_client().get("/json")

    assert response.headers["Cache-Control"] == NO_STORE_CACHE_CONTROL
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Content-Security-Policy"] == API_CONTENT_SECURITY_POLICY


def test_endpoint_declared_cache_control_wins():
    response = _build_client().get("/cached-file")

    assert response.headers["Cache-Control"] == "private, max-age=3600"
    assert "Pragma" not in response.headers


def test_html_response_gets_no_api_csp_but_still_no_store():
    # Swagger UI (non-production only) must not be broken by default-src 'none'.
    response = _build_client().get("/docs-like")

    assert "Content-Security-Policy" not in response.headers
    assert response.headers["Cache-Control"] == NO_STORE_CACHE_CONTROL
