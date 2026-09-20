"""Empty merge: collapse remove_academy_8_001 and roster_owner_alloc_cfg_001 into a single head.

`roster_owner_alloc_cfg_001` (this branch's roster-ownership work) branches from
`drop_nstc_subtype_desc_001`, while `remove_academy_8_001` sits at the tip of the
chain this branch picked up from main. Two heads make `alembic upgrade head` — what
`scripts/reset_database.sh` and every CI workflow run — fail outright, so collapse
them. They touch disjoint tables (academies vs payment rosters), so the merge order
is irrelevant for correctness.

No-op upgrade/downgrade — alembic just collapses the DAG.

Revision ID: merge_20260921_dual
Revises: remove_academy_8_001, roster_owner_alloc_cfg_001
Create Date: 2026-09-21
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_20260921_dual"
down_revision: Union[str, Sequence[str], None] = (
    "remove_academy_8_001",
    "roster_owner_alloc_cfg_001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
