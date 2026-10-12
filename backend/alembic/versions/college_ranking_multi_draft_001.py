"""Several draft college rankings per period, at most one finalized

Partially reverses college_ranking_single_001. A college may again keep several
DRAFT rankings per (scholarship_type, sub_type, academic_year, semester) to
compare them; 確認排名 (finalize) deletes the other drafts of that scope and no
new ranking can be created while the finalized one stays locked.

Steps:
1. Drop the full unique index uq_college_rankings_single_per_college (it would
   reject the second draft).
2. Create the partial unique index uq_college_rankings_finalized_per_college over
   the same key, limited to finalized rows (is_finalized IS TRUE), so two rankings
   of one scope can never both be locked. NULL semester (yearly) and NULL
   college_code (admin global ranking) are coalesced to sentinels, as before.
   A NEW name is used on purpose: the initial migration builds the schema with
   Base.metadata.create_all, so a fresh DB already carries whatever the model
   declares, and re-using the old name would make the existence check skip the
   drop on existing DBs.

No data change is needed: the old index guaranteed at most one ranking per scope,
so the partial index cannot be violated by existing rows.

Downgrade drops the partial index and re-creates the full unique index ONLY when
no scope holds more than one ranking. Otherwise it logs a warning and leaves the
old index absent — a downgrade never deletes a college's rankings.

Revision ID: college_ranking_multi_draft_001
Revises: college_ranking_single_001
Create Date: 2026-10-13
"""

import logging

import sqlalchemy as sa

from alembic import op

revision = "college_ranking_multi_draft_001"
down_revision = "college_ranking_single_001"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "college_rankings"
OLD_INDEX_NAME = "uq_college_rankings_single_per_college"
NEW_INDEX_NAME = "uq_college_rankings_finalized_per_college"

# Same key expressions as the model's Index and the old migration.
_SCOPE_KEY_SQL = (
    "scholarship_type_id, sub_type_code, academic_year, COALESCE(semester, 'yearly'), COALESCE(college_code, '')"
)

_SCOPES_WITH_SEVERAL_RANKINGS_SQL = f"""
    SELECT COUNT(*) FROM (
        SELECT 1
        FROM {TABLE}
        GROUP BY {_SCOPE_KEY_SQL}
        HAVING COUNT(*) > 1
    ) AS crowded_scopes
"""


def _scope_columns() -> list:
    return [
        "scholarship_type_id",
        "sub_type_code",
        "academic_year",
        sa.text("COALESCE(semester, 'yearly')"),
        sa.text("COALESCE(college_code, '')"),
    ]


def _existing_indexes(bind) -> set:
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return

    existing_indexes = _existing_indexes(bind)

    if OLD_INDEX_NAME in existing_indexes:
        op.drop_index(OLD_INDEX_NAME, table_name=TABLE)

    if NEW_INDEX_NAME not in existing_indexes:
        op.create_index(
            NEW_INDEX_NAME,
            TABLE,
            _scope_columns(),
            unique=True,
            postgresql_where=sa.text("is_finalized IS TRUE"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if TABLE not in sa.inspect(bind).get_table_names():
        return

    existing_indexes = _existing_indexes(bind)

    if NEW_INDEX_NAME in existing_indexes:
        op.drop_index(NEW_INDEX_NAME, table_name=TABLE)

    if OLD_INDEX_NAME in existing_indexes:
        return

    crowded_scopes = bind.execute(sa.text(_SCOPES_WITH_SEVERAL_RANKINGS_SQL)).scalar() or 0
    if crowded_scopes:
        logger.warning(
            "college_ranking_multi_draft_001 downgrade: %d ranking scope(s) hold more than one ranking; "
            "NOT re-creating %s (rankings are never deleted by a downgrade). Remove the extra drafts and "
            "create the index manually if the single-ranking rule is needed.",
            crowded_scopes,
            OLD_INDEX_NAME,
        )
        return

    op.create_index(OLD_INDEX_NAME, TABLE, _scope_columns(), unique=True)
