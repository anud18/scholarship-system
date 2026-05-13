"""
Pure-function tests for `ScholarshipRulesService` rule-evaluation helpers.

This service has its own copy of the rule-engine helpers (in addition
to `EligibilityService`'s). The two copies must agree — if they drift,
the rule-management UI shows one verdict while the eligibility check
returns another, which is the worst kind of silent bug for admins
debugging student rejections.

2 pure helpers covered (13 cases):
- `_get_nested_field_value(data, field_path)` : dot-path lookup
- `_evaluate_rule_condition(value, op, expected)` : 10 operators
"""

import pytest

from app.services.scholarship_rules_service import ScholarshipRulesService


@pytest.fixture
def service():
    return ScholarshipRulesService(db=None)  # type: ignore[arg-type]


# ─── _get_nested_field_value ─────────────────────────────────────────


def test_nested_field_top_level_lookup(service):
    assert service._get_nested_field_value({"gpa": 3.8}, "gpa") == 3.8


def test_nested_field_dotted_path_traverses_dicts(service):
    data = {"profile": {"academic": {"gpa": 3.9}}}
    assert service._get_nested_field_value(data, "profile.academic.gpa") == 3.9


def test_nested_field_missing_top_level_returns_empty_string(service):
    """No key ⇒ '' (NOT None — the rule engine treats '' as no-data sentinel
    consistent with EligibilityService)."""
    assert service._get_nested_field_value({}, "missing") == ""


def test_nested_field_missing_nested_returns_empty_string(service):
    """Missing key at any level halts traversal and returns ''."""
    assert service._get_nested_field_value({"a": {}}, "a.b.c") == ""


def test_nested_field_traversal_through_non_dict_returns_empty_string(service):
    """If a path component lands on a non-dict (string, int, list),
    traversal halts and returns '' — defensive guard against malformed data."""
    assert service._get_nested_field_value({"a": "string-not-dict"}, "a.b") == ""
    assert service._get_nested_field_value({"a": [1, 2]}, "a.b") == ""


# ─── _evaluate_rule_condition: numeric operators ─────────────────────


def test_evaluate_gte_passes(service):
    assert service._evaluate_rule_condition("3.8", ">=", "3.5") is True


def test_evaluate_gte_fails(service):
    assert service._evaluate_rule_condition("3.2", ">=", "3.5") is False


def test_evaluate_all_numeric_operators(service):
    """All four numeric ops must agree with arithmetic comparison."""
    assert service._evaluate_rule_condition("3.8", "<=", "4.0") is True
    assert service._evaluate_rule_condition("3.8", ">", "3.5") is True
    assert service._evaluate_rule_condition("3.0", "<", "3.5") is True


# ─── _evaluate_rule_condition: equality + collection operators ───────


def test_evaluate_equality_with_string_coercion(service):
    """== and != compare via str() — '3' == '3' even if one is int."""
    assert service._evaluate_rule_condition(3, "==", "3") is True
    assert service._evaluate_rule_condition("x", "!=", "y") is True


def test_evaluate_in_with_csv_expected(service):
    """'in' splits expected_value by comma, stripping whitespace."""
    assert service._evaluate_rule_condition("TW", "in", "TW, US, JP") is True
    assert service._evaluate_rule_condition("CN", "in", "TW, US, JP") is False


def test_evaluate_not_in_with_csv(service):
    assert service._evaluate_rule_condition("CN", "not_in", "CN, HK") is False
    assert service._evaluate_rule_condition("TW", "not_in", "CN, HK") is True


def test_evaluate_contains_and_not_contains(service):
    """Substring containment — useful for partial name / email match."""
    assert service._evaluate_rule_condition("王小明", "contains", "小") is True
    assert service._evaluate_rule_condition("王小明", "not_contains", "李") is True


# ─── _evaluate_rule_condition: defensive branches ────────────────────


def test_evaluate_unknown_operator_returns_false(service):
    """Unknown operators silently return False (don't accidentally pass an
    eligibility check on garbage input)."""
    assert service._evaluate_rule_condition("3.8", "@@invalid", "3.5") is False


def test_evaluate_non_numeric_for_numeric_op_returns_false(service):
    """float('not-a-number') raises ValueError → caught → False (defensive,
    don't auto-pass; surfaces as 'rule failed' rather than crash)."""
    assert service._evaluate_rule_condition("not-a-number", ">=", "3.5") is False
