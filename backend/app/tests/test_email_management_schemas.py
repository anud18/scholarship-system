"""
Tests for `app/schemas/email_management.py`.

These schemas back the admin email-management page (history list,
scheduled-email queue, processing stats, summary cards). The
non-obvious invariants:

  - `priority` on `ScheduledEmailBase` is bounded **[1, 10]** —
    out-of-range values must reject so the scheduler's priority queue
    stays in a well-defined state.
  - `sent_by_system` defaults to **True** — manual sends are the
    exception, not the rule. Flipping the default would mis-classify
    every system-generated reminder as "sent by admin", breaking the
    admin/system filter on the history page.
  - `requires_approval` defaults to **False** — auto-send by default.
    Flipping to True would freeze every scheduled email until manually
    approved (an outage in disguise).
  - `retry_count` defaults to **0** — not None. Some math elsewhere
    increments this value; None would crash.

12 cases pinning 8 schemas.
"""

import pytest
from pydantic import ValidationError

from app.models.email_management import EmailCategory, EmailStatus
from app.schemas.email_management import (
    EmailHistoryBase,
    EmailProcessingStats,
    EmailSummaryStats,
    ScheduledEmailBase,
    ScheduledEmailCreate,
    ScheduledEmailUpdate,
    SendTestEmailRequest,
    SimpleTestEmailRequest,
)
from datetime import datetime, timezone

# ─── ScheduledEmailBase priority bounds ─────────────────────────────


def test_scheduled_email_priority_defaults_to_5():
    # Pin: middle-of-range default. Most admin-scheduled emails are
    # "normal priority" — flipping the default would shift the queue.
    e = ScheduledEmailBase(
        recipient_email="a@b.com",
        subject="hi",
        body="x",
        scheduled_for=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )
    assert e.priority == 5


def test_scheduled_email_priority_rejects_zero():
    # Pin: ge=1. Priority 0 would either be ignored by the scheduler
    # or trigger highest-priority by accident.
    with pytest.raises(ValidationError):
        ScheduledEmailBase(
            recipient_email="a@b.com",
            subject="x",
            body="x",
            scheduled_for=datetime(2025, 10, 22, tzinfo=timezone.utc),
            priority=0,
        )


def test_scheduled_email_priority_rejects_eleven():
    # Pin: le=10. Bound prevents arbitrary-int priority that breaks
    # the comparator in the scheduler heap.
    with pytest.raises(ValidationError):
        ScheduledEmailBase(
            recipient_email="a@b.com",
            subject="x",
            body="x",
            scheduled_for=datetime(2025, 10, 22, tzinfo=timezone.utc),
            priority=11,
        )


def test_scheduled_email_priority_accepts_boundary_values():
    # Pin: inclusive boundaries (1 and 10 valid).
    for p in (1, 10):
        e = ScheduledEmailBase(
            recipient_email="a@b.com",
            subject="x",
            body="x",
            scheduled_for=datetime(2025, 10, 22, tzinfo=timezone.utc),
            priority=p,
        )
        assert e.priority == p


# ─── Default values that gate system behaviour ──────────────────────


def test_email_history_sent_by_system_defaults_true():
    # Pin: most history rows come from system-generated sends. A
    # regression flipping this to False would mis-classify every
    # auto-sent notification as "manually sent by admin", breaking
    # filter UX on the admin email history page.
    h = EmailHistoryBase(
        recipient_email="a@b.com",
        subject="x",
        body="x",
        status=EmailStatus.sent,
    )
    assert h.sent_by_system is True


def test_email_history_retry_count_defaults_zero():
    # Pin: retry_count starts at 0, NOT None. Downstream code does
    # `row.retry_count += 1` — None would crash.
    h = EmailHistoryBase(
        recipient_email="a@b.com",
        subject="x",
        body="x",
        status=EmailStatus.sent,
    )
    assert h.retry_count == 0


def test_scheduled_email_requires_approval_defaults_false():
    # Pin: auto-send by default. Flipping to True would freeze every
    # scheduled email — silent outage masquerading as "queue empty".
    e = ScheduledEmailBase(
        recipient_email="a@b.com",
        subject="x",
        body="x",
        scheduled_for=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )
    assert e.requires_approval is False


# ─── ScheduledEmailCreate requires created_by_user_id ───────────────


def test_scheduled_create_requires_created_by_user_id():
    # Pin: created_by_user_id is required on Create (audit trail).
    # An anonymous-create would surface as "system-sent" in the
    # history, which it isn't.
    with pytest.raises(ValidationError):
        ScheduledEmailCreate(  # type: ignore[call-arg]
            recipient_email="a@b.com",
            subject="x",
            body="x",
            scheduled_for=datetime(2025, 10, 22, tzinfo=timezone.utc),
        )


# ─── ScheduledEmailUpdate is PATCH-shaped ───────────────────────────


def test_scheduled_update_all_optional():
    # Pin: PATCH semantics — empty body is a valid no-op.
    u = ScheduledEmailUpdate()
    assert u.subject is None
    assert u.body is None
    assert u.approval_notes is None


# ─── Stats schemas default fields ───────────────────────────────────


def test_processing_stats_defaults_zero():
    # Pin: counters default to 0 so callers don't need to seed them.
    # A regression to None would break sum() / max() arithmetic.
    s = EmailProcessingStats()
    assert s.processed == 0
    assert s.sent == 0
    assert s.failed == 0
    assert s.skipped == 0


def test_summary_stats_dict_fields_default_to_empty_dict():
    # Pin: by_category / by_scholarship_type default to {} so the
    # frontend can iterate without null-checks. A regression to None
    # would break .items() on the consumer side.
    s = EmailSummaryStats()
    assert s.by_category == {}
    assert s.by_scholarship_type == {}
    assert s.total_sent_today == 0


# ─── SendTestEmailRequest / SimpleTestEmailRequest ──────────────────


def test_send_test_email_request_test_data_defaults_empty_dict():
    # Pin: default_factory=dict — each call gets a fresh dict
    # (NOT a shared mutable default, which would be a classic Python
    # gotcha producing cross-request data leaks).
    r1 = SendTestEmailRequest(template_key="welcome", recipient_email="a@b.com")
    r2 = SendTestEmailRequest(template_key="welcome", recipient_email="c@d.com")
    r1.test_data["x"] = 1
    assert r2.test_data == {}  # not affected


def test_simple_test_email_request_required_fields():
    # Pin: recipient_email + subject + body all required. SimpleTest
    # is for system smoke-tests, no defaults.
    with pytest.raises(ValidationError):
        SimpleTestEmailRequest(recipient_email="a@b.com", subject="x")  # type: ignore[call-arg]
