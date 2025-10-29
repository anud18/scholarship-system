from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.email_management import EmailCategory
from app.services import email_automation_service as email_automation_module
from app.services.email_automation_service import EmailAutomationRule, EmailAutomationService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class StubAsyncSession:
    def __init__(self, results=None, side_effect=None):
        self.results = results or []
        self.side_effect = side_effect
        self.executed = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, query, params=None):
        self.executed.append((query, params))
        if self.side_effect:
            raise self.side_effect
        return FakeResult(self.results)

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


class StubEmailService:
    def __init__(self):
        self.sent_with_template = []
        self.scheduled = []

    async def send_with_template(self, **kwargs):
        self.sent_with_template.append(kwargs)

    async def schedule_email(self, **kwargs):
        self.scheduled.append(kwargs)
        return {"id": 99, **kwargs}


@pytest.mark.asyncio
async def test_get_recipients_returns_email_list(monkeypatch):
    service = EmailAutomationService()
    rule = EmailAutomationRule(
        id=1,
        template_key="application_submitted_student",
        trigger_event="submit",
        condition_query="SELECT '{student_email}'",
    )

    db = StubAsyncSession(results=[("person@example.com",)])

    recipients = await service._get_recipients(db, rule, {"student_email": "person@example.com"})

    assert recipients == [{"email": "person@example.com"}]


@pytest.mark.asyncio
async def test_get_recipients_handles_failures():
    service = EmailAutomationService()
    rule = EmailAutomationRule(
        id=2,
        template_key="application_submitted_student",
        trigger_event="submit",
        condition_query="SELECT '{missing_key}'",
    )

    db = StubAsyncSession()

    recipients = await service._get_recipients(db, rule, {})

    assert recipients == []


def test_get_email_category_from_template_key():
    service = EmailAutomationService()

    assert (
        service._get_email_category_from_template_key("application_submitted_student")
        == EmailCategory.application_student
    )
    assert service._get_email_category_from_template_key("nonexistent_template") == EmailCategory.system


@pytest.mark.asyncio
async def test_send_automated_email_invokes_email_service():
    service = EmailAutomationService()
    stub_email_service = StubEmailService()
    service.email_service = stub_email_service

    db = StubAsyncSession()
    await service._send_automated_email(
        db=db,
        template_key="application_submitted_student",
        recipient_email="user@example.com",
        context={"name": "User"},
        email_category=EmailCategory.application_student,
        trigger_context={"application_id": 5, "scholarship_type_id": 9},
    )

    assert len(stub_email_service.sent_with_template) == 1
    payload = stub_email_service.sent_with_template[0]
    assert payload["to"] == "user@example.com"
    assert payload["default_subject"].startswith("Automated notification")
    assert payload["email_category"] == EmailCategory.application_student
    assert payload["application_id"] == 5


@pytest.mark.asyncio
async def test_schedule_automated_email_formats_and_calls_service(monkeypatch):
    service = EmailAutomationService()
    stub_email_service = StubEmailService()
    service.email_service = stub_email_service

    template = SimpleNamespace(
        subject_template="Hi {name}",
        body_template="Body {name}",
        cc="cc1@example.com,cc2@example.com",
        bcc="bcc1@example.com",
    )

    async def fake_get_template(db, template_key):
        return template

    monkeypatch.setattr(email_automation_module.EmailTemplateService, "get_template", fake_get_template)

    db = StubAsyncSession()
    scheduled_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

    result = await service._schedule_automated_email(
        db=db,
        template_key="application_submitted_student",
        recipient_email="user@example.com",
        context={"name": "Person"},
        scheduled_for=scheduled_at,
        email_category=EmailCategory.application_student,
        trigger_context={"application_id": 1, "scholarship_type_id": 2},
    )

    assert result["scheduled_for"] == scheduled_at
    scheduled_payload = stub_email_service.scheduled[0]
    assert scheduled_payload["subject"] == "Hi Person"
    assert scheduled_payload["body"] == "Body Person"
    assert scheduled_payload["cc"] == ["cc1@example.com", "cc2@example.com"]
    assert scheduled_payload["bcc"] == ["bcc1@example.com"]


