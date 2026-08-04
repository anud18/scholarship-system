"""make scheduled_emails.created_by_user_id nullable

Revision ID: 20260530_sched_email_nullable
Revises: 20260529_merge_roster_supp_docs
Create Date: 2026-05-30

Automated/system-scheduled emails (e.g. dispatched by EmailAutomationService
and other background flows) do not always have an acting user. The original
NOT NULL constraint forced callers to fabricate or look up a user ID, which
breaks the schedule path with an IntegrityError. Relax to NULL so the column
records "who scheduled this" only when known.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260530_sched_email_nullable"
down_revision: Union[str, Sequence[str], None] = "20260529_merge_roster_supp_docs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make scheduled_emails.created_by_user_id nullable (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()
    if "scheduled_emails" not in existing_tables:
        # Nothing to do if the table does not exist (fresh test DBs etc.)
        return

    cols = {c["name"]: c for c in inspector.get_columns("scheduled_emails")}
    target = cols.get("created_by_user_id")
    if target is None:
        return

    if target.get("nullable") is True:
        # Already nullable — idempotent no-op.
        return

    # Use batch_alter_table so this also works on SQLite-backed test DBs,
    # which cannot ALTER COLUMN in place.
    with op.batch_alter_table("scheduled_emails") as batch_op:
        batch_op.alter_column(
            "created_by_user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    """Restore NOT NULL on scheduled_emails.created_by_user_id.

    This is a non-reversible-by-default change: any rows inserted with NULL
    after the upgrade would block a straightforward NOT NULL restoration.
    Operators choosing to downgrade must first backfill or delete those rows
    out-of-band (e.g. with a one-off SQL statement) before running this.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = inspector.get_table_names()
    if "scheduled_emails" not in existing_tables:
        return

    cols = {c["name"]: c for c in inspector.get_columns("scheduled_emails")}
    target = cols.get("created_by_user_id")
    if target is None:
        return

    if target.get("nullable") is False:
        return

    with op.batch_alter_table("scheduled_emails") as batch_op:
        batch_op.alter_column(
            "created_by_user_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
