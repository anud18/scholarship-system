"""add_missing_system_settings_for_staging

Revision ID: be06a159931a
Revises: 5c2b79ec3cff
Create Date: 2025-10-26 14:01:16.270590

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "be06a159931a"
down_revision: Union[str, None] = "5c2b79ec3cff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add missing system settings that were not seeded in some environments.
    Uses ON CONFLICT DO NOTHING to safely skip if settings already exist.
    """
    op.execute(
        """
        INSERT INTO system_settings
        (key, value, category, data_type, is_sensitive, allow_empty, description, last_modified_by)
        VALUES
        ('gemini_api_key', '', 'api_keys', 'string', true, true, 'Google Gemini API 金鑰', 1),
        ('smtp_user', '', 'email', 'string', true, true, 'SMTP 使用者名稱', 1),
        ('smtp_password', '', 'email', 'string', true, true, 'SMTP 密碼', 1)
        ON CONFLICT (key) DO NOTHING;
        """
    )


def downgrade() -> None:
    """
    Remove the system settings added in upgrade.
    Only removes if they still have empty values (to avoid deleting user-configured settings).
    """
    op.execute(
        """
        DELETE FROM system_settings
        WHERE key IN ('gemini_api_key', 'smtp_user', 'smtp_password')
        AND value = '';
        """
    )
