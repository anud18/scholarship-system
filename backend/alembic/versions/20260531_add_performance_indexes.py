"""add performance indexes: audit_logs resource lookup + applications config FK

Revision ID: 20260531_perf_indexes
Revises: 20260530_sched_email_nullable
Create Date: 2026-05-31

Two missing indexes that cause full-table scans on hot paths:

1. audit_logs has no index on (resource_type, resource_id, created_at). The
   per-entity audit-trail view filters resource_type + resource_id and orders by
   created_at desc on an ever-growing table -> sequential scan.

2. applications.scholarship_configuration_id is a foreign key with no index.
   PostgreSQL does not auto-index FKs, and roster_service filters heavily on it.

Both indexes are created idempotently (skipped if already present) so the
migration is safe to re-run on databases that already have them.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260531_perf_indexes"
down_revision: Union[str, Sequence[str], None] = "20260530_sched_email_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AUDIT_INDEX = "ix_audit_logs_resource_lookup"
APP_CONFIG_INDEX = "ix_applications_scholarship_configuration_id"


def upgrade() -> None:
    """Create the two performance indexes if they do not already exist."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "audit_logs" in existing_tables:
        audit_indexes = {i["name"] for i in inspector.get_indexes("audit_logs")}
        if AUDIT_INDEX not in audit_indexes:
            op.create_index(
                AUDIT_INDEX,
                "audit_logs",
                ["resource_type", "resource_id", "created_at"],
                unique=False,
            )

    if "applications" in existing_tables:
        app_indexes = {i["name"] for i in inspector.get_indexes("applications")}
        if APP_CONFIG_INDEX not in app_indexes:
            op.create_index(
                APP_CONFIG_INDEX,
                "applications",
                ["scholarship_configuration_id"],
                unique=False,
            )


def downgrade() -> None:
    """Drop the two performance indexes if present."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "applications" in existing_tables:
        app_indexes = {i["name"] for i in inspector.get_indexes("applications")}
        if APP_CONFIG_INDEX in app_indexes:
            op.drop_index(APP_CONFIG_INDEX, table_name="applications")

    if "audit_logs" in existing_tables:
        audit_indexes = {i["name"] for i in inspector.get_indexes("audit_logs")}
        if AUDIT_INDEX in audit_indexes:
            op.drop_index(AUDIT_INDEX, table_name="audit_logs")
