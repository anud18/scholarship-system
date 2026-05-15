"""
Tests for `UserProfileService._scan_for_virus` — the SECURITY-relevant
upload-scanning gate.

This is a placeholder hook that production deployments wire to an external
virus scanner (ClamAV / VirusTotal). Two contracts are SECURITY-critical
and pinned here:

1. **Fail-open when scanner not configured** — refusing every upload
   because the scanner URL is unset would brick the bank-document upload
   flow. The current behavior: log a warning, set warning="Scanner not
   configured", return is_safe=True. Pin this so a future refactor doesn't
   silently flip to fail-closed without an explicit migration.

2. **Fail-open on scanner exception / error response** — same reasoning.
   The scanner is best-effort defense-in-depth, not a hard gate.

Note: `aiohttp` is imported lazily inside `_scan_for_virus` and is not in
the test container's dependency set. The configured-path tests inject a
fake aiohttp module via sys.modules so the function-level import succeeds.

Wave 6a162.
"""

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.user_profile_service import UserProfileService


@pytest.fixture
def service():
    return UserProfileService(db=MagicMock())


# ---------------------------------------------------------------------------
# 1. Unconfigured scanner — fail-open with warning (no aiohttp needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unconfigured_scanner_returns_safe_with_warning(service):
    """Pin SECURITY: when neither URL nor key is set, the helper short-
    circuits to is_safe=True with a warning marker. Pin so a refactor
    doesn't flip to fail-closed (would brick every bank-doc upload)."""
    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = ""
        mock_settings.virus_scan_api_key = ""

        result = await service._scan_for_virus(b"file contents", "image/jpeg")

    assert result["is_safe"] is True
    assert "warning" in result
    assert "not configured" in result["warning"]


@pytest.mark.asyncio
async def test_missing_url_only_still_returns_safe(service):
    """Pin: URL absent but key present → still fail-open. Pin so a
    partial config (one of two fields set) doesn't engage broken scanner."""
    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = ""
        mock_settings.virus_scan_api_key = "some-key"

        result = await service._scan_for_virus(b"data", "application/pdf")

    assert result["is_safe"] is True
    assert "warning" in result


@pytest.mark.asyncio
async def test_missing_key_only_still_returns_safe(service):
    """Pin: key absent but URL present → still fail-open."""
    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = "https://scanner.example/scan"
        mock_settings.virus_scan_api_key = ""

        result = await service._scan_for_virus(b"data", "application/pdf")

    assert result["is_safe"] is True


# ---------------------------------------------------------------------------
# Fake aiohttp scaffolding for the configured-path tests
# ---------------------------------------------------------------------------


def _make_fake_aiohttp(*, post_response=None, post_raises=None, session_raises=None):
    """Build a fake aiohttp module that returns the supplied response (or
    raises). The fake exposes `ClientSession`, `ClientTimeout`, and is
    installed into sys.modules so the function-level `import aiohttp`
    inside `_scan_for_virus` succeeds."""
    fake = ModuleType("aiohttp")

    # ClientTimeout — function under test just calls it with kwargs; we
    # don't care about its return value.
    fake.ClientTimeout = MagicMock()

    if session_raises is not None:

        class ExplodingSession:
            def __init__(self, *args, **kwargs):
                raise session_raises

        fake.ClientSession = ExplodingSession
        return fake

    # post() returns an async context manager yielding the response
    class FakePostCtx:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            if post_raises is not None:
                raise post_raises
            return self._resp

        async def __aexit__(self, *args):
            return None

    class FakeSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def post(self, *args, **kwargs):
            return FakePostCtx(post_response)

    fake.ClientSession = FakeSession
    return fake


def _make_response(status, json_body=None):
    resp = MagicMock()
    resp.status = status
    if json_body is not None:
        resp.json = AsyncMock(return_value=json_body)
    return resp


# ---------------------------------------------------------------------------
# 2. Scanner exception — fail-open with warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_exception_returns_safe_with_warning(service):
    """Pin SECURITY: when the scanner integration raises (network error /
    timeout / etc.), the helper catches it and fail-opens. Pin so a refactor
    propagating the exception doesn't crash the whole upload flow."""
    fake = _make_fake_aiohttp(session_raises=RuntimeError("network down"))

    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = "https://scanner.example/scan"
        mock_settings.virus_scan_api_key = "test-key"
        mock_settings.virus_scan_timeout = 5
        sys.modules["aiohttp"] = fake
        try:
            result = await service._scan_for_virus(b"data", "application/pdf")
        finally:
            sys.modules.pop("aiohttp", None)

    assert result["is_safe"] is True
    assert "warning" in result
    assert "exception" in result["warning"].lower()
    assert "network down" in result["warning"]


# ---------------------------------------------------------------------------
# 3. Scanner returns 200 + clean → safe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_clean_response_returns_safe(service):
    """Pin: scanner returns 200 with `{"clean": true}` → is_safe=True,
    reason=None."""
    fake = _make_fake_aiohttp(post_response=_make_response(200, {"clean": True}))

    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = "https://scanner.example/scan"
        mock_settings.virus_scan_api_key = "test-key"
        mock_settings.virus_scan_timeout = 5
        sys.modules["aiohttp"] = fake
        try:
            result = await service._scan_for_virus(b"data", "application/pdf")
        finally:
            sys.modules.pop("aiohttp", None)

    assert result["is_safe"] is True
    assert result["reason"] is None


# ---------------------------------------------------------------------------
# 4. Scanner returns 200 + malware found → unsafe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_malware_response_returns_unsafe(service):
    """Pin: scanner returns `{"clean": false, "malware_name": "..."}` →
    is_safe=False with malware_name surfaced as reason."""
    fake = _make_fake_aiohttp(
        post_response=_make_response(200, {"clean": False, "malware_name": "EICAR-Test-Signature"})
    )

    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = "https://scanner.example/scan"
        mock_settings.virus_scan_api_key = "test-key"
        mock_settings.virus_scan_timeout = 5
        sys.modules["aiohttp"] = fake
        try:
            result = await service._scan_for_virus(b"bad data", "application/pdf")
        finally:
            sys.modules.pop("aiohttp", None)

    assert result["is_safe"] is False
    assert result["reason"] == "EICAR-Test-Signature"


# ---------------------------------------------------------------------------
# 5. Scanner returns non-200 → fail-open with warning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_non_200_status_returns_safe(service):
    """Pin SECURITY: scanner returns 500 / 503 / etc → is_safe=True with
    warning marker. Pin so a transient scanner outage doesn't block all
    bank-doc uploads."""
    fake = _make_fake_aiohttp(post_response=_make_response(503))

    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = "https://scanner.example/scan"
        mock_settings.virus_scan_api_key = "test-key"
        mock_settings.virus_scan_timeout = 5
        sys.modules["aiohttp"] = fake
        try:
            result = await service._scan_for_virus(b"data", "application/pdf")
        finally:
            sys.modules.pop("aiohttp", None)

    assert result["is_safe"] is True
    assert "warning" in result


# ---------------------------------------------------------------------------
# 6. Return dict always has is_safe (downstream caller depends on shape)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_return_always_includes_is_safe(service):
    """Pin: every code path returns a dict with `is_safe` key. The caller
    accesses `result["is_safe"]` unconditionally — a missing key would
    crash the upload flow with KeyError."""
    with patch("app.services.user_profile_service.settings") as mock_settings:
        mock_settings.virus_scan_api_url = ""
        mock_settings.virus_scan_api_key = ""

        result = await service._scan_for_virus(b"", "application/octet-stream")

    assert "is_safe" in result
