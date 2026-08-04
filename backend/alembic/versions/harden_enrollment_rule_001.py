"""Make the 在學生身分 (trm_studystatus) rules hard (#1139)

The PhD / direct-PhD "active student status" rule (trm_studystatus in 1,2,3)
was seeded as a soft rule. Soft non-warning failures are silently swallowed
by both the batch-import eligibility precheck and the roster eligibility
gate, so 休學/退學 students flowed to payment rosters with no flag anywhere.
Seed data is fixed alongside this migration; this backfills existing DBs.

Revision ID: harden_enrollment_rule_001
Revises: align_academy_names_001
"""

import sqlalchemy as sa

from alembic import op

revision = "harden_enrollment_rule_001"
down_revision = "align_academy_names_001"
branch_labels = None
depends_on = None

TABLE = "scholarship_rules"

_WHERE = "condition_field = 'trm_studystatus' AND rule_name LIKE '%在學生身分%'"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    bind.execute(sa.text(f"UPDATE {TABLE} SET is_hard_rule = true WHERE {_WHERE}"))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    bind.execute(sa.text(f"UPDATE {TABLE} SET is_hard_rule = false WHERE {_WHERE}"))
