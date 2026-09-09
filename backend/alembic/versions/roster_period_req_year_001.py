"""relabel distribution rosters' period_label to the requesting academic year

Revision ID: roster_period_req_year_001
Revises: drop_nstc_subtype_desc_001
Create Date: 2026-09-09 00:00:00.000000

generate_rosters_from_distribution used to key period_label on the CONSUMED
config's academic year: a 115 renewal (or a 115 新申請 paid out of a
borrowed 114 slot) landed in a roster labelled "114" under the 115 config.
That row matched no schedule period, so the 造冊列表 showed no 造冊期間 for it,
and its Excel 說明 read 期間:114 although the money is the 115-09~116-08 award.

The period is now the requesting config's academic year (allocation_year
still records which year's slot was consumed). Bring the already-generated
rows in line. The unique key is
(scholarship_configuration_id, period_label, COALESCE(allocation_year,-1),
COALESCE(sub_type,'')); the generator derived the old label from
allocation_config_id, so no two rows of one config can collide after the
relabel — the NOT EXISTS guard is belt-and-braces only.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "roster_period_req_year_001"
down_revision: Union[str, Sequence[str], None] = "drop_nstc_subtype_desc_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE payment_rosters AS pr
        SET period_label = pr.academic_year::text
        WHERE pr.roster_cycle = 'yearly'
          AND pr.allocation_config_id IS NOT NULL
          AND pr.period_label <> pr.academic_year::text
          AND NOT EXISTS (
              SELECT 1 FROM payment_rosters AS other
              WHERE other.scholarship_configuration_id = pr.scholarship_configuration_id
                AND other.period_label = pr.academic_year::text
                AND COALESCE(other.allocation_year, -1) = COALESCE(pr.allocation_year, -1)
                AND COALESCE(other.sub_type, '') = COALESCE(pr.sub_type, '')
          )
        """)


def downgrade() -> None:
    op.execute("""
        UPDATE payment_rosters AS pr
        SET period_label = pr.allocation_year::text
        WHERE pr.roster_cycle = 'yearly'
          AND pr.allocation_config_id IS NOT NULL
          AND pr.allocation_year IS NOT NULL
          AND pr.period_label <> pr.allocation_year::text
          AND NOT EXISTS (
              SELECT 1 FROM payment_rosters AS other
              WHERE other.scholarship_configuration_id = pr.scholarship_configuration_id
                AND other.period_label = pr.allocation_year::text
                AND COALESCE(other.allocation_year, -1) = COALESCE(pr.allocation_year, -1)
                AND COALESCE(other.sub_type, '') = COALESCE(pr.sub_type, '')
          )
        """)
