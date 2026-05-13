"""
Deep async-DB tests for NotificationService unread-counting and
mark-as-read operations.

These are user-facing helpers (driving the unread badge in the navbar and
the click-to-dismiss behavior on individual notifications). Existing
tests for the service use mocked DB; this file adds real-DB coverage so
the SQL filtering (expired notifications, personal vs system, user-scoped
read state) is pinned to actual rows.

Methods covered:
- `getUnreadNotificationCount(user_id)`
- `markNotificationAsRead(notification_id, user_id)`

Contract pinned:
- Unread count includes personal notifications where is_read=false.
- Expired personal notifications (expires_at < now) are EXCLUDED.
- System announcements (user_id IS NULL) count as unread until the user
  inserts a NotificationRead row.
- Read state is scoped per-user — userA reading a system announcement
  does NOT reduce userB's unread count.
- markNotificationAsRead on a personal notification flips is_read.
- markNotificationAsRead on a system announcement creates a
  NotificationRead row (does NOT mutate the shared Notification).
- A second markAsRead on the same system announcement is a no-op
  (no duplicate NotificationRead rows).
- Wrong user_id on a personal notification doesn't flip its is_read.
- Nonexistent notification_id returns False, no exceptions.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationRead, NotificationType
from app.models.user import User, UserRole, UserType
from app.services.notification_service import NotificationService


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


def _val(x):
    return x.value if hasattr(x, "value") else x


async def _seed_personal(
    db: AsyncSession,
    *,
    user_id: int,
    is_read: bool = False,
    expires_at: datetime | None = None,
    title: str = "personal",
) -> Notification:
    n = Notification(
        user_id=user_id,
        title=title,
        message=title,
        notification_type=NotificationType.info,
        is_read=is_read,
        expires_at=expires_at,
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
async def test_unread_count_personal_only(db: AsyncSession):
    user = await _seed_user(db, nycu_id="ur_personal")
    other = await _seed_user(db, nycu_id="ur_other")
    await _seed_personal(db, user_id=user.id, title="user-unread-1")
    await _seed_personal(db, user_id=user.id, title="user-unread-2")
    # Read one — should not count.
    await _seed_personal(db, user_id=user.id, is_read=True, title="user-read")
    # Other user's unread — must not leak into our count.
    await _seed_personal(db, user_id=other.id, title="other-unread")

    service = NotificationService(db)
    count = await service.getUnreadNotificationCount(user.id)
    assert count == 2


@pytest.mark.asyncio
async def test_unread_count_excludes_expired_personal(db: AsyncSession):
    """Expired notifications must NOT count as unread."""
    user = await _seed_user(db, nycu_id="ur_expired")
    # Past expiry.
    await _seed_personal(
        db,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        title="expired",
    )
    # Future expiry — counts.
    await _seed_personal(
        db,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        title="future-expiry",
    )
    # No expiry — counts.
    await _seed_personal(db, user_id=user.id, title="no-expiry")

    service = NotificationService(db)
    count = await service.getUnreadNotificationCount(user.id)
    assert count == 2


@pytest.mark.asyncio
async def test_unread_count_includes_system_announcements(db: AsyncSession):
    """System announcements count as unread until a NotificationRead row exists for the user."""
    user = await _seed_user(db, nycu_id="ur_sys")
    await _seed_system(db, title="sys-1")
    await _seed_system(db, title="sys-2")

    service = NotificationService(db)
    count = await service.getUnreadNotificationCount(user.id)
    assert count == 2


@pytest.mark.asyncio
async def test_system_announcement_read_state_is_per_user(db: AsyncSession):
    """User A marking a system announcement as read must NOT reduce user B's count."""
    user_a = await _seed_user(db, nycu_id="ur_a")
    user_b = await _seed_user(db, nycu_id="ur_b")
    sys_notif = await _seed_system(db, title="cross-user-sys")

    service = NotificationService(db)
    # A reads the announcement.
    await service.markNotificationAsRead(sys_notif.id, user_a.id)

    # A sees 0 unread; B still sees 1.
    assert await service.getUnreadNotificationCount(user_a.id) == 0
    assert await service.getUnreadNotificationCount(user_b.id) == 1


@pytest.mark.asyncio
async def test_mark_personal_notification_flips_is_read(db: AsyncSession):
    user = await _seed_user(db, nycu_id="mr_personal")
    n = await _seed_personal(db, user_id=user.id, title="to-read")

    service = NotificationService(db)
    ok = await service.markNotificationAsRead(n.id, user.id)
    assert ok is True

    await db.refresh(n)
    assert n.is_read is True


@pytest.mark.asyncio
async def test_mark_system_announcement_creates_read_row(db: AsyncSession):
    user = await _seed_user(db, nycu_id="mr_sys")
    sys_notif = await _seed_system(db, title="sys-mark")

    service = NotificationService(db)
    ok = await service.markNotificationAsRead(sys_notif.id, user.id)
    assert ok is True

    # A NotificationRead row exists for (notification_id, user_id).
    rows = (
        (
            await db.execute(
                select(NotificationRead).where(
                    NotificationRead.notification_id == sys_notif.id,
                    NotificationRead.user_id == user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1

    # The shared system notification's is_read stays False.
    await db.refresh(sys_notif)
    assert sys_notif.is_read is False


@pytest.mark.asyncio
async def test_mark_system_announcement_twice_is_idempotent(db: AsyncSession):
    """Two markAsRead calls on the same system announcement must NOT create
    duplicate NotificationRead rows."""
    user = await _seed_user(db, nycu_id="mr_twice")
    sys_notif = await _seed_system(db, title="sys-twice")

    service = NotificationService(db)
    await service.markNotificationAsRead(sys_notif.id, user.id)
    await service.markNotificationAsRead(sys_notif.id, user.id)

    rows = (
        (
            await db.execute(
                select(NotificationRead).where(
                    NotificationRead.notification_id == sys_notif.id,
                    NotificationRead.user_id == user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1, "second markAsRead must not insert a duplicate row"


@pytest.mark.asyncio
async def test_mark_personal_notification_wrong_user_does_not_flip(db: AsyncSession):
    """The personal-notification branch checks ownership before mutating."""
    owner = await _seed_user(db, nycu_id="mr_owner")
    intruder = await _seed_user(db, nycu_id="mr_intruder")
    n = await _seed_personal(db, user_id=owner.id, title="owned")

    service = NotificationService(db)
    result = await service.markNotificationAsRead(n.id, intruder.id)
    # The method returns True (no error) but is_read stays False because
    # `notification.user_id != intruder.id` and `notification.user_id`
    # is not None (so the system-announcement branch is skipped too).
    assert result is True

    await db.refresh(n)
    assert n.is_read is False


@pytest.mark.asyncio
async def test_mark_nonexistent_notification_returns_false(db: AsyncSession):
    user = await _seed_user(db, nycu_id="mr_404")
    service = NotificationService(db)
    result = await service.markNotificationAsRead(999_999_999, user.id)
    assert result is False
