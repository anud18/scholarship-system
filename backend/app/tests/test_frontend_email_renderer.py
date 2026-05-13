"""
Tests for `app.services.frontend_email_renderer.render_email_via_frontend`.

This is the bridge between the backend email-send path and the frontend
React Email renderer. Every transactional email goes through this
function before SMTP send. A bug here would:
- Send empty / malformed HTML to recipients (bad UX)
- Crash the email worker on transient network errors (lost emails)
- Hang the email worker indefinitely (no timeout enforcement)

The function MUST return None (not raise) on every failure path —
otherwise the email scheduler doesn't get a chance to mark the email
as 'failed' and retry later.

7 cases covering all HTTP/exception branches. httpx mocked via patch.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.frontend_email_renderer import render_email_via_frontend


# Helper: build a fake httpx response object
def _fake_response(status_code: int, json_data: dict, content: bytes = b'{"x":1}'):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.content = content
    return resp


# Helper: patch the AsyncClient context manager to return a stubbed client
def _patch_client(response_or_exception):
    """Patch httpx.AsyncClient to return a client whose post() yields the given response or raises the given exception."""
    mock_client = AsyncMock()
    if isinstance(response_or_exception, Exception):
        mock_client.post.side_effect = response_or_exception
    else:
        mock_client.post.return_value = response_or_exception
    # AsyncClient is used as `async with httpx.AsyncClient(...) as client:` so
    # we need __aenter__ to return the mock client.
    async_cm = AsyncMock()
    async_cm.__aenter__.return_value = mock_client
    async_cm.__aexit__.return_value = None
    return patch("app.services.frontend_email_renderer.httpx.AsyncClient", return_value=async_cm)


# ─── Success path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_returns_html():
    """Pin: 200 + success:true + html field → returns the HTML string."""
    response = _fake_response(
        200,
        {"success": True, "html": "<html><body>Hello 王小明</body></html>"},
    )
    with _patch_client(response):
        result = await render_email_via_frontend(
            frontend_url="http://frontend:3000",
            template_name="application-submitted",
            context={"student_name": "王小明"},
        )
    assert result == "<html><body>Hello 王小明</body></html>"


# ─── HTTP error response paths ───────────────────────────────────────


@pytest.mark.asyncio
async def test_non_200_response_returns_none():
    """Pin: non-200 status → None. Caller (email worker) marks email
    as failed; otherwise it'd try to send malformed/empty HTML."""
    response = _fake_response(500, {"error": "internal server error"})
    with _patch_client(response):
        result = await render_email_via_frontend("http://frontend", "x", {})
    assert result is None


@pytest.mark.asyncio
async def test_response_success_false_returns_none():
    """Pin: 200 + success:false → None. The frontend explicitly reports
    a rendering failure (e.g., template not found, missing context var).
    Caller MUST get None so it doesn't send the half-rendered HTML."""
    response = _fake_response(200, {"success": False, "error": "template not found"})
    with _patch_client(response):
        result = await render_email_via_frontend("http://frontend", "missing-template", {})
    assert result is None


@pytest.mark.asyncio
async def test_response_success_true_but_no_html_returns_none():
    """Pin: 200 + success:true but missing html field → None. Defensive
    against a frontend bug that reports success but forgets to set the
    html field."""
    response = _fake_response(200, {"success": True})  # no 'html' key
    with _patch_client(response):
        result = await render_email_via_frontend("http://frontend", "x", {})
    assert result is None


# ─── Network / exception paths ───────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_exception_returns_none():
    """Pin: httpx.TimeoutException → None (NOT raised).
    SECURITY-RELEVANT: if the frontend renderer hangs (e.g., compromised
    container, network partition), the email worker MUST recover and
    schedule a retry rather than blocking indefinitely. The 30s timeout
    enforces this."""
    with _patch_client(httpx.TimeoutException("rendering took too long")):
        result = await render_email_via_frontend("http://frontend", "x", {})
    assert result is None


@pytest.mark.asyncio
async def test_connect_error_returns_none():
    """Pin: ConnectError (frontend container down) → None. Caller
    re-schedules; an exception bubbling up would crash the email
    worker process."""
    with _patch_client(httpx.ConnectError("connection refused")):
        result = await render_email_via_frontend("http://frontend", "x", {})
    assert result is None


@pytest.mark.asyncio
async def test_unexpected_exception_returns_none():
    """Pin: catch-all → None. Any unexpected error (DNS failure, JSON
    parse error, etc.) must not propagate. Logged via logger.error +
    exc_info=True (out-of-scope for this test) but kept inside the
    function."""
    with _patch_client(RuntimeError("unexpected condition")):
        result = await render_email_via_frontend("http://frontend", "x", {})
    assert result is None
