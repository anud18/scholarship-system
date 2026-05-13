"""
Pure-function tests for `EligibilityService` dev-mode toggles and the
subtype-error shaping helper.

The dev-mode toggles are the safety valves that let developers bypass
whitelist and application-period restrictions in local development.
They MUST evaluate to False in production — a regression here would
let students bypass the whitelist or apply outside the application
window when deployed.

The `_process_subtype_rule_errors` helper is the contract for what
shape of dict the frontend receives. The frontend's subtype rule UI
depends on the keys `passed`, `warnings`, `errors` always being lists
(never undefined).

4 helpers covered (10 cases):
- `_is_dev_mode`                    : settings.debug OR env=development
- `_should_bypass_whitelist`        : dev_mode AND BYPASS_WHITELIST flag
- `_should_bypass_application_period`: dev_mode AND ALWAYS_OPEN flag
- `_process_subtype_rule_errors`    : list-only dict shape contract
"""

from unittest.mock import patch

import pytest

from app.services.eligibility_service import EligibilityService


@pytest.fixture
def service():
    return EligibilityService(db=None)  # type: ignore[arg-type]


# ─── _is_dev_mode ────────────────────────────────────────────────────


@patch("app.services.eligibility_service.settings")
def test_is_dev_mode_true_when_debug(mock_settings, service):
    """settings.debug=True → dev_mode regardless of environment string."""
    mock_settings.debug = True
    mock_settings.environment = "production"  # debug overrides
    assert service._is_dev_mode() is True


@patch("app.services.eligibility_service.settings")
def test_is_dev_mode_true_when_environment_development(mock_settings, service):
    """environment='development' → dev_mode even with debug=False."""
    mock_settings.debug = False
    mock_settings.environment = "development"
    assert service._is_dev_mode() is True


@patch("app.services.eligibility_service.settings")
def test_is_dev_mode_false_in_production(mock_settings, service):
    """The safety check: production env + debug=False → NOT dev_mode.
    This is what prevents student-facing bypasses in deployed envs."""
    mock_settings.debug = False
    mock_settings.environment = "production"
    assert service._is_dev_mode() is False


# ─── _should_bypass_whitelist ────────────────────────────────────────


@patch("app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS", {"BYPASS_WHITELIST": True})
@patch("app.services.eligibility_service.settings")
def test_bypass_whitelist_requires_both_dev_mode_and_flag(mock_settings, service):
    """Both dev_mode AND BYPASS_WHITELIST=True must hold."""
    mock_settings.debug = True
    mock_settings.environment = "development"
    assert service._should_bypass_whitelist() is True


@patch("app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS", {"BYPASS_WHITELIST": True})
@patch("app.services.eligibility_service.settings")
def test_bypass_whitelist_blocked_in_prod_even_with_flag(mock_settings, service):
    """Critical: even if someone toggles BYPASS_WHITELIST=True in prod
    config, the dev-mode guard blocks the bypass."""
    mock_settings.debug = False
    mock_settings.environment = "production"
    assert service._should_bypass_whitelist() is False


@patch("app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS", {"BYPASS_WHITELIST": False})
@patch("app.services.eligibility_service.settings")
def test_bypass_whitelist_blocked_when_flag_false(mock_settings, service):
    """Dev mode alone isn't enough — flag must also be set."""
    mock_settings.debug = True
    mock_settings.environment = "development"
    assert service._should_bypass_whitelist() is False


# ─── _should_bypass_application_period ───────────────────────────────


@patch("app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS", {"ALWAYS_OPEN_APPLICATION": True})
@patch("app.services.eligibility_service.settings")
def test_bypass_app_period_requires_dev_and_flag(mock_settings, service):
    mock_settings.debug = True
    mock_settings.environment = "development"
    assert service._should_bypass_application_period() is True


@patch("app.services.eligibility_service.DEV_SCHOLARSHIP_SETTINGS", {"ALWAYS_OPEN_APPLICATION": True})
@patch("app.services.eligibility_service.settings")
def test_bypass_app_period_blocked_in_prod(mock_settings, service):
    """Production safety: ALWAYS_OPEN can't take effect outside dev."""
    mock_settings.debug = False
    mock_settings.environment = "production"
    assert service._should_bypass_application_period() is False


# ─── _process_subtype_rule_errors ────────────────────────────────────


def test_process_subtype_returns_three_list_keys(service):
    """The frontend depends on passed/warnings/errors all being arrays.
    Pin so a future refactor doesn't drop one of the keys."""
    details = {"passed": [{"rule_id": 1}], "warnings": [{"rule_id": 2}], "errors": [{"rule_id": 3}]}
    result = service._process_subtype_rule_errors(details)
    assert set(result.keys()) == {"passed", "warnings", "errors"}
    assert isinstance(result["passed"], list)
    assert isinstance(result["warnings"], list)
    assert isinstance(result["errors"], list)


def test_process_subtype_copies_lists_not_references(service):
    """The helper does [:] slicing — pin so mutating the returned lists
    doesn't accidentally mutate the caller's `details` dict."""
    original = {"passed": [{"x": 1}], "warnings": [], "errors": []}
    result = service._process_subtype_rule_errors(original)
    result["passed"].append({"x": 2})
    # Mutation of result should NOT leak into original.
    assert len(original["passed"]) == 1
