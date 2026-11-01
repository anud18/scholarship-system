"""add open_sub_types to scholarship_configurations

Revision ID: config_open_sub_types_001
Revises: identity_labels_strip_nat_001
Create Date: 2026-11-02 00:00:00.000000

Admins reopen general applications per configuration and choose which
sub-types this opening accepts. NULL keeps every real sub-type open, so
existing rows need no backfill.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "config_open_sub_types_001"
down_revision: Union[str, None] = "identity_labels_strip_nat_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "scholarship_configurations"
COLUMN = "open_sub_types"


def _has_column() -> bool:
    inspector = sa.inspect(op.get_bind())
    if TABLE not in inspector.get_table_names():
        return False
    return COLUMN in [col["name"] for col in inspector.get_columns(TABLE)]


def upgrade() -> None:
    if not _has_column():
        op.add_column(TABLE, sa.Column(COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column():
        op.drop_column(TABLE, COLUMN)
