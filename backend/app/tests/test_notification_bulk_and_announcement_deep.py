"""
Deep async-DB tests for NotificationService.markAllNotificationsAsRead +
createSystemAnnouncement.

Two related methods extending the unread/read coverage in #248:
- markAllNotificationsAsRead bulk-flips personal `is_read` AND creates
  NotificationRead rows for unread system announcements.
- createSystemAnnouncement persists a Notification with user_id=NULL
  (the marker for system-wide visibility).

Contract pinned (5 cases):
- createSystemAnnouncement: row persisted with user_id=NULL,
  related_resource_type='system', and meta_data round-trips.
- markAllNotificationsAsRead: personal notifications flip is_read.
- markAllNotificationsAsRead: unread system announcements get a
  NotificationRead row for the user.
- markAllNotificationsAsRead: expired system announcements are NOT
  marked read (the expires_at filter).
- markAllNotificationsAsRead: total return value = personal + system count.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationPriority, NotificationRead, NotificationType
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


async def _seed_personal(db: AsyncSession, *, user_id: int, is_read: bool = False, title: str = "p") -> Notification:
    n = Notification(
        user_id=user_id,
        title=title,
        message=title,
        notification_type=NotificationType.info,
        is_read=is_read,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def _seed_system(db: AsyncSession, *, title: str, expires_at: datetime | None = None) -> Notification:
    n = Notification(
        user_id=None,
        title=title,
        message=title,
        notification_type=NotificationType.info,
        is_read=False,
        expires_at=expires_at,
    )
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


@pytest.mark.asyncio
async def test_create_system_announcement_persists_with_null_user_id(db: AsyncSession):
    """user_id=NULL is the system-wide visibility marker; related_resource_type='system'."""
    service = NotificationService(db)
    announcement = await service.createSystemAnnouncement(
        title="維護通知",
        message="今晚 11 點到 1 點維護",
        title_en="Maintenance",
        message_en="Maintenance tonight 23:00–01:00",
        priority=NotificationPriority.urgent,
        metadata={"category": "system_maintenance"},
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == announcement.id))).scalar_one()
    assert fetched.user_id is None
    assert fetched.related_resource_type == "system"
    assert fetched.title == "維護通知"
    assert fetched.title_en == "Maintenance"
    assert _val(fetched.priority) == NotificationPriority.urgent.value
    assert fetched.meta_data == {"category": "system_maintenance"}


@pytest.mark.asyncio
async def test_mark_all_flips_personal_is_read(db: AsyncSession):
    user = await _seed_user(db, nycu_id="bulk_user_personal")
    other = await _seed_user(db, nycu_id="bulk_other")

    n1 = await _seed_personal(db, user_id=user.id, title="p1")
    n2 = await _seed_personal(db, user_id=user.id, title="p2")
    already_read = await _seed_personal(db, user_id=user.id, is_read=True, title="p3_read")
    # Other user's notification — must NOT be touched.
    n_other = await _seed_personal(db, user_id=other.id, title="other_unread")

    service = NotificationService(db)
    count = await service.markAllNotificationsAsRead(user.id)

    # 2 personal unread were flipped.
    assert count >= 2

    await db.refresh(n1)
    await db.refresh(n2)
    await db.refresh(already_read)
    await db.refresh(n_other)

    assert n1.is_read is True
    assert n2.is_read is True
    assert already_read.is_read is True  # was already read
    assert n_other.is_read is False  # other user's untouched


@pytest.mark.asyncio
async def test_mark_all_creates_notification_read_rows_for_system_announcements(db: AsyncSession):
    user = await _seed_user(db, nycu_id="bulk_user_sys")
    sys_a = await _seed_system(db, title="sys_a")
    sys_b = await _seed_system(db, title="sys_b")

    service = NotificationService(db)
    await service.markAllNotificationsAsRead(user.id)

    rows = (await db.execute(select(NotificationRead).where(NotificationRead.user_id == user.id))).scalars().all()
    notif_ids = {r.notification_id for r in rows}
    assert sys_a.id in notif_ids
    assert sys_b.id in notif_ids


@pytest.mark.asyncio
async def test_mark_all_skips_expired_system_announcements(db: AsyncSession):
    """Expired announcements shouldn't be marked read — they're already filtered out of the unread view."""
    user = await _seed_user(db, nycu_id="bulk_user_expired")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    expired_sys = await _seed_system(db, title="expired_sys", expires_at=past)
    fresh_sys = await _seed_system(db, title="fresh_sys")

    service = NotificationService(db)
    await service.markAllNotificationsAsRead(user.id)

    rows = (await db.execute(select(NotificationRead).where(NotificationRead.user_id == user.id))).scalars().all()
    notif_ids = {r.notification_id for r in rows}
    # Fresh announcement marked read; expired skipped.
    assert fresh_sys.id in notif_ids
    assert expired_sys.id not in notif_ids


@pytest.mark.asyncio
async def test_mark_all_returns_total_count(db: AsyncSession):
    """Return value = personal flipped + system NotificationRead rows created."""
    user = await _seed_user(db, nycu_id="bulk_user_count")

    await _seed_personal(db, user_id=user.id, title="p1")
    await _seed_personal(db, user_id=user.id, title="p2")
    await _seed_system(db, title="sys1")

    service = NotificationService(db)
    count = await service.markAllNotificationsAsRead(user.id)
    # 2 personal + 1 system = 3.
    assert count == 3
