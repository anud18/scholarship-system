"""Index the advisor-match columns and backfill orphaned professor assignments

Revision ID: advisor_backfill_idx_001
Revises: email_timing_three_triggers_001
Create Date: 2026-08-17 00:00:00.000000

A submitted application only gets `professor_id` when the advisor the student
named in `user_profiles.advisor_nycu_id` ALREADY exists as a role=professor
User (application_builder.assign_professor_from_profile). Applications naming an
advisor who had not yet signed in were stored with professor_id NULL and never
reached any review queue.

The code fix claims those rows on professor login and on every professor queue
load. This migration:

1. Backfills the rows that are already orphaned, so they surface immediately
   instead of waiting for their advisor's next login.
2. Adds the two indexes that lookup path needs — `user_profiles.advisor_nycu_id`
   (new hot column) and `applications.professor_id` (already filtered by every
   professor queue / stats query, never indexed because PostgreSQL does not
   auto-index foreign keys).

The row filter mirrors application_builder.backfill_professor_assignments:
statuses from PROFESSOR_ACTIONABLE_APPLICATION_STATUSES (app/models/enums.py)
and deleted_at IS NULL. Three exclusions, all deliberate:

- Drafts get their professor at submission time from the profile as it reads
  then.
- Already-decided applications (approved / partial_approved / rejected) would
  land in the professor's 待審核 bucket — which has no status gate — while the
  review endpoint refuses them, stranding the row with a permanent 403.
- Soft-deleted rows are never resurfaced.
- Configurations without a professor stage, or whose professor review window
  has closed, are skipped: the badge would count such a row while the list
  hides it, or the review endpoint would 403 it forever.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "advisor_backfill_idx_001"
down_revision: Union[str, None] = "email_timing_three_triggers_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APPLICATIONS_INDEX = "ix_applications_professor_id"
USER_PROFILES_INDEX = "ix_user_profiles_advisor_nycu_id"

# Kept in sync with PROFESSOR_ACTIONABLE_APPLICATION_STATUSES (app/models/enums.py).
ACTIONABLE_STATUSES = ("submitted", "under_review")

# The config predicate mirrors application_builder.backfill_professor_assignments:
# only claim on a configuration that HAS a professor stage for that application
# kind and whose professor review window has not closed (NULL bounds = no gate,
# exactly as ApplicationService.can_professor_submit_review treats them).
BACKFILL_SQL = """
    UPDATE applications AS a
    SET professor_id = u.id
    FROM user_profiles AS p
    JOIN users AS u
      ON u.nycu_id = p.advisor_nycu_id
     AND u.role = 'professor',
    scholarship_configurations AS c
    WHERE a.user_id = p.user_id
      AND c.id = a.scholarship_configuration_id
      AND a.professor_id IS NULL
      AND a.deleted_at IS NULL
      AND p.advisor_nycu_id IS NOT NULL
      AND p.advisor_nycu_id <> ''
      AND a.status::text IN :statuses
      AND (
            (
                a.is_renewal IS FALSE
                AND c.requires_professor_recommendation IS TRUE
                AND (
                    c.application_start_date IS NULL
                    OR c.professor_review_end IS NULL
                    OR c.professor_review_end >= NOW()
                )
            )
            OR (
                a.is_renewal IS TRUE
                AND c.renewal_requires_professor_review IS TRUE
                AND (
                    c.renewal_professor_review_start IS NULL
                    OR c.renewal_professor_review_end IS NULL
                    OR c.renewal_professor_review_end >= NOW()
                )
            )
      )
"""


def _index_names(inspector, table: str) -> set:
    return {idx["name"] for idx in inspector.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if {"applications", "user_profiles", "users", "scholarship_configurations"} <= tables:
        result = bind.execute(
            sa.text(BACKFILL_SQL).bindparams(sa.bindparam("statuses", expanding=True)),
            {"statuses": list(ACTIONABLE_STATUSES)},
        )
        print(f"[advisor_backfill_idx_001] assigned advisor to {result.rowcount} orphaned application(s)")

    if "applications" in tables and APPLICATIONS_INDEX not in _index_names(inspector, "applications"):
        op.create_index(APPLICATIONS_INDEX, "applications", ["professor_id"])

    if "user_profiles" in tables and USER_PROFILES_INDEX not in _index_names(inspector, "user_profiles"):
        op.create_index(USER_PROFILES_INDEX, "user_profiles", ["advisor_nycu_id"])


def downgrade() -> None:
    # Only the indexes are reversible. The backfilled professor_id values are
    # indistinguishable from assignments made at submission time, so clearing
    # them would destroy correct data — they are intentionally left in place.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "user_profiles" in tables and USER_PROFILES_INDEX in _index_names(inspector, "user_profiles"):
        op.drop_index(USER_PROFILES_INDEX, table_name="user_profiles")

    if "applications" in tables and APPLICATIONS_INDEX in _index_names(inspector, "applications"):
        op.drop_index(APPLICATIONS_INDEX, table_name="applications")
