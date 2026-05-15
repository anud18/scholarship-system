"""
Tests for two previously-untested SQLAlchemy models:

  - **DocumentRequestStatus** + **DocumentRequest.__repr__**
    (app.models.document_request)

  - **StudentBankAccount.__repr__** + table-args invariants
    (app.models.student_bank_account)

These models are largely declarative (columns + relationships), but
two pinned surfaces matter:

  1. **DocumentRequestStatus enum values** — the wire-shape contract
     per CLAUDE.md §4. The column is String(20) with CHECK constraint
     (not Enum type), so the values stored MUST exactly match these
     strings. A regression renaming or adding a value breaks the
     CHECK constraint silently in migrations.

  2. **__repr__ formatting** — pinned because debug logs / Sentry
     payloads / pytest fixtures all rely on the repr text for
     attribution. Changing the format is technically free but
     scattered greps across logs would break.

  3. **UniqueConstraint name** — referenced by Alembic migrations
     by exact name. Renaming silently leaves orphaned constraints.

11 cases.
"""

from types import SimpleNamespace

import pytest

from app.models.document_request import DocumentRequest, DocumentRequestStatus
from app.models.student_bank_account import StudentBankAccount

# ─── DocumentRequestStatus enum ──────────────────────────────────────


def test_document_request_status_has_three_values():
    # Pin: exactly 3 statuses. Adding a fourth requires updating
    # the migration CHECK constraint AND the admin UI dropdown.
    assert {s.value for s in DocumentRequestStatus} == {
        "pending",
        "fulfilled",
        "cancelled",
    }


def test_document_request_status_pending_value():
    # Pin: lowercase value "pending" per CLAUDE.md §4 wire shape.
    assert DocumentRequestStatus.pending.value == "pending"


def test_document_request_status_fulfilled_value():
    assert DocumentRequestStatus.fulfilled.value == "fulfilled"


def test_document_request_status_cancelled_value():
    # Pin: British spelling "cancelled" (not "canceled"). Match
    # exists in migration CHECK constraint; renaming to American
    # spelling would silently break the constraint.
    assert DocumentRequestStatus.cancelled.value == "cancelled"


def test_document_request_status_member_names_match_values():
    # Pin: member name == value (lowercase). Per CLAUDE.md §4
    # Python enum member names must match DB values.
    for member in DocumentRequestStatus:
        assert member.name == member.value


# ─── DocumentRequest.__repr__ ────────────────────────────────────────


def test_document_request_repr_format():
    # Pin: repr format used in log statements + Sentry payloads.
    # The exact format is the contract — production grepping
    # depends on it. Bypass SQLAlchemy instrumented attributes
    # by invoking the unbound method against a duck-typed stand-in.
    stand_in = SimpleNamespace(id=42, application_id=7, status="pending")
    out = DocumentRequest.__repr__(stand_in)
    assert "DocumentRequest" in out
    assert "id=42" in out
    assert "application_id=7" in out
    assert "status=pending" in out


# ─── StudentBankAccount ──────────────────────────────────────────────


def test_student_bank_account_repr_format():
    # Pin: repr includes id / user_id / account_number / status.
    # When debugging a verification flow, an admin reads this
    # string from logs — pinned format. Invoke unbound method on
    # a duck-typed stand-in to bypass SQLAlchemy instrumentation.
    stand_in = SimpleNamespace(id=5, user_id=10, account_number="12345-67890", verification_status="verified")
    out = StudentBankAccount.__repr__(stand_in)
    assert "StudentBankAccount" in out
    assert "id=5" in out
    assert "user_id=10" in out
    assert "account_number=12345-67890" in out
    assert "status=verified" in out


def test_student_bank_account_unique_constraint_name():
    # Pin: the UniqueConstraint name is referenced by Alembic
    # migrations. Renaming silently leaves orphan constraints in
    # the migration history.
    constraint_names = [c.name for c in StudentBankAccount.__table_args__ if hasattr(c, "name")]
    assert "uq_student_bank_account_user_number" in constraint_names


def test_student_bank_account_tablename():
    # Pin: __tablename__ matches the production table name. Migration
    # rollback / data migration scripts query by name.
    assert StudentBankAccount.__tablename__ == "student_bank_accounts"


def test_document_request_tablename():
    # Pin: __tablename__ matches production table.
    assert DocumentRequest.__tablename__ == "document_requests"


def test_document_request_status_default_is_pending():
    # Pin: default value for new requests is "pending". This is
    # documented in the SQLAlchemy column default — pin so a
    # refactor that flips the default (e.g., to "fulfilled") is
    # caught.
    col = DocumentRequest.__table__.c.status
    assert col.default.arg == "pending"


def test_student_bank_account_verification_status_default():
    # Pin: default verification_status is "verified" — admin-
    # verified accounts are the primary write path.
    col = StudentBankAccount.__table__.c.verification_status
    assert col.default.arg == "verified"
