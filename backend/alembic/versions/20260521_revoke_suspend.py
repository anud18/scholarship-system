"""Add revoke/suspend metadata to applications + excel_stale flag to payment_rosters.

Spec: docs/superpowers/specs/2026-05-21-revoke-suspend-distribution-design.md

# Schema changes

`applications` — 6 new nullable columns capturing who/when/why an application
was revoked or suspended:
  - revoked_at, revoked_by (FK users), revoke_reason (text)
  - suspended_at, suspended_by (FK users), suspend_reason (text)

`payment_rosters` — 1 new boolean `excel_stale` (default False). Flipped True
when an admin removes an item from a LOCKED roster; cleared on Excel re-export.

# Safety

All `add_column` calls are wrapped in existence checks so the migration is
idempotent on partially-migrated databases (matches project convention —
see backend/CLAUDE.md "Alembic Migration Development Rules").

`quota_allocation_status` already accepts arbitrary strings (plain VARCHAR);
the new values `revoked`/`suspended` need no DDL.

Revision ID: revoke_suspend_001
Revises: email_tpl_scholar_type_001
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "revoke_suspend_001"
down_revision: Union[str, Sequence[str], None] = "email_tpl_scholar_type_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APPLICATION_COLUMNS = [
    ("revoked_at", sa.DateTime(timezone=True), True, None),
    ("revoked_by", sa.Integer(), True, "users.id"),
    ("revoke_reason", sa.Text(), True, None),
    ("suspended_at", sa.DateTime(timezone=True), True, None),
    ("suspended_by", sa.Integer(), True, "users.id"),
    ("suspend_reason", sa.Text(), True, None),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_app_cols = {c["name"] for c in inspector.get_columns("applications")}
    for name, coltype, nullable, fk in APPLICATION_COLUMNS:
        if name in existing_app_cols:
            continue
        kwargs = {"nullable": nullable}
        col = sa.Column(name, coltype, **kwargs)
        op.add_column("applications", col)
        if fk:
            # Create FK separately so the column add stays simple
            op.create_foreign_key(
                f"fk_applications_{name}_users",
                "applications",
                "users",
                [name],
                ["id"],
                ondelete="SET NULL",
            )

    existing_roster_cols = {c["name"] for c in inspector.get_columns("payment_rosters")}
    if "excel_stale" not in existing_roster_cols:
        op.add_column(
            "payment_rosters",
            sa.Column(
                "excel_stale",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_app_cols = {c["name"] for c in inspector.get_columns("applications")}
    for name, _coltype, _nullable, fk in APPLICATION_COLUMNS:
        if name not in existing_app_cols:
            continue
        if fk:
            # Best-effort: drop constraint by predictable name
            try:
                op.drop_constraint(f"fk_applications_{name}_users", "applications", type_="foreignkey")
            except Exception:
                pass
        op.drop_column("applications", name)

    existing_roster_cols = {c["name"] for c in inspector.get_columns("payment_rosters")}
    if "excel_stale" in existing_roster_cols:
        op.drop_column("payment_rosters", "excel_stale")
