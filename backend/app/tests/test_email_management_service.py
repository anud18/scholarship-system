"""
Contract tests for EmailManagementService (previously zero coverage).

The scheduled-email lifecycle endpoints (process_due / approve / cancel) had no
unit or HTTP test. These tests pin the observable contract with stubbed db +
email collaborators (no SMTP, no real ScheduledEmail rows):

- process_due_emails: per-email send, sent/failed accounting, mark_as_sent /
  mark_as_failed side effects, commit-per-email
- approve_scheduled_email / cancel_scheduled_email: the status guards that raise
  ValueError, and the happy-path state transition
"""

import pytest

from app.models.email_management import ScheduleStatus
from app.services.email_management_service import EmailManagementService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        rows = list(self._rows)
        return rows[0] if rows else None


class StubAsyncSession:
    def __init__(self, results=None):
        self.results = results or []
        self.executed = []
        self.committed = 0
        self.refreshed = []

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        return FakeResult(self.results)

    async def commit(self):
        self.committed += 1

    async def refresh(self, obj):
        self.refreshed.append(obj)


class StubEmailService:
    def __init__(self, raises: Exception = None):
        self.calls = []
        self.raises = raises

    async def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return True


class FakeScheduledEmail:
    """Duck-typed ScheduledEmail with the methods the service calls."""

    def __init__(self, **attrs):
        # sensible defaults for process_due_emails
        self.id = attrs.get("id", 1)
        self.recipient_email = attrs.get("recipient_email", "to@nycu.edu.tw")
        self.subject = attrs.get("subject", "Subject")
        self.body = attrs.get("body", "Body")
        self.cc_emails = attrs.get("cc_emails", None)
        self.bcc_emails = attrs.get("bcc_emails", None)
        self.email_category = attrs.get("email_category", "notification")
        self.application_id = attrs.get("application_id", None)
        self.scholarship_type_id = attrs.get("scholarship_type_id", None)
        self.template_key = attrs.get("template_key", "tpl")
        # for approve/cancel guards
        self.status = attrs.get("status", ScheduleStatus.pending)
        self.requires_approval = attrs.get("requires_approval", True)
        self.approved_by_user_id = attrs.get("approved_by_user_id", None)
        # recorded side effects
        self.sent = False
        self.failed_reason = None
        self.approved_with = None
        self.cancelled = False

    def mark_as_sent(self):
        self.sent = True

    def mark_as_failed(self, reason):
        self.failed_reason = reason

    def approve(self, user_id, notes=None):
        self.approved_with = (user_id, notes)

    def cancel(self):
        self.cancelled = True


def _service(email_raises=None):
    svc = EmailManagementService()
    svc.email_service = StubEmailService(raises=email_raises)
    return svc


# ─── process_due_emails ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_process_due_emails_sends_each_and_counts(monkeypatch):
    svc = _service()
    emails = [FakeScheduledEmail(id=1), FakeScheduledEmail(id=2)]

    async def fake_due(db, limit):
        return emails

    monkeypatch.setattr(svc, "get_due_scheduled_emails", fake_due)
    db = StubAsyncSession()

    stats = await svc.process_due_emails(db, batch_size=10)

    assert stats == {"processed": 2, "sent": 2, "failed": 0, "skipped": 0}
    assert all(e.sent for e in emails)
    assert len(svc.email_service.calls) == 2
    assert svc.email_service.calls[0]["to"] == "to@nycu.edu.tw"
    assert db.committed == 2  # one commit per email


@pytest.mark.asyncio
async def test_process_due_emails_empty_is_noop(monkeypatch):
    svc = _service()

    async def fake_due(db, limit):
        return []

    monkeypatch.setattr(svc, "get_due_scheduled_emails", fake_due)
    db = StubAsyncSession()

    stats = await svc.process_due_emails(db, batch_size=10)

    assert stats == {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}
    assert svc.email_service.calls == []


@pytest.mark.asyncio
async def test_process_due_emails_marks_failed_on_send_error(monkeypatch):
    svc = _service(email_raises=RuntimeError("SMTP down"))
    email = FakeScheduledEmail(id=5)

    async def fake_due(db, limit):
        return [email]

    monkeypatch.setattr(svc, "get_due_scheduled_emails", fake_due)
    db = StubAsyncSession()

    stats = await svc.process_due_emails(db, batch_size=10)

    assert stats == {"processed": 1, "sent": 0, "failed": 1, "skipped": 0}
    assert email.sent is False
    assert "SMTP down" in email.failed_reason
    assert db.committed == 1  # still commits the failed-state change


# ─── approve_scheduled_email ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_raises_when_not_found():
    svc = _service()
    db = StubAsyncSession(results=[])
    with pytest.raises(ValueError, match="not found"):
        await svc.approve_scheduled_email(db, email_id=99, approved_by_user_id=1)


@pytest.mark.asyncio
async def test_approve_raises_when_not_pending():
    svc = _service()
    email = FakeScheduledEmail(status=ScheduleStatus.sent)
    db = StubAsyncSession(results=[email])
    with pytest.raises(ValueError, match="Cannot approve"):
        await svc.approve_scheduled_email(db, email_id=1, approved_by_user_id=1)


@pytest.mark.asyncio
async def test_approve_happy_path_transitions_and_commits():
    svc = _service()
    email = FakeScheduledEmail(status=ScheduleStatus.pending, requires_approval=True, approved_by_user_id=None)
    db = StubAsyncSession(results=[email])

    result = await svc.approve_scheduled_email(db, email_id=1, approved_by_user_id=7, notes="ok")

    assert result is email
    assert email.approved_with == (7, "ok")
    assert db.committed == 1


# ─── cancel_scheduled_email ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_raises_when_not_found():
    svc = _service()
    db = StubAsyncSession(results=[])
    with pytest.raises(ValueError, match="not found"):
        await svc.cancel_scheduled_email(db, email_id=99)


@pytest.mark.asyncio
async def test_cancel_raises_when_not_pending():
    svc = _service()
    email = FakeScheduledEmail(status=ScheduleStatus.sent)
    db = StubAsyncSession(results=[email])
    with pytest.raises(ValueError, match="Cannot cancel"):
        await svc.cancel_scheduled_email(db, email_id=1)


@pytest.mark.asyncio
async def test_cancel_happy_path_transitions_and_commits():
    svc = _service()
    email = FakeScheduledEmail(status=ScheduleStatus.pending)
    db = StubAsyncSession(results=[email])

    result = await svc.cancel_scheduled_email(db, email_id=1)

    assert result is email
    assert email.cancelled is True
    assert db.committed == 1
