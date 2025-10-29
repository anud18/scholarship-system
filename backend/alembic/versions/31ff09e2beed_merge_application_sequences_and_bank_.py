"""merge_application_sequences_and_bank_removal

Revision ID: 31ff09e2beed
Revises: 6e466296a228, 6b5cb44d2fe3
Create Date: 2025-10-14 00:41:08.475179

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "31ff09e2beed"
down_revision: Union[str, None] = ("6e466296a228", "6b5cb44d2fe3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
