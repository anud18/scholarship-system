"""
Contract tests for ScholarshipNotificationService (previously zero coverage).

This service was exercised in the suite only via a StubNotificationService in
bulk_approval tests, so the real implementation never ran. These tests pin the
observable contract of its email-sending methods with stubbed collaborators
(no DB session, no SMTP):

- recipient resolution (student `user.email` vs `professor_user.email`)
- the guards that return False (missing user / missing student_data)
- the happy-path return value and that send_email is actually invoked
- exceptions from the email layer are swallowed into a False return
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.application import ApplicationStatus
from app.services.scholarship_notification_service import ScholarshipNotificationService


class FakeResult:
    """Mimics the subset of a SQLAlchemy Result the service uses."""

    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        rows = list(self._rows)
        return rows[0] if rows else None


class StubAsyncSession:
    """Records execute/commit; returns a preset row list for the User lookup."""

    def __init__(self, results=None):
        self.results = results or []
        self.executed = []
        self.committed = 0

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        return FakeResult(self.results)

    async def commit(self):
        self.committed += 1


class StubEmailService:
    """Records send_email calls; optionally raises to test the error path."""

    def __init__(self, raises: Exception = None):
        self.calls = []
        self.raises = raises

    async def send_email(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return True


def _service(results=None, email_raises=None):
    """Build the service with stubbed db + email collaborators."""
    svc = ScholarshipNotificationService(db=StubAsyncSession(results=results))
    svc.email_service = StubEmailService(raises=email_raises)
    return svc


def _application(**overrides):
    """Duck-typed Application — the service only reads attributes."""
    defaults = {
        "id": 1,
        "user_id": 42,
        "app_id": "APP-114-1-00001",
        "status": ApplicationStatus.submitted.value,
        "student_data": {"std_cname": "王小明", "std_stdcode": "310460031"},
        "scholarship_name": "國科會博士生獎學金",
        "sub_scholarship_type": "nstc",
        "semester": "first",
        "academic_year": 114,
        "submitted_at": datetime(2026, 5, 30, 12, 0, 0, tzinfo=timezone.utc),
        "review_deadline": None,
        "is_renewal": False,
        "reviews": [],
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _user(email="student@nycu.edu.tw"):
    return SimpleNamespace(id=42, email=email, name="王小明", nycu_id="310460031")


# ─── send_application_submitted_notification ──────────────────────────────────


@pytest.mark.asyncio
async def test_submitted_happy_path_sends_to_student_email():
    svc = _service(results=[_user("stu@nycu.edu.tw")])
    ok = await svc.send_application_submitted_notification(_application())
    assert ok is True
    assert len(svc.email_service.calls) == 1
    assert svc.email_service.calls[0]["to"] == "stu@nycu.edu.tw"


@pytest.mark.asyncio
async def test_submitted_returns_false_when_user_missing():
    svc = _service(results=[])  # User lookup yields nothing
    ok = await svc.send_application_submitted_notification(_application())
    assert ok is False
    assert svc.email_service.calls == []  # no email attempted


@pytest.mark.asyncio
async def test_submitted_returns_false_when_student_data_missing():
    svc = _service(results=[_user()])
    ok = await svc.send_application_submitted_notification(_application(student_data=None))
    assert ok is False
    assert svc.email_service.calls == []


@pytest.mark.asyncio
async def test_submitted_returns_false_when_email_layer_raises():
    svc = _service(results=[_user()], email_raises=RuntimeError("SMTP down"))
    ok = await svc.send_application_submitted_notification(_application())
    assert ok is False  # exception swallowed, not propagated


@pytest.mark.asyncio
async def test_submitted_renewal_still_sends():
    svc = _service(results=[_user()])
    ok = await svc.send_application_submitted_notification(_application(is_renewal=True))
    assert ok is True
    assert len(svc.email_service.calls) == 1


# ─── send_status_change_notification ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_change_happy_path_sends_to_student():
    svc = _service(results=[_user("stu@nycu.edu.tw")])
    ok = await svc.send_status_change_notification(
        _application(),
        old_status=ApplicationStatus.submitted.value,
        new_status=ApplicationStatus.approved.value,
    )
    assert ok is True
    assert svc.email_service.calls[0]["to"] == "stu@nycu.edu.tw"


@pytest.mark.asyncio
async def test_status_change_returns_false_when_student_data_missing():
    svc = _service(results=[_user()])
    ok = await svc.send_status_change_notification(
        _application(student_data=None),
        old_status="submitted",
        new_status="approved",
    )
    assert ok is False
    assert svc.email_service.calls == []


# ─── send_professor_review_request ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_professor_review_request_sends_to_professor_email():
    # No User lookup on this path — professor_user is passed in directly.
    svc = _service(results=[])
    professor = SimpleNamespace(id=7, email="prof@nycu.edu.tw", name="李教授")
    ok = await svc.send_professor_review_request(_application(), professor)
    assert ok is True
    assert svc.email_service.calls[0]["to"] == "prof@nycu.edu.tw"


@pytest.mark.asyncio
async def test_professor_review_request_returns_false_without_student_data():
    svc = _service(results=[])
    professor = SimpleNamespace(id=7, email="prof@nycu.edu.tw", name="李教授")
    ok = await svc.send_professor_review_request(_application(student_data=None), professor)
    assert ok is False
    assert svc.email_service.calls == []
