"""Empty merge: collapse the two heads that diverged off 20260531_perf_indexes.

PR #918 (config-level shared quota pools) and the roster removed/restore/audit
feature both branched from ``20260531_perf_indexes``, producing two open heads:

- ``20260608_shared_quota_drop``   → shared_quota_sources on scholarship_configurations,
                                      drops the legacy prior_quota_years column
- ``add_item_restore_audit_001``   → soft-delete/restore + audit columns on
                                      payment_roster_items

The two touch disjoint tables, so the merge order is irrelevant for correctness.
No-op upgrade/downgrade — alembic just collapses the DAG into a single head.

Revision ID: merge_20260608_sq_audit
Revises: 20260608_shared_quota_drop, add_item_restore_audit_001
Create Date: 2026-06-08
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "merge_20260608_sq_audit"
down_revision: Union[str, Sequence[str], None] = (
    "20260608_shared_quota_drop",
    "add_item_restore_audit_001",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No schema change — this migration only collapses the DAG."""


def downgrade() -> None:
    """No-op: downgrading past the merge would re-expose the two-head state."""
