"""Snapshot the pre-cancellation state on applications (撤銷/停發 → 復原).

撤銷 (revoke) / 停發 (suspend) are no longer restricted to already-distributed
students: an admin must be able to mark a student who 休學/退學/畢業 between
學院排序 and 確認分發 so the distribution skips them. Restoring such a student
must NOT put them into approved/allocated — it has to put them back exactly
where they were.

`applications` — 2 new nullable columns holding that snapshot:
  - cancelled_from_status        (the ApplicationStatus value before the cancel)
  - cancelled_from_quota_status  (the quota_allocation_status before the cancel)

Both are cleared by `restore_allocation`. Rows revoked/suspended before this
migration carry NULL, which the service reads as "was allocated" — correct by
construction, since that was the only state a cancel could start from.

# Safety

Both `add_column` calls are wrapped in existence checks so the migration is
idempotent on partially-migrated databases (matches project convention — see
backend/CLAUDE.md "Alembic Migration Development Rules").

Revision ID: cancel_prior_state_001
Revises: add_appfile_idx_001
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "cancel_prior_state_001"
down_revision = "add_appfile_idx_001"
branch_labels = None
depends_on = None

COLUMNS = [
    ("cancelled_from_status", sa.String(length=30)),
    ("cancelled_from_quota_status", sa.String(length=20)),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "applications" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("applications")}
    for name, coltype in COLUMNS:
        if name not in existing:
            op.add_column("applications", sa.Column(name, coltype, nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "applications" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("applications")}
    for name, _coltype in COLUMNS:
        if name in existing:
            op.drop_column("applications", name)
