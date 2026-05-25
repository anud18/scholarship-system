"""
Unit tests for `RosterService._validate_student_eligibility` — the gatekeeper
that decides whether an Application becomes a payment-roster line item.

Closes issue #124 § 2 (eligibility validation flow).

Note on coverage scope
======================
§ 1 of the issue (operator-level + per-rule unit tests for `_evaluate_condition`
and `_evaluate_scholarship_rule`) is ALREADY covered by:
- `test_roster_eligibility_operators.py` — 10 operators × happy/edge cases
- `test_roster_evaluate_scholarship_rule.py` — per-rule dict shape + exception swallowing
- `test_roster_get_student_field_value.py` — field-lookup priority + unknown fields

This file fills the actual remaining gap: the AND-aggregation across multiple
rules, the missing-student / missing-config short-circuits, the "no rules
found → default eligible" pass-through, and the top-level exception-swallow
that prevents one bad rule from crashing the monthly roster build.

The method is dependency-light (only `_get_scholarship_rules` touches the DB);
we instantiate the service with a `MagicMock` session and monkeypatch
`_get_scholarship_rules` to return SimpleNamespace rule stubs. `_evaluate_
scholarship_rule` is NOT mocked so the AND aggregation path is real-tested
end-to-end.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.roster_service import RosterService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service():
    """RosterService with a mocked DB session.

    `_validate_student_eligibility` only touches the DB via
    `_get_scholarship_rules`, which we monkeypatch per-test below.
    """
    return RosterService(db=MagicMock())


def _make_student(**overrides):
    """Minimal student stub. `_get_student_field_value` falls back to
    `getattr(student, field_name)` for arbitrary field names, so the
    namespace can carry any attribute the rule references."""
    defaults = dict(
        gpa=3.85,
        nationality="TW",
        ranking=5,
        department="CS",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_scholarship_config(scholarship_type_id=1):
    return SimpleNamespace(scholarship_type_id=scholarship_type_id)


def _make_application(student=None, scholarship_config=None, **overrides):
    """SimpleNamespace stub of Application — `_validate_student_eligibility`
    reads .student, .scholarship_configuration, .sub_scholarship_type, .id,
    and .student_data (for snapshot fallback in field lookup)."""
    defaults = dict(
        id=42,
        student=student if student is not None else _make_student(),
        scholarship_configuration=scholarship_config if scholarship_config is not None else _make_scholarship_config(),
        sub_scholarship_type=None,
        student_data={},
        term_count=4,
        previous_scholarship=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_rule(**overrides):
    """Stub of ScholarshipRule with the attributes
    `_evaluate_scholarship_rule` reads."""
    defaults = dict(
        id=1,
        rule_name="GPA Floor",
        rule_type="gpa",
        condition_field="gpa",
        operator=">=",
        expected_value="3.0",
        message="GPA must be >= 3.0",
        description="Minimum GPA requirement",
        is_hard_rule=True,
        is_warning=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# 1. Happy path — all rules pass
# ---------------------------------------------------------------------------


def test_happy_path_all_rules_pass(service, monkeypatch):
    """Pin: when every rule's condition is satisfied, `is_eligible=True`
    and both `failed_rules` and `warning_rules` are empty."""
    rules = [
        _make_rule(rule_name="GPA Floor", condition_field="gpa", operator=">=", expected_value="3.0"),
        _make_rule(rule_name="Ranking Top 10", condition_field="ranking", operator="<=", expected_value="10"),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application(student=_make_student(gpa=3.85, ranking=5))
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is True
    assert result["failed_rules"] == []
    assert result["warning_rules"] == []
    # `details` is the per-rule breakdown; one entry per rule.
    assert f"rule_{rules[0].id}" in result["details"]
    assert f"rule_{rules[1].id}" in result["details"]


# ---------------------------------------------------------------------------
# 2. Hard rule failure → ineligible, message routed to failed_rules
# ---------------------------------------------------------------------------


def test_hard_rule_failure_marks_ineligible(service, monkeypatch):
    """Pin: a hard rule that fails → `is_eligible=False`. The rule's
    `message` field surfaces in `failed_rules` so the operator-facing
    Excel exclusion-reason cell can be assembled downstream."""
    rules = [
        _make_rule(
            rule_name="GPA Floor",
            condition_field="gpa",
            operator=">=",
            expected_value="3.5",
            message="GPA must be >= 3.5",
            is_hard_rule=True,
            is_warning=False,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application(student=_make_student(gpa=2.9))
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert "GPA must be >= 3.5" in result["failed_rules"]
    assert result["warning_rules"] == []


def test_hard_rule_failure_message_falls_back_to_name_description(service, monkeypatch):
    """Pin: when `rule.message` is empty, `_evaluate_scholarship_rule`
    falls back to `f"{rule_name}: {description}"`. That fallback must
    survive the aggregation and land in `failed_rules`."""
    rules = [
        _make_rule(
            rule_name="GPA Floor",
            description="Min 3.5",
            message=None,
            condition_field="gpa",
            operator=">=",
            expected_value="3.5",
            is_hard_rule=True,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application(student=_make_student(gpa=2.9))
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert "GPA Floor: Min 3.5" in result["failed_rules"]


# ---------------------------------------------------------------------------
# 3. Warning rule failure → still eligible, message routed to warning_rules
# ---------------------------------------------------------------------------


def test_warning_rule_failure_keeps_eligible(service, monkeypatch):
    """Pin: a warning rule that fails does NOT disqualify the student;
    its message lands in `warning_rules` only. The roster Excel will
    still include this student with a yellow flag."""
    rules = [
        _make_rule(
            rule_name="Ranking Bonus",
            condition_field="ranking",
            operator="<=",
            expected_value="3",
            message="Recommend ranking <= 3",
            is_hard_rule=False,
            is_warning=True,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application(student=_make_student(ranking=10))
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is True
    assert result["failed_rules"] == []
    assert "Recommend ranking <= 3" in result["warning_rules"]


def test_mixed_hard_and_warning_failures_route_correctly(service, monkeypatch):
    """Pin: when a hard rule AND a warning rule both fail, the hard
    failure routes to `failed_rules` (disqualifying) and the warning
    routes to `warning_rules` (non-disqualifying). Cross-contamination
    between the two lists has bitten previous refactors."""
    rules = [
        _make_rule(
            rule_name="GPA Floor",
            condition_field="gpa",
            operator=">=",
            expected_value="3.5",
            message="hard: gpa",
            is_hard_rule=True,
            is_warning=False,
            id=1,
        ),
        _make_rule(
            rule_name="Ranking Bonus",
            condition_field="ranking",
            operator="<=",
            expected_value="3",
            message="warn: ranking",
            is_hard_rule=False,
            is_warning=True,
            id=2,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application(student=_make_student(gpa=2.9, ranking=10))
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert result["failed_rules"] == ["hard: gpa"]
    assert result["warning_rules"] == ["warn: ranking"]


# ---------------------------------------------------------------------------
# 4. AND-across-rules aggregation — verifies issue #124 § 1's open question
# ---------------------------------------------------------------------------


def test_and_semantics_one_failure_disqualifies(service, monkeypatch):
    """Pin (resolves issue #124 § 1's "AND vs OR" question): rules are
    AND-ed. Three hard rules; two pass, one fails → `is_eligible=False`.
    The two passing rules do NOT appear in `failed_rules`."""
    rules = [
        _make_rule(
            rule_name="A",
            condition_field="gpa",
            operator=">=",
            expected_value="3.0",
            message="A failed",
            is_hard_rule=True,
            id=1,
        ),
        _make_rule(
            rule_name="B",
            condition_field="ranking",
            operator="<=",
            expected_value="10",
            message="B failed",
            is_hard_rule=True,
            id=2,
        ),
        _make_rule(
            rule_name="C",
            condition_field="nationality",
            operator="==",
            expected_value="JP",
            message="C failed",
            is_hard_rule=True,
            id=3,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    # gpa=3.85 (A passes), ranking=5 (B passes), nationality="TW" (C fails)
    application = _make_application(student=_make_student())
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert result["failed_rules"] == ["C failed"]


def test_and_semantics_all_pass_returns_eligible(service, monkeypatch):
    """Pin: AND semantics — all hard rules pass → eligible."""
    rules = [
        _make_rule(rule_name="A", condition_field="gpa", operator=">=", expected_value="3.0", is_hard_rule=True, id=1),
        _make_rule(
            rule_name="B", condition_field="ranking", operator="<=", expected_value="10", is_hard_rule=True, id=2
        ),
        _make_rule(
            rule_name="C", condition_field="nationality", operator="==", expected_value="TW", is_hard_rule=True, id=3
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application(student=_make_student())
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is True
    assert result["failed_rules"] == []


# ---------------------------------------------------------------------------
# 5. Missing relationship data — three short-circuit branches
# ---------------------------------------------------------------------------


def test_missing_student_returns_ineligible_with_reason(service):
    """Pin: application with no `.student` relationship → ineligible,
    `failed_rules=['缺少學生資訊']`. Data-integrity hole that must
    surface in the Excel exclusion reason, not silently pass."""
    application = _make_application(student=None, scholarship_config=_make_scholarship_config())
    application.student = None  # explicit
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert result["failed_rules"] == ["缺少學生資訊"]
    assert result["warning_rules"] == []


def test_missing_scholarship_config_returns_ineligible_with_reason(service):
    """Pin: application with no `.scholarship_configuration` relationship
    → ineligible, `failed_rules=['缺少獎學金配置']`."""
    application = _make_application(scholarship_config=None)
    application.scholarship_configuration = None  # explicit
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert result["failed_rules"] == ["缺少獎學金配置"]


def test_missing_both_student_and_config_combines_reason(service):
    """Pin: when BOTH student and scholarship_configuration are missing,
    the reason combines both ('缺少學生資訊/獎學金配置'). The order matters
    because the operator's Excel cell parses by exact string match."""
    application = _make_application()
    application.student = None
    application.scholarship_configuration = None
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert result["failed_rules"] == ["缺少學生資訊/獎學金配置"]


# ---------------------------------------------------------------------------
# 6. No rules found — silent pass-through
# ---------------------------------------------------------------------------


def test_no_rules_found_defaults_to_eligible(service, monkeypatch):
    """Pin: when `_get_scholarship_rules` returns `[]` for the
    (scholarship_type, year, period, sub_type) tuple, the student
    defaults to eligible with `details={"no_rules_found": True}`.

    # VERIFY: silent pass-through — intentional?
    # Today this is the current behavior (roster_service.py:1029-1036): no
    # rules configured means "no constraints, everybody passes". Issue #124
    # § 2 explicitly flags this as a "verify intentional, not a silent bug"
    # case. The bit `details.no_rules_found=True` is the audit signal that
    # this happened — downstream operator UI should surface "X students
    # marked eligible because no rules are configured" when this fires.
    """
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: [])

    application = _make_application()
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is True
    assert result["failed_rules"] == []
    assert result["warning_rules"] == []
    assert result["details"].get("no_rules_found") is True


