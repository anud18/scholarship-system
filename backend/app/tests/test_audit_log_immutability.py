"""G4 (#966): audit_logs is append-only — UPDATE/DELETE must be refused.

Two enforcement layers, two test surfaces:

- ORM listeners (app/models/audit_log.py) — backend-agnostic, exercised here
  against the test DB: flushing an UPDATE or DELETE of an AuditLog row must
  raise AuditLogImmutableError and leave the row intact.
- PostgreSQL trigger (migration audit_logs_immutability_001) — the test DB
  is created from metadata (no alembic), so the trigger itself can't run
  here; its DDL contract is pinned statically instead (UPDATE blocked
  unconditionally, DELETE only via the sanctioned `app.audit_purge` GUC).
"""

import pathlib

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditLog, AuditLogImmutableError
from app.models.user import User, UserRole, UserType

pytestmark = pytest.mark.integration

MIGRATION = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "audit_logs_immutability_001.py"


async def _make_log(db) -> AuditLog:
    user = User(
        nycu_id="g4actor",
        name="G4 Actor",
        email="g4actor@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()
    row = AuditLog.create_log(
        user_id=user.id,
        action="create",
        resource_type="application",
        resource_id="424242",
        description="G4 immutability fixture",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def test_orm_update_is_refused_and_row_unchanged(db):
    row = await _make_log(db)
    row_id, original = row.id, row.description

    row.description = "tampered"
    with pytest.raises(AuditLogImmutableError):
        await db.commit()
    await db.rollback()

    res = await db.execute(select(AuditLog).where(AuditLog.id == row_id))
    persisted = res.scalar_one()
    assert persisted.description == original


async def test_orm_delete_is_refused_and_row_survives(db):
    row = await _make_log(db)
    row_id = row.id

    await db.delete(row)
    with pytest.raises(AuditLogImmutableError):
        await db.commit()
    await db.rollback()

    res = await db.execute(select(AuditLog).where(AuditLog.id == row_id))
    assert res.scalar_one_or_none() is not None


async def test_inserts_still_work(db):
    row = await _make_log(db)
    assert row.id is not None


# ── Static contract of the DB-level trigger ─────────────────────────────


def test_migration_defines_append_only_trigger():
    text = MIGRATION.read_text()
    assert "BEFORE UPDATE OR DELETE ON audit_logs" in text
    assert "audit_logs_block_mutation" in text
    # The sanctioned-destruction escape hatch exists for DELETE only.
    assert "app.audit_purge" in text
    assert "TG_OP = 'DELETE'" in text


def test_orm_listeners_are_registered():
    from sqlalchemy import event

    from app.models import audit_log as m

    assert event.contains(AuditLog, "before_update", m._audit_log_block_update)
    assert event.contains(AuditLog, "before_delete", m._audit_log_block_delete)
