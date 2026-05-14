"""
Tests for the smaller schemas at the end of `app/schemas/application.py`:

  - **ApplicationStatusUpdate**: minimal status-mutation payload.
  - **DashboardStats**: zero-initialized counter schema for the admin
    dashboard. Default 0 + [] prevent dashboard math crashes.
  - **ProfessorAssignmentRequest** + **BulkApproveRequest**: admin
    bulk-action payloads. BulkApprove has SECURITY/UX-relevant
    invariants — min_length=1 (no empty bulk), send_notifications
    defaults True (admins MUST opt-out to silence emails).

These complete coverage of the application.py module (Validators
covered by 6a21, list-response props by 6a78, this wave fills the
remaining response/request schemas).

13 cases.
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.application import (
    ApplicationReviewCreate,
    ApplicationStatusUpdate,
    BulkApproveRequest,
    DashboardStats,
    ProfessorAssignmentRequest,
)

# ─── ApplicationStatusUpdate ────────────────────────────────────────


def test_status_update_requires_status():
    # Pin: status is the only required field. Comments/reason are
    # optional but the underlying endpoint may enforce one of them
    # per status transition.
    with pytest.raises(ValidationError):
        ApplicationStatusUpdate()  # type: ignore[call-arg]


def test_status_update_status_accepts_any_string():
    # Pin: schema-level is permissive (str) — the actual allowlist
    # is enforced server-side per state-machine transition. Pin so
    # a regression to enum doesn't break the existing API surface.
    obj = ApplicationStatusUpdate(status="anything-goes")
    assert obj.status == "anything-goes"


def test_status_update_optional_fields_default_none():
    obj = ApplicationStatusUpdate(status="approved")
    assert obj.comments is None
    assert obj.rejection_reason is None


# ─── DashboardStats counters ────────────────────────────────────────


def test_dashboard_stats_all_counters_default_zero():
    # Pin: 0-initialized counters so dashboard math (sum, max, ratio)
    # never crashes on an empty result set. A regression to None
    # would crash the cards.
    s = DashboardStats()
    assert s.total_applications == 0
    assert s.draft_applications == 0
    assert s.submitted_applications == 0
    assert s.approved_applications == 0
    assert s.rejected_applications == 0
    assert s.pending_review == 0


def test_dashboard_stats_total_amount_default_zero():
    # Pin: total_amount is Decimal(0), not None — frontend currency
    # formatter doesn't null-check.
    s = DashboardStats()
    assert s.total_amount == Decimal(0)


def test_dashboard_stats_recent_activities_default_empty_list():
    # Pin: [] not None — frontend .map() iteration safe.
    s = DashboardStats()
    assert s.recent_activities == []


# ─── ProfessorAssignmentRequest ─────────────────────────────────────


def test_professor_assignment_requires_nycu_id():
    # Pin: nycu_id is the only field. Endpoint resolves to professor
    # record by ID.
    with pytest.raises(ValidationError):
        ProfessorAssignmentRequest()  # type: ignore[call-arg]


# ─── BulkApproveRequest ─────────────────────────────────────────────


def test_bulk_approve_requires_application_ids():
    with pytest.raises(ValidationError):
        BulkApproveRequest()  # type: ignore[call-arg]


def test_bulk_approve_min_length_1():
    # Pin: empty list rejected. Admin shouldn't be able to "bulk
    # approve nothing" — endpoint would do no work but log audit
    # noise.
    with pytest.raises(ValidationError):
        BulkApproveRequest(application_ids=[])


def test_bulk_approve_send_notifications_defaults_true():
    # Pin: send_notifications=True default. Admins expect approvals
    # to notify the student by default. Flipping to False would
    # silently approve applications without telling anyone.
    r = BulkApproveRequest(application_ids=[1, 2, 3])
    assert r.send_notifications is True


def test_bulk_approve_send_notifications_can_be_disabled():
    # Pin: explicit opt-out works (silent bulk for migrations).
    r = BulkApproveRequest(application_ids=[1], send_notifications=False)
    assert r.send_notifications is False


def test_bulk_approve_comments_optional():
    r = BulkApproveRequest(application_ids=[1])
    assert r.comments is None


# ─── ApplicationReviewCreate ────────────────────────────────────────


def test_application_review_create_requires_application_id_and_stage():
    # Pin: minimum required fields. score/comments/recommendation
    # are all optional — the endpoint may allow score-only or
    # comment-only reviews.
    with pytest.raises(ValidationError):
        ApplicationReviewCreate(application_id=1)  # type: ignore[call-arg]
