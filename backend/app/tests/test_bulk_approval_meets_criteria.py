"""
Pure-function tests for `BulkApprovalService._meets_approval_criteria`.

Predicate that gates auto-approval. Regression risk: a permissive bug
auto-approves applications that should have gone to manual review
(compliance / quota risk).

8 cases pinning the criteria evaluator:
- Empty criteria → True (no filter, all pass).
- max_ranking with application BELOW threshold → True (passes).
- max_ranking with application ABOVE threshold → False (filtered out).
- max_ranking with NULL class_ranking_percent → True (the AND-guard
  trips on falsy ranking).
- require_renewal=True with is_renewal=False → False.
- require_renewal=True with is_renewal=True → True.
- require_renewal=False is a no-op (doesn't reject anything).
- Exception inside the body returns False (defensive).
"""

from types import SimpleNamespace

import pytest

from app.services.bulk_approval_service import BulkApprovalService


@pytest.fixture
def service():
    return BulkApprovalService(db=None)  # type: ignore[arg-type]


def _app(*, class_ranking_percent=None, is_renewal=False, id=1) -> SimpleNamespace:
    """Duck-typed Application with just the fields the predicate reads."""
    return SimpleNamespace(
        id=id,
        class_ranking_percent=class_ranking_percent,
        is_renewal=is_renewal,
    )


def test_empty_criteria_passes_anything(service):
    """No filter ⇒ all applications meet criteria (no-op approval)."""
    assert service._meets_approval_criteria(_app(), {}) is True


def test_max_ranking_below_threshold_passes(service):
    """Applicant ranked in the top 10% with max_ranking=20 passes."""
    assert service._meets_approval_criteria(_app(class_ranking_percent="10.5"), {"max_ranking": 20.0}) is True


def test_max_ranking_above_threshold_rejected(service):
    """Applicant ranked at 30% with max_ranking=20 is rejected."""
    assert service._meets_approval_criteria(_app(class_ranking_percent="30.0"), {"max_ranking": 20.0}) is False


def test_max_ranking_with_null_ranking_passes(service):
    """class_ranking_percent=None ⇒ the AND-guard short-circuits, application
    passes through (because we don't have data to reject it on this criterion)."""
    assert service._meets_approval_criteria(_app(class_ranking_percent=None), {"max_ranking": 20.0}) is True


def test_require_renewal_true_blocks_non_renewals(service):
    assert service._meets_approval_criteria(_app(is_renewal=False), {"require_renewal": True}) is False


def test_require_renewal_true_accepts_renewals(service):
    assert service._meets_approval_criteria(_app(is_renewal=True), {"require_renewal": True}) is True


def test_require_renewal_false_is_noop(service):
    """require_renewal=False doesn't filter — both renewal and non-renewal pass."""
    assert service._meets_approval_criteria(_app(is_renewal=False), {"require_renewal": False}) is True
    assert service._meets_approval_criteria(_app(is_renewal=True), {"require_renewal": False}) is True


def test_exception_in_body_returns_false(service):
    """If something inside throws (e.g., max_ranking float() on bad data),
    return False — defensive default that doesn't auto-approve."""
    # max_ranking present + class_ranking_percent non-numeric ⇒ float() raises.
    app = _app(class_ranking_percent="not-a-number")
    assert service._meets_approval_criteria(app, {"max_ranking": 20.0}) is False


def test_multiple_criteria_all_must_pass(service):
    """Multiple filters AND together — failing any one rejects."""
    # max_ranking ok BUT not a renewal ⇒ rejected by the renewal check.
    app = _app(class_ranking_percent="5.0", is_renewal=False)
    assert service._meets_approval_criteria(app, {"max_ranking": 20.0, "require_renewal": True}) is False

    # Both pass.
    app2 = _app(class_ranking_percent="5.0", is_renewal=True)
    assert service._meets_approval_criteria(app2, {"max_ranking": 20.0, "require_renewal": True}) is True
