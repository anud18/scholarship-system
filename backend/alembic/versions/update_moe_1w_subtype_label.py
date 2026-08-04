"""update moe_1w sub-type label to 每月 $5000 元 wording

Revision ID: update_moe_1w_label_001
Revises: college_view_distribution_001
Create Date: 2026-07-08 00:00:00.000000

The student wizard renders sub-type cards straight from
scholarship_sub_type_configs.name. The seed only inserts when the row is
missing, so seed-side renames never reach existing DBs — depending on when a
deployment was seeded, its phd moe_1w row may carry either the original
"教育部博士生獎學金 (指導教授配合款一萬)" wording or the interim
"教育部博士生獎學金 (指導教授配合款每月五千)" wording. This migration rewrites
whichever variant is present. downgrade() restores the interim wording (the
label the codebase seed shipped immediately before this revision), NOT the
original 一萬 wording.

Updates the phd moe_1w sub-type config:
- name:        教育部博士生獎學金 (指導教授配合款每月 $5000 元)
- description: 教育部博士生獎學金，指導教授配合款每月 $5000 元
- name_en / description_en aligned to the NT$5,000/month wording

The UPDATE is scoped to the phd scholarship type: sub_type_code values are
configuration-driven strings, not globally unique, so another scholarship
type could legitimately define its own 'moe_1w' with a different label.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "update_moe_1w_label_001"
down_revision: Union[str, Sequence[str], None] = "college_view_distribution_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE scholarship_sub_type_configs
        SET
            name = '教育部博士生獎學金 (指導教授配合款每月 $5000 元)',
            name_en = 'MOE PHD Scholarship (Professor Match NT$5,000/month)',
            description = '教育部博士生獎學金，指導教授配合款每月 $5000 元',
            description_en = 'MOE PHD Scholarship with professor match of NT$5,000/month'
        WHERE sub_type_code = 'moe_1w'
          AND scholarship_type_id IN (
              SELECT id FROM scholarship_types WHERE code = 'phd'
          )
        """)


def downgrade() -> None:
    op.execute("""
        UPDATE scholarship_sub_type_configs
        SET
            name = '教育部博士生獎學金 (指導教授配合款每月五千)',
            name_en = 'MOE PHD Scholarship (Professor Match NT$5,000/month)',
            description = '教育部博士生獎學金，指導教授配合款每月五千元',
            description_en = 'MOE PHD Scholarship with professor match of NT$5,000/month'
        WHERE sub_type_code = 'moe_1w'
          AND scholarship_type_id IN (
              SELECT id FROM scholarship_types WHERE code = 'phd'
          )
        """)
