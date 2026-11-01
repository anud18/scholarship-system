"""Add 多梯次申請 (additional application rounds)

Revision ID: application_rounds_001
Revises: blank_user_email_to_null_001
Create Date: 2026-10-19 00:00:00.000000

- scholarship_application_rounds: rounds 2..n of a configuration (window, open
  sub-types, optional per-round review windows). Round 1 stays the configuration's
  own application_start_date / application_end_date.
- scholarship_configurations.first_round_open_sub_types: the sub-types round 1 opens.
  NULL = every sub-type, so existing configurations keep accepting all of them.
- applications.application_round: the round an application was submitted in.
  Existing rows are round 1 (server default), so single-round data is unchanged.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "application_rounds_001"
down_revision: Union[str, None] = "blank_user_email_to_null_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROUNDS_TABLE = "scholarship_application_rounds"
CONFIGS_TABLE = "scholarship_configurations"
FIRST_ROUND_COLUMN = "first_round_open_sub_types"


def _columns(inspector, table: str) -> set:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if ROUNDS_TABLE not in tables:
        op.create_table(
            ROUNDS_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "configuration_id",
                sa.Integer(),
                sa.ForeignKey("scholarship_configurations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("round_number", sa.Integer(), nullable=False),
            sa.Column("application_start_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("application_end_date", sa.DateTime(timezone=True), nullable=False),
            sa.Column("open_sub_types", sa.JSON(), nullable=False),
            sa.Column("professor_review_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("professor_review_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("college_review_start", sa.DateTime(timezone=True), nullable=True),
            sa.Column("college_review_end", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.UniqueConstraint("configuration_id", "round_number", name="uq_application_round_config_number"),
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes(ROUNDS_TABLE)}
    for column in ("id", "configuration_id"):
        name = f"ix_{ROUNDS_TABLE}_{column}"
        if name not in indexes:
            op.create_index(name, ROUNDS_TABLE, [column])

    if "applications" in tables and "application_round" not in _columns(inspector, "applications"):
        op.add_column(
            "applications",
            sa.Column("application_round", sa.Integer(), nullable=False, server_default="1"),
        )

    if CONFIGS_TABLE in tables and FIRST_ROUND_COLUMN not in _columns(inspector, CONFIGS_TABLE):
        op.add_column(CONFIGS_TABLE, sa.Column(FIRST_ROUND_COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if CONFIGS_TABLE in tables and FIRST_ROUND_COLUMN in _columns(inspector, CONFIGS_TABLE):
        op.drop_column(CONFIGS_TABLE, FIRST_ROUND_COLUMN)

    if "applications" in tables and "application_round" in _columns(inspector, "applications"):
        op.drop_column("applications", "application_round")

    if ROUNDS_TABLE in tables:
        op.drop_table(ROUNDS_TABLE)
