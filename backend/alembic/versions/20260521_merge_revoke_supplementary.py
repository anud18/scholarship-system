"""Empty merge: collapse add_supplementary_import_001 and revoke_suspend_001 into single head.

Both add_supplementary_import_001 and revoke_suspend_001 branch from
email_tpl_scholar_type_001. They touch disjoint tables so the merge order
is irrelevant for correctness.

No-op upgrade/downgrade — alembic just collapses the DAG.

Revision ID: merge_20260521_revoke_supplementary
Revises: add_supplementary_import_001, revoke_suspend_001
Create Date: 2026-05-21
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_20260521_revoke_supplementary"
down_revision: Union[str, Sequence[str], None] = (
    "add_supplementary_import_001",
    "revoke_suspend_001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
