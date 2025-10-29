"""add_document_requests_table

Revision ID: e532ef9a7342
Revises: 3e2ed9878cad
Create Date: 2025-10-11 02:50:38.964741

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e532ef9a7342"
down_revision: Union[str, None] = "3e2ed9878cad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table already exists before creating it
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "document_requests" not in existing_tables:
        # Create document_requests table
        # Use VARCHAR with CHECK constraint instead of ENUM to avoid conflicts
        op.create_table(
            "document_requests",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("requested_by_id", sa.Integer(), nullable=False),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("requested_documents", sa.dialects.postgresql.JSONB(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancelled_by_id", sa.Integer(), nullable=True),
            sa.Column("cancellation_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.CheckConstraint("status IN ('pending', 'fulfilled', 'cancelled')", name="ck_document_request_status"),
        )

        # Create indexes
        op.create_index("ix_document_requests_application_id", "document_requests", ["application_id"])
        op.create_index("ix_document_requests_status", "document_requests", ["status"])
        op.create_index("ix_document_requests_id", "document_requests", ["id"])

        # Create foreign key constraints
        op.create_foreign_key(
            "fk_document_requests_application_id", "document_requests", "applications", ["application_id"], ["id"]
        )
        op.create_foreign_key(
            "fk_document_requests_requested_by_id", "document_requests", "users", ["requested_by_id"], ["id"]
        )
        op.create_foreign_key(
            "fk_document_requests_cancelled_by_id", "document_requests", "users", ["cancelled_by_id"], ["id"]
        )


def downgrade() -> None:
    # Check if table exists before dropping it
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "document_requests" in existing_tables:
        # Drop foreign key constraints
        op.drop_constraint("fk_document_requests_cancelled_by_id", "document_requests", type_="foreignkey")
        op.drop_constraint("fk_document_requests_requested_by_id", "document_requests", type_="foreignkey")
        op.drop_constraint("fk_document_requests_application_id", "document_requests", type_="foreignkey")

        # Drop indexes
        op.drop_index("ix_document_requests_id", table_name="document_requests")
        op.drop_index("ix_document_requests_status", table_name="document_requests")
        op.drop_index("ix_document_requests_application_id", table_name="document_requests")

        # Drop table
        op.drop_table("document_requests")
