"""add item_restore to rosterauditaction enum

The 回復 (restore) feature writes RosterAuditLog(action=ITEM_RESTORE). The
Python enum gained ITEM_RESTORE = "item_restore", but the native PostgreSQL
enum type `rosterauditaction` (created in 5ee2f1e2708b with only item_add /
item_remove / item_update) was never altered — so inserting an ITEM_RESTORE
audit row raised `psycopg2.errors.InvalidTextRepresentation: invalid input
value for enum rosterauditaction: "item_restore"`. The unit suite runs on
SQLite (no enum constraint) so it could not catch this.

Revision ID: add_item_restore_audit_001
Revises: 20260531_perf_indexes
Create Date: 2026-06-08

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_item_restore_audit_001"
down_revision: Union[str, None] = "20260531_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL only supports ADDING enum values. IF NOT EXISTS makes this
    # idempotent (safe on a fresh DB where create_all already includes the
    # value, and on an existing DB that lacks it).
    op.execute("ALTER TYPE rosterauditaction ADD VALUE IF NOT EXISTS 'item_restore'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly; leave the
    # value in place (mirrors f333214c4735). No-op.
    pass
