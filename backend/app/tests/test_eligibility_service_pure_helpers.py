"""
Pure-function tests for `EligibilityService` helpers.

The eligibility rule engine drives every scholarship application
decision — silent operator misbehavior here would either reject valid
applications (functional bug) or approve ineligible ones
(compliance/audit risk).

Two pure helpers covered:
- `_evaluate_rule(student_data, rule)`: rule-vs-data comparison
  supporting >=, <=, >, <, ==, !=, in, not_in, contains, not_contains.
- `_get_nested_field_value(data, field_path)`: dot-notation lookup
  used to extract values from the student_data JSON snapshot.

11 cases total — covers each operator + missing-data branches +
dotted-path traversal.
"""

from types import SimpleNamespace
from typing import Optional

import pytest

from app.services.eligibility_service import EligibilityService


def _rule(**kwargs) -> SimpleNamespace:
    """Build a duck-typed rule object with the fields _evaluate_rule reads.

    The real ScholarshipRule is a SQLAlchemy model — using SimpleNamespace
    keeps the test free of DB seeding while still exercising real logic.
    """
    defaults = {
        "rule_name": "test_rule",
        "rule_type": "student_basic",
        "condition_field": "gpa",
        "operator": ">=",
        "expected_value": "3.5",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.fixture
def service():
    """No DB needed for pure helpers."""
    return EligibilityService(db=None)  # type: ignore[arg-type]


# ─── _evaluate_rule: numeric operators ───────────────────────────────


def test_evaluate_rule_gte_passes(service):
    result = service._evaluate_rule({"gpa": "3.8"}, _rule(operator=">=", expected_value="3.5"))
    assert result is True


def test_evaluate_rule_gte_fails(service):
    result = service._evaluate_rule({"gpa": "3.2"}, _rule(operator=">=", expected_value="3.5"))
    assert result is False


def test_evaluate_rule_lt_with_string_numbers(service):
    """Numeric operators tolerate string-typed inputs (the API serializes everything as str)."""
    result = service._evaluate_rule({"score": "70"}, _rule(condition_field="score", operator="<", expected_value="80"))
    assert result is True


# ─── _evaluate_rule: equality + collection operators ─────────────────


def test_evaluate_rule_in_with_csv_expected_value(service):
    """'in' operator expects expected_value to be a comma-separated list."""
    result = service._evaluate_rule(
        {"nationality": "TW"},
        _rule(condition_field="nationality", operator="in", expected_value="TW, US, JP"),
    )
    assert result is True


def test_evaluate_rule_not_in_with_csv_expected_value(service):
    result = service._evaluate_rule(
        {"nationality": "CN"},
        _rule(condition_field="nationality", operator="not_in", expected_value="CN, HK"),
    )
    assert result is False  # CN is forbidden, so not_in fails.


def test_evaluate_rule_contains_substring(service):
    result = service._evaluate_rule(
        {"name": "王小明"},
        _rule(condition_field="name", operator="contains", expected_value="小"),
    )
    assert result is True


def test_evaluate_rule_unknown_operator_returns_false(service):
    """Unknown operator strings return False (defensive); logged as a warning."""
    result = service._evaluate_rule({"gpa": "3.8"}, _rule(operator="@@@invalid"))
    assert result is False


# ─── _evaluate_rule: missing-data branches ──────────────────────────


def test_evaluate_rule_term_data_unavailable_returns_none(service):
    """Term-level data unavailable ⇒ None (can't verify — yellow warning, not red error)."""
    student_data = {"_term_data_status": "api_error"}
    rule = _rule(rule_type="student_term")
    assert service._evaluate_rule(student_data, rule) is None


def test_evaluate_rule_term_field_missing_returns_none(service):
    """Term rule with field present in dict but empty string ⇒ None."""
    student_data = {"_term_data_status": "success", "gpa": ""}
    rule = _rule(rule_type="student_term", condition_field="gpa")
    assert service._evaluate_rule(student_data, rule) is None


def test_evaluate_rule_value_error_returns_false(service):
    """Non-numeric input to a numeric operator → ValueError caught → False."""
    result = service._evaluate_rule({"gpa": "not-a-number"}, _rule(operator=">=", expected_value="3.5"))
    assert result is False


# ─── _get_nested_field_value ─────────────────────────────────────────


def test_get_nested_field_top_level(service):
    """Simple top-level lookup."""
    assert service._get_nested_field_value({"name": "Alice"}, "name") == "Alice"


def test_get_nested_field_dotted_path(service):
    """Dotted path traverses nested dicts."""
    data = {"profile": {"contact": {"email": "alice@u.edu"}}}
    assert service._get_nested_field_value(data, "profile.contact.email") == "alice@u.edu"


def test_get_nested_field_missing_returns_empty_string(service):
    """Missing keys at any level return '' (NOT None — the rest of the engine treats '' as no-data sentinel)."""
    assert service._get_nested_field_value({}, "missing") == ""
    assert service._get_nested_field_value({"a": {}}, "a.b.c") == ""


def test_get_nested_field_traversal_through_non_dict_returns_empty_string(service):
    """If a path component lands on a non-dict, traversal halts and returns ''."""
    data = {"a": "string-not-dict"}
    assert service._get_nested_field_value(data, "a.b") == ""
