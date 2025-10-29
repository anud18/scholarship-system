"""add bank_verification_tasks table

Creates bank_verification_tasks table for tracking async batch verification tasks.
This table stores task progress, results, and status for batch bank verification operations.

Revision ID: 20251028_add_verification_tasks
Revises: 20251028_add_passbook_cover
Create Date: 2025-10-28 21:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_add_verification_tasks"
down_revision: Union[str, None] = "20251028_add_passbook_cover"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create bank_verification_tasks table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table already exists
    existing_tables = inspector.get_table_names()
    if "bank_verification_tasks" in existing_tables:
        print("bank_verification_tasks table already exists, skipping")
        return

    # Create enum type for task status
    task_status_enum = sa.Enum(
        "pending",
        "processing",
        "completed",
        "failed",
        "cancelled",
        name="bankverificationtaskstatus",
        create_type=True,
    )

    # Create bank_verification_tasks table
    op.create_table(
        "bank_verification_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            task_status_enum,
            nullable=False,
            server_default="pending",
        ),
        # Target applications (stored as JSON array)
        sa.Column("application_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        # Progress counters
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("needs_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        # Detailed results (stored as JSON)
        sa.Column("results", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        # Task metadata
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        # Constraints
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", name="uq_bank_verification_task_task_id"),
    )

    # Create indexes
    op.create_index("ix_bank_verification_tasks_id", "bank_verification_tasks", ["id"])
    op.create_index("ix_bank_verification_tasks_task_id", "bank_verification_tasks", ["task_id"])
    op.create_index("ix_bank_verification_tasks_status", "bank_verification_tasks", ["status"])
    op.create_index("ix_bank_verification_tasks_created_by_user_id", "bank_verification_tasks", ["created_by_user_id"])


def downgrade() -> None:
    """Drop bank_verification_tasks table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists
    existing_tables = inspector.get_table_names()
    if "bank_verification_tasks" not in existing_tables:
        return

    # Drop indexes
    op.drop_index("ix_bank_verification_tasks_created_by_user_id", table_name="bank_verification_tasks")
    op.drop_index("ix_bank_verification_tasks_status", table_name="bank_verification_tasks")
    op.drop_index("ix_bank_verification_tasks_task_id", table_name="bank_verification_tasks")
    op.drop_index("ix_bank_verification_tasks_id", table_name="bank_verification_tasks")

    # Drop table
    op.drop_table("bank_verification_tasks")

    # Drop enum type
    sa.Enum(name="bankverificationtaskstatus").drop(bind, checkfirst=True)
