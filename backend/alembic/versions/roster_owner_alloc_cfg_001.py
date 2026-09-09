"""rosters belong to the configuration whose slots they consume

Revision ID: roster_owner_alloc_cfg_001
Revises: drop_nstc_subtype_desc_001
Create Date: 2026-09-09 00:00:00.000000

A scholarship configuration owns all 36 months of its cohort: the 新申請 year
plus two 續領 years, and any later applicant 補發 onto one of its freed
slots. Its 造冊列表 therefore shows three year segments, and every roster
that pays out of that configuration's slots (allocation_config_id) hangs
under it, with period_label = the academic year actually being paid.

generate_rosters_from_distribution used to attach the borrowed-slot roster
to the REQUESTING (current-year) configuration and label it with the
consumed configuration's year: the 115 distribution's "nstc on 114 slots"
roster sat under phd_115 as period "114". Move such rows to the consumed
configuration and relabel them with the paying year (academic_year).

The unique key is (scholarship_configuration_id, period_label,
COALESCE(allocation_year,-1), COALESCE(sub_type,'')); a NOT EXISTS guard
skips a row whose target slot is already taken.

Downgrade restores the old period_label (= allocation_year) but cannot know
the requesting configuration, so ownership stays with the consumed one.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "roster_owner_alloc_cfg_001"
down_revision: Union[str, Sequence[str], None] = "drop_nstc_subtype_desc_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE payment_rosters AS pr
        SET scholarship_configuration_id = pr.allocation_config_id,
            period_label = pr.academic_year::text
        WHERE pr.roster_cycle = 'yearly'
          AND pr.allocation_config_id IS NOT NULL
          AND (
              pr.scholarship_configuration_id <> pr.allocation_config_id
              OR pr.period_label <> pr.academic_year::text
          )
          AND NOT EXISTS (
              SELECT 1 FROM payment_rosters AS other
              WHERE other.id <> pr.id
                AND other.scholarship_configuration_id = pr.allocation_config_id
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
              WHERE other.id <> pr.id
                AND other.scholarship_configuration_id = pr.scholarship_configuration_id
                AND other.period_label = pr.allocation_year::text
                AND COALESCE(other.allocation_year, -1) = COALESCE(pr.allocation_year, -1)
                AND COALESCE(other.sub_type, '') = COALESCE(pr.sub_type, '')
          )
        """)
