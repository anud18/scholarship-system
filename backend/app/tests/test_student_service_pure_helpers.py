"""
Pure-function tests for `StudentService` helpers.

This service is the bridge to the NYCU student-information API.

3 helpers covered:
- `get_student_type_from_data`  : degree code → 'phd' | 'master' | 'undergraduate'
- `determine_student_api_type`  : currently always 'student' (regression guard)
- `is_api_available`            : reflects self.api_enabled
"""

import pytest

from app.services.student_service import StudentService


@pytest.fixture
def service():
    """StudentService.__init__ reads settings; in test envs api_enabled is
    False by default."""
    s = StudentService()
    return s


# ─── get_student_type_from_data ──────────────────────────────────────


def test_student_type_phd(service):
    """std_degree '1' ⇒ phd."""
    assert service.get_student_type_from_data({"std_degree": "1"}) == "phd"


def test_student_type_master(service):
    """std_degree '2' ⇒ master."""
    assert service.get_student_type_from_data({"std_degree": "2"}) == "master"


def test_student_type_undergraduate_default(service):
    """std_degree '3' or anything else ⇒ undergraduate (the SIS default)."""
    assert service.get_student_type_from_data({"std_degree": "3"}) == "undergraduate"
    assert service.get_student_type_from_data({"std_degree": "9"}) == "undergraduate"


def test_student_type_missing_field_defaults_to_undergraduate(service):
    """Missing std_degree key ⇒ falls back via .get default '3' ⇒ undergraduate.
    Don't blow up — just degrade to the largest student segment."""
    assert service.get_student_type_from_data({}) == "undergraduate"


# ─── determine_student_api_type ──────────────────────────────────────


def test_determine_api_type_returns_student_for_none_config(service):
    """Current behavior is 'always student'. This test pins that contract so
    a regression to 'student_term' surfaces immediately (would break the API
    call signature in get_student_data_by_type)."""
    assert service.determine_student_api_type(None) == "student"


def test_determine_api_type_returns_student_for_any_config(service):
    """Even with a config object passed, it returns 'student' until the
    config-driven branch (commented-out) is enabled."""

    class _FakeConfig:
        requires_term_data = True

    assert service.determine_student_api_type(_FakeConfig()) == "student"


# ─── is_api_available ────────────────────────────────────────────────


def test_is_api_available_reflects_api_enabled(service):
    service.api_enabled = True
    assert service.is_api_available() is True

    service.api_enabled = False
    assert service.is_api_available() is False
