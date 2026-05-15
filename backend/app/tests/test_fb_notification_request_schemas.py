"""
Tests for `backend/app/api/v1/endpoints/notifications_facebook_demo.py` —
the 3 Pydantic request models inline in the router module.

Module has tests/test_facebook_notification_request_schemas.py
referenced in waves history but no such file exists in main —
this fills the gap. SECURITY-critical PRIVACY defaults on
PreferenceUpdateRequest (sms/push off, in_app/email on).

Wave 6a144 pins the 3 schemas' field shapes, defaults, and
type contracts without invoking the FastAPI routes.
"""

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.notifications_facebook_demo import (
    CreateNotificationRequest,
    BatchNotificationRequest,
    PreferenceUpdateRequest,
)


class TestCreateNotificationRequest:
    """Pin: 7 fields — user_id optional, notification_type required,
    data required, channels optional list, priority defaults
    'normal', href + group_key optional."""

    def test_minimal_required_fields(self):
        # Pin: only notification_type + data are required.
        req = CreateNotificationRequest(
            notification_type="info",
            data={"message": "hello"},
        )
        assert req.notification_type == "info"
        assert req.data == {"message": "hello"}
        assert req.user_id is None
        assert req.channels is None
        assert req.priority == "normal"
        assert req.href is None
        assert req.group_key is None

    def test_priority_defaults_to_normal(self):
        # Pin: priority default is the string "normal" (NOT enum).
        # Pin so refactor to enum doesn't break the JSON-encoding
        # path that ships this to backend.
        req = CreateNotificationRequest(notification_type="x", data={})
        assert req.priority == "normal"
        assert isinstance(req.priority, str)

    def test_channels_accepts_list_of_strings(self):
        # Pin: channels is a list of STRINGS (not enum). Backend
        # endpoint coerces to NotificationChannel inside the
        # handler. Pin so refactor doesn't change the wire shape.
        req = CreateNotificationRequest(
            notification_type="info",
            data={},
            channels=["in_app", "email", "sms"],
        )
        assert req.channels == ["in_app", "email", "sms"]

    def test_missing_notification_type_raises(self):
        with pytest.raises(ValidationError) as exc:
            CreateNotificationRequest(data={})
        assert "notification_type" in str(exc.value)

    def test_missing_data_raises(self):
        # Pin: data is REQUIRED (NOT defaulted to empty dict).
        # Pin so refactor making it optional doesn't silently
        # accept notifications without context.
        with pytest.raises(ValidationError) as exc:
            CreateNotificationRequest(notification_type="info")
        assert "data" in str(exc.value)


class TestBatchNotificationRequest:
    """Pin: batch defaults — 100 size, 5 minute delay."""

    def test_required_fields(self):
        # Pin: user_ids, notification_type, data required.
        req = BatchNotificationRequest(
            user_ids=[1, 2, 3],
            notification_type="info",
            data={"x": 1},
        )
        assert req.user_ids == [1, 2, 3]
        assert req.batch_size == 100
        assert req.delay_minutes == 5

    def test_batch_size_default_100(self):
        # Pin: 100 is the SECURITY-relevant rate-limit boundary.
        # Pin so refactor doesn't drop to 1 (storm backend) or
        # raise to 10000 (DoS).
        req = BatchNotificationRequest(user_ids=[1], notification_type="x", data={})
        assert req.batch_size == 100

    def test_delay_minutes_default_5(self):
        # Pin: 5-minute spacing between batches by default.
        req = BatchNotificationRequest(user_ids=[1], notification_type="x", data={})
        assert req.delay_minutes == 5

    def test_empty_user_ids_list_accepted(self):
        # Pin: empty list is currently ACCEPTED (no min_length
        # constraint). Document this — refactor adding min_length
        # would tighten the contract.
        req = BatchNotificationRequest(user_ids=[], notification_type="x", data={})
        assert req.user_ids == []


class TestPreferenceUpdateRequestPrivacyDefaults:
    """Pin SECURITY: PRIVACY defaults — in_app + email enabled by
    default (the channels students have implicit consent for),
    sms + push DISABLED by default (require explicit opt-in).
    Drift would silently spam students on channels they didn't
    consent to."""

    def test_in_app_default_true(self):
        # Pin SECURITY: in_app on by default (system needs ability
        # to deliver notifications inside the app).
        req = PreferenceUpdateRequest(notification_type="info")
        assert req.in_app_enabled is True

    def test_email_default_true(self):
        # Pin SECURITY: email on by default (covered by initial
        # account-creation consent).
        req = PreferenceUpdateRequest(notification_type="info")
        assert req.email_enabled is True

    def test_sms_default_false(self):
        # Pin SECURITY: sms OFF by default. Students must
        # explicitly opt-in to receive SMS (carrier costs, more
        # intrusive).
        req = PreferenceUpdateRequest(notification_type="info")
        assert req.sms_enabled is False

    def test_push_default_false(self):
        # Pin SECURITY: push OFF by default. Push requires
        # browser/OS permission AND user opt-in.
        req = PreferenceUpdateRequest(notification_type="info")
        assert req.push_enabled is False

    def test_frequency_default_immediate(self):
        # Pin: "immediate" delivery default (NOT batched). Pin so
        # refactor doesn't silently switch to digest mode (delays
        # critical notifications like application-status changes).
        req = PreferenceUpdateRequest(notification_type="info")
        assert req.frequency == "immediate"

    def test_explicit_opt_in_overrides_default(self):
        # Pin: caller can explicitly enable sms/push. Pin so
        # refactor doesn't reject the request as "invalid".
        req = PreferenceUpdateRequest(
            notification_type="info",
            sms_enabled=True,
            push_enabled=True,
        )
        assert req.sms_enabled is True
        assert req.push_enabled is True

    def test_explicit_opt_out_overrides_default(self):
        # Pin: caller can explicitly disable in_app/email. Pin so
        # refactor doesn't lock students into receiving channels
        # they want disabled.
        req = PreferenceUpdateRequest(
            notification_type="info",
            in_app_enabled=False,
            email_enabled=False,
        )
        assert req.in_app_enabled is False
        assert req.email_enabled is False

    def test_missing_notification_type_raises(self):
        # Pin: notification_type is REQUIRED. Pin so refactor to
        # optional doesn't accept undifferentiated preference
        # updates.
        with pytest.raises(ValidationError):
            PreferenceUpdateRequest()
