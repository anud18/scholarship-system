"""add prior_quota_years to scholarship_configurations

Revision ID: add_prior_quota_years_001
Revises: add_roster_sub_type_001
Create Date: 2026-03-08

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_prior_quota_years_001"
down_revision: Union[str, None] = "add_roster_sub_type_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("scholarship_configurations")]

    if "prior_quota_years" not in existing_columns:
        op.add_column(
            "scholarship_configurations",
            sa.Column("prior_quota_years", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("scholarship_configurations")]

    if "prior_quota_years" in existing_columns:
        op.drop_column("scholarship_configurations", "prior_quota_years")
