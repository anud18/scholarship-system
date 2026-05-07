"""
Regression for the notification_service timezone fix in 4d05f0e.

All Notification.expires_at + read_at columns are TZ-aware (DateTime with
timezone=True). Pre-fix, six call sites used naive `datetime.now()` for
both filter WHERE clauses and column writes — under Asia/Taipei
(our compose stack's TZ) that produced an 8-hour offset against UTC,
silently labelling "expired" notifications as active and vice versa
near the midnight UTC boundary.

This test pins the source-level invariant: every `datetime.now(...)` call
inside notification_service must be TZ-aware. Cheap module-level grep
keeps the regression visible if a future commit reintroduces a naive
form.
"""

import inspect
import re

from app.services import notification_service


def test_notification_service_has_no_naive_datetime_now():
    """Source must not contain bare `datetime.now()` in notification_service."""
    source = inspect.getsource(notification_service)
    # Match `datetime.now(` followed by a closing paren immediately or whitespace
    # then `)`, but allow `datetime.now(timezone.utc)` etc.
    matches = re.findall(r"datetime\.now\(\s*\)", source)
    assert not matches, (
        "notification_service must use timezone-aware datetime.now(timezone.utc); "
        f"found {len(matches)} naive datetime.now() call(s) — likely a regression of 4d05f0e."
    )


def test_notification_service_uses_timezone_utc():
    """Sanity: there's at least one `datetime.now(timezone.utc)` reference in the module."""
    source = inspect.getsource(notification_service)
    assert "datetime.now(timezone.utc)" in source, (
        "notification_service should be calling datetime.now(timezone.utc) — "
        "if this fails the timezone fix has been removed entirely."
    )
