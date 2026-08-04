"""Empty merge: collapse add_renewal_challenge_001 and merge_20260521_dual into single head.

add_renewal_challenge_001 branches from seed_phd_college_export_001.
merge_20260521_dual is the current main head (revoke/suspend + supplementary).
They touch disjoint tables so merge order is irrelevant for correctness.

No-op upgrade/downgrade — alembic just collapses the DAG.

Revision ID: merge_renewal_main_001
Revises: add_renewal_challenge_001, merge_20260521_dual
Create Date: 2026-05-21
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_renewal_main_001"
down_revision: Union[str, Sequence[str], None] = (
    "add_renewal_challenge_001",
    "merge_20260521_dual",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
