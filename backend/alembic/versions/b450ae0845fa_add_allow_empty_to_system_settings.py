"""add_allow_empty_to_system_settings

Revision ID: b450ae0845fa
Revises: 155ce2e54698
Create Date: 2025-10-04 17:41:41.273232

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b450ae0845fa"
down_revision: Union[str, None] = "691c27876bc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add allow_empty column to system_settings table"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("system_settings")}

    if "allow_empty" not in columns:
        op.add_column(
            "system_settings",
            sa.Column("allow_empty", sa.Boolean(), nullable=False, server_default="false"),
        )
        columns.add("allow_empty")

    if "allow_empty" in columns:
        # For string type configurations, set allow_empty to true by default
        op.execute(
            """
            UPDATE system_settings
            SET allow_empty = true
            WHERE data_type = 'string' AND is_sensitive = false
        """
        )

        # For sensitive configurations (API keys, SMTP credentials), allow empty to disable features
        # This includes: gemini_api_key, smtp_user, smtp_password, etc.
        op.execute(
            """
            UPDATE system_settings
            SET allow_empty = true
            WHERE is_sensitive = true
        """
        )


def downgrade() -> None:
    """Remove allow_empty column from system_settings table"""
    op.drop_column("system_settings", "allow_empty")
