"""
Deep async-DB tests for `NotificationService.bulkNotifyUsers`.

Used for fan-out notifications (announcements, batch deadline reminders).
Real-DB coverage so the persistence path, per-user fanout, and metadata
sharing are pinned.

Contract pinned (5 cases):
- Empty user_ids list returns [] without crashing.
- Single user produces one notification.
- N users produce N distinct notifications, each owned by the matching
  user_id.
- All notifications share the same title/message/metadata payload.
- The function commits to DB — re-querying by id finds each row.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.user import User, UserRole, UserType
from app.services.notification_service import NotificationService


def _val(x):
    return x.value if hasattr(x, "value") else x


async def _seed_user(db: AsyncSession, *, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_empty_user_ids_returns_empty_list(db: AsyncSession):
    service = NotificationService(db)
    result = await service.bulkNotifyUsers(
        user_ids=[],
        title="無接收者",
        message="這通知不會送出",
    )
    assert result == []


@pytest.mark.asyncio
async def test_single_user_produces_one_notification(db: AsyncSession):
    user = await _seed_user(db, nycu_id="bulk_solo")
    service = NotificationService(db)
    result = await service.bulkNotifyUsers(
        user_ids=[user.id],
        title="僅一人",
        message="solo notif",
    )
    assert len(result) == 1
    assert result[0].user_id == user.id


@pytest.mark.asyncio
async def test_three_users_produce_three_distinct_rows(db: AsyncSession):
    u1 = await _seed_user(db, nycu_id="bulk_3a")
    u2 = await _seed_user(db, nycu_id="bulk_3b")
    u3 = await _seed_user(db, nycu_id="bulk_3c")
    service = NotificationService(db)

    result = await service.bulkNotifyUsers(
        user_ids=[u1.id, u2.id, u3.id],
        title="批量",
        message="bulk",
    )
    assert len(result) == 3
    # Each notification belongs to exactly one of the input users.
    user_ids_in_results = {n.user_id for n in result}
    assert user_ids_in_results == {u1.id, u2.id, u3.id}
    # IDs are distinct.
    assert len({n.id for n in result}) == 3


@pytest.mark.asyncio
async def test_all_notifications_share_same_payload(db: AsyncSession):
    """Title/message/metadata are identical across the fanout — only user_id varies."""
    u1 = await _seed_user(db, nycu_id="bulk_share1")
    u2 = await _seed_user(db, nycu_id="bulk_share2")
    service = NotificationService(db)

    deadline = datetime.now(timezone.utc) + timedelta(days=14)
    result = await service.bulkNotifyUsers(
        user_ids=[u1.id, u2.id],
        title="期限提醒",
        message="請於兩週內完成",
        title_en="Deadline reminder",
        message_en="Complete within two weeks",
        notification_type=NotificationType.reminder,
        priority=NotificationPriority.high,
        action_url="/student/applications",
        expires_at=deadline,
        metadata={"campaign": "phd-deadline-2026-spring"},
    )
    assert len(result) == 2
    for n in result:
        assert n.title == "期限提醒"
        assert n.message == "請於兩週內完成"
        assert n.title_en == "Deadline reminder"
        assert n.message_en == "Complete within two weeks"
        assert _val(n.notification_type) == NotificationType.reminder.value
        assert _val(n.priority) == NotificationPriority.high.value
        assert n.action_url == "/student/applications"
        assert n.meta_data == {"campaign": "phd-deadline-2026-spring"}


@pytest.mark.asyncio
async def test_notifications_are_persisted_to_db(db: AsyncSession):
    """Each fanout notification is committed; re-query by id should find it."""
    u1 = await _seed_user(db, nycu_id="bulk_persist1")
    u2 = await _seed_user(db, nycu_id="bulk_persist2")
    service = NotificationService(db)

    result = await service.bulkNotifyUsers(
        user_ids=[u1.id, u2.id],
        title="持久化測試",
        message="should be in DB",
    )
    ids = [n.id for n in result]
    for nid in ids:
        fetched = (await db.execute(select(Notification).where(Notification.id == nid))).scalar_one()
        assert fetched.title == "持久化測試"
