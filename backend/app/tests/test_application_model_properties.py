"""
Pure-property tests for the `Application` SQLAlchemy model.

These properties drive UI affordances:
- `is_editable` decides whether the student sees Save/Cancel vs view-only
- `can_be_reviewed` gates the professor's review queue inclusion
- `is_overdue` colors the deadline banner red
- `academic_term_label` / `application_type_label` render on every card

Bugs cause:
- Lock-out (is_editable returns False for editable apps) → student
  panic + admin tickets
- Stale queue inclusion (can_be_reviewed True after approval) → confused
  reviewers
- Wrong overdue verdict → student misses real deadlines

These are pure attribute checks — they read `self.status`, `self.semester`,
etc. SimpleNamespace duck-types the Application.

11 properties / methods covered (14 cases).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.application import Application
from app.models.enums import ApplicationStatus, Semester


def _make(application_obj_class=Application, **overrides) -> Application:
    """Construct an Application without invoking SQLAlchemy ORM init.
    We bind attributes directly so properties read them."""
    app = object.__new__(application_obj_class)
    defaults = {
        "id": 1,
        "app_id": "APP-114-1-00001",
        "status": ApplicationStatus.draft,
        "semester": Semester.first,
        "academic_year": 114,
        "is_renewal": False,
        "review_deadline": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        object.__setattr__(app, k, v)
    return app


# ─── is_editable ─────────────────────────────────────────────────────


def test_is_editable_draft():
    """Draft is editable — student can save and submit."""
    assert _make(status=ApplicationStatus.draft).is_editable is True


def test_is_editable_returned():
    """Returned status is editable — student can amend per reviewer
    feedback and re-submit."""
    assert _make(status=ApplicationStatus.returned).is_editable is True


def test_is_editable_submitted_is_false():
    """Once submitted, NOT editable. Pin so a refactor doesn't
    accidentally re-enable editing post-submission (would corrupt
    audit trail)."""
    assert _make(status=ApplicationStatus.submitted).is_editable is False
    assert _make(status=ApplicationStatus.approved).is_editable is False
    assert _make(status=ApplicationStatus.rejected).is_editable is False


# ─── is_submitted ────────────────────────────────────────────────────


def test_is_submitted_true_for_anything_not_draft():
    """is_submitted = (status != draft). All non-draft statuses are
    considered 'submitted' from a workflow perspective."""
    for s in (
        ApplicationStatus.submitted,
        ApplicationStatus.under_review,
        ApplicationStatus.approved,
        ApplicationStatus.rejected,
        ApplicationStatus.withdrawn,
    ):
        assert _make(status=s).is_submitted is True, f"status={s}"


def test_is_submitted_false_for_draft():
    assert _make(status=ApplicationStatus.draft).is_submitted is False


# ─── can_be_reviewed ─────────────────────────────────────────────────


def test_can_be_reviewed_only_submitted_or_under_review():
    """Pin the exact two statuses that gate review-queue inclusion —
    any other status (approved/rejected/etc.) must be excluded."""
    assert _make(status=ApplicationStatus.submitted).can_be_reviewed is True
    assert _make(status=ApplicationStatus.under_review).can_be_reviewed is True

    for s in (
        ApplicationStatus.draft,
        ApplicationStatus.approved,
        ApplicationStatus.rejected,
        ApplicationStatus.withdrawn,
    ):
        assert _make(status=s).can_be_reviewed is False, f"status={s} unexpectedly reviewable"


# ─── is_overdue ──────────────────────────────────────────────────────


def test_is_overdue_no_deadline_is_false():
    """Without a deadline, can't be overdue (don't color banner red
    on apps that haven't been queued yet)."""
    assert _make(review_deadline=None).is_overdue is False


def test_is_overdue_deadline_in_past_is_true():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _make(review_deadline=past).is_overdue is True


def test_is_overdue_deadline_in_future_is_false():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _make(review_deadline=future).is_overdue is False


# ─── Label methods ───────────────────────────────────────────────────


def test_academic_term_label_first():
    label = _make(academic_year=114, semester=Semester.first).academic_term_label
    assert label == "114學年度 第一學期"


def test_academic_term_label_second():
    label = _make(academic_year=113, semester=Semester.second).academic_term_label
    assert label == "113學年度 第二學期"


def test_academic_term_label_yearly():
    label = _make(academic_year=114, semester=Semester.yearly).academic_term_label
    assert label == "114學年度 全年"


def test_application_type_label_renewal_vs_general():
    """Renewal apps say '續領申請', new apps say '一般申請'. Pin so the UI
    badge doesn't silently flip."""
    assert _make(is_renewal=True).application_type_label == "續領申請"
    assert _make(is_renewal=False).application_type_label == "一般申請"


def test_is_renewal_application_and_is_general_are_inverses():
    """Pin invariant: at most one is True. Future-self should not be
    able to refactor to both False without surfacing here."""
    for is_renewal_flag in (True, False):
        app = _make(is_renewal=is_renewal_flag)
        assert app.is_renewal_application is not app.is_general_application


# ─── get_review_stage ────────────────────────────────────────────────


def test_get_review_stage_renewal_routes():
    """Renewal apps route to renewal_professor / renewal_college."""
    assert _make(is_renewal=True, status=ApplicationStatus.submitted).get_review_stage() == "renewal_professor"
    assert _make(is_renewal=True, status=ApplicationStatus.under_review).get_review_stage() == "renewal_college"


def test_get_review_stage_general_routes():
    """General apps route to general_professor / general_college."""
    assert _make(is_renewal=False, status=ApplicationStatus.submitted).get_review_stage() == "general_professor"
    assert _make(is_renewal=False, status=ApplicationStatus.under_review).get_review_stage() == "general_college"


def test_get_review_stage_returns_none_for_terminal_states():
    """Approved/rejected/draft → None (no active review stage).
    Pin so admin dashboard's 'current stage' column doesn't accidentally
    show a stale value."""
    for s in (ApplicationStatus.draft, ApplicationStatus.approved, ApplicationStatus.rejected):
        assert _make(status=s).get_review_stage() is None, f"status={s}"
