"""
Pydantic validator tests for `notification.py` and `application_field.py`.

`NotificationCreate / NotificationUpdate` validators are allowlist gates
on `notification_type` and `priority` — these are stored as strings but
must match the enum values. A bypass would store junk strings that
break the frontend's switch-on-type rendering (icon, color, route).

`ApplicationFieldBase._validate_export_flag` is the college-export gate:
`include_in_college_export=True` is only legal when `field_type='text'`.
Otherwise the Excel export would try to serialize select/checkbox/date
data as plain text strings, leading to garbled exports the college
review team relies on.

7 validators (17 cases). Pure Pydantic, no DB.
"""

import pytest
from pydantic import ValidationError

from app.models.application_field import FieldType
from app.models.notification import NotificationPriority, NotificationType
from app.schemas.application_field import (
    ApplicationFieldBase,
    ApplicationFieldUpdate,
)
from app.schemas.notification import NotificationCreate, NotificationUpdate

# ─── NotificationCreate.validate_notification_type ───────────────────


def test_notification_type_known_enum_accepted():
    """Pin: all NotificationType enum values must round-trip via the
    string-typed schema field. Pick a representative subset."""
    for t in [NotificationType.info, NotificationType.deadline_approaching, NotificationType.security_alert]:
        n = NotificationCreate(title="X", message="Y", notification_type=t.value)
        assert n.notification_type == t.value


def test_notification_type_unknown_string_rejected():
    """SECURITY-ADJACENT: arbitrary type string would let the API store
    'unknown_type' or even 'admin_override' values. Pin the allowlist."""
    with pytest.raises(ValidationError) as exc:
        NotificationCreate(title="X", message="Y", notification_type="custom_type")
    assert "Invalid notification type" in str(exc.value)


def test_notification_type_default_is_info():
    """Pin: default value is 'info' when omitted — the catch-all bucket
    for backwards-compat. Refactor that drops the default would surface here."""
    n = NotificationCreate(title="X", message="Y")
    assert n.notification_type == NotificationType.info.value


# ─── NotificationCreate.validate_priority ────────────────────────────


def test_priority_known_values_accepted():
    for p in [
        NotificationPriority.low,
        NotificationPriority.normal,
        NotificationPriority.high,
        NotificationPriority.urgent,
    ]:
        n = NotificationCreate(title="X", message="Y", priority=p.value)
        assert n.priority == p.value


def test_priority_unknown_value_rejected():
    """Pin: 'critical' (the old enum name) explicitly NOT accepted —
    forces the new 'urgent' usage everywhere."""
    with pytest.raises(ValidationError) as exc:
        NotificationCreate(title="X", message="Y", priority="critical")
    assert "Invalid priority" in str(exc.value)


def test_priority_default_is_normal():
    n = NotificationCreate(title="X", message="Y")
    assert n.priority == NotificationPriority.normal.value


# ─── NotificationUpdate parallel validators (separate code path) ─────


def test_update_notification_type_none_passes_through():
    """Pin: None → no change (sentinel preserved). Otherwise a partial
    update that doesn't touch notification_type would crash."""
    upd = NotificationUpdate(notification_type=None)
    assert upd.notification_type is None


def test_update_notification_type_unknown_still_rejected():
    """Pin: when SET on Update, allowlist still enforced."""
    with pytest.raises(ValidationError):
        NotificationUpdate(notification_type="weird")


def test_update_priority_none_passes_through():
    upd = NotificationUpdate(priority=None)
    assert upd.priority is None


def test_update_priority_unknown_rejected():
    with pytest.raises(ValidationError):
        NotificationUpdate(priority="critical")  # old enum name no longer accepted


# ─── NotificationCreate field-level constraints ──────────────────────


def test_notification_title_max_length():
    """Pin: title 200-char cap (matches DB column)."""
    with pytest.raises(ValidationError):
        NotificationCreate(title="x" * 201, message="Y")


def test_notification_action_url_max_length():
    """Pin: action_url 500-char cap. Defensive against pathological URLs."""
    with pytest.raises(ValidationError):
        NotificationCreate(title="X", message="Y", action_url="http://example.com/" + "x" * 500)


# ─── ApplicationFieldBase._validate_export_flag (model_validator) ────


def _field_payload(**overrides) -> dict:
    payload = {
        "scholarship_type": "PHD",
        "field_name": "comments",
        "field_label": "備註",
        "field_type": FieldType.TEXT.value,
    }
    payload.update(overrides)
    return payload


def test_export_flag_with_text_field_accepted():
    """include_in_college_export=True is only legal with field_type='text'."""
    f = ApplicationFieldBase(**_field_payload(include_in_college_export=True))
    assert f.include_in_college_export is True


def test_export_flag_with_select_field_rejected():
    """Pin: select fields with include_in_college_export=True rejected.
    Otherwise the export script serializes the option array as a junk
    string and college reviewers see corrupt cells."""
    with pytest.raises(ValidationError) as exc:
        ApplicationFieldBase(**_field_payload(field_type=FieldType.SELECT.value, include_in_college_export=True))
    assert "field_type='text'" in str(exc.value)


def test_export_flag_with_number_field_rejected():
    """Pin: number, date, checkbox, radio — none allowed for export.
    The college Excel template only supports text columns."""
    for ft in (FieldType.NUMBER, FieldType.DATE, FieldType.CHECKBOX, FieldType.RADIO):
        with pytest.raises(ValidationError):
            ApplicationFieldBase(**_field_payload(field_type=ft.value, include_in_college_export=True))


def test_export_flag_false_allows_any_field_type():
    """Pin: include_in_college_export=False (default) bypasses the gate
    — non-text fields can exist as long as they're NOT exported."""
    for ft in (FieldType.SELECT, FieldType.NUMBER, FieldType.DATE):
        f = ApplicationFieldBase(**_field_payload(field_type=ft.value, include_in_college_export=False))
        assert f.field_type == ft.value


# ─── ApplicationFieldUpdate._validate_export_flag (parallel) ─────────


def test_update_export_flag_with_select_field_rejected():
    """Pin: Update path enforces the same gate."""
    with pytest.raises(ValidationError):
        ApplicationFieldUpdate(include_in_college_export=True, field_type=FieldType.SELECT.value)


def test_update_export_flag_with_field_type_unchanged_accepted():
    """field_type=None on Update means 'not changing' — the validator
    must NOT block in that case. Pin: include_in_college_export=True
    with field_type=None passes the validator (the field's existing
    type is presumably 'text' or the validation was applied earlier)."""
    upd = ApplicationFieldUpdate(include_in_college_export=True, field_type=None)
    assert upd.include_in_college_export is True


def test_update_export_flag_false_with_select_accepted():
    """Pin: include_in_college_export=False even paired with a non-text
    field_type — no gate fires."""
    upd = ApplicationFieldUpdate(include_in_college_export=False, field_type=FieldType.SELECT.value)
    assert upd.include_in_college_export is False
