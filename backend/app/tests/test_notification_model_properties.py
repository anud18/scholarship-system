"""
Pure-property tests for `Notification` model.

Notifications drive every status indicator on student/admin dashboards.
Bugs in these properties cause:
- Expired notifications still shown (user clutter) — is_expired wrong
- Urgent notification not surfaced to alert ticker — is_urgent wrong
- System announcements treated as personal → wrong user filter
- Mark-as-read no-ops when already read → no setter side effect
- Legacy meta_data lost when merging into effective_data → data
  archeology lost

8 properties + 3 setter methods covered (15 cases).
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.notification import Notification, NotificationPriority


class _FakeNotification:
    """SA-free helper — bypasses SQLAlchemy column instrumentation so pure
    Python @property methods can be exercised without _sa_instance_state."""

    def __init__(self, **attrs):
        self.__dict__.update(attrs)

    is_expired = property(Notification.is_expired.fget)
    is_urgent = property(Notification.is_urgent.fget)
    is_critical = property(Notification.is_critical.fget)
    is_system_announcement = property(Notification.is_system_announcement.fget)
    age_in_hours = property(Notification.age_in_hours.fget)
    effective_href = property(Notification.effective_href.fget)
    effective_data = property(Notification.effective_data.fget)
    mark_as_read = Notification.mark_as_read
    mark_as_unread = Notification.mark_as_unread
    archive = Notification.archive
    hide = Notification.hide
    dismiss = Notification.dismiss


def _notif(**overrides) -> _FakeNotification:
    defaults = {
        "id": 1,
        "user_id": 42,
        "priority": NotificationPriority.normal,
        "expires_at": None,
        "created_at": datetime.now(timezone.utc),
        "is_read": False,
        "is_archived": False,
        "is_hidden": False,
        "is_dismissed": False,
        "read_at": None,
        "href": None,
        "action_url": None,
        "data": None,
        "meta_data": None,
    }
    defaults.update(overrides)
    return _FakeNotification(**defaults)


# ─── is_expired ──────────────────────────────────────────────────────


def test_is_expired_no_deadline_is_false():
    """No expires_at → never expired (don't auto-hide notifications
    without explicit TTL)."""
    assert _notif(expires_at=None).is_expired is False


def test_is_expired_past_time_is_true():
    """expires_at in past → expired."""
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    assert _notif(expires_at=past).is_expired is True


def test_is_expired_future_time_is_false():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _notif(expires_at=future).is_expired is False


# ─── is_urgent + is_critical ─────────────────────────────────────────


def test_is_urgent_includes_high_and_urgent():
    """Pin: urgent AND high → urgent. Routine/low → not urgent."""
    assert _notif(priority=NotificationPriority.urgent).is_urgent is True
    assert _notif(priority=NotificationPriority.high).is_urgent is True
    assert _notif(priority=NotificationPriority.normal).is_urgent is False
    assert _notif(priority=NotificationPriority.low).is_urgent is False


def test_is_critical_only_urgent():
    """is_critical narrower than is_urgent — pin so 'high' doesn't get
    promoted to critical alerts (would page people unnecessarily)."""
    assert _notif(priority=NotificationPriority.urgent).is_critical is True
    assert _notif(priority=NotificationPriority.high).is_critical is False
    assert _notif(priority=NotificationPriority.normal).is_critical is False


# ─── is_system_announcement ──────────────────────────────────────────


def test_is_system_announcement_when_user_id_is_none():
    """user_id=None marks system-wide announcements. Pin: any other
    user_id (even 0) is NOT a system announcement."""
    assert _notif(user_id=None).is_system_announcement is True
    assert _notif(user_id=42).is_system_announcement is False
    # 0 is a valid user_id (don't trip on falsy check).
    assert _notif(user_id=0).is_system_announcement is False


# ─── age_in_hours ────────────────────────────────────────────────────


def test_age_in_hours_recent_is_small():
    """A notification created 'now' has age ≈ 0 hours. Allow slack for
    test execution time. Pin so hour conversion (seconds/3600) isn't
    swapped accidentally."""
    n = _notif(created_at=datetime.now(timezone.utc))
    assert 0 <= n.age_in_hours < 0.01


def test_age_in_hours_three_hours_ago():
    """3-hour-old notification reports age ≈ 3."""
    three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    n = _notif(created_at=three_hours_ago)
    assert 2.99 < n.age_in_hours < 3.01


# ─── effective_href / effective_data (legacy support) ────────────────


def test_effective_href_prefers_new_href():
    """href (new) wins over action_url (legacy)."""
    assert _notif(href="/new", action_url="/old").effective_href == "/new"
    # No href → fall back to action_url.
    assert _notif(href=None, action_url="/old").effective_href == "/old"
    # Neither → None.
    assert _notif(href=None, action_url=None).effective_href is None


def test_effective_data_merges_legacy_into_new():
    """Pin: legacy meta_data merged FIRST, then new data overrides keys.
    Drops nothing — both surfaces must be visible in admin debug views."""
    n = _notif(meta_data={"legacy_key": "v1", "shared": "old"}, data={"new_key": "v2", "shared": "new"})
    result = n.effective_data
    assert result["legacy_key"] == "v1"
    assert result["new_key"] == "v2"
    # `data` wins on collision (new overrides legacy).
    assert result["shared"] == "new"


def test_effective_data_handles_missing_fields():
    """Both None → empty dict (not None — caller expects dict for spread)."""
    n = _notif(meta_data=None, data=None)
    assert n.effective_data == {}


# ─── State setters (mark/archive/hide/dismiss) ───────────────────────


def test_mark_as_read_sets_flag_and_timestamp():
    """First read: is_read=True + read_at populated."""
    n = _notif(is_read=False, read_at=None)
    n.mark_as_read()
    assert n.is_read is True
    assert n.read_at is not None


def test_mark_as_read_is_idempotent():
    """Calling on already-read notification doesn't touch read_at
    (preserves original read timestamp). Pin so analytics 'time-to-
    read' isn't reset on every dashboard refresh."""
    original_read_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    n = _notif(is_read=True, read_at=original_read_at)
    n.mark_as_read()
    assert n.read_at == original_read_at


def test_mark_as_unread_clears_flag_and_timestamp():
    """Unread reset: is_read=False AND read_at=None (don't keep stale
    timestamp)."""
    n = _notif(is_read=True, read_at=datetime.now(timezone.utc))
    n.mark_as_unread()
    assert n.is_read is False
    assert n.read_at is None


def test_archive_hide_dismiss_setters():
    """Three independent state flags. Pin the property names."""
    n = _notif()
    n.archive()
    assert n.is_archived is True
    n.hide()
    assert n.is_hidden is True
    n.dismiss()
    assert n.is_dismissed is True
