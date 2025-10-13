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
    # Add html_body column (nullable for backward compatibility)
    op.add_column(
        "scheduled_emails",
        sa.Column(
            "html_body", sa.Text(), nullable=True, comment="Pre-rendered HTML from frontend (@react-email/render)"
        ),
    )


def downgrade() -> None:
    """Remove html_body column from scheduled_emails table"""
    op.drop_column("scheduled_emails", "html_body")
