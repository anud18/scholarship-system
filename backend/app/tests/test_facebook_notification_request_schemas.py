"""
Tests for the Pydantic request schemas in
`app.schemas.notification_facebook`:

  - CreateNotificationRequest
  - BatchNotificationRequest
  - PreferenceUpdateRequest

Module had ZERO test coverage. These schemas drive the Facebook-
style notification flow. The schemas are pure Pydantic with
carefully-chosen defaults that affect:

  - Notification priority routing (default "normal")
  - Batch send rate-limiting (batch_size=100, delay_minutes=5 —
    SECURITY: too-large batch_size could be used to spam users)
  - User notification preference defaults (in_app/email ON,
    sms/push OFF — privacy-respecting defaults)

Wave 6a112 pins these defaults so a refactor doesn't silently
change rollout behaviour or default privacy posture.

13 cases.

The schemas were originally defined inline in
``app.api.v1.endpoints.notifications_facebook_demo`` but that module
was deleted (it was never router-mounted in production). See issue
#665 category C.
"""

import pytest
from pydantic import ValidationError

from app.schemas.notification_facebook import (
    BatchNotificationRequest,
    CreateNotificationRequest,
    PreferenceUpdateRequest,
)

# ─── CreateNotificationRequest ──────────────────────────────────────


def test_create_request_minimal_required_fields():
    # Pin: required = notification_type + data. user_id, channels,
    # group_key, href are all optional.
    req = CreateNotificationRequest(notification_type="app_status_change", data={"app_id": 1})
    assert req.notification_type == "app_status_change"
    assert req.data == {"app_id": 1}
    assert req.user_id is None
    assert req.channels is None


def test_create_request_priority_default_is_normal():
    # Pin: default priority "normal". Pin so a refactor to "high"
    # doesn't accidentally make every demo notification urgent.
    req = CreateNotificationRequest(notification_type="x", data={})
    assert req.priority == "normal"


def test_create_request_data_is_required():
    # Pin: data field has no default — missing → ValidationError.
    with pytest.raises(ValidationError):
        CreateNotificationRequest(notification_type="x")


def test_create_request_notification_type_is_required():
    with pytest.raises(ValidationError):
        CreateNotificationRequest(data={})


def test_create_request_accepts_full_payload():
    # Pin: all fields settable when explicitly provided.
    req = CreateNotificationRequest(
        user_id=1,
        notification_type="info",
        data={"k": "v"},
        channels=["in_app", "email"],
        priority="high",
        href="/x",
        group_key="g1",
    )
    assert req.user_id == 1
    assert req.channels == ["in_app", "email"]
    assert req.priority == "high"


# ─── BatchNotificationRequest ───────────────────────────────────────


def test_batch_request_required_fields():
    # Pin: user_ids + notification_type + data are required.
    req = BatchNotificationRequest(user_ids=[1, 2, 3], notification_type="ann", data={})
    assert req.user_ids == [1, 2, 3]
    assert req.notification_type == "ann"


def test_batch_request_batch_size_default_is_100():
    # Pin: default batch_size 100. SECURITY-relevant — too-large
    # default could be misused to spam users. Pin so a refactor
    # raising the default (e.g., to 1000) forces explicit review.
    req = BatchNotificationRequest(user_ids=[1], notification_type="x", data={})
    assert req.batch_size == 100


def test_batch_request_delay_minutes_default_is_5():
    # Pin: default 5-minute rate-limit between batches. Pin so a
    # refactor to 0 doesn't accidentally send a burst.
    req = BatchNotificationRequest(user_ids=[1], notification_type="x", data={})
    assert req.delay_minutes == 5


def test_batch_request_accepts_empty_user_ids():
    # Pin: empty user_ids accepted (no min_length=1). The endpoint
    # may treat empty as a noop — pinned so a refactor to forbid
    # empty doesn't silently break that code path.
    req = BatchNotificationRequest(user_ids=[], notification_type="x", data={})
    assert req.user_ids == []


# ─── PreferenceUpdateRequest ────────────────────────────────────────


def test_preference_request_defaults_privacy_respecting():
    # Pin: in_app + email default TRUE; sms + push default FALSE.
    # SECURITY/PRIVACY-relevant — pin so a refactor flipping sms/
    # push to True-by-default doesn't accidentally enable channels
    # the user never opted into.
    req = PreferenceUpdateRequest(notification_type="app_status_change")
    assert req.in_app_enabled is True
    assert req.email_enabled is True
    assert req.sms_enabled is False
    assert req.push_enabled is False


def test_preference_request_frequency_default_is_immediate():
    # Pin: default frequency "immediate". Pin so a refactor to
    # "daily" doesn't silently batch user notifications.
    req = PreferenceUpdateRequest(notification_type="x")
    assert req.frequency == "immediate"


def test_preference_request_notification_type_required():
    # Pin: notification_type is required.
    with pytest.raises(ValidationError):
        PreferenceUpdateRequest()


def test_preference_request_all_fields_overridable():
    req = PreferenceUpdateRequest(
        notification_type="x",
        in_app_enabled=False,
        email_enabled=False,
        sms_enabled=True,
        push_enabled=True,
        frequency="daily",
    )
    assert req.in_app_enabled is False
    assert req.sms_enabled is True
    assert req.frequency == "daily"
