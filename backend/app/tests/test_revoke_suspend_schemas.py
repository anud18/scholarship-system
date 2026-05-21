"""Pin: revoke/suspend request schemas reject empty/too-long reasons and
parse valid input. RevokedSuspendedListResponse shape mirrors the API spec."""

import pytest
from pydantic import ValidationError

from app.schemas.application import RevokeRequest, SuspendRequest
from app.schemas.payment_roster import (
    RemoveLockedItemRequest,
    RevokedSuspendedListResponse,
    RevokedSuspendedEntry,
)


def test_revoke_request_requires_non_empty_reason():
    with pytest.raises(ValidationError):
        RevokeRequest(reason="")


def test_revoke_request_rejects_too_long_reason():
    with pytest.raises(ValidationError):
        RevokeRequest(reason="x" * 501)


def test_revoke_request_accepts_valid_reason():
    req = RevokeRequest(reason="violated scholarship terms")
    assert req.reason == "violated scholarship terms"


def test_suspend_request_validates_same_way():
    with pytest.raises(ValidationError):
        SuspendRequest(reason="")
    assert SuspendRequest(reason="leave of absence").reason == "leave of absence"


def test_remove_locked_item_request_reason_optional():
    assert RemoveLockedItemRequest().reason is None
    assert RemoveLockedItemRequest(reason="clean up").reason == "clean up"


def test_revoked_suspended_list_response_shape():
    entry = RevokedSuspendedEntry(
        application_id=1,
        student_name="王小明",
        student_id_number="B12345",
        event_at="2026-05-21T10:00:00Z",
        reason="test",
    )
    resp = RevokedSuspendedListResponse(revoked=[entry], suspended=[])
    assert resp.revoked[0].student_name == "王小明"
    assert resp.suspended == []
