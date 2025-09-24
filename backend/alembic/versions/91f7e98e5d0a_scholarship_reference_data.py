"""Scholarship reference data

Revision ID: 91f7e98e5d0a
Revises: 4f0a9ad1219f
Create Date: 2025-09-24 20:28:34.442308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91f7e98e5d0a'
down_revision: Union[str, None] = '4f0a9ad1219f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Scholarship data is handled by seed script (app/seed.py)
    #
    # Rationale:
    # - Scholarship data is environment-specific (dev vs prod)
    # - Complex rules and configurations are better suited for seed scripts
    # - Allows for easier testing and modification
    #
    # See app/seed.py:
    # - seed_scholarships() for scholarship types
    # - seed_application_fields() for field configurations
    pass


def downgrade() -> None:
    # No-op: Scholarship data is managed by seed script
    pass