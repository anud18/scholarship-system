"""
Tests for `Application.is_editable`, `is_submitted`, and `can_be_reviewed`
status-derived properties.

These properties encode the application state-machine boundary: which
statuses are user-editable, which are review-actionable, and which count
as "submitted" for filter/dashboard purposes. They drive:

- Frontend "edit" / "submit" button visibility (a regression here would
  let users mutate already-submitted applications)
- Professor review queue filtering (regression = reviewers see / can act
  on irrelevant rows)
- Audit log "submitted vs. not yet" categorization

The state machine has 12 enum members (see ApplicationStatus); the tests
parametrise over every member to prevent silent drift if a new state is
added without updating the property logic.

Wave 2a of the production-readiness rollout — second batch (the first
batch covered the app-id format contract in PR #222).
"""

from __future__ import annotations

import pytest

from app.models.application import Application
from app.models.enums import ApplicationStatus

pytestmark = pytest.mark.smoke


def _app_with_status(status: ApplicationStatus) -> Application:
    """
    Build a minimal Application instance with only `status` set. The
    properties under test only read `self.status`, so the rest can stay
    unset / default. No DB involved.
    """
    app = Application()
    app.status = status
    return app


# ---------------------------------------------------------------------------
# is_editable
# ---------------------------------------------------------------------------


class TestIsEditable:
    """An application is editable iff status ∈ {draft, returned}."""

    @pytest.mark.parametrize(
        "status",
        [ApplicationStatus.draft, ApplicationStatus.returned],
    )
    def test_editable_statuses(self, status: ApplicationStatus) -> None:
        assert _app_with_status(status).is_editable is True

    @pytest.mark.parametrize(
        "status",
        [
            ApplicationStatus.submitted,
            ApplicationStatus.under_review,
            ApplicationStatus.pending_documents,
            ApplicationStatus.approved,
            ApplicationStatus.partial_approved,
            ApplicationStatus.rejected,
            ApplicationStatus.withdrawn,
            ApplicationStatus.cancelled,
            ApplicationStatus.manual_excluded,
            ApplicationStatus.deleted,
        ],
    )
    def test_non_editable_statuses(self, status: ApplicationStatus) -> None:
        assert _app_with_status(status).is_editable is False

    def test_all_enum_members_classified(self) -> None:
        """
        Defense against future regressions: when a new ApplicationStatus is
        added, this test forces us to also decide if it's editable. Counts
        both branches and asserts that draft + returned are exactly the two
        editable members.
        """
        editable = {s for s in ApplicationStatus if _app_with_status(s).is_editable}
        assert editable == {ApplicationStatus.draft, ApplicationStatus.returned}


# ---------------------------------------------------------------------------
# is_submitted
# ---------------------------------------------------------------------------


class TestIsSubmitted:
    """`is_submitted` is the inverse of "still in draft" — anything other
    than draft counts as submitted (including terminal states like rejected
    / withdrawn). That's a deliberate semantics choice: dashboards distinguish
    "student hasn't filed yet" from "the system has it now".
    """

    def test_draft_is_not_submitted(self) -> None:
        assert _app_with_status(ApplicationStatus.draft).is_submitted is False

    @pytest.mark.parametrize(
        "status",
        [
            ApplicationStatus.submitted,
            ApplicationStatus.under_review,
            ApplicationStatus.pending_documents,
            ApplicationStatus.approved,
            ApplicationStatus.partial_approved,
            ApplicationStatus.rejected,
            ApplicationStatus.returned,
            ApplicationStatus.withdrawn,
            ApplicationStatus.cancelled,
            ApplicationStatus.manual_excluded,
            ApplicationStatus.deleted,
        ],
    )
    def test_non_draft_is_submitted(self, status: ApplicationStatus) -> None:
        assert _app_with_status(status).is_submitted is True


# ---------------------------------------------------------------------------
# can_be_reviewed
# ---------------------------------------------------------------------------


class TestCanBeReviewed:
    """An application is review-actionable iff status ∈ {submitted,
    under_review}. Anything in pending_documents needs more info from the
    student first, and terminal states (approved/rejected/etc.) are done."""

    @pytest.mark.parametrize(
        "status",
        [ApplicationStatus.submitted, ApplicationStatus.under_review],
    )
    def test_reviewable_statuses(self, status: ApplicationStatus) -> None:
        assert _app_with_status(status).can_be_reviewed is True

    @pytest.mark.parametrize(
        "status",
        [
            ApplicationStatus.draft,
            ApplicationStatus.pending_documents,
            ApplicationStatus.approved,
            ApplicationStatus.partial_approved,
            ApplicationStatus.rejected,
            ApplicationStatus.returned,
            ApplicationStatus.withdrawn,
            ApplicationStatus.cancelled,
            ApplicationStatus.manual_excluded,
            ApplicationStatus.deleted,
        ],
    )
    def test_non_reviewable_statuses(self, status: ApplicationStatus) -> None:
        assert _app_with_status(status).can_be_reviewed is False

    def test_all_enum_members_classified(self) -> None:
        """Same defense-in-depth as TestIsEditable: a new status must
        explicitly land on one side of the reviewable boundary."""
        reviewable = {s for s in ApplicationStatus if _app_with_status(s).can_be_reviewed}
        assert reviewable == {
            ApplicationStatus.submitted,
            ApplicationStatus.under_review,
        }


# ---------------------------------------------------------------------------
# Invariants across all three properties
# ---------------------------------------------------------------------------


class TestStatusPropertyInvariants:
    """Cross-property invariants. If any of these break, the state machine has
    a contradiction (e.g., a status that's both editable and reviewable at the
    same time would be a UX bug)."""

    def test_editable_and_reviewable_are_disjoint(self) -> None:
        """No status should be both editable AND review-actionable. A status
        that's user-editable means the student is still working on it; the
        professor shouldn't see it in their queue yet."""
        for status in ApplicationStatus:
            app = _app_with_status(status)
            assert not (app.is_editable and app.can_be_reviewed), (
                f"Status {status.value} is both editable and reviewable — "
                "this would let professors review an in-progress draft."
            )

    def test_editable_implies_not_submitted(self) -> None:
        """If a student can still edit it, it can't have been considered
        submitted by downstream filters. (returned is the documented edge:
        it's editable AND is_submitted, because the system DID receive it
        — the professor sent it back for revision.)"""
        # draft must NOT be submitted
        assert _app_with_status(ApplicationStatus.draft).is_editable is True
        assert _app_with_status(ApplicationStatus.draft).is_submitted is False
        # returned IS submitted even though editable (documented exception)
        assert _app_with_status(ApplicationStatus.returned).is_editable is True
        assert _app_with_status(ApplicationStatus.returned).is_submitted is True

    def test_reviewable_implies_submitted(self) -> None:
        """If the professor can act on it, the system must have received it."""
        for status in ApplicationStatus:
            app = _app_with_status(status)
            if app.can_be_reviewed:
                assert app.is_submitted is True, (
                    f"Status {status.value} is reviewable but not submitted — " "contradicts the state machine."
                )
