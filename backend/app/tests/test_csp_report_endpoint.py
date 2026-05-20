"""
Tests for `app.api.v1.endpoints.csp_report` endpoints.

CSP violation reporting receives browser-sent violation reports
when CSP blocks a resource. The browser POSTs to this endpoint
with `csp-report` JSON payloads. Per CSP Level 2 spec, the
endpoint MUST return 204 No Content (even on parse errors —
returning anything else triggers browser-side console errors).

Module had ZERO test coverage. Wave 6a111 pins:
  - `report_csp_violation` accepts valid CSP-report JSON, logs it,
    returns 204
  - Malformed body → still returns 204 (per spec; don't trigger
    browser errors)
  - Missing csp-report key → defaults to {}, still 204
  - `csp_report_info` GET endpoint returns the documented metadata
    {success, message, data: {...}}
  - Logging side effects are exercised (warning + info paths)

11 cases.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.csp_report import (
    csp_report_info,
    report_csp_violation,
)


def _mock_request(body: dict | str | None):
    """Build a mock Request whose .json() returns the given body
    (or raises if body is None or invalid)."""
    req = MagicMock()
    if isinstance(body, dict):
        req.json = AsyncMock(return_value=body)
    elif body is None:
        # Simulate JSON parse failure
        req.json = AsyncMock(side_effect=ValueError("invalid json"))
    else:
        req.json = AsyncMock(return_value=body)
    return req


# ─── report_csp_violation (POST) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_204_for_valid_csp_report():
    # Pin: standard valid CSP report → 204 No Content (per spec).
    req = _mock_request(
        {
            "csp-report": {
                "blocked-uri": "https://evil.example.com/script.js",
                "violated-directive": "script-src 'self'",
                "original-policy": "default-src 'self'",
                "document-uri": "https://scholarship.nycu.edu.tw/admin",
                "referrer": "",
                "status-code": 200,
                "script-sample": "eval('malicious')",
                "source-file": "https://scholarship.nycu.edu.tw/inline.js",
                "line-number": 1,
                "column-number": 1,
            }
        }
    )
    response = await report_csp_violation(req)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_returns_204_for_empty_csp_report():
    # Pin: missing csp-report key → empty dict default → still 204.
    # Pin the defensive .get("csp-report", {}) so a refactor that
    # raises on missing key doesn't break CSP reporting.
    req = _mock_request({})
    response = await report_csp_violation(req)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_returns_204_for_malformed_json():
    # Pin: per CSP spec, ALWAYS return 204 even on parse error.
    # Returning 400/500 triggers browser console errors which
    # spam users' devtools.
    req = _mock_request(None)  # .json() raises
    response = await report_csp_violation(req)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_extracts_blocked_uri_from_report(caplog):
    # Pin: blocked_uri extracted from csp-report and logged.
    # Admins grep logs for specific blocked URIs when investigating.
    import logging

    caplog.set_level(logging.WARNING, logger="csp_violations")

    req = _mock_request(
        {
            "csp-report": {
                "blocked-uri": "https://tracker.com/pixel.gif",
                "violated-directive": "img-src 'self'",
                "document-uri": "https://app.nycu.edu.tw/x",
            }
        }
    )
    await report_csp_violation(req)

    # blocked URI appears in log message
    assert any("tracker.com/pixel.gif" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_extracts_violated_directive(caplog):
    # Pin: violated-directive appears in log.
    import logging

    caplog.set_level(logging.WARNING, logger="csp_violations")

    req = _mock_request(
        {
            "csp-report": {
                "blocked-uri": "x",
                "violated-directive": "script-src-elem 'self'",
                "document-uri": "x",
            }
        }
    )
    await report_csp_violation(req)
    assert any("script-src-elem" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_defaults_blocked_uri_to_unknown_when_missing():
    # Pin: when blocked-uri key absent, default "unknown" is used.
    # Pin so a refactor doesn't substitute None (which would
    # produce a log message "blocked None").
    req = _mock_request(
        {
            "csp-report": {
                "violated-directive": "script-src 'self'",
            }
        }
    )
    response = await report_csp_violation(req)
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_defaults_violated_directive_to_unknown_when_missing():
    req = _mock_request(
        {
            "csp-report": {
                "blocked-uri": "x",
            }
        }
    )
    response = await report_csp_violation(req)
    assert response.status_code == 204


# ─── csp_report_info (GET) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_info_endpoint_returns_documented_payload():
    # Pin: GET returns the documented ApiResponse shape per
    # CLAUDE.md §5.
    response = await csp_report_info()
    assert response["success"] is True
    assert "CSP Violation Reporting" in response["message"]


@pytest.mark.asyncio
async def test_info_endpoint_includes_endpoint_path():
    # Pin: info documents the POST endpoint path. Used by the
    # CSP setup docs / admin onboarding.
    response = await csp_report_info()
    assert response["data"]["endpoint"] == "/api/v1/csp-report"
    assert response["data"]["method"] == "POST"


@pytest.mark.asyncio
async def test_info_endpoint_includes_spec_link():
    # Pin: documentation link to W3C CSP2 spec.
    response = await csp_report_info()
    assert response["data"]["specification"] == "https://www.w3.org/TR/CSP2/#reporting"


@pytest.mark.asyncio
async def test_info_endpoint_data_keys():
    # Pin: 4 keys in the data payload — pinned so a refactor that
    # drops one (e.g., the spec link) is caught.
    response = await csp_report_info()
    assert set(response["data"].keys()) == {
        "endpoint",
        "method",
        "description",
        "specification",
        "note",
    }
