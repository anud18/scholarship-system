"""add_email_automation_rules_table

Revision ID: d4198ecb46e2
Revises: 6ccdc349c2ea
Create Date: 2025-09-18 13:45:53.022651

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4198ecb46e2"
down_revision: Union[str, None] = "6ccdc349c2ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create email_automation_rules table
    op.create_table(
        "email_automation_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("trigger_event", sa.String(50), nullable=False),
        sa.Column("delay_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("condition_query", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["template_key"], ["email_templates.key"], ondelete="CASCADE"
        ),
    )

    # Create indexes for performance
    op.create_index(
        "idx_automation_rules_trigger",
        "email_automation_rules",
        ["trigger_event", "is_active"],
    )
    op.create_index(
        "idx_automation_rules_template", "email_automation_rules", ["template_key"]
    )


def downgrade() -> None:
    # Drop indexes first
    op.drop_index("idx_automation_rules_template", "email_automation_rules")
    op.drop_index("idx_automation_rules_trigger", "email_automation_rules")

    # Drop the table
    op.drop_table("email_automation_rules")
