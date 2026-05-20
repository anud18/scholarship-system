"""
Tests for `app/schemas/notification.py` field bounds + alias mapping.

Wave 6a26 covered the allowlist validators (notification_type +
priority). This wave covers the **structural** invariants:

  - **Title/message length bounds**: title min=1 max=200, message
    min=1. Empty title/message would surface as blank announcement
    cards on the dashboard. Title over 200 silently truncates
    in the DB.

  - **action_url max=500** — caps the click-through URL length so
    the column doesn't bloat with attacker-crafted long URLs.

  - **NotificationResponse alias `meta_data` ↔ `metadata`**: the
    SQLAlchemy column is named `meta_data` to avoid colliding with
    the ORM's reserved `metadata` attribute, but the wire shape
    uses `metadata`. `populate_by_name=True` means both names work
    on input. Drift breaks model_validate(orm_row).

  - **Default values**: `notification_type=NotificationType.info.value`,
    `priority=NotificationPriority.normal.value`. Flipping the
    type default would auto-classify every announcement as
    success/warning/error.

15 cases.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.notification import NotificationPriority, NotificationType
from app.schemas.notification import (
    NotificationCreate,
    NotificationResponse,
    NotificationUpdate,
)

# ─── NotificationCreate length bounds ────────────────────────────────


def test_create_title_min_length_1():
    # Pin: empty title rejected. The dashboard renders the title
    # as the announcement headline — empty would surface as a
    # blank card.
    with pytest.raises(ValidationError):
        NotificationCreate(title="", message="x")


def test_create_title_max_length_200():
    # Pin: 200-char cap. The column is sized for headlines, not
    # paragraphs.
    with pytest.raises(ValidationError):
        NotificationCreate(title="x" * 201, message="x")


def test_create_title_exactly_200_accepted():
    # Pin: inclusive boundary.
    n = NotificationCreate(title="x" * 200, message="y")
    assert len(n.title) == 200


def test_create_title_en_optional_with_max_200():
    # Pin: English title is Optional but same 200 cap.
    with pytest.raises(ValidationError):
        NotificationCreate(title="x", message="y", title_en="x" * 201)


def test_create_message_min_length_1():
    with pytest.raises(ValidationError):
        NotificationCreate(title="x", message="")


def test_create_message_no_max_length():
    # Pin: message has min=1 but NO max — full-text announcement
    # bodies can be long. If a regression added a max, paragraph-
    # length announcements would silently truncate.
    long_message = "x" * 5000
    n = NotificationCreate(title="x", message=long_message)
    assert n.message == long_message


def test_create_action_url_max_length_500():
    # Pin: 500-char cap on click-through URL. Long URLs would bloat
    # the column and could be attacker-crafted.
    with pytest.raises(ValidationError):
        NotificationCreate(title="x", message="y", action_url="https://example.com/" + "x" * 500)


# ─── NotificationCreate defaults ────────────────────────────────────


def test_create_notification_type_defaults_to_info():
    # Pin: `info` is the safest default — wave 6a55 pinned the
    # security_alert routing for high-priority categories; `info`
    # never triggers the SECURITY routing.
    n = NotificationCreate(title="x", message="y")
    assert n.notification_type == NotificationType.info.value


def test_create_priority_defaults_to_normal():
    # Pin: `normal` priority — never auto-escalates an admin
    # announcement to urgent (which surfaces as a banner).
    n = NotificationCreate(title="x", message="y")
    assert n.priority == NotificationPriority.normal.value


# ─── NotificationUpdate PATCH semantics ─────────────────────────────


def test_update_all_fields_optional():
    obj = NotificationUpdate()
    assert obj.title is None
    assert obj.message is None
    assert obj.is_dismissed is None


def test_update_title_min_length_still_enforced():
    # Pin: when supplied, title min=1 still applies. PATCH doesn't
    # accept empty values, only "field not present".
    with pytest.raises(ValidationError):
        NotificationUpdate(title="")


# ─── NotificationResponse alias mapping ─────────────────────────────


def _response_min():
    return dict(
        id=1,
        title="hi",
        message="body",
        notification_type="info",
        priority="normal",
        is_read=False,
        is_dismissed=False,
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )


def test_response_accepts_meta_data_alias_from_orm():
    # Pin: ORM column name is `meta_data` (SQLAlchemy reserves
    # `metadata`). `populate_by_name=True` + `alias="meta_data"`
    # means the response accepts model_validate({"meta_data": ...}).
    r = NotificationResponse(**_response_min(), meta_data={"k": "v"})
    assert r.metadata == {"k": "v"}


def test_response_accepts_python_field_name_metadata():
    # Pin: both `metadata` (Python field) and `meta_data` (alias)
    # accepted on input.
    r = NotificationResponse(**_response_min(), metadata={"k": "v"})
    assert r.metadata == {"k": "v"}


def test_response_metadata_defaults_none():
    r = NotificationResponse(**_response_min())
    assert r.metadata is None


def test_response_required_anchor_fields():
    # Pin: id / title / message / notification_type / priority /
    # is_read / is_dismissed / created_at all required. The
    # dashboard card depends on each.
    with pytest.raises(ValidationError):
        NotificationResponse(
            id=1,
            title="hi",
            message="body",
            notification_type="info",
            priority="normal",
            is_read=False,
            # is_dismissed missing
            created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        )
