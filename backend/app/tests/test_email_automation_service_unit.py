from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.email_management import EmailCategory
from app.services import email_automation_service as email_automation_module
from app.core.sql_read_only_guard import UnsafeConditionQueryError
from app.services.email_automation_service import EmailAutomationRule, EmailAutomationService


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)

    def fetchall(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        rows = list(self._rows)
        return rows[0] if rows else None


class StubSavepoint:
    """Stands in for the SAVEPOINT `_execute_read_only` always rolls back."""

    def __init__(self, session):
        self._session = session

    async def rollback(self):
        self._session.savepoint_rollbacks += 1


class StubAsyncSession:
    def __init__(self, results=None, side_effect=None):
        self.results = results or []
        self.side_effect = side_effect
        self.executed = []
        self.committed = 0
        self.rolled_back = 0
        self.savepoint_rollbacks = 0

    async def begin_nested(self):
        return StubSavepoint(self)

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

    async def send_with_react_template(self, **kwargs):
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
        # Shaped like the real seeded rules: the placeholder sits in SQL position,
        # not inside a string literal.
        condition_query="SELECT email FROM users WHERE id = {application_id}",
    )

    db = StubAsyncSession(results=[("person@example.com",)])

    recipients = await service._get_recipients(db, rule, {"application_id": 1})

    assert recipients == [{"email": "person@example.com"}]
    # {application_id} was rewritten to a BOUND parameter, never interpolated.
    executed_sql = str(db.executed[-1][0])
    assert ":application_id" in executed_sql
    assert "{application_id}" not in executed_sql
    # The savepoint is always rolled back, so a rule can never leave writes behind
    # nor leave the caller's transaction read-only.
    assert db.savepoint_rollbacks == 1


@pytest.mark.asyncio
async def test_placeholder_inside_a_string_literal_is_not_rewritten():
    """A `{...}` inside a literal is data, not a placeholder.

    The old naive str.replace rewrote it anyway, corrupting the literal.
    """
    from app.services.email_automation_service import bind_placeholders

    sql = "SELECT '{not_a_placeholder}' , x FROM t WHERE id = {application_id}"
    out = bind_placeholders(sql, {"application_id": 1, "not_a_placeholder": "x"})

    assert "'{not_a_placeholder}'" in out
    assert "id = :application_id" in out


@pytest.mark.asyncio
async def test_savepoint_is_rolled_back_even_when_the_query_raises():
    service = EmailAutomationService()
    rule = EmailAutomationRule(
        id=4,
        template_key="application_submitted_student",
        trigger_event="submit",
        condition_query="SELECT email FROM users WHERE id = {application_id}",
    )

    db = StubAsyncSession(side_effect=RuntimeError("boom"))

    with pytest.raises(RuntimeError):
        await service._get_recipients(db, rule, {"application_id": 1})

    # Without the rollback the caller's transaction stays aborted and its later
    # scheduled_emails INSERT fails — the live bug this fix also closes.
    assert db.savepoint_rollbacks == 1


@pytest.mark.asyncio
async def test_get_recipients_raises_on_missing_context_key():
    """A placeholder with no context key now RAISES instead of returning [].

    #1223 A: swallowing turned a misconfigured rule into "nobody was supposed to
    be notified", and left the caller's transaction aborted. process_trigger
    already isolates each rule, so raising is contained.
    """
    service = EmailAutomationService()
    rule = EmailAutomationRule(
        id=2,
        template_key="application_submitted_student",
        trigger_event="submit",
        condition_query="SELECT {missing_key}",
    )

    db = StubAsyncSession()

    with pytest.raises(UnsafeConditionQueryError, match="missing_key"):
        await service._get_recipients(db, rule, {})

    assert db.executed == []  # never reached the database


@pytest.mark.asyncio
async def test_get_recipients_refuses_unsafe_query_without_executing():
    service = EmailAutomationService()
    rule = EmailAutomationRule(
        id=3,
        template_key="application_submitted_student",
        trigger_event="submit",
        condition_query="SELECT 1; DROP TABLE users",
    )

    db = StubAsyncSession()

    with pytest.raises(UnsafeConditionQueryError):
        await service._get_recipients(db, rule, {})

    assert db.executed == []


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
    assert payload["subject"].startswith("Automated notification")
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

    async def fake_send(
        db,
        template_key,
        recipient_email,
        recipient_context,
        scheduled_for,
        email_category,
        trigger_context,
    ):
        send_calls.append(
            {
                "template_key": template_key,
                "recipient_email": recipient_email,
                "recipient_context": recipient_context,
                "scheduled_for": scheduled_for,
                "email_category": email_category,
                "trigger_context": trigger_context,
            }
        )

    monkeypatch.setattr(service, "_schedule_automated_email", fake_send)

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


def test_dedupe_recipient_rows_is_case_insensitive_and_drops_blanks():
    from app.services.email_automation_service import dedupe_recipient_rows

    rows = [
        ("Prof@nycu.edu.tw",),
        ("prof@nycu.edu.tw",),  # same inbox, different case → folded
        ("  prof@nycu.edu.tw  ",),  # whitespace → folded
        ("other@nycu.edu.tw",),
        (None,),
        ("",),
        None,
    ]

    assert dedupe_recipient_rows(rows) == [{"email": "Prof@nycu.edu.tw"}, {"email": "other@nycu.edu.tw"}]


@pytest.mark.asyncio
async def test_get_recipients_folds_case_variants_of_the_same_address(monkeypatch):
    service = EmailAutomationService()
    rule = EmailAutomationRule(
        id=1,
        template_key="professor_review_notification",
        trigger_event="submit",
        condition_query="SELECT email FROM users WHERE id = {application_id}",
    )
    db = StubAsyncSession(results=[("Prof@nycu.edu.tw",), ("prof@nycu.edu.tw",)])

    recipients = await service._get_recipients(db, rule, {"application_id": 1})

    assert recipients == [{"email": "Prof@nycu.edu.tw"}]
