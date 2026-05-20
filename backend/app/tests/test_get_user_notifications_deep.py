"""
Deep async-DB tests for `NotificationService.getUserNotifications`.

The list endpoint behind the notification bell UI. Returns a flat dict
list combining personal + system notifications with computed is_read
state (personal: column; system: NotificationRead row).

Contract pinned (6 cases):
- Returns both personal and system notifications.
- Other users' personal notifications are excluded.
- unread_only=True excludes already-read personals + announcements with
  a NotificationRead row.
- Expired notifications (past expires_at) are excluded.
- Each result row has computed is_read consistent with the underlying
  read state.
- Ordered by created_at DESC (newest first).
"""

from datetime import datetime, timedelta, timezone

import pytest
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


async def _seed_personal(
    db: AsyncSession,
    *,
    user_id: int,
    title: str = "personal",
    is_read: bool = False,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Notification:
    n = Notification(
        user_id=user_id,
        title=title,
        message=title,
        notification_type=NotificationType.info,
        is_read=is_read,
        expires_at=expires_at,
    )
    if created_at:
        n.created_at = created_at
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


async def _seed_system(
    db: AsyncSession,
    *,
    title: str = "system",
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Notification:
    n = Notification(
        user_id=None,
        title=title,
        message=title,
        notification_type=NotificationType.info,
        is_read=False,
        expires_at=expires_at,
    )
    if created_at:
        n.created_at = created_at
    db.add(n)
    await db.commit()
    await db.refresh(n)
    return n


@pytest.mark.asyncio
async def test_returns_both_personal_and_system_notifications(db: AsyncSession):
    user = await _seed_user(db, nycu_id="getnotif_mix")
    await _seed_personal(db, user_id=user.id, title="personal-mix")
    await _seed_system(db, title="system-mix")

    service = NotificationService(db)
    result = await service.getUserNotifications(user.id)
    titles = {r["title"] for r in result}
    assert "personal-mix" in titles
    assert "system-mix" in titles


@pytest.mark.asyncio
async def test_excludes_other_users_personal_notifications(db: AsyncSession):
    user = await _seed_user(db, nycu_id="getnotif_owner")
    other = await _seed_user(db, nycu_id="getnotif_intruder")
    await _seed_personal(db, user_id=user.id, title="mine")
    await _seed_personal(db, user_id=other.id, title="theirs")

    service = NotificationService(db)
    result = await service.getUserNotifications(user.id)
    titles = {r["title"] for r in result}
    assert "mine" in titles
    assert "theirs" not in titles


@pytest.mark.asyncio
async def test_unread_only_excludes_read_personal_and_announcements(db: AsyncSession):
    user = await _seed_user(db, nycu_id="getnotif_unread")
    # Personal: 1 unread, 1 read.
    await _seed_personal(db, user_id=user.id, title="p_unread")
    await _seed_personal(db, user_id=user.id, title="p_read", is_read=True)

    # System: 1 unread, 1 marked read via NotificationRead.
    await _seed_system(db, title="s_unread")
    s_marked = await _seed_system(db, title="s_marked")
    db.add(NotificationRead(notification_id=s_marked.id, user_id=user.id))
    await db.commit()

    service = NotificationService(db)
    result = await service.getUserNotifications(user.id, unread_only=True)
    titles = {r["title"] for r in result}
    assert "p_unread" in titles
    assert "s_unread" in titles
    # Read items excluded.
    assert "p_read" not in titles
    assert "s_marked" not in titles


@pytest.mark.asyncio
async def test_excludes_expired_notifications(db: AsyncSession):
    """Notifications past expires_at don't appear in the list."""
    user = await _seed_user(db, nycu_id="getnotif_expired")
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=7)

    await _seed_personal(db, user_id=user.id, title="expired_personal", expires_at=past)
    await _seed_personal(db, user_id=user.id, title="fresh_personal", expires_at=future)
    await _seed_system(db, title="expired_system", expires_at=past)
    await _seed_system(db, title="fresh_system", expires_at=future)
    await _seed_personal(db, user_id=user.id, title="no_expiry_personal")

    service = NotificationService(db)
    result = await service.getUserNotifications(user.id)
    titles = {r["title"] for r in result}
    # Expired items excluded.
    assert "expired_personal" not in titles
    assert "expired_system" not in titles
    # Fresh + no-expiry items present.
    assert "fresh_personal" in titles
    assert "fresh_system" in titles
    assert "no_expiry_personal" in titles


@pytest.mark.asyncio
async def test_is_read_field_reflects_underlying_state(db: AsyncSession):
    """Personal: is_read column. System: NotificationRead row presence."""
    user = await _seed_user(db, nycu_id="getnotif_isread")
    await _seed_personal(db, user_id=user.id, title="p_isread_no")
    await _seed_personal(db, user_id=user.id, title="p_isread_yes", is_read=True)
    await _seed_system(db, title="s_isread_no")
    s_read = await _seed_system(db, title="s_isread_yes")
    db.add(NotificationRead(notification_id=s_read.id, user_id=user.id))
    await db.commit()

    service = NotificationService(db)
    result = await service.getUserNotifications(user.id)
    by_title = {r["title"]: r for r in result}

    assert by_title["p_isread_no"]["is_read"] is False
    assert by_title["p_isread_yes"]["is_read"] is True
    assert by_title["s_isread_no"]["is_read"] is False
    assert by_title["s_isread_yes"]["is_read"] is True


@pytest.mark.asyncio
async def test_ordered_by_created_at_desc(db: AsyncSession):
    user = await _seed_user(db, nycu_id="getnotif_order")
    now = datetime.now(timezone.utc)
    await _seed_personal(db, user_id=user.id, title="oldest", created_at=now - timedelta(days=10))
    await _seed_personal(db, user_id=user.id, title="newest", created_at=now - timedelta(days=1))
    await _seed_personal(db, user_id=user.id, title="middle", created_at=now - timedelta(days=5))

    service = NotificationService(db)
    result = await service.getUserNotifications(user.id)
    titles = [r["title"] for r in result]
    # Newest first.
    assert titles[0] == "newest"
    assert titles[1] == "middle"
    assert titles[2] == "oldest"
