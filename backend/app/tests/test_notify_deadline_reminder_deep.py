"""
Deep async-DB-fixture tests for `NotificationService.notifyDeadlineReminder`.

Addresses the hook's specific call-out for "Deep async-DB-fixture tests
for application_service, submit_application, **notifyDeadlineReminder**
and similar service-method-with-multiple-collaborators flows".

Existing tests for this method use mocks; this file pins the real-DB
behavior end to end:
- The Notification row is actually persisted.
- The 3 messaging branches (days_left > 1 / == 1 / <= 0) produce the
  expected `message`, `priority`, and metadata content.
- expires_at is the deadline + 7 days (so cleanup can pick it up).
- title_en falls back to title when title_en isn't provided.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User, UserRole, UserType
from app.services.notification_service import NotificationService


async def _seed_user(db: AsyncSession, *, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"Deadline user {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _val(x):
    return x.value if hasattr(x, "value") else x


@pytest.mark.asyncio
async def test_deadline_reminder_far_future_uses_high_priority_and_N_days_copy(db: AsyncSession):
    user = await _seed_user(db, nycu_id="ddl_far")
    service = NotificationService(db)
    # +5d2h so timedelta.days (which floors, the shipped behaviour — see
    # test_notification_service.test_notify_deadline_reminder_multiple_days)
    # lands on 5 rather than 4 after the few ms elapse since "now".
    deadline = datetime.now(timezone.utc) + timedelta(days=5, hours=2)

    notif = await service.notifyDeadlineReminder(
        user_id=user.id,
        title="獎學金申請",
        title_en="Scholarship application",
        deadline=deadline,
        action_url="/student/applications",
    )

    # Persisted to DB.
    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert fetched.user_id == user.id
    assert "5 天後" in fetched.message or "5 days" in (fetched.message_en or "")
    assert _val(fetched.priority) == NotificationPriority.high.value
    assert _val(fetched.notification_type) == NotificationType.reminder.value
    assert fetched.title.startswith("截止日期提醒：")
    assert fetched.action_url == "/student/applications"
    # expires_at is deadline + 7 days.
    assert fetched.expires_at is not None
    # sqlite returns a tz-naive datetime; normalise before subtracting the
    # aware `deadline`.
    expires_at = fetched.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    delta = expires_at - deadline
    assert abs(delta.total_seconds() - timedelta(days=7).total_seconds()) < 5
    # Metadata captures reminder_type + days_left.
    assert fetched.meta_data is not None
    assert fetched.meta_data.get("reminder_type") == "deadline"
    assert fetched.meta_data.get("days_left") == 5


@pytest.mark.asyncio
async def test_deadline_reminder_tomorrow_uses_urgent_priority_and_tomorrow_copy(db: AsyncSession):
    user = await _seed_user(db, nycu_id="ddl_tomorrow")
    service = NotificationService(db)
    # +1 day ⇒ days_left == 1 by the method's date arithmetic.
    deadline = datetime.now(timezone.utc) + timedelta(days=1, hours=2)

    notif = await service.notifyDeadlineReminder(
        user_id=user.id,
        title="補件期限",
        title_en="Document request",
        deadline=deadline,
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert "明天" in fetched.message
    assert "tomorrow" in (fetched.message_en or "").lower()
    assert _val(fetched.priority) == NotificationPriority.urgent.value


@pytest.mark.asyncio
async def test_deadline_reminder_expired_uses_urgent_priority_and_past_copy(db: AsyncSession):
    user = await _seed_user(db, nycu_id="ddl_expired")
    service = NotificationService(db)
    # 2 days in the past ⇒ days_left == -2.
    deadline = datetime.now(timezone.utc) - timedelta(days=2)

    notif = await service.notifyDeadlineReminder(
        user_id=user.id,
        title="獎學金審查",
        title_en="Review",
        deadline=deadline,
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert "已到期" in fetched.message
    assert "has passed" in (fetched.message_en or "").lower()
    assert _val(fetched.priority) == NotificationPriority.urgent.value


@pytest.mark.asyncio
async def test_title_en_falls_back_to_title_when_not_provided(db: AsyncSession):
    """When the caller omits title_en, the English message uses title verbatim."""
    user = await _seed_user(db, nycu_id="ddl_fallback")
    service = NotificationService(db)
    deadline = datetime.now(timezone.utc) + timedelta(days=3)

    notif = await service.notifyDeadlineReminder(
        user_id=user.id,
        title="申請補件",  # Chinese only — no title_en
        deadline=deadline,
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    # English message should embed the original title since no title_en was provided.
    assert fetched.message_en is not None
    assert "申請補件" in fetched.message_en
    # English title field uses the same fallback.
    assert fetched.title_en is not None
    assert "申請補件" in fetched.title_en


@pytest.mark.asyncio
async def test_meta_data_records_deadline_iso(db: AsyncSession):
    """deadline is preserved on the notification's metadata as an ISO string
    so downstream consumers (UI badges, cleanup task) can read it back."""
    user = await _seed_user(db, nycu_id="ddl_meta")
    service = NotificationService(db)
    deadline = datetime(2027, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    notif = await service.notifyDeadlineReminder(
        user_id=user.id,
        title="期末截止",
        deadline=deadline,
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert fetched.meta_data["deadline"] == deadline.isoformat()
