"""
Tests for `EmailHistory` model on `app.models.email_management`.

Wave 6a18 covered ScheduledEmail state machine; wave 6a42 covered
EmailTestModeAudit factories; wave 6a53 covered email enum value
contracts. This wave fills the remaining EmailHistory surface:

  - **__repr__ format** (production log greps)
  - **__tablename__** (rollback scripts)
  - **__table_args__ index names** — 4 named indexes for query
    performance. Alembic migrations reference these by exact name;
    renaming silently leaves orphan indexes that consume disk.
  - **Column defaults**:
    * sent_by_system=True (system-sent is the default; manual
      sends must explicitly set False)
    * retry_count=0 (new history rows have zero retries)
    * status="sent" (history rows are recorded AFTER send attempt)

11 cases.
"""

from types import SimpleNamespace

from app.models.email_management import EmailHistory

# ─── __repr__ format ─────────────────────────────────────────────────


def test_email_history_repr_format():
    # Pin: repr includes id/recipient/status. Logs use this
    # exact format for attribution.
    stand_in = SimpleNamespace(id=42, recipient_email="test@nycu.edu.tw", status="sent")
    out = EmailHistory.__repr__(stand_in)
    assert "EmailHistory" in out
    assert "id=42" in out
    assert "recipient=test@nycu.edu.tw" in out
    assert "status=sent" in out


def test_email_history_repr_includes_failed_status():
    # Pin: repr works for ALL status values (verified via failed).
    stand_in = SimpleNamespace(id=99, recipient_email="x@y.com", status="failed")
    out = EmailHistory.__repr__(stand_in)
    assert "status=failed" in out


# ─── __tablename__ ──────────────────────────────────────────────────


def test_email_history_tablename():
    # Pin: __tablename__ matches production table — rollback /
    # data migration scripts query by name.
    assert EmailHistory.__tablename__ == "email_history"


# ─── __table_args__ index names ─────────────────────────────────────


def _index_names():
    return [c.name for c in EmailHistory.__table_args__ if hasattr(c, "name") and c.name]


def test_email_history_has_recipient_date_index():
    # Pin: idx_email_history_recipient_date — used by the per-
    # user email log query. Renaming orphans the index.
    assert "idx_email_history_recipient_date" in _index_names()


def test_email_history_has_category_date_index():
    # Pin: idx_email_history_category_date — used by the admin
    # email category filter UI.
    assert "idx_email_history_category_date" in _index_names()


def test_email_history_has_scholarship_date_index():
    # Pin: idx_email_history_scholarship_date — used by per-
    # scholarship email log queries.
    assert "idx_email_history_scholarship_date" in _index_names()


def test_email_history_has_status_date_index():
    # Pin: idx_email_history_status_date — used by the bounced/
    # failed email filter (admin retry workflow).
    assert "idx_email_history_status_date" in _index_names()


def test_email_history_has_four_indexes():
    # Pin: exactly 4 named indexes. Adding a 5th requires an
    # Alembic migration; this test ensures the count stays in
    # sync with the migration history.
    assert len(_index_names()) == 4


# ─── Column defaults ────────────────────────────────────────────────


def test_sent_by_system_default_is_true():
    # Pin: default sent_by_system=True (system-sent is the
    # default). Manual sends must explicitly set False — pinned
    # so a refactor flipping the default doesn't silently
    # misattribute every email.
    col = EmailHistory.__table__.c.sent_by_system
    assert col.default.arg is True


def test_retry_count_default_is_zero():
    # Pin: new history rows have zero retries.
    col = EmailHistory.__table__.c.retry_count
    assert col.default.arg == 0


def test_status_default_is_sent():
    # Pin: default status="sent". History rows are recorded
    # AFTER the send attempt; "sent" is the success-path default,
    # callers override on failure/bounce.
    col = EmailHistory.__table__.c.status
    assert col.default.arg == "sent"