@pytest.mark.asyncio
async def test_process_single_rule_no_recipients(monkeypatch):
    service = EmailAutomationService()

    async def fake_get_recipients(db, rule, context):
        return []

    monkeypatch.setattr(service, "_get_recipients", fake_get_recipients)

    rule = EmailAutomationRule(id=1, template_key="application_submitted_student", trigger_event="submit")

    send_calls = []

    async def fake_send(*args, **kwargs):
        send_calls.append((args, kwargs))

    monkeypatch.setattr(service, "_send_automated_email", fake_send)

    db = StubAsyncSession()
    await service._process_single_rule(db, rule, {"application_id": 1})

    assert send_calls == []


@pytest.mark.asyncio
async def test_process_single_rule_missing_template(monkeypatch):
    service = EmailAutomationService()

    async def fake_get_recipients(db, rule, context):
        return [{"email": "person@example.com"}]

    monkeypatch.setattr(service, "_get_recipients", fake_get_recipients)

    async def fake_get_template(db, template_key):
        return None

    monkeypatch.setattr(email_automation_module.EmailTemplateService, "get_template", fake_get_template)

    send_calls = []

    async def fake_send(*args, **kwargs):
        send_calls.append((args, kwargs))

    monkeypatch.setattr(service, "_send_automated_email", fake_send)

    rule = EmailAutomationRule(id=2, template_key="application_submitted_student", trigger_event="submit")
    db = StubAsyncSession()

    await service._process_single_rule(db, rule, {"application_id": 1})

    assert send_calls == []


@pytest.mark.asyncio
async def test_process_single_rule_immediate_send(monkeypatch):
    service = EmailAutomationService()

    async def fake_get_recipients(db, rule, context):
        return [{"email": "person@example.com", "extra": "data"}]

    monkeypatch.setattr(service, "_get_recipients", fake_get_recipients)

    async def fake_get_template(db, template_key):
        return SimpleNamespace()

    monkeypatch.setattr(email_automation_module.EmailTemplateService, "get_template", fake_get_template)

    send_calls = []

    async def fake_send(db, template_key, recipient_email, recipient_context, email_category, trigger_context):
        send_calls.append(
            {
                "template_key": template_key,
                "recipient_email": recipient_email,
                "recipient_context": recipient_context,
                "email_category": email_category,
                "trigger_context": trigger_context,
            }
        )

    monkeypatch.setattr(service, "_send_automated_email", fake_send)

    rule = EmailAutomationRule(id=3, template_key="result_notification_student", trigger_event="submit", delay_hours=0)

    db = StubAsyncSession()
    base_context = {"application_id": 7, "context": "value"}

    await service._process_single_rule(db, rule, base_context)

    assert len(send_calls) == 1
    call = send_calls[0]
    assert call["recipient_email"] == "person@example.com"
    assert call["recipient_context"]["extra"] == "data"
    assert call["email_category"] == EmailCategory.result_student


@pytest.mark.asyncio
async def test_process_single_rule_schedules_when_delay_set(monkeypatch):
    service = EmailAutomationService()

    async def fake_get_recipients(db, rule, context):
        return [{"email": "person@example.com"}]

    monkeypatch.setattr(service, "_get_recipients", fake_get_recipients)

    async def fake_get_template(db, template_key):
        return SimpleNamespace()

    monkeypatch.setattr(email_automation_module.EmailTemplateService, "get_template", fake_get_template)

    scheduled_calls = []

    async def fake_schedule(
        db, template_key, recipient_email, recipient_context, scheduled_for, email_category, trigger_context
    ):
        scheduled_calls.append(
            {
                "recipient": recipient_email,
                "scheduled_for": scheduled_for,
                "email_category": email_category,
                "trigger_context": trigger_context,
            }
        )

    monkeypatch.setattr(service, "_schedule_automated_email", fake_schedule)

    rule = EmailAutomationRule(
        id=4, template_key="application_submitted_student", trigger_event="submit", delay_hours=3
    )

    db = StubAsyncSession()
    context = {"application_id": 12}

    before = datetime.now(timezone.utc)
    await service._process_single_rule(db, rule, context)
    after = datetime.now(timezone.utc)

    assert len(scheduled_calls) == 1
    scheduled = scheduled_calls[0]
    assert scheduled["recipient"] == "person@example.com"
    assert scheduled["email_category"] == EmailCategory.application_student
    assert before <= scheduled["scheduled_for"] <= after + timedelta(hours=3, minutes=1)
