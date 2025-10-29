from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.notification import NotificationChannel, NotificationPriority, NotificationType
from app.services.notification_service import NotificationService


@pytest.fixture
def dummy_service():
    class DummySession:
        pass

    service = NotificationService(DummySession())
    service.notifyApplicationStatusChange = AsyncMock()
    service.create_notification = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_notify_application_batch_updates_single(dummy_service):
    updates = [
        {
            "user_id": 10,
            "application_id": 501,
            "status": "approved",
            "application_title": "AI Scholarship",
        }
    ]

    result = await dummy_service.notify_application_batch_updates(updates)

    dummy_service.notifyApplicationStatusChange.assert_awaited_once_with(
        user_id=10,
        application_id=501,
        new_status="approved",
        application_title="AI Scholarship",
    )
    dummy_service.create_notification.assert_not_called()
    assert result == {
        "individual_notifications": 1,
        "aggregated_notifications": 0,
        "total_users": 1,
    }


@pytest.mark.asyncio
async def test_notify_application_batch_updates_multi_all_approved(dummy_service):
    updates = [
        {"user_id": 7, "application_id": 1, "status": "approved"},
        {"user_id": 7, "application_id": 2, "status": "approved"},
    ]

    result = await dummy_service.notify_application_batch_updates(updates)

    dummy_service.notifyApplicationStatusChange.assert_not_called()
    dummy_service.create_notification.assert_awaited_once()
    args, kwargs = dummy_service.create_notification.await_args

    assert kwargs["user_id"] == 7
    assert kwargs["notification_type"] == NotificationType.application_approved
    assert kwargs["priority"] == NotificationPriority.high
    assert kwargs["href"] == "/applications"
    assert kwargs["group_key"] == "application_results"
    payload = kwargs["data"]
    assert payload["approved_count"] == 2
    assert payload["rejected_count"] == 0
    assert payload["total_count"] == 2

    assert result == {
        "individual_notifications": 0,
        "aggregated_notifications": 1,
        "total_users": 1,
    }


@pytest.mark.asyncio
async def test_notify_application_batch_updates_mixed_statuses(dummy_service):
    updates = [
        {"user_id": 9, "application_id": 11, "status": "approved"},
        {"user_id": 9, "application_id": 12, "status": "rejected"},
        {"user_id": 9, "application_id": 13, "status": "pending"},
    ]

    await dummy_service.notify_application_batch_updates(updates)

    args, kwargs = dummy_service.create_notification.await_args
    payload = kwargs["data"]
    assert payload["approved_count"] == 1
    assert payload["rejected_count"] == 1
    assert payload["total_count"] == 3
    assert "核准：1" in payload["message"]
    assert kwargs["notification_type"] == NotificationType.info


