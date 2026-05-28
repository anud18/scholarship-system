"""merge backfill_roster_national_id + add_supp_docs_001 heads

Revision ID: 20260529_merge_roster_supp_docs
Revises: 20260529_backfill_roster_national_id, add_supp_docs_001
"""

from __future__ import annotations

from typing import Sequence, Union

revision: str = "20260529_merge_roster_supp_docs"
down_revision: Union[str, Sequence[str], None] = (
    "20260529_backfill_roster_national_id",
    "add_supp_docs_001",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