# ---------------------------------------------------------------------------
# 7. Rule whose field_path doesn't exist on the student → False, no crash
# ---------------------------------------------------------------------------


def test_unknown_field_path_disqualifies_does_not_crash(service, monkeypatch):
    """Pin (issue #124 § 1): a hard rule whose `condition_field` doesn't
    exist on the student (typo in admin config, schema drift, etc.)
    must NOT crash. `_get_student_field_value` returns None, then
    `_evaluate_condition` returns False — so a hard rule fails the
    student rather than tanking the whole roster build."""
    rules = [
        _make_rule(
            rule_name="Missing Field Rule",
            condition_field="totally_made_up_field_name",
            operator=">=",
            expected_value="3.0",
            message="should fail because field is missing",
            is_hard_rule=True,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application()
    # Must NOT raise:
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert "should fail because field is missing" in result["failed_rules"]


# ---------------------------------------------------------------------------
# 8. fresh_api_data is forwarded to per-rule evaluation
# ---------------------------------------------------------------------------


def test_fresh_api_data_takes_priority_over_snapshot(service, monkeypatch):
    """Pin: `fresh_api_data` (the just-fetched 學籍 API payload) is
    forwarded into per-rule evaluation. Without this, a student whose
    GPA improved since application submission would be unfairly
    disqualified against the stale snapshot."""
    rules = [
        _make_rule(
            rule_name="Term GPA Floor",
            condition_field="trm_ascore_gpa",
            operator=">=",
            expected_value="3.9",
            message="term gpa below 3.9",
            is_hard_rule=True,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    # Snapshot says 3.7 (would fail); fresh API says 3.95 (passes)
    application = _make_application()
    application.student_data = {"trm_ascore_gpa": 3.7}
    fresh = {"trm_ascore_gpa": 3.95}

    result = service._validate_student_eligibility(
        application, academic_year=113, period_label="113-01", fresh_api_data=fresh
    )

    assert result["is_eligible"] is True
    assert result["failed_rules"] == []


def test_no_fresh_api_data_falls_back_to_snapshot(service, monkeypatch):
    """Pin: when `fresh_api_data` is None (e.g., 學籍 API returned
    API_ERROR), the snapshot is consulted instead. Roster generation
    must proceed — NOT crash — when the upstream API is down."""
    rules = [
        _make_rule(
            rule_name="Term GPA Floor",
            condition_field="trm_ascore_gpa",
            operator=">=",
            expected_value="3.5",
            message="term gpa below 3.5",
            is_hard_rule=True,
        ),
    ]
    monkeypatch.setattr(service, "_get_scholarship_rules", lambda *a, **kw: rules)

    application = _make_application()
    application.student_data = {"trm_ascore_gpa": 3.7}

    # fresh_api_data=None (simulating API_ERROR upstream)
    result = service._validate_student_eligibility(
        application, academic_year=113, period_label="113-01", fresh_api_data=None
    )

    assert result["is_eligible"] is True


# ---------------------------------------------------------------------------
# 9. Top-level exception swallowing — one bad rule must NOT crash the roster
# ---------------------------------------------------------------------------


def test_top_level_exception_returns_failed_not_raises(service, monkeypatch):
    """Pin SECURITY: any uncaught exception inside the eligibility
    pipeline (e.g., `_get_scholarship_rules` itself blows up due to
    a DB hiccup) is converted to `{"is_eligible": False, "failed_rules":
    ["驗證過程發生錯誤: ..."]}`. The once-a-month roster generation must
    NEVER die on a single bad student — at most that student is
    disqualified with an error message in the Excel exclusion-reason cell.
    """

    def boom(*args, **kwargs):
        raise RuntimeError("simulated DB hiccup")

    monkeypatch.setattr(service, "_get_scholarship_rules", boom)

    application = _make_application()

    # Must NOT raise:
    result = service._validate_student_eligibility(application, academic_year=113, period_label="113-01")

    assert result["is_eligible"] is False
    assert len(result["failed_rules"]) == 1
    assert "驗證過程發生錯誤" in result["failed_rules"][0]
    assert "simulated DB hiccup" in result["failed_rules"][0]
    assert "error" in result["details"]


# ---------------------------------------------------------------------------
# 10. _get_scholarship_rules call-shape — academic_year, period_label, sub_type
# ---------------------------------------------------------------------------


def test_get_scholarship_rules_called_with_correct_keys(service, monkeypatch):
    """Pin: `_get_scholarship_rules` is invoked with
    (scholarship_type_id, academic_year, period_label, sub_scholarship_type).
    A regression that swaps the period_label and academic_year would
    silently pull the WRONG rule set — every student would be evaluated
    against last year's rules with no obvious symptom."""
    captured = {}

    def capture_args(scholarship_type_id, academic_year, period_label, sub_type):
        captured["scholarship_type_id"] = scholarship_type_id
        captured["academic_year"] = academic_year
        captured["period_label"] = period_label
        captured["sub_type"] = sub_type
        return []  # no rules → silent pass-through

    monkeypatch.setattr(service, "_get_scholarship_rules", capture_args)

    application = _make_application(
        scholarship_config=_make_scholarship_config(scholarship_type_id=7),
    )
    application.sub_scholarship_type = "nstc"

    service._validate_student_eligibility(application, academic_year=114, period_label="114-H1")

    assert captured == {
        "scholarship_type_id": 7,
        "academic_year": 114,
        "period_label": "114-H1",
        "sub_type": "nstc",
    }
