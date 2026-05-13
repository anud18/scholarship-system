"""
Pure-function tests for `ScheduledEmail` state machine.

ScheduledEmail.is_ready_to_send gates the cron worker — if it returns
True for an unsent email that shouldn't go yet (e.g., not yet approved,
or already sent), we duplicate-send. If False for an email that should
send, students miss notifications.

The approval-required path is SECURITY-adjacent: it gates batch-send
emails that require admin sign-off (e.g., reject letters). A bypass
here could send harsh letters without admin review.

6 helpers covered (12 cases):
- `is_due`              : time-based gate
- `is_ready_to_send`    : composite gate (4 conditions)
- `mark_as_sent`        : terminal status transition
- `mark_as_failed`      : error capture + retry counter
- `approve`             : admin sign-off recording
- `cancel`              : explicit cancellation
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.email_management import ScheduledEmail, ScheduleStatus


def _email(**overrides) -> ScheduledEmail:
    e = object.__new__(ScheduledEmail)
    defaults = {
        "id": 1,
        "recipient_email": "test@u.tw",
        "scheduled_for": datetime.now(timezone.utc),
        "status": ScheduleStatus.pending,
        "requires_approval": False,
        "approved_by_user_id": None,
        "approved_at": None,
        "approval_notes": None,
        "last_error": None,
        "retry_count": 0,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        object.__setattr__(e, k, v)
    return e


# ─── is_due ──────────────────────────────────────────────────────────


def test_is_due_past_scheduled_time():
    """scheduled_for in past → due (boundary inclusive via <=)."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _email(scheduled_for=past).is_due is True


def test_is_due_future_scheduled_time():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _email(scheduled_for=future).is_due is False


def test_is_due_boundary_inclusive():
    """scheduled_for == now → due. Pin so an email scheduled for 'now'
    is picked up by the worker rather than skipped."""
    now = datetime.now(timezone.utc)
    e = _email(scheduled_for=now)
    # `is_due` uses `<= datetime.now()` — between the time we set
    # scheduled_for and the property read, now() will be slightly later,
    # so the comparison returns True.
    assert e.is_due is True


# ─── is_ready_to_send (composite gate) ───────────────────────────────


def test_is_ready_pending_due_no_approval_required():
    """All 4 checks pass: due + pending + not requires_approval."""
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    e = _email(scheduled_for=past, status=ScheduleStatus.pending, requires_approval=False)
    assert e.is_ready_to_send is True


def test_is_ready_blocked_when_not_due():
    """Not yet due → not ready."""
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    e = _email(scheduled_for=future, status=ScheduleStatus.pending)
    assert e.is_ready_to_send is False


def test_is_ready_blocked_when_not_pending():
    """Status not pending (sent/failed/cancelled) → not ready.
    SECURITY: prevents duplicate sends — once status is 'sent',
    is_ready must return False."""
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    for s in (ScheduleStatus.sent, ScheduleStatus.failed, ScheduleStatus.cancelled):
        e = _email(scheduled_for=past, status=s)
        assert e.is_ready_to_send is False, f"status={s} unexpectedly ready"


def test_is_ready_blocked_when_approval_required_but_missing():
    """SECURITY: requires_approval=True + no approved_by_user_id → NOT
    ready. Pin the approval gate — bypass would batch-send admin-gated
    emails (e.g., reject letters) without sign-off."""
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    e = _email(
        scheduled_for=past,
        status=ScheduleStatus.pending,
        requires_approval=True,
        approved_by_user_id=None,
    )
    assert e.is_ready_to_send is False


def test_is_ready_when_approval_required_and_present():
    """Once approved, the email passes the approval check."""
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    e = _email(
        scheduled_for=past,
        status=ScheduleStatus.pending,
        requires_approval=True,
        approved_by_user_id=42,
    )
    assert e.is_ready_to_send is True


# ─── State transition methods ────────────────────────────────────────


def test_mark_as_sent_transitions_to_sent():
    e = _email(status=ScheduleStatus.pending)
    e.mark_as_sent()
    assert e.status == ScheduleStatus.sent


def test_mark_as_failed_captures_error_and_increments_retry():
    """Pin: sets status, last_error, AND increments retry_count.
    The retry_count drives the exponential backoff in the worker —
    failing to increment would loop forever."""
    e = _email(status=ScheduleStatus.pending, retry_count=2)
    e.mark_as_failed("SMTP connection refused")
    assert e.status == ScheduleStatus.failed
    assert e.last_error == "SMTP connection refused"
    assert e.retry_count == 3


def test_approve_records_user_timestamp_and_notes():
    """Approval records WHO approved, WHEN, and optional notes."""
    e = _email(requires_approval=True)
    e.approve(approved_by_user_id=99, notes="batch reject letters reviewed")
    assert e.approved_by_user_id == 99
    assert e.approved_at is not None
    assert e.approval_notes == "batch reject letters reviewed"


def test_approve_without_notes_leaves_notes_none():
    """Optional notes — None when not provided. Pin so a refactor that
    accidentally sets notes="None" (literal string) is caught."""
    e = _email()
    e.approve(approved_by_user_id=99)
    assert e.approved_by_user_id == 99
    assert e.approval_notes is None


def test_cancel_transitions_to_cancelled():
    """Cancel is a terminal state — pin the transition. Note: no guard
    against cancelling already-sent emails (current implementation
    allows it; pin so a future tightening is intentional)."""
    e = _email(status=ScheduleStatus.pending)
    e.cancel()
    assert e.status == ScheduleStatus.cancelled
