"""Add renewal review requirement flags to scholarship_configurations

Renewal applications previously inherited the general-application review
requirements (requires_professor_recommendation / requires_college_review).
Administrators now decide independently whether renewals need professor
and/or college review, so each renewal review window gets its own flag:

- renewal_requires_professor_review
- renewal_requires_college_review

Existing rows are backfilled from the general flags to preserve the
current behavior (renewal review dates were validated against the general
flags before this change).

Revision ID: add_renewal_review_flags_001
Revises: 20260712_app_user_idx
"""

import sqlalchemy as sa

from alembic import op

revision = "add_renewal_review_flags_001"
down_revision = "20260712_app_user_idx"
branch_labels = None
depends_on = None

TABLE = "scholarship_configurations"

COLUMNS = {
    "renewal_requires_professor_review": "requires_professor_recommendation",
    "renewal_requires_college_review": "requires_college_review",
}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    for new_column, source_column in COLUMNS.items():
        if new_column in existing_columns:
            continue
        op.add_column(
            TABLE,
            sa.Column(new_column, sa.Boolean(), nullable=False, server_default="false"),
        )
        # Preserve current behavior: renewal review requirement used to follow
        # the general-application flag.
        if source_column in existing_columns:
            op.execute(
                sa.text(f"UPDATE {TABLE} SET {new_column} = COALESCE({source_column}, false)")  # nosec B608
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if TABLE not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}

    for new_column in COLUMNS:
        if new_column in existing_columns:
            op.drop_column(TABLE, new_column)
