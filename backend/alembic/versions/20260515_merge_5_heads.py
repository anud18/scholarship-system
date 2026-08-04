"""Empty merge: collapse the 5 unmerged alembic heads into a single head.

The migration graph had drifted to 5 open heads, which makes
``alembic upgrade head`` and ``./scripts/reset_database.sh`` ambiguous
and blocks any new schema change from landing without compounding the
branch count. See issue #668.

The 5 heads are independent — they touch disjoint tables, so the merge
order is irrelevant for correctness:

- ``add_college_rejected_001``        → adds column to ``college_ranking_items``
- ``add_renewal_year_001``            → adds column to ``applications``
- ``add_roster_sub_type_001``         → adds columns to ``payment_rosters`` + ``scholarship_configurations``
- ``20260513_doc_req_deadline``       → adds column to ``document_requests``
- ``seed_phd_college_export_001``     → data-only seed (no schema changes)

No-op upgrade/downgrade — alembic just collapses the DAG.

Revision ID: merge_20260515_heads
Revises: add_college_rejected_001, add_renewal_year_001, add_roster_sub_type_001, 20260513_doc_req_deadline, seed_phd_college_export_001
Create Date: 2026-05-15
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_20260515_heads"
down_revision: Union[str, Sequence[str], None] = (
    "add_college_rejected_001",
    "add_renewal_year_001",
    "add_roster_sub_type_001",
    "20260513_doc_req_deadline",
    "seed_phd_college_export_001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No schema change — this migration only collapses the DAG."""


def downgrade() -> None:
    """No-op: downgrading past the merge would re-expose the 5-head state."""
