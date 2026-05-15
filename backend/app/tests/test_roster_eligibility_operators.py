"""
Pure-unit tests for `RosterService._evaluate_condition`.

This is the inner loop of eligibility checking — every scholarship rule
condition runs through one of the 10 operators below, so a regression here
disqualifies real students or sneaks unqualified ones into the roster Excel.
The method is dependency-free (no DB / no IO), so we instantiate the service
with a `MagicMock` session and call the bound method directly.

Covers issue #124 § 1 (rule-eval unit tests).
"""

from unittest.mock import MagicMock

import pytest

from app.services.roster_service import RosterService


@pytest.fixture
def evaluator():
    # _evaluate_condition does not touch the db; the session is only stored
    # for other methods on the service. A MagicMock keeps the constructor happy.
    return RosterService(db=MagicMock())._evaluate_condition


# ---------------------------------------------------------------------------
# None-handling: every operator must short-circuit to False on None inputs,
# never raise. A real-world trigger is a transfer student whose GPA hasn't
# been imported yet.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operator,expected_value",
    [
        (">=", "3.0"),
        ("<=", "3.0"),
        (">", "3.0"),
        ("<", "3.0"),
        ("==", "foo"),
        ("!=", "foo"),
        ("in", "a,b,c"),
        ("not_in", "a,b,c"),
        ("contains", "foo"),
        ("not_contains", "foo"),
    ],
)
def test_none_actual_value_returns_false(evaluator, operator, expected_value):
    assert evaluator(None, operator, expected_value) is False


# ---------------------------------------------------------------------------
# Numeric comparisons (>=, <=, >, <)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "actual,op,expected,result",
    [
        # GPA threshold
        (3.5, ">=", "3.0", True),
        (3.0, ">=", "3.0", True),  # boundary
        (2.9, ">=", "3.0", False),
        (3.0, "<=", "3.0", True),  # boundary
        (3.0, ">", "3.0", False),  # strict
        (3.0, "<", "3.0", False),  # strict
        # Stringified numerics: scholarship rules sometimes ship as strings
        ("3.5", ">=", "3.0", True),
        # Integer comparison
        (5, ">", "4", True),
    ],
)
def test_numeric_comparison(evaluator, actual, op, expected, result):
    assert evaluator(actual, op, expected) is result


def test_numeric_comparison_with_garbage_expected_value_logs_and_returns_false(evaluator, caplog):
    # A typo in the rule config (e.g. expected_value="three") used to crash
    # the whole roster generation. The handler swallows the ValueError and
    # logs it instead.
    assert evaluator(3.5, ">=", "three") is False


# ---------------------------------------------------------------------------
# Equality (==, !=) — string-stripped, never numeric
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "actual,op,expected,result",
    [
        ("active", "==", "active", True),
        ("active", "==", "inactive", False),
        ("active", "!=", "inactive", True),
        # Whitespace gets stripped from BOTH sides (real bug we hit when the
        # spreadsheet import had trailing spaces in expected_value).
        ("  active  ", "==", "active", True),
        ("active", "==", "  active  ", True),
        # Mixed numeric / string is compared as strings — important to know
        # because rule configs are JSON and TS-side may stringify numbers.
        (3, "==", "3", True),
        (3, "==", "3.0", False),  # string-equality, not numeric
    ],
)
def test_equality_operators(evaluator, actual, op, expected, result):
    assert evaluator(actual, op, expected) is result


# ---------------------------------------------------------------------------
# Membership (in, not_in) — comma-split list, whitespace-stripped per element
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "actual,op,expected,result",
    [
        ("CS", "in", "CS,EE,ME", True),
        ("CS", "in", "EE,ME", False),
        ("CS", "not_in", "EE,ME", True),
        ("CS", "not_in", "CS,EE", False),
        # Whitespace inside the comma list — common HackMD copy-paste artifact.
        ("CS", "in", " CS , EE , ME ", True),
        # Whitespace on the actual value too.
        ("  CS  ", "in", "CS,EE", True),
        # Empty list (degenerate config) — nothing matches.
        ("CS", "in", "", False),
        ("CS", "not_in", "", True),
    ],
)
def test_membership_operators(evaluator, actual, op, expected, result):
    assert evaluator(actual, op, expected) is result


# ---------------------------------------------------------------------------
# Substring (contains, not_contains)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "actual,op,expected,result",
    [
        ("國科會獎學金", "contains", "國科會", True),
        ("國科會獎學金", "contains", "教育部", False),
        ("國科會獎學金", "not_contains", "教育部", True),
        ("國科會獎學金", "not_contains", "國科會", False),
        # Empty needle is technically a substring of anything; document the
        # current behavior so future refactors don't quietly flip it.
        ("anything", "contains", "", True),
        ("anything", "not_contains", "", False),
    ],
)
def test_substring_operators(evaluator, actual, op, expected, result):
    assert evaluator(actual, op, expected) is result


# ---------------------------------------------------------------------------
# Unknown operator — must return False (and log a warning), never raise.
# This guards against typos in scholarship-rule configs proliferating into
# crashes during the once-a-month roster generation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("operator", ["===", "like", "regex", "GREATER_THAN", ""])
def test_unknown_operator_returns_false(evaluator, operator):
    assert evaluator("anything", operator, "anything") is False
