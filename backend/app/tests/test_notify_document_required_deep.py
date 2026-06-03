"""
Deep async-DB tests for `NotificationService.notifyDocumentRequired`.

Helper for the document-request flow — fires when a reviewer asks the
student for additional documents. Wraps createUserNotification with
fixed copy + warning priority + structured metadata for the UI.

Contract pinned (5 cases):
- Document list joined with Chinese delimiter '、'; English uses ', '.
- Notification persists with type=warning, priority=high,
  related_resource_type='action_url', and action_url referencing
  the documents path.
- meta_data contains application_id + required_documents list + deadline
  ISO string (or None) so the UI can render structured info.
- With deadline: message includes the '請於 YYYY/MM/DD 前上傳' suffix.
- Without deadline: no deadline suffix; meta_data.deadline = None.
"""

from datetime import datetime, timezone

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
async def test_document_list_joined_with_chinese_delimiter(db: AsyncSession):
    user = await _seed_user(db, nycu_id="docreq_chinese")
    service = NotificationService(db)

    notif = await service.notifyDocumentRequired(
        user_id=user.id,
        application_id=10,
        required_documents=["成績單", "推薦信", "研究計畫"],
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    # Chinese delimiter for the in-app/zh message.
    assert "成績單、推薦信、研究計畫" in fetched.message
    # English uses ', '.
    assert "成績單, 推薦信, 研究計畫" in (fetched.message_en or "")


@pytest.mark.asyncio
async def test_persists_with_warning_type_high_priority_and_action_url(db: AsyncSession):
    user = await _seed_user(db, nycu_id="docreq_fields")
    service = NotificationService(db)

    notif = await service.notifyDocumentRequired(
        user_id=user.id,
        application_id=77,
        required_documents=["transcript"],
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert _val(fetched.notification_type) == NotificationType.warning.value
    assert _val(fetched.priority) == NotificationPriority.high.value
    assert fetched.related_resource_type == "application"
    assert fetched.related_resource_id == 77
    assert fetched.action_url == "/applications/77/documents"


@pytest.mark.asyncio
async def test_meta_data_includes_application_documents_and_deadline(db: AsyncSession):
    user = await _seed_user(db, nycu_id="docreq_meta")
    service = NotificationService(db)
    deadline = datetime(2026, 6, 30, 23, 59, 0, tzinfo=timezone.utc)

    notif = await service.notifyDocumentRequired(
        user_id=user.id,
        application_id=33,
        required_documents=["transcript", "research_plan"],
        deadline=deadline,
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert fetched.meta_data is not None
    assert fetched.meta_data["application_id"] == 33
    assert fetched.meta_data["required_documents"] == ["transcript", "research_plan"]
    assert fetched.meta_data["deadline"] == deadline.isoformat()


@pytest.mark.asyncio
async def test_with_deadline_includes_upload_by_suffix(db: AsyncSession):
    user = await _seed_user(db, nycu_id="docreq_with_deadline")
    service = NotificationService(db)
    deadline = datetime(2026, 12, 15, tzinfo=timezone.utc)

    notif = await service.notifyDocumentRequired(
        user_id=user.id,
        application_id=99,
        required_documents=["transcript"],
        deadline=deadline,
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert "請於 2026/12/15 前上傳" in fetched.message
    assert "Please upload by 2026/12/15" in (fetched.message_en or "")
    # expires_at is set to the deadline.
    assert fetched.expires_at is not None
    # Compare as UTC; the model column may strip subseconds and the sqlite test
    # DB returns a tz-naive value, so normalise to aware-UTC before comparing.
    expires_at = fetched.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    assert expires_at.replace(microsecond=0) == deadline.replace(microsecond=0)


@pytest.mark.asyncio
async def test_without_deadline_omits_suffix(db: AsyncSession):
    user = await _seed_user(db, nycu_id="docreq_no_deadline")
    service = NotificationService(db)

    notif = await service.notifyDocumentRequired(
        user_id=user.id,
        application_id=12,
        required_documents=["transcript"],
    )

    fetched = (await db.execute(select(Notification).where(Notification.id == notif.id))).scalar_one()
    assert "請於" not in fetched.message
    assert "Please upload by" not in (fetched.message_en or "")
    assert fetched.meta_data["deadline"] is None
    # expires_at remains None when no deadline.
    assert fetched.expires_at is None
