"""
Unit tests for StudentService (external-API-backed, no database dependency).

StudentService proxies student data from the university's SIS API.
It is stateless — no `db` session in __init__.

Covered:
- `get_student_type_from_data` : pure degree-code → type mapping
- `determine_student_api_type` : constant "student" for now
- `is_api_available`           : reflects api_enabled flag
- `get_student_snapshot`       : raises ServiceUnavailableError when API disabled
- `validate_student_exists`    : returns False when API disabled
- `get_student_basic_info`     : happy + error paths with mocked httpx
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ServiceUnavailableError
from app.services.student_service import StudentService


@pytest.fixture
def service(monkeypatch):
    """StudentService with the SIS API force-disabled.

    `settings.student_api_enabled` defaults to True and the base_url/account
    settings have non-None defaults, so a bare StudentService() is
    "configured" in every environment (CI included). Force the disabled state so
    the disabled-path assertions are deterministic instead of env-dependent.
    """
    import app.services.student_service as student_service_module

    monkeypatch.setattr(student_service_module.settings, "student_api_enabled", False)
    return StudentService()


@pytest.fixture
def api_service():
    """StudentService with API enabled via direct attribute injection."""
    svc = StudentService()
    svc.api_enabled = True
    svc.api_base_url = "http://fake-sis-api"
    svc.api_timeout = 5.0
    return svc


# ─── is_api_available ────────────────────────────────────────────────────────


def test_is_api_available_false_when_not_configured(service):
    """API disabled in CI (no env vars) → is_api_available() is False."""
    assert service.is_api_available() is False


def test_is_api_available_true_when_enabled(api_service):
    assert api_service.is_api_available() is True


# ─── get_student_type_from_data ──────────────────────────────────────────────


def test_get_student_type_phd(service):
    assert service.get_student_type_from_data({"std_degree": "1"}) == "phd"


def test_get_student_type_master(service):
    assert service.get_student_type_from_data({"std_degree": "2"}) == "master"


def test_get_student_type_undergraduate(service):
    assert service.get_student_type_from_data({"std_degree": "3"}) == "undergraduate"


def test_get_student_type_unknown_defaults_to_undergraduate(service):
    """Missing or unknown degree code → undergraduate (safe default)."""
    assert service.get_student_type_from_data({}) == "undergraduate"
    assert service.get_student_type_from_data({"std_degree": "99"}) == "undergraduate"


# ─── determine_student_api_type ──────────────────────────────────────────────


def test_determine_student_api_type_defaults_to_student(service):
    assert service.determine_student_api_type() == "student"
    assert service.determine_student_api_type(scholarship_config=None) == "student"


# ─── get_student_snapshot (API disabled) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_student_snapshot_raises_when_api_disabled(service):
    """No API configured → ServiceUnavailableError, not silent None."""
    with pytest.raises(ServiceUnavailableError):
        await service.get_student_snapshot("any_code")


# ─── validate_student_exists (API disabled) ──────────────────────────────────


@pytest.mark.asyncio
async def test_validate_student_exists_returns_false_when_api_disabled(service):
    """API disabled → False (not an exception; caller can handle gracefully)."""
    result = await service.validate_student_exists("any_code")
    assert result is False


# ─── get_student_basic_info (mocked httpx) ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_student_basic_info_returns_none_when_disabled(service):
    """API not enabled → returns None immediately, no HTTP call."""
    result = await service.get_student_basic_info("114550001")
    assert result is None


@pytest.mark.asyncio
async def test_get_student_basic_info_happy_path(api_service):
    """API returns student record → service returns the first data element."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": 200,
        "data": [{"std_stdcode": "114550001", "std_cname": "王小明"}],
    }
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_cls.return_value.__aenter__.return_value = mock_client

        result = await api_service.get_student_basic_info("114550001")

    assert result == {"std_stdcode": "114550001", "std_cname": "王小明"}


@pytest.mark.asyncio
async def test_get_student_basic_info_not_found_returns_none(api_service):
    """API returns 404 code → None (student not found, not an error)."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 404, "data": None}
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_cls.return_value.__aenter__.return_value = mock_client

        result = await api_service.get_student_basic_info("999999")

    assert result is None


@pytest.mark.asyncio
async def test_get_student_basic_info_raises_on_5xx(api_service):
    """HTTP 500 from SIS API → ServiceUnavailableError."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_cls.return_value.__aenter__.return_value = mock_client

        with pytest.raises(ServiceUnavailableError):
            await api_service.get_student_basic_info("114550001")


# ─── get_student_data_by_type ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_student_data_by_type_student_calls_basic_info(service):
    """api_type='student' delegates to get_student_basic_info."""
    with patch.object(service, "get_student_basic_info", return_value=None) as mock_method:
        await service.get_student_data_by_type("114550001", api_type="student")
    mock_method.assert_called_once_with("114550001")


@pytest.mark.asyncio
async def test_get_student_data_by_type_missing_year_returns_none(service):
    """api_type='student_term' without year/term → None (guard check)."""
    result = await service.get_student_data_by_type("114550001", api_type="student_term")
    assert result is None