@pytest.mark.asyncio
async def test_notify_deadline_reminders_batch_creates_queue_entries(dummy_service, monkeypatch):
    base_time = datetime(2024, 5, 1, 12, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return base_time if tz is None else base_time.astimezone(tz)

    monkeypatch.setattr("app.services.notification_service.datetime", FixedDateTime)

    queue_records = []

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            queue_records.append(kwargs)

    monkeypatch.setattr("app.services.notification_service.NotificationQueue", FakeQueue)

    dummy_service.db.add = lambda entry: None
    dummy_service.db.commit = AsyncMock()

    deadline_items = [
        {"user_id": 1, "id": 101, "title": "Upload transcript", "deadline": base_time + timedelta(days=3)},
        {"user_id": 2, "id": 201, "title": "Professor review", "deadline": base_time + timedelta(days=2)},
        {"user_id": 2, "id": 202, "title": "Financial docs", "deadline": base_time + timedelta(days=4)},
    ]

    batch_id = await dummy_service.notify_deadline_reminders_batch(deadline_items, days_before=5)

    assert batch_id
    assert len(queue_records) == 2

    first = queue_records[0]
    assert first["user_id"] == 1
    assert first["notifications_data"]["user_ids"] == [1]
    assert first["notifications_data"]["data"]["deadline_id"] == 101
    assert first["scheduled_for"] == base_time + timedelta(hours=1)

    second = queue_records[1]
    assert second["user_id"] == 2
    assert second["notifications_data"]["data"]["count"] == 2
    assert second["scheduled_for"] == base_time + timedelta(hours=1, seconds=30)

    dummy_service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_notification_analytics(dummy_service, monkeypatch):
    base_time = datetime(2024, 6, 1, 0, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return base_time if tz is None else base_time.astimezone(tz)

    monkeypatch.setattr("app.services.notification_service.datetime", FixedDateTime)

    notifications = [
        type(
            "Notif",
            (),
            {
                "created_at": base_time - timedelta(days=1),
                "is_read": True,
                "notification_type": NotificationType.application_approved,
                "priority": NotificationPriority.high,
                "channel": NotificationChannel.in_app,
            },
        )(),
        type(
            "Notif",
            (),
            {
                "created_at": base_time - timedelta(days=2),
                "is_read": False,
                "notification_type": NotificationType.application_rejected,
                "priority": NotificationPriority.normal,
                "channel": NotificationChannel.email,
            },
        )(),
    ]

    class FakeScalarResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            class _Wrapper:
                def __init__(self, items):
                    self._items = items

                def all(self):
                    return list(self._items)

            return _Wrapper(self._items)

    dummy_service.db.execute = AsyncMock(return_value=FakeScalarResult(notifications))

    analytics = await dummy_service.get_notification_analytics(user_id=42, days=7)

    assert analytics["total_notifications"] == 2
    assert analytics["read_notifications"] == 1
    assert analytics["unread_notifications"] == 1
    assert analytics["engagement_rate"] == 50.0
    assert analytics["type_breakdown"][NotificationType.application_approved.value] == 1
    assert analytics["priority_breakdown"][NotificationPriority.high.value] == 1
    assert analytics["channel_breakdown"][NotificationChannel.email.value] == 1
    assert analytics["user_id"] == 42


@pytest.mark.asyncio
async def test_create_batched_notification_enqueues_batches(dummy_service, monkeypatch):
    base_time = datetime(2024, 7, 10, 8, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return base_time if tz is None else base_time.astimezone(tz)

    monkeypatch.setattr("app.services.notification_service.datetime", FixedDateTime)

    queue_entries = []

    class FakeQueue:
        def __init__(self, *args, **kwargs):
            queue_entries.append(kwargs)

    monkeypatch.setattr("app.services.notification_service.NotificationQueue", FakeQueue)

    dummy_service.db.add = lambda entry: None
    dummy_service.db.commit = AsyncMock()

    user_ids = list(range(5))
    batch_id = await dummy_service.create_batched_notification(
        user_ids=user_ids,
        notification_type=NotificationType.info,
        data={"title": "Bulk update"},
        batch_size=2,
        delay_minutes=10,
    )

    assert batch_id
    assert len(queue_entries) == 3
    assert queue_entries[0]["notifications_data"]["user_ids"] == [0, 1]
    assert queue_entries[1]["notifications_data"]["user_ids"] == [2, 3]
    assert queue_entries[2]["notifications_data"]["user_ids"] == [4]
    assert queue_entries[1]["scheduled_for"] == base_time + timedelta(minutes=10)
    dummy_service.db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_aggregate_notifications_returns_grouped_data(dummy_service, monkeypatch):
    base_time = datetime(2024, 8, 1, 10, 0, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return base_time if tz is None else base_time.astimezone(tz)

    monkeypatch.setattr("app.services.notification_service.datetime", FixedDateTime)

    class FakeNotification:
        def __init__(self, created_at, notif_type):
            self.user_id = 3
            self.group_key = "updates"
            self.created_at = created_at
            self.is_read = False
            self.notification_type = notif_type
            self.effective_href = "/applications"

        def to_dict(self):
            return {"created_at": self.created_at.isoformat(), "type": self.notification_type.value}

    notifications = [
        FakeNotification(base_time - timedelta(hours=1), NotificationType.application_approved),
        FakeNotification(base_time - timedelta(hours=2), NotificationType.application_approved),
        FakeNotification(base_time - timedelta(hours=3), NotificationType.application_rejected),
    ]

    class FakeScalarResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            class _Wrapper:
                def __init__(self, items):
                    self._items = items

                def all(self):
                    return list(self._items)

            return _Wrapper(self._items)

    dummy_service.db.execute = AsyncMock(return_value=FakeScalarResult(notifications))

    aggregated = await dummy_service.aggregate_notifications(user_id=3, group_key="updates")

    assert aggregated["count"] == 3
    assert aggregated["type_counts"][NotificationType.application_approved.value] == 2
    assert aggregated["type_counts"][NotificationType.application_rejected.value] == 1
    assert aggregated["latest"]["created_at"].startswith(str(base_time.year))


@pytest.mark.asyncio
async def test_aggregate_notifications_empty_returns_empty_dict(dummy_service, monkeypatch):
    class FakeScalarResult:
        def scalars(self):
            class _Wrapper:
                def all(self):
                    return []

            return _Wrapper()

    dummy_service.db.execute = AsyncMock(return_value=FakeScalarResult())

    result = await dummy_service.aggregate_notifications(user_id=9, group_key="none")
    assert result == {}


@pytest.mark.asyncio
async def test_add_and_remove_websocket(dummy_service):
    connection = object()
    await dummy_service.add_websocket_connection(user_id=1, websocket=connection)
    assert dummy_service._websocket_connections[1] == [connection]

    await dummy_service.remove_websocket_connection(user_id=1, websocket=connection)
    assert dummy_service._websocket_connections[1] == []
