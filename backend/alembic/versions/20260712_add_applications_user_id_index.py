"""add index on applications.user_id FK

Revision ID: 20260712_app_user_idx
Revises: harden_enrollment_rule_001
Create Date: 2026-07-12

applications.user_id is a foreign key with no plain index. PostgreSQL does not
auto-index FKs, and the partial unique indexes leading with user_id
(uq_user_renewal_app / uq_user_challenge_app / uq_user_pure_new_app) cannot
serve arbitrary user_id lookups because of their WHERE predicates. Hot paths
probing applications by user_id include the student application list and the
admin student list's applied-scholarships aggregation / EXISTS filters.

The index is created idempotently (skipped if already present) so the
migration is safe to re-run on databases that already have it.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260712_app_user_idx"
down_revision: Union[str, Sequence[str], None] = "harden_enrollment_rule_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_USER_INDEX = "ix_applications_user_id"


def upgrade() -> None:
    """Create the applications.user_id index if it does not already exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "applications" in existing_tables:
        app_indexes = {i["name"] for i in inspector.get_indexes("applications")}
        if APP_USER_INDEX not in app_indexes:
            op.create_index(
                APP_USER_INDEX,
                "applications",
                ["user_id"],
                unique=False,
            )


def downgrade() -> None:
    """Drop the applications.user_id index if present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "applications" in existing_tables:
        app_indexes = {i["name"] for i in inspector.get_indexes("applications")}
        if APP_USER_INDEX in app_indexes:
            op.drop_index(APP_USER_INDEX, table_name="applications")
