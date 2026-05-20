"""
Tests for `ScholarshipConfigurationService.validate_configuration_requirements`.

Wave 6aa covered `validate_configuration_data` (the substantive
admin-create validation) and `calculate_application_score`. This
file pins the SMALL placeholder helper that lives next to them:

  - **validate_configuration_requirements(config, application_data)**:
    currently always returns `(True, [])`. This is documented as a
    "placeholder" for future quota validation. Pin so:
      1. The placeholder behaviour is explicit (no caller relies
         on it actually validating).
      2. When real validation is implemented (per the source
         comment "Quota validation can be added here if needed"),
         these tests break and force explicit review of every
         existing caller.

5 cases.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.scholarship_configuration_service import ScholarshipConfigurationService


@pytest.fixture
def service():
    return ScholarshipConfigurationService(db=MagicMock())


def _config():
    return SimpleNamespace()


def test_validate_requirements_always_returns_passed(service):
    # Pin: placeholder returns (True, []) regardless of input.
    ok, errors = service.validate_configuration_requirements(_config(), {})
    assert ok is True
    assert errors == []


def test_validate_requirements_returns_tuple_shape(service):
    # Pin: caller signature is `ok, errors = ...`. Return must be
    # a 2-tuple of (bool, list).
    result = service.validate_configuration_requirements(_config(), {})
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], bool)
    assert isinstance(result[1], list)


def test_validate_requirements_ignores_application_data_keys(service):
    # Pin: applicaton_data is unused — pin so a regression that
    # accidentally introduces a key-presence check doesn't surface
    # silently.
    ok1, _ = service.validate_configuration_requirements(_config(), {})
    ok2, _ = service.validate_configuration_requirements(_config(), {"any": "thing", "academic_year": 99999})
    assert ok1 == ok2


def test_validate_requirements_ignores_config_attributes(service):
    # Pin: config arg is unused. Same return regardless.
    cfg_a = SimpleNamespace(amount=0, has_quota_limit=True, total_quota=0)
    cfg_b = SimpleNamespace(amount=10**9, has_quota_limit=False)
    ok_a, _ = service.validate_configuration_requirements(cfg_a, {})
    ok_b, _ = service.validate_configuration_requirements(cfg_b, {})
    assert ok_a is True
    assert ok_b is True


def test_validate_requirements_errors_list_is_fresh_each_call(service):
    # Pin: each call returns a new list (no shared mutable default
    # leak — classic Python gotcha to guard against).
    _, errors1 = service.validate_configuration_requirements(_config(), {})
    _, errors2 = service.validate_configuration_requirements(_config(), {})
    assert errors1 is not errors2  # different list objects
