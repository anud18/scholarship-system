"""One ranking per college per period (college_rankings unique index)

A college may hold only ONE ranking per (scholarship_type, sub_type, academic_year,
semester). Previously 「建立新排名」 could stack several rankings for the same college
and the reviewer picked which one to finalize; now the single ranking is the one
that gets sent.

Steps:
1. Collapse existing duplicates. Per key group keep, in priority order, the
   ranking whose distribution was executed (its items carry the live allocation
   state rosters join on — an unfinalize does not clear that flag), else the
   finalized one, else the newest (highest id). Payment rosters that pointed at a
   dropped duplicate are re-pointed to the survivor (same college / scholarship /
   period); the duplicates' items and rows are deleted.
2. Create the unique index uq_college_rankings_single_per_college over the key,
   coalescing NULL semester (yearly) and NULL college_code (admin global ranking)
   so NULLs cannot bypass uniqueness.

Revision ID: college_ranking_single_001
Revises: align_academy_names_003
Create Date: 2026-09-16
"""

import logging

import sqlalchemy as sa
from alembic import op

revision = "college_ranking_single_001"
down_revision = "align_academy_names_003"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

INDEX_NAME = "uq_college_rankings_single_per_college"

# Ranks every ranking inside its key group; rn = 1 is the survivor.
_RANKED_DUPLICATES_CTE = """
    WITH ranked AS (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY scholarship_type_id,
                                sub_type_code,
                                academic_year,
                                COALESCE(semester, 'yearly'),
                                COALESCE(college_code, '')
                   ORDER BY distribution_executed DESC NULLS LAST,
                            is_finalized DESC NULLS LAST,
                            id DESC
               ) AS rn,
               FIRST_VALUE(id) OVER (
                   PARTITION BY scholarship_type_id,
                                sub_type_code,
                                academic_year,
                                COALESCE(semester, 'yearly'),
                                COALESCE(college_code, '')
                   ORDER BY distribution_executed DESC NULLS LAST,
                            is_finalized DESC NULLS LAST,
                            id DESC
               ) AS keeper_id
        FROM college_rankings
    )
"""


def _collapse_duplicates(bind) -> None:
    duplicates = bind.execute(
        sa.text(_RANKED_DUPLICATES_CTE + "SELECT id, keeper_id FROM ranked WHERE rn > 1")
    ).fetchall()
    if not duplicates:
        return

    logger.info("college_ranking_single_001: collapsing %d duplicate college rankings", len(duplicates))
    for duplicate_id, keeper_id in duplicates:
        bind.execute(
            sa.text("UPDATE payment_rosters SET ranking_id = :keeper WHERE ranking_id = :dup"),
            {"keeper": keeper_id, "dup": duplicate_id},
        )
        bind.execute(
            sa.text("DELETE FROM college_ranking_items WHERE ranking_id = :dup"),
            {"dup": duplicate_id},
        )
        bind.execute(sa.text("DELETE FROM college_rankings WHERE id = :dup"), {"dup": duplicate_id})


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "college_rankings" not in inspector.get_table_names():
        return

    _collapse_duplicates(bind)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("college_rankings")}
    if INDEX_NAME not in existing_indexes:
        op.create_index(
            INDEX_NAME,
            "college_rankings",
            [
                "scholarship_type_id",
                "sub_type_code",
                "academic_year",
                sa.text("COALESCE(semester, 'yearly')"),
                sa.text("COALESCE(college_code, '')"),
            ],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "college_rankings" not in inspector.get_table_names():
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("college_rankings")}
    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name="college_rankings")
