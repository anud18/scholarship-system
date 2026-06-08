"""shared quota pools — DROP dead columns (allocation_year, prior_quota_years)

Revision ID: 20260608_shared_quota_drop
Revises: 20260608_shared_quota_add
Create Date: 2026-06-08

MIGRATION 2 of 2 (destructive). Drops:
  - college_ranking_items.allocation_year   (superseded by allocation_config_id)
  - scholarship_configurations.prior_quota_years (superseded by shared_quota_sources)

ORDERING: this migration's APPLICATION must wait until every service, endpoint,
seed, and test stops reading the two dropped columns (later implementation
phases). The file ships now so the revision chain is complete; do not run it
against an environment whose code still reads allocation_year / prior_quota_years.

payment_rosters.allocation_year and payment_roster_items.allocation_year are
KEPT — repurposed as the denormalized display snapshot (= consumed config's
academic_year). They are intentionally NOT dropped here.

Existence-checked per project convention.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260608_shared_quota_drop"
down_revision: Union[str, Sequence[str], None] = "20260608_shared_quota_add"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cri_cols = [c["name"] for c in inspector.get_columns("college_ranking_items")]
    if "allocation_year" in cri_cols:
        op.drop_column("college_ranking_items", "allocation_year")

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "prior_quota_years" in sc_cols:
        op.drop_column("scholarship_configurations", "prior_quota_years")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cri_cols = [c["name"] for c in inspector.get_columns("college_ranking_items")]
    if "allocation_year" not in cri_cols:
        op.add_column("college_ranking_items", sa.Column("allocation_year", sa.Integer(), nullable=True))

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "prior_quota_years" not in sc_cols:
        op.add_column("scholarship_configurations", sa.Column("prior_quota_years", sa.JSON(), nullable=True))
