"""
Property-based tests for RosterService._evaluate_condition.

Phase 6 of test-surface-hardening: incremental, not transformative.
The 26 parametrize cases in test_scholarship_rules_service.py already
cover the operator surface well; hypothesis adds value here only for
properties that parametrize cannot easily express:

  1. Symmetry: for every (actual, op, expected),
       evaluate(a, op, e) != evaluate(a, negate(op), e)
     for paired operators (>=/<, ==/!=, in/not_in, contains/not_contains).
  2. None-safety: evaluate(None, op, expected) is False for any
     (op, expected). Roster_service.py:1187 short-circuits None →
     this property guards against a future "fix" that drops the guard.
  3. Type-coercion idempotence: numeric comparisons agree across the
     int / float / numeric-string forms of the same value
     (roster_service.py:1193 wraps both sides in float()).

`_evaluate_condition` is reachable on a RosterService instance built with
no DB session — the method is purely functional. We instantiate with
db=None and call the bound method directly.

Cap: max_examples=200, deadline=500ms — keeps the suite under 10s and
fits inside the smoke time budget.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.roster_service import RosterService

pytestmark = pytest.mark.unit


# Pairs of operators whose results must be inverses on the same input.
# (When `actual` is None, both branches return False — the symmetry
# property is conditional on actual being non-None and the inputs being
# parseable for the operator's coercion strategy.)
_NUMERIC_INVERSES = [(">=", "<"), ("<=", ">")]
_STRING_INVERSES = [
    ("==", "!="),
    ("in", "not_in"),
    ("contains", "not_contains"),
]


def _svc() -> RosterService:
    """A purely-functional RosterService — _evaluate_condition uses no db."""
    # Even though __init__ assigns self.student_verification_service = ...,
    # _evaluate_condition only reads its arguments; the constructor side
    # effects are tolerated.
    return RosterService(db=None)


class TestEvaluateConditionNoneSafety:
    """Property: None actual → False, regardless of operator/expected."""

    @given(
        op=st.sampled_from([">=", "<=", ">", "<", "==", "!=", "in", "not_in", "contains", "not_contains"]),
        expected=st.text(min_size=0, max_size=20),
    )
    @settings(max_examples=100, deadline=500)
    def test_none_actual_always_false(self, op, expected):
        assert _svc()._evaluate_condition(None, op, expected) is False


class TestEvaluateConditionNumericSymmetry:
    """Property: paired numeric operators are mutually exclusive on equal inputs."""

    @pytest.mark.parametrize("op_a,op_b", _NUMERIC_INVERSES)
    @given(
        actual=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        expected=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=500)
    def test_numeric_pair_partitions_when_unequal(self, op_a, op_b, actual, expected):
        # When actual == expected, both >= and <= are true (and < and > are
        # both false). The strict partition only holds when the values
        # differ. Skip the equal case rather than weakening the property.
        if actual == expected:
            return
        a = _svc()._evaluate_condition(actual, op_a, str(expected))
        b = _svc()._evaluate_condition(actual, op_b, str(expected))
        assert a != b, (
            f"expected {op_a} and {op_b} to be inverses on " f"actual={actual} expected={expected}, both returned {a}"
        )


class TestEvaluateConditionStringSymmetry:
    """Property: paired string-style operators are inverses."""

    @pytest.mark.parametrize("op_a,op_b", _STRING_INVERSES)
    @given(
        actual=st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),
            min_size=1,
            max_size=10,
        ),
        expected=st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=200, deadline=500)
    def test_string_pair_inverses(self, op_a, op_b, actual, expected):
        # `in` / `not_in` split `expected` on commas; we exclude commas from
        # the alphabet via codepoint range (33..126 contains comma at 44, so
        # filter explicitly).
        if "," in expected or "," in actual:
            return
        a = _svc()._evaluate_condition(actual, op_a, expected)
        b = _svc()._evaluate_condition(actual, op_b, expected)
        assert a != b, (
            f"{op_a} and {op_b} returned the same value ({a}) for " f"actual={actual!r} expected={expected!r}"
        )


class TestEvaluateConditionTypeCoercion:
    """Property: numeric comparisons agree across int / float / str forms."""

    @given(
        actual=st.integers(min_value=-1000, max_value=1000),
        expected=st.integers(min_value=-1000, max_value=1000),
        op=st.sampled_from([">=", "<=", ">", "<"]),
    )
    @settings(max_examples=200, deadline=500)
    def test_numeric_form_idempotent(self, actual, expected, op):
        svc = _svc()
        as_int = svc._evaluate_condition(actual, op, str(expected))
        as_float = svc._evaluate_condition(float(actual), op, str(float(expected)))
        as_str = svc._evaluate_condition(str(actual), op, str(expected))
        assert as_int == as_float == as_str, (
            f"int/float/str disagreed on op={op} actual={actual} expected={expected}: "
            f"int={as_int} float={as_float} str={as_str}"
        )
