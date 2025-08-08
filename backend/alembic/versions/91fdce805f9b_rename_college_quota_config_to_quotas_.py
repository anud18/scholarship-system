"""rename college_quota_config to quotas and remove quota_allocation_rules

Revision ID: 91fdce805f9b
Revises: 4f22265b1968
Create Date: 2025-08-08 09:38:06.270003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91fdce805f9b'
down_revision: Union[str, None] = '4f22265b1968'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass