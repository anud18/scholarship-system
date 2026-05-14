"""
Tests for `app/schemas/document_request.py`.

These schemas gate every document-request operation a professor or
admin performs — "please upload your transcript", "this request is
fulfilled", "I'm cancelling this request". A regression in the length
constraints would either:

  - **bypass min_length** → empty/single-character reasons silently
    accepted (students get useless "blank" reminders).
  - **bypass max_length** → unbounded reason field grows the DB column
    and gets truncated mid-string on render.

The min/max bounds in this schema are the only enforcement layer
between professor-typed text and the database — pin them precisely.

19 cases.
"""

import pytest
from pydantic import ValidationError

from app.schemas.document_request import (
    DocumentRequestCancel,
    DocumentRequestCreate,
    DocumentRequestFulfill,
    DocumentRequestListItem,
    DocumentRequestResponse,
    StudentDocumentRequestResponse,
)
from datetime import datetime, timezone

# ─── DocumentRequestCreate ──────────────────────────────────────────


def test_create_requires_requested_documents_and_reason():
    # Pin: both fields non-optional. Empty payload must reject.
    with pytest.raises(ValidationError):
        DocumentRequestCreate()  # type: ignore[call-arg]


def test_create_reason_min_length_10():
    # Pin: 9 chars rejected. The bound exists so professors can't type
    # "ok" and call it a request.
    with pytest.raises(ValidationError):
        DocumentRequestCreate(
            requested_documents=["transcript"],
            reason="too short",  # 9 chars
        )


def test_create_reason_max_length_1000():
    # Pin: 1001 chars rejected. Bound exists so the DB column doesn't
    # silently truncate.
    with pytest.raises(ValidationError):
        DocumentRequestCreate(
            requested_documents=["transcript"],
            reason="x" * 1001,
        )


def test_create_reason_exactly_10_chars_accepted():
    # Pin: inclusive boundary.
    obj = DocumentRequestCreate(
        requested_documents=["transcript"],
        reason="x" * 10,
    )
    assert len(obj.reason) == 10


def test_create_notes_optional_with_max_2000():
    # Pin: notes optional, but if present capped at 2000.
    obj = DocumentRequestCreate(
        requested_documents=["transcript"],
        reason="需要補充成績單以確認學業成績",
    )
    assert obj.notes is None

    with pytest.raises(ValidationError):
        DocumentRequestCreate(
            requested_documents=["transcript"],
            reason="需要補充成績單以確認學業成績",
            notes="x" * 2001,
        )


def test_create_deadline_optional():
    # Pin: deadline is Optional[datetime] — None = no hard deadline.
    obj = DocumentRequestCreate(
        requested_documents=["transcript"],
        reason="需要補充成績單以確認學業成績",
    )
    assert obj.deadline is None


def test_create_accepts_list_of_strings_for_requested_documents():
    # Pin: requested_documents is List[str] — admins free-typed
    # strings, NOT an enum (CLAUDE.md §4 sub-type-style configuration).
    obj = DocumentRequestCreate(
        requested_documents=["transcript", "recommendation_letter", "research_plan"],
        reason="需要補充多項申請文件確認資格",
    )
    assert obj.requested_documents == ["transcript", "recommendation_letter", "research_plan"]


# ─── DocumentRequestFulfill ─────────────────────────────────────────


def test_fulfill_notes_optional():
    # Pin: fulfill operation needs no required fields — fulfilling a
    # request can happen silently when the document has been uploaded.
    obj = DocumentRequestFulfill()
    assert obj.notes is None


def test_fulfill_notes_max_500():
    # Pin: fulfill notes capped tighter than create notes (500 vs
    # 2000). The cap is documented; pin both bounds independently.
    with pytest.raises(ValidationError):
        DocumentRequestFulfill(notes="x" * 501)


def test_fulfill_notes_exactly_500_accepted():
    obj = DocumentRequestFulfill(notes="x" * 500)
    assert obj.notes is not None
    assert len(obj.notes) == 500


# ─── DocumentRequestCancel ──────────────────────────────────────────


def test_cancel_requires_cancellation_reason():
    # Pin: cancellation must always carry a reason — audit-trail
    # requirement for staff actions.
    with pytest.raises(ValidationError):
        DocumentRequestCancel()  # type: ignore[call-arg]


def test_cancel_reason_min_length_5():
    # Pin: 4 chars rejected. Bound is tighter than create's 10-char
    # threshold because cancellations often legitimately just say
    # "重複" (duplicate) — but not single character.
    with pytest.raises(ValidationError):
        DocumentRequestCancel(cancellation_reason="重複")  # 2 chars


def test_cancel_reason_max_length_500():
    with pytest.raises(ValidationError):
        DocumentRequestCancel(cancellation_reason="x" * 501)


def test_cancel_reason_five_chars_inclusive():
    obj = DocumentRequestCancel(cancellation_reason="x" * 5)
    assert len(obj.cancellation_reason) == 5


# ─── DocumentRequestResponse ────────────────────────────────────────


def _resp_kwargs():
    return dict(
        id=1,
        application_id=42,
        requested_by_id=7,
        requested_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        requested_documents=["transcript"],
        reason="需要補充成績單以確認學業成績",
        status="pending",
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        updated_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )


def test_response_minimal_required_fields():
    # Pin: id / application_id / requested_by_id / requested_at /
    # requested_documents / reason / status / created_at / updated_at
    # — these 9 fields are the persisted record's anchor set. None can
    # become optional without DB-row-without-id risk.
    obj = DocumentRequestResponse(**_resp_kwargs())
    assert obj.id == 1
    assert obj.status == "pending"
    assert obj.notes is None  # default
    assert obj.fulfilled_at is None
    assert obj.cancelled_at is None


def test_response_from_attributes_enabled():
    # Pin: model_validate(orm_row) works.
    class _Row:
        def __init__(self):
            for k, v in _resp_kwargs().items():
                setattr(self, k, v)
            self.notes = None
            self.fulfilled_at = None
            self.deadline = None
            self.cancelled_at = None
            self.cancelled_by_id = None
            self.cancellation_reason = None
            self.requested_by_name = "Prof"
            self.cancelled_by_name = None
            self.application_app_id = "APP-113-1-00001"

    r = DocumentRequestResponse.model_validate(_Row())
    assert r.requested_by_name == "Prof"
    assert r.application_app_id == "APP-113-1-00001"


# ─── DocumentRequestListItem ────────────────────────────────────────


def test_list_item_omits_response_only_fields():
    # Pin: list item is intentionally lighter — no notes,
    # cancellation_reason, cancelled_by_id, cancelled_by_name,
    # updated_at. Don't widen silently; the list endpoint depends on
    # this surface area.
    fields = set(DocumentRequestListItem.model_fields.keys())
    assert "notes" not in fields
    assert "cancellation_reason" not in fields
    assert "cancelled_by_id" not in fields
    assert "updated_at" not in fields


# ─── StudentDocumentRequestResponse ─────────────────────────────────


def test_student_view_carries_scholarship_context():
    # Pin: the student-side view enriches the basic shape with
    # scholarship context (type name, academic year, semester). These
    # are the "where does this request come from?" anchor on the
    # student dashboard.
    fields = set(StudentDocumentRequestResponse.model_fields.keys())
    assert "scholarship_type_name" in fields
    assert "academic_year" in fields
    assert "semester" in fields
    assert "application_app_id" in fields
