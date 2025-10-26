"""update_gemini_api_key_category

Revision ID: 5c2b79ec3cff
Revises: 5b7fb81203ac
Create Date: 2025-10-26 05:32:35.750822

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c2b79ec3cff"
down_revision: Union[str, None] = "5b7fb81203ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update gemini_api_key category from 'ocr' to 'api_keys'"""
    # Update category for gemini_api_key
    op.execute(
        """
        UPDATE system_settings
        SET category = 'api_keys'
        WHERE key = 'gemini_api_key' AND category = 'ocr'
        """
    )


def downgrade() -> None:
    """Revert gemini_api_key category from 'api_keys' back to 'ocr'"""
    # Revert category for gemini_api_key
    op.execute(
        """
        UPDATE system_settings
        SET category = 'ocr'
        WHERE key = 'gemini_api_key' AND category = 'api_keys'
        """
    )
