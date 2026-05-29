"""
Tests for `ApplicationService._validate_sub_type_for_submission`.

Regression pin for the csphd0003 "申請類別 = general" bug: a PhD application
(scholarship type defines real sub-types nstc/moe_1w) was submitted carrying
the synthetic "general" category because the student never selected a sub-type
and both the frontend and backend silently defaulted to "general". A "general"
application matches no quota slot during manual distribution, so it must be
rejected at submission time.

The guard is a pure staticmethod — tested via SimpleNamespace bypass of
SQLAlchemy, no DB needed.
"""

from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.services.application_service import ApplicationService


def _scholarship(sub_type_list):
    return SimpleNamespace(sub_type_list=sub_type_list)


# ─── scholarships that define real sub-types: "general"/empty is rejected ───


def test_phd_general_submission_rejected():
    # The exact csphd0003 bug: nstc/moe_1w defined, "general" submitted.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "general")


def test_phd_none_submission_rejected():
    # Empty sub_scholarship_type collapses to "general" → rejected.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), None)


def test_sub_type_not_in_list_rejected():
    # Submitted a sub-type the scholarship doesn't define.
    with pytest.raises(ValidationError):
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc"]), "moe_1w")


def test_error_message_lists_valid_sub_types():
    with pytest.raises(ValidationError) as exc:
        ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "general")
    msg = str(exc.value)
    assert "nstc" in msg and "moe_1w" in msg


# ─── valid submissions: no exception ───


def test_valid_concrete_sub_type_passes():
    # nstc is in the defined list → allowed.
    ApplicationService._validate_sub_type_for_submission(_scholarship(["nstc", "moe_1w"]), "nstc")


def test_general_scholarship_allows_general():
    # Scholarship whose only "sub-type" is the synthetic general → general ok.
    ApplicationService._validate_sub_type_for_submission(_scholarship(["general"]), "general")


def test_scholarship_without_sub_types_allows_general():
    # No sub-types defined at all → general is the correct category.
    ApplicationService._validate_sub_type_for_submission(_scholarship([]), "general")


def test_scholarship_with_none_sub_type_list_allows_general():
    # Defensive: sub_type_list may be None on older rows.
    ApplicationService._validate_sub_type_for_submission(_scholarship(None), "general")
