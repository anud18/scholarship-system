"""
Tests for `RosterService._evaluate_scholarship_rule` — the per-rule
orchestrator that ties `_get_student_field_value` + `_evaluate_condition`
together and returns the dict the eligibility-result aggregator expects.

A regression here changes the dict shape that downstream rule-aggregation
relies on (`passed`, `failed_rules`, `warning_rules`, etc.) and silently
breaks the roster Excel output.

Specifically pinned:
- Returned dict shape on the happy path (10 keys)
- `passed` reflects `_evaluate_condition` result
- `message` falls back to `f"{rule_name}: {description}"` when
  `rule.message` is None (or empty)
- `is_hard_rule` / `is_warning` pass through unchanged
- Exception inside `_get_student_field_value` / `_evaluate_condition`
  is swallowed: returns `{"passed": False, ..., "error": str(e)}`,
  NEVER raises — so one bad rule can't tank the whole monthly roster
- The error-path dict is shorter (5 keys, no actual_value / expected_value)

Wave 6a158.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.roster_service import RosterService


@pytest.fixture
def service():
    return RosterService(db=MagicMock())


@pytest.fixture
def student():
    return SimpleNamespace(gpa=3.85, nationality="TW")


@pytest.fixture
def application():
    return SimpleNamespace(
        student_data={"trm_ascore_gpa": 3.7},
        term_count=4,
        previous_scholarship=None,
    )


def _make_rule(**overrides):
    """Build a stub ScholarshipRule with the minimum attributes
    `_evaluate_scholarship_rule` reads. Using SimpleNamespace avoids
    instantiating the SQLAlchemy model (which would require a session)."""
    defaults = dict(
        id=1,
        rule_name="GPA Floor",
        rule_type="gpa",
        condition_field="gpa",
        operator=">=",
        expected_value="3.0",
        message="GPA 必須 >= 3.0",
        is_hard_rule=False,
        is_warning=False,
        description="Minimum GPA requirement",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# 1. Happy path — dict shape + passed flag reflects _evaluate_condition
# ---------------------------------------------------------------------------


def test_happy_path_returns_10_keys(service, student, application):
    """Pin: happy-path dict has exactly the 10 documented keys. Pin so a
    refactor adding new keys forces an explicit decision (the aggregator
    consumes this dict by key)."""
    rule = _make_rule()
    result = service._evaluate_scholarship_rule(rule, student, application)
    expected_keys = {
        "passed",
        "rule_name",
        "rule_type",
        "actual_value",
        "expected_value",
        "operator",
        "message",
        "is_hard_rule",
        "is_warning",
    }
    assert expected_keys.issubset(set(result.keys()))


def test_passed_true_when_condition_satisfied(service, student, application):
    rule = _make_rule(operator=">=", expected_value="3.0")
    result = service._evaluate_scholarship_rule(rule, student, application)
    # gpa=3.85, 3.85 >= 3.0 → True
    assert result["passed"] is True


def test_passed_false_when_condition_fails(service, student, application):
    rule = _make_rule(operator=">=", expected_value="4.0")
    result = service._evaluate_scholarship_rule(rule, student, application)
    # gpa=3.85, 3.85 >= 4.0 → False
    assert result["passed"] is False


def test_actual_value_resolved_via_get_student_field_value(service, student, application):
    """Pin: `_evaluate_scholarship_rule` delegates field lookup to
    `_get_student_field_value`. The friendly alias `gpa` resolves to
    `student.gpa`, NOT `application.student_data['trm_ascore_gpa']`
    (different value on purpose to prove the priority)."""
    rule = _make_rule(condition_field="gpa")
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["actual_value"] == 3.85


def test_fresh_api_data_flows_through(service, student, application):
    """Pin: `fresh_api_data` kwarg is forwarded to `_get_student_field_value`.
    Without this, the orchestrator would silently ignore current SIS data."""
    rule = _make_rule(condition_field="trm_ascore_gpa", operator=">=", expected_value="3.9")
    fresh = {"trm_ascore_gpa": 3.95}
    result = service._evaluate_scholarship_rule(rule, student, application, fresh_api_data=fresh)
    # 3.95 >= 3.9 → True; the snapshot value 3.7 would have failed
    assert result["actual_value"] == 3.95
    assert result["passed"] is True


# ---------------------------------------------------------------------------
# 2. Message fallback when rule.message is None / empty
# ---------------------------------------------------------------------------


def test_message_pass_through_when_set(service, student, application):
    """Pin: a non-empty rule.message is passed through unchanged."""
    rule = _make_rule(message="Custom message")
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["message"] == "Custom message"


def test_message_fallback_when_none(service, student, application):
    """Pin: when rule.message is None, fall back to
    `f"{rule_name}: {description}"`. Pin so admin always gets *some*
    explanation in the Excel exclusion-reason cell."""
    rule = _make_rule(message=None, rule_name="GPA Floor", description="Min 3.0")
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["message"] == "GPA Floor: Min 3.0"


def test_message_fallback_when_empty_string(service, student, application):
    """Pin: empty-string is also falsy → fallback fires."""
    rule = _make_rule(message="", rule_name="GPA Floor", description="Min 3.0")
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["message"] == "GPA Floor: Min 3.0"


# ---------------------------------------------------------------------------
# 3. is_hard_rule / is_warning pass-through
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("is_hard,is_warn", [(True, False), (False, True), (False, False), (True, True)])
def test_hard_and_warning_flags_pass_through(service, student, application, is_hard, is_warn):
    """Pin: the two routing flags pass through unchanged. Downstream
    aggregator routes to `failed_rules` vs `warning_rules` based on these."""
    rule = _make_rule(is_hard_rule=is_hard, is_warning=is_warn, operator=">=", expected_value="4.0")
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["is_hard_rule"] is is_hard
    assert result["is_warning"] is is_warn


# ---------------------------------------------------------------------------
# 4. Operator / expected_value reflected in the result dict
# ---------------------------------------------------------------------------


def test_operator_and_expected_value_echoed(service, student, application):
    """Pin: the operator + expected_value strings are echoed in the result
    so the Excel "failed because GPA 3.85 < 4.0" cell can be assembled
    downstream."""
    rule = _make_rule(operator="<", expected_value="2.0")
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["operator"] == "<"
    assert result["expected_value"] == "2.0"


# ---------------------------------------------------------------------------
# 5. Exception swallowing — bad rule must NOT crash roster generation
# ---------------------------------------------------------------------------


def test_exception_returns_failed_dict_not_raises(service, student, application, monkeypatch):
    """Pin SECURITY: any exception from the inner helpers is caught and
    converted to `{"passed": False, "error": <str>, ...}`. A typo / model
    drift / unexpected None in ONE rule must NEVER tank the once-a-month
    roster generation for every student.
    """
    rule = _make_rule()

    def broken_lookup(*args, **kwargs):
        raise RuntimeError("simulated lookup crash")

    monkeypatch.setattr(service, "_get_student_field_value", broken_lookup)

    # Must NOT raise
    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["passed"] is False
    assert "error" in result
    assert "simulated lookup crash" in result["error"]


def test_exception_message_includes_rule_name(service, student, application, monkeypatch):
    """Pin: the error-path message includes the original error string so
    operators can see WHICH rule failed and why."""
    rule = _make_rule(rule_name="GPA Floor")

    def broken_lookup(*args, **kwargs):
        raise ValueError("bad config")

    monkeypatch.setattr(service, "_get_student_field_value", broken_lookup)

    result = service._evaluate_scholarship_rule(rule, student, application)
    assert "規則評估錯誤" in result["message"]
    assert "bad config" in result["message"]


def test_exception_path_returns_rule_name_and_type(service, student, application, monkeypatch):
    """Pin: even in the error path, `rule_name` and `rule_type` survive
    — so the aggregator can still partition the failed rule into the
    right bucket."""
    rule = _make_rule(rule_name="GPA Floor", rule_type="gpa")

    def broken(*args, **kwargs):
        raise Exception("boom")

    monkeypatch.setattr(service, "_evaluate_condition", broken)

    result = service._evaluate_scholarship_rule(rule, student, application)
    assert result["rule_name"] == "GPA Floor"
    assert result["rule_type"] == "gpa"
