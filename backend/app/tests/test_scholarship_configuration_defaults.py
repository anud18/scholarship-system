"""
Tests for `app/schemas/scholarship_configuration.py` defaults +
length bounds.

Wave 6a22 covered the model validators (total_quota gated by
has_quota_limit, quotas-matrix sum, renewal-date feature flag,
effective date strict ordering). This wave covers what 6a22 left:

  - **config_name min=1 max=200, config_code min=1 max=50** —
    these are the natural-key identifiers; drift truncates DB rows.

  - **amount field constraint gt=0** — non-zero positive integer
    only. Pinned alongside academic_year gt=0.

  - **currency max=10** with default "TWD".

  - **Boolean defaults that gate workflow**: has_quota_limit=False,
    has_college_quota=False, quota_management_mode=NONE,
    requires_professor_recommendation=False, requires_college_review
    =False, is_active=True. Flipping any one would silently change
    workflow on every new configuration.

  - **whitelist_student_ids defaults {}** (not None).

15 cases.
"""

import pytest
from pydantic import ValidationError

from app.models.enums import QuotaManagementMode, Semester
from app.schemas.scholarship_configuration import ScholarshipConfigurationBase


def _kwargs(**overrides):
    base = dict(
        academic_year=113,
        semester=Semester.first,
        config_name="獎學金A",
        config_code="schA_113_1",
        amount=10000,
    )
    base.update(overrides)
    return base


# ─── config_name length bounds ──────────────────────────────────────


def test_config_name_min_length_1():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(config_name=""))


def test_config_name_max_length_200():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(config_name="x" * 201))


# ─── config_code length bounds ──────────────────────────────────────


def test_config_code_min_length_1():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(config_code=""))


def test_config_code_max_length_50():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(config_code="x" * 51))


# ─── academic_year / amount must be positive ───────────────────────


def test_academic_year_zero_rejected():
    # Pin: gt=0 — 民國年 0 is nonsensical.
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(academic_year=0))


def test_amount_zero_rejected():
    # Pin: gt=0 — a 0-amount scholarship would silently pay students
    # nothing.
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(amount=0))


def test_amount_negative_rejected():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(amount=-100))


# ─── currency ────────────────────────────────────────────────────────


def test_currency_defaults_to_TWD():
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.currency == "TWD"


def test_currency_max_length_10():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_kwargs(currency="x" * 11))


# ─── Workflow-gate boolean defaults ─────────────────────────────────


def test_has_quota_limit_defaults_false():
    # Pin: no quota by default. Flipping would force every new config
    # to require total_quota + quotas matrix (wave 6a22 validators).
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.has_quota_limit is False


def test_has_college_quota_defaults_false():
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.has_college_quota is False


def test_quota_management_mode_defaults_none():
    # Pin: NONE means quota is disabled at the system level. Flipping
    # to MATRIX_BASED would silently activate the complex matrix UI
    # for every new config.
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.quota_management_mode == QuotaManagementMode.none


def test_workflow_flags_default_false():
    # Pin: requires_professor_recommendation=False and
    # requires_college_review=False. The simplest workflow (direct
    # admin approval) is the default; multi-stage workflows require
    # explicit opt-in by the underlying scholarship config.
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.requires_professor_recommendation is False
    assert c.requires_college_review is False


def test_is_active_defaults_true():
    # Pin: new configs are ACTIVE by default. Flipping to False would
    # silently hide every newly-created config from students.
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.is_active is True


# ─── whitelist_student_ids default ──────────────────────────────────


def test_whitelist_student_ids_defaults_empty_dict():
    # Pin: {} (not None) — endpoint code iterates with .items()
    # without null-checks.
    c = ScholarshipConfigurationBase(**_kwargs())
    assert c.whitelist_student_ids == {}
