"""add_gemini_query_delay_setting

Revision ID: 94e544932d78
Revises: be06a159931a
Create Date: 2025-10-26 18:16:11.316060

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "94e544932d78"
down_revision: Union[str, None] = "be06a159931a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add gemini_query_delay system setting for rate limiting Gemini API queries.
    Uses ON CONFLICT DO NOTHING to safely skip if setting already exists.
    Sets last_modified_by to NULL to avoid foreign key constraint issues in fresh databases.
    """
    op.execute(
        """
        INSERT INTO system_settings
        (key, value, category, data_type, is_sensitive, is_readonly, allow_empty, description, last_modified_by)
        VALUES
        ('gemini_query_delay', '5.0', 'ocr', 'float', false, false, false, 'Gemini API 查詢間隔（秒）- 避免超過流量限制', NULL)
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    """
    Remove the gemini_query_delay system setting added in upgrade.
    Only removes if it still has the default value (to avoid deleting user-configured settings).
    """
    op.execute(
        """
        DELETE FROM system_settings
        WHERE key = 'gemini_query_delay'
        AND value = '5.0';
        """
    )
