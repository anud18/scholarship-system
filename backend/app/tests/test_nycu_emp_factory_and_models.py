"""
Tests for `app.integrations.nycu_emp` factory + models + exceptions.

The NYCU Employee API integration is the source of truth for staff
data. The factory decides between mock (dev/test) and HTTP (staging
/prod) clients based on env config. A regression here either:
  - Silently uses MOCK in production (security: stale staff data)
  - Silently uses HTTP in dev/test (calls real API; flaky tests)

Wave 6a107 pins:
  - create_nycu_emp_client mode dispatch (mock/http/invalid)
  - HTTP mode required-param validation (account/endpoint/key)
  - Default mode (env unset → "mock")
  - NYCUEmpPage.is_success property contract
  - Exception class messages + http_status codes

17 cases.
"""

import os
import pytest

from app.integrations.nycu_emp.client_http import NYCUEmpHttpClient
from app.integrations.nycu_emp.client_mock import NYCUEmpMockClient
from app.integrations.nycu_emp.exceptions import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
)
from app.integrations.nycu_emp.factory import create_nycu_emp_client
from app.integrations.nycu_emp.models import NYCUEmpPage

# ─── create_nycu_emp_client mode dispatch ────────────────────────────


def test_factory_mock_mode_returns_mock_client():
    # Pin: explicit mode="mock" → NYCUEmpMockClient. Used for
    # dev / test envs and CI.
    client = create_nycu_emp_client(mode="mock")
    assert isinstance(client, NYCUEmpMockClient)


def test_factory_mock_mode_case_insensitive():
    # Pin: "MOCK" / "Mock" also dispatch to mock client. Defensive
    # against env-var casing inconsistency.
    assert isinstance(create_nycu_emp_client(mode="MOCK"), NYCUEmpMockClient)
    assert isinstance(create_nycu_emp_client(mode="Mock"), NYCUEmpMockClient)


def test_factory_http_mode_returns_http_client_with_valid_params():
    # Pin: HTTP mode with all required params → NYCUEmpHttpClient.
    client = create_nycu_emp_client(
        mode="http",
        account="test-account",
        key_hex="abcdef",
        endpoint="https://api.example.com",
    )
    assert isinstance(client, NYCUEmpHttpClient)


def test_factory_http_mode_raises_when_account_missing():
    # Pin: SECURITY — must reject HTTP mode without account.
    # Better to fail loudly than fall back to mock silently.
    with pytest.raises(ValueError, match="account is required"):
        create_nycu_emp_client(mode="http", endpoint="https://x", key_hex="ab")


def test_factory_http_mode_raises_when_endpoint_missing():
    with pytest.raises(ValueError, match="endpoint is required"):
        create_nycu_emp_client(mode="http", account="acc", key_hex="ab")


def test_factory_http_mode_raises_when_both_keys_missing():
    # Pin: at least one of key_hex / key_raw is required.
    with pytest.raises(ValueError, match="key_hex or key_raw"):
        create_nycu_emp_client(mode="http", account="acc", endpoint="https://x")


def test_factory_http_mode_accepts_key_raw_alone():
    # Pin: key_raw is acceptable alternative to key_hex.
    client = create_nycu_emp_client(
        mode="http",
        account="acc",
        key_raw="raw-key",
        endpoint="https://x",
    )
    assert isinstance(client, NYCUEmpHttpClient)


def test_factory_invalid_mode_raises():
    # Pin: unknown mode → ValueError. NOT silent fallback to mock.
    with pytest.raises(ValueError, match="Invalid NYCU_EMP_MODE"):
        create_nycu_emp_client(mode="bogus")


def test_factory_default_mode_from_env_is_mock(monkeypatch):
    # Pin: when no mode passed AND NYCU_EMP_MODE env unset, default
    # is "mock". Ensures dev/test environments without explicit
    # config don't accidentally hit the real API.
    monkeypatch.delenv("NYCU_EMP_MODE", raising=False)
    client = create_nycu_emp_client()
    assert isinstance(client, NYCUEmpMockClient)


def test_factory_env_mode_used_when_no_arg(monkeypatch):
    # Pin: NYCU_EMP_MODE env var read when mode param not passed.
    monkeypatch.setenv("NYCU_EMP_MODE", "mock")
    client = create_nycu_emp_client()
    assert isinstance(client, NYCUEmpMockClient)


# ─── NYCUEmpPage.is_success property ─────────────────────────────────


def test_page_is_success_when_status_is_0000():
    # Pin: status="0000" means success. This is the NYCU API
    # success sentinel — pinning so a refactor to numeric 0 or
    # bool doesn't break the upstream check.
    page = NYCUEmpPage(
        status="0000",
        message="OK",
        total_page=1,
        total_count=0,
        empDataList=[],
    )
    assert page.is_success is True


def test_page_is_not_success_when_status_is_other():
    # Pin: any other status → False.
    page = NYCUEmpPage(
        status="0001",
        message="Error",
        total_page=0,
        total_count=0,
        empDataList=[],
    )
    assert page.is_success is False


# ─── Exception classes ──────────────────────────────────────────────


def test_nycu_emp_error_str_format():
    # Pin: __str__ includes message + status + http_status.
    err = NYCUEmpError("test msg", status="0001", http_status=500)
    s = str(err)
    assert "test msg" in s
    assert "0001" in s
    assert "500" in s


def test_authentication_error_sets_http_status_401():
    # Pin: AuthenticationError implies HTTP 401. Used by
    # downstream code branching on http_status.
    err = NYCUEmpAuthenticationError()
    assert err.http_status == 401


def test_validation_error_sets_http_status_400():
    # Pin: ValidationError → HTTP 400.
    err = NYCUEmpValidationError()
    assert err.http_status == 400


def test_connection_error_default_message():
    # Pin: defaults documented for caller convenience.
    err = NYCUEmpConnectionError()
    assert "Failed to connect" in err.message


def test_timeout_error_default_message():
    err = NYCUEmpTimeoutError()
    assert "timed out" in err.message
