"""
Tests for the 4 notification enums in `app.models.notification`.

These enums drive:
- Delivery channel routing (in_app/email/sms/push)
- ~30 distinct notification types covering full application lifecycle
- 4 priority levels (low/normal/high/urgent)
- 4 delivery frequencies (immediate/daily/weekly/disabled)

Bugs cause:
- Channel rename → notifications routed to wrong delivery worker
- Type rename → frontend can't render notification icon/color
  (switch-on-type falls through to default)
- Priority rename → admin alert filter loses urgent/high
- Frequency rename → daily digest worker stops finding queued items

4 enums (8 cases). Pure, no DB.
"""

from app.models.notification import (
    NotificationChannel,
    NotificationFrequency,
    NotificationPriority,
    NotificationType,
)

# ─── NotificationChannel ─────────────────────────────────────────────


def test_notification_channel_values():
    """Pin: 4 delivery channels — in_app/email/sms/push. The notification
    worker dispatches based on this string; a rename would orphan the
    handler."""
    assert NotificationChannel.in_app.value == "in_app"
    assert NotificationChannel.email.value == "email"
    assert NotificationChannel.sms.value == "sms"
    assert NotificationChannel.push.value == "push"
    assert len(list(NotificationChannel)) == 4


def test_notification_channel_in_app_uses_underscore():
    """Pin: 'in_app' uses underscore (not 'inapp' or 'in-app').
    DB enum + frontend filter rely on this exact spelling."""
    assert NotificationChannel.in_app.value == "in_app"


# ─── NotificationType (large allowlist) ──────────────────────────────


def test_notification_type_legacy_types():
    """Pin: 5 legacy types kept for backward compatibility with older
    notification rows. Removing any would break historical-data display."""
    assert NotificationType.info.value == "info"
    assert NotificationType.warning.value == "warning"
    assert NotificationType.error.value == "error"
    assert NotificationType.success.value == "success"
    assert NotificationType.reminder.value == "reminder"


def test_notification_type_application_lifecycle():
    """Pin: 5 application lifecycle types. The frontend dashboard
    groups notifications by these to render the application timeline."""
    assert NotificationType.application_submitted.value == "application_submitted"
    assert NotificationType.application_approved.value == "application_approved"
    assert NotificationType.application_rejected.value == "application_rejected"
    assert NotificationType.application_requires_review.value == "application_requires_review"
    assert NotificationType.application_under_review.value == "application_under_review"


def test_notification_type_security_alert_pinned():
    """SECURITY-CRITICAL: security_alert type triggers immediate admin
    paging via the notification worker. A rename would silently disable
    security alerts."""
    assert NotificationType.security_alert.value == "security_alert"


def test_notification_type_count_pinned():
    """Pin: ~28 notification types defined. Adding a new type without
    updating the frontend switch-on-type renderer would silently use
    the default icon/color."""
    assert len(list(NotificationType)) == 28


# ─── NotificationPriority ────────────────────────────────────────────


def test_notification_priority_values():
    """Pin: 4 priorities. Critical: 'urgent' (formerly 'critical' —
    documented in the model) is the highest level. Admin paging filters
    by this exact string."""
    assert NotificationPriority.low.value == "low"
    assert NotificationPriority.normal.value == "normal"
    assert NotificationPriority.high.value == "high"
    assert NotificationPriority.urgent.value == "urgent"
    assert len(list(NotificationPriority)) == 4


# ─── NotificationFrequency ───────────────────────────────────────────


def test_notification_frequency_values():
    """Pin: 4 frequencies — immediate/daily/weekly/disabled. The
    digest worker filters queue entries by these strings; rename
    breaks digest delivery."""
    assert NotificationFrequency.immediate.value == "immediate"
    assert NotificationFrequency.daily.value == "daily"
    assert NotificationFrequency.weekly.value == "weekly"
    assert NotificationFrequency.disabled.value == "disabled"
    assert len(list(NotificationFrequency)) == 4
