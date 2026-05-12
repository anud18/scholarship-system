"""
Deep async-DB tests for `EmailService.schedule_email`.

The async email-queue write path used everywhere notifications fan out to
external email (assign-professor notifications, deadline reminders,
status updates, etc.). Real-DB coverage so the persistence path is
exercised end-to-end, including the JSON-serialized cc/bcc fields and
the metadata kwargs.

Contract pinned (6 cases):
- Minimal happy path: required fields (recipient, subject, body,
  scheduled_for) persist correctly.
- cc/bcc lists serialize to JSON strings (not Python list repr).
- None cc/bcc become NULL in the DB (not 'null' string).
- html_content persists into html_body column when provided.
- Metadata kwargs (template_key, application_id, scholarship_type_id,
  created_by_user_id, email_category) all land on their respective
  columns.
- priority + requires_approval flow through to their columns.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_management import ScheduledEmail
from app.services.email_service import EmailService


@pytest.mark.asyncio
async def test_minimal_happy_path_persists_required_fields(db: AsyncSession):
    service = EmailService()
    scheduled_for = datetime(2026, 7, 1, 9, 0, 0, tzinfo=timezone.utc)

    result = await service.schedule_email(
        db=db,
        to="student@u.edu",
        subject="申請已提交",
        body="您的申請已成功送出。",
        scheduled_for=scheduled_for,
    )

    fetched = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == result.id))).scalar_one()
    assert fetched.recipient_email == "student@u.edu"
    assert fetched.subject == "申請已提交"
    assert fetched.body == "您的申請已成功送出。"
    # SQLite may strip tz; allow naive comparison.
    assert fetched.scheduled_for.replace(tzinfo=None) == scheduled_for.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_cc_bcc_serialize_to_json_strings(db: AsyncSession):
    service = EmailService()
    scheduled_for = datetime(2026, 7, 2, tzinfo=timezone.utc)

    result = await service.schedule_email(
        db=db,
        to="primary@u.edu",
        subject="cc/bcc test",
        body="b",
        scheduled_for=scheduled_for,
        cc=["cc1@u.edu", "cc2@u.edu"],
        bcc=["bcc1@u.edu"],
    )

    fetched = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == result.id))).scalar_one()
    # JSON-encoded strings (not Python list repr like "['x', 'y']").
    assert fetched.cc_emails == '["cc1@u.edu", "cc2@u.edu"]'
    assert fetched.bcc_emails == '["bcc1@u.edu"]'


@pytest.mark.asyncio
async def test_none_cc_bcc_persisted_as_null(db: AsyncSession):
    service = EmailService()
    scheduled_for = datetime(2026, 7, 3, tzinfo=timezone.utc)

    result = await service.schedule_email(
        db=db,
        to="solo@u.edu",
        subject="no cc",
        body="b",
        scheduled_for=scheduled_for,
        cc=None,
        bcc=None,
    )

    fetched = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == result.id))).scalar_one()
    assert fetched.cc_emails is None
    assert fetched.bcc_emails is None


@pytest.mark.asyncio
async def test_html_content_persists_to_html_body_column(db: AsyncSession):
    service = EmailService()
    scheduled_for = datetime(2026, 7, 4, tzinfo=timezone.utc)

    html = "<html><body><h1>已通過</h1></body></html>"
    result = await service.schedule_email(
        db=db,
        to="html@u.edu",
        subject="html",
        body="plain fallback",
        scheduled_for=scheduled_for,
        html_content=html,
    )

    fetched = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == result.id))).scalar_one()
    assert fetched.html_body == html
    assert fetched.body == "plain fallback"


@pytest.mark.asyncio
async def test_metadata_kwargs_persist_to_their_columns(db: AsyncSession):
    """template_key, application_id, scholarship_type_id, email_category,
    created_by_user_id all flow through **metadata kwargs."""
    service = EmailService()
    scheduled_for = datetime(2026, 7, 5, tzinfo=timezone.utc)

    result = await service.schedule_email(
        db=db,
        to="meta@u.edu",
        subject="meta",
        body="b",
        scheduled_for=scheduled_for,
        template_key="professor_review_notification",
        application_id=42,
        scholarship_type_id=7,
        email_category="review",
        created_by_user_id=100,
    )

    fetched = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == result.id))).scalar_one()
    assert fetched.template_key == "professor_review_notification"
    assert fetched.application_id == 42
    assert fetched.scholarship_type_id == 7
    assert fetched.email_category == "review"
    assert fetched.created_by_user_id == 100


@pytest.mark.asyncio
async def test_priority_and_requires_approval_flow_through(db: AsyncSession):
    service = EmailService()
    scheduled_for = datetime(2026, 7, 6, tzinfo=timezone.utc)

    result = await service.schedule_email(
        db=db,
        to="prio@u.edu",
        subject="prio test",
        body="b",
        scheduled_for=scheduled_for,
        priority=1,
        requires_approval=True,
    )

    fetched = (await db.execute(select(ScheduledEmail).where(ScheduledEmail.id == result.id))).scalar_one()
    assert fetched.priority == 1
    assert fetched.requires_approval is True
