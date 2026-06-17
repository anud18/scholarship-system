"""Add college_code to college_rankings (per-college ranking scoping, issue #1034)

Rankings are scoped per (scholarship_type, sub_type, academic_year, semester, college).
This adds an explicit college_code column so create/list scope by college instead of by
created_by — fixing the case where multiple reviewers of one college (or one college
colliding with another) produced wrong/duplicate rankings.

Revision ID: college_ranking_college_code_001
Revises: audit_logs_immutability_001
Create Date: 2026-06-17
"""

import sqlalchemy as sa
from alembic import op

revision = "college_ranking_college_code_001"
down_revision = "audit_logs_immutability_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "college_rankings" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("college_rankings")}
    if "college_code" not in columns:
        op.add_column("college_rankings", sa.Column("college_code", sa.String(length=10), nullable=True))

    # Backfill from the creator's college so existing rankings keep working under the
    # new college-scoped lookups.
    op.execute("""
        UPDATE college_rankings cr
        SET college_code = u.college_code
        FROM users u
        WHERE u.id = cr.created_by
          AND cr.college_code IS NULL
          AND u.college_code IS NOT NULL
        """)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("college_rankings")}
    if "ix_college_rankings_college_code" not in existing_indexes:
        op.create_index("ix_college_rankings_college_code", "college_rankings", ["college_code"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "college_rankings" not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("college_rankings")}
    if "ix_college_rankings_college_code" in existing_indexes:
        op.drop_index("ix_college_rankings_college_code", table_name="college_rankings")

    columns = {col["name"] for col in inspector.get_columns("college_rankings")}
    if "college_code" in columns:
        op.drop_column("college_rankings", "college_code")
