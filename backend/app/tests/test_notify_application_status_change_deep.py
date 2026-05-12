"""
Deep async-DB tests for `NotificationService.notifyApplicationStatusChange`.

This wraps create_notification with status-specific copy + priority routing:
- approved → NotificationType.success, NotificationPriority.high
- rejected → NotificationType.info, NotificationPriority.high
- under_review → NotificationType.info, NotificationPriority.normal
- other → NotificationType.info, NotificationPriority.normal (default)

The copy table itself is bug-prone — a status missing from the dict
silently falls through to the generic message. We pin the four
status-specific branches explicitly.

Contract pinned (5 cases):
- approved produces success-type notification with approval copy and
  high priority.
- rejected produces info-type notification with rejection copy.
- under_review produces info notification with under-review copy.
- An unknown status falls through to the generic 'status updated' copy.
- group_key and href follow the application_id convention.
"""

from typing import Any
from unittest.mock import AsyncMock

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


@pytest.fixture
def silence_delivery(monkeypatch):
    """Skip the real-time delivery side effects (websocket/email/sms/push)."""
    monkeypatch.setattr(
        NotificationService,
        "_deliver_notification",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        NotificationService,
        "_get_notification_template",
        AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_approved_status_uses_success_type_and_high_priority(db: AsyncSession, silence_delivery):
    user = await _seed_user(db, nycu_id="status_appr")
    service = NotificationService(db)

    notif = await service.notifyApplicationStatusChange(
        user_id=user.id,
        application_id=42,
        new_status="approved",
        application_title="博士獎學金",
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert _val(fetched.notification_type) == NotificationType.success.value
    assert _val(fetched.priority) == NotificationPriority.high.value
    assert "已獲得核准" in fetched.message
    assert fetched.href == "/applications/42"
    assert fetched.group_key == "application_42"


@pytest.mark.asyncio
async def test_rejected_status_uses_high_priority_and_rejection_copy(db: AsyncSession, silence_delivery):
    user = await _seed_user(db, nycu_id="status_rej")
    service = NotificationService(db)

    notif = await service.notifyApplicationStatusChange(
        user_id=user.id,
        application_id=7,
        new_status="rejected",
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert _val(fetched.notification_type) == NotificationType.info.value
    assert _val(fetched.priority) == NotificationPriority.high.value
    assert "未獲得核准" in fetched.message


@pytest.mark.asyncio
async def test_under_review_status_uses_normal_priority(db: AsyncSession, silence_delivery):
    user = await _seed_user(db, nycu_id="status_under")
    service = NotificationService(db)

    notif = await service.notifyApplicationStatusChange(
        user_id=user.id,
        application_id=99,
        new_status="under_review",
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    # under_review is NOT in {approved, rejected} → normal priority.
    assert _val(fetched.priority) == NotificationPriority.normal.value
    assert "正在審核中" in fetched.message


@pytest.mark.asyncio
async def test_unknown_status_falls_through_to_generic_copy(db: AsyncSession, silence_delivery):
    user = await _seed_user(db, nycu_id="status_unknown")
    service = NotificationService(db)

    notif = await service.notifyApplicationStatusChange(
        user_id=user.id,
        application_id=12,
        new_status="some_new_status_we_dont_know",
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    # Falls through to the default 'status has been updated' message.
    assert "狀態已更新" in fetched.message
    # Unknown status not in {approved, rejected} → normal priority.
    assert _val(fetched.priority) == NotificationPriority.normal.value


@pytest.mark.asyncio
async def test_href_and_group_key_reference_application_id(db: AsyncSession, silence_delivery):
    """The grouping convention is `application_<id>` so multiple status
    notifications on the same application can be deduped/batched."""
    user = await _seed_user(db, nycu_id="status_grouping")
    service = NotificationService(db)

    n1 = await service.notifyApplicationStatusChange(user_id=user.id, application_id=555, new_status="under_review")
    n2 = await service.notifyApplicationStatusChange(user_id=user.id, application_id=555, new_status="approved")

    # Same group_key + href for both notifications on the same application.
    assert n1.group_key == "application_555"
    assert n2.group_key == "application_555"
    assert n1.href == "/applications/555"
    assert n2.href == "/applications/555"
