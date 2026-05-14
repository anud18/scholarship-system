"""
Tests for `ApplicationListResponse` computed properties + defaults.

This is the schema returned by every application-list endpoint
(student dashboard, professor review queue, admin search). Three
computed properties drive UI state on the cards:

  - **is_editable** = True iff status ∈ {draft, returned}.
    Drives the "Edit" button visibility. A regression would either
    let students edit submitted applications (data integrity) or
    block them from editing draft/returned (UX block).

  - **is_submitted** = True iff status ≠ draft.
    Drives the "View" vs "Edit" routing.

  - **can_be_reviewed** = True iff status ∈ {submitted,
    under_review}. Drives the professor review queue filter.

Defaults pinned:
  - currency="TWD" — flipping the default would silently change
    every new record's currency.
  - is_renewal=False, agree_terms=False, requires_professor_
    recommendation=False, requires_college_review=False — none of
    these are ever True by default; they all require explicit
    opt-in by the underlying scholarship configuration.

15 cases.
"""

from datetime import datetime, timezone

import pytest

from app.models.enums import ApplicationStatus
from app.schemas.application import ApplicationListResponse


def _kwargs(status: str = "draft", **overrides):
    base = dict(
        id=1,
        app_id="APP-113-1-00001",
        user_id=1,
        scholarship_type_id=1,
        status=status,
        status_name=None,
        academic_year=113,
        student_data={},
        submitted_form_data={},
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        updated_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return base


# ─── is_editable property ────────────────────────────────────────────


def test_is_editable_true_for_draft():
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.draft.value))
    assert r.is_editable is True


def test_is_editable_true_for_returned():
    # Pin: returned (sent back to student for revision) is the
    # second "Edit" state — without this students couldn't fix
    # what professors asked them to fix.
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.returned.value))
    assert r.is_editable is True


def test_is_editable_false_for_submitted():
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.submitted.value))
    assert r.is_editable is False


def test_is_editable_false_for_under_review():
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.under_review.value))
    assert r.is_editable is False


def test_is_editable_false_for_approved_and_rejected():
    # Pin: terminal states can't be edited.
    for s in (ApplicationStatus.approved.value, ApplicationStatus.rejected.value):
        r = ApplicationListResponse(**_kwargs(status=s))
        assert r.is_editable is False, f"approved/rejected must not be editable (got True for {s})"


# ─── is_submitted property ───────────────────────────────────────────


def test_is_submitted_false_for_draft():
    # Pin: only draft counts as "not submitted".
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.draft.value))
    assert r.is_submitted is False


def test_is_submitted_true_for_every_other_status():
    # Pin: everything except draft is "submitted" (even rejected
    # historically went through submission).
    for s in (
        ApplicationStatus.submitted.value,
        ApplicationStatus.under_review.value,
        ApplicationStatus.approved.value,
        ApplicationStatus.rejected.value,
        ApplicationStatus.returned.value,
    ):
        r = ApplicationListResponse(**_kwargs(status=s))
        assert r.is_submitted is True, f"expected is_submitted=True for {s}"


# ─── can_be_reviewed property ────────────────────────────────────────


def test_can_be_reviewed_true_for_submitted():
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.submitted.value))
    assert r.can_be_reviewed is True


def test_can_be_reviewed_true_for_under_review():
    r = ApplicationListResponse(**_kwargs(status=ApplicationStatus.under_review.value))
    assert r.can_be_reviewed is True


def test_can_be_reviewed_false_for_terminal_statuses():
    # Pin: approved/rejected/returned all FALSE — review is a
    # one-shot transition out of submitted/under_review.
    for s in (
        ApplicationStatus.approved.value,
        ApplicationStatus.rejected.value,
        ApplicationStatus.returned.value,
        ApplicationStatus.draft.value,
    ):
        r = ApplicationListResponse(**_kwargs(status=s))
        assert r.can_be_reviewed is False, f"expected can_be_reviewed=False for {s}"


# ─── Defaults ────────────────────────────────────────────────────────


def test_currency_defaults_to_twd():
    # Pin: TWD is the canonical NYCU currency. Flipping would
    # silently change every new record's currency.
    r = ApplicationListResponse(**_kwargs())
    assert r.currency == "TWD"


def test_is_renewal_defaults_false():
    # Pin: new applications are NOT renewals by default. The
    # scholarship configuration sets renewal eligibility — applicant
    # opts-in via the form.
    r = ApplicationListResponse(**_kwargs())
    assert r.is_renewal is False


def test_agree_terms_defaults_false():
    # Pin: agreement must be EXPLICITLY accepted by the student
    # before submission. Default False protects against form-skipping.
    r = ApplicationListResponse(**_kwargs())
    assert r.agree_terms is False


def test_workflow_flags_default_false():
    # Pin: requires_professor_recommendation +
    # requires_college_review default False. These are set on
    # the underlying scholarship config — the response surfaces
    # them for the frontend, but default is "no extra workflow".
    r = ApplicationListResponse(**_kwargs())
    assert r.requires_professor_recommendation is False
    assert r.requires_college_review is False


def test_scholarship_subtype_list_defaults_empty():
    # Pin: empty list, NOT None — frontend .map() doesn't have to
    # null-check.
    r = ApplicationListResponse(**_kwargs())
    assert r.scholarship_subtype_list == []
