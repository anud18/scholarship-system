"""Add manual_distribution_history table for undo/redo tracking

Revision ID: add_distribution_history_001
Revises: add_allocation_year_001
Create Date: 2025-02-24 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "add_distribution_history_001"
down_revision = "add_allocation_year_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add manual_distribution_history table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Only create if table doesn't exist
    if "manual_distribution_history" not in existing_tables:
        op.create_table(
            "manual_distribution_history",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("scholarship_type_id", sa.Integer(), nullable=False),
            sa.Column("academic_year", sa.Integer(), nullable=False),
            sa.Column("semester", sa.String(20), nullable=False),
            sa.Column("allocations_snapshot", postgresql.JSONB(), nullable=False),
            sa.Column("operation_type", sa.String(50), nullable=False),
            sa.Column("change_summary", sa.Text(), nullable=True),
            sa.Column("total_allocated", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["scholarship_type_id"], ["scholarship_types.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_manual_distribution_history_id",
            "manual_distribution_history",
            ["id"],
        )
        op.create_index(
            "ix_manual_distribution_history_lookup",
            "manual_distribution_history",
            [
                "scholarship_type_id",
                "academic_year",
                "semester",
                "created_at",
            ],
        )


def downgrade() -> None:
    """Drop manual_distribution_history table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if "manual_distribution_history" in existing_tables:
        op.drop_index("ix_manual_distribution_history_lookup")
        op.drop_index("ix_manual_distribution_history_id")
        op.drop_table("manual_distribution_history")
