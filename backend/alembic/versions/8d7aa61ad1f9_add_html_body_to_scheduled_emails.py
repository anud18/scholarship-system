"""add_html_body_to_scheduled_emails

Revision ID: 8d7aa61ad1f9
Revises: 24f4d6ba449b
Create Date: 2025-10-13 13:19:34.370351

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8d7aa61ad1f9"
down_revision: Union[str, None] = "24f4d6ba449b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add html_body column to scheduled_emails table for storing pre-rendered HTML from frontend"""
    # Check if column already exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scheduled_emails")}

    # Only add column if it doesn't exist
    if "html_body" not in existing_columns:
        op.add_column(
            "scheduled_emails",
            sa.Column(
                "html_body", sa.Text(), nullable=True, comment="Pre-rendered HTML from frontend (@react-email/render)"
            ),
        )


def downgrade() -> None:
    """Remove html_body column from scheduled_emails table"""
    # Check if column exists before trying to drop it
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {col["name"] for col in inspector.get_columns("scheduled_emails")}

    if "html_body" in existing_columns:
        op.drop_column("scheduled_emails", "html_body")
