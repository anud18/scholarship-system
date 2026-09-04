"""prefix moe_1w sub-type label with 115學年度 and note the rolling adjustment

Revision ID: moe_1w_ay115_label_001
Revises: add_footer_link_section_001
Create Date: 2026-09-04 00:00:00.000000

The professor review screen renders the sub-type heading straight from
scholarship_sub_type_configs.name (see
ApplicationService.get_application_available_sub_types), and the seed only
inserts when the row is missing, so a seed-side rename never reaches an
existing DB. This migration rewrites the phd moe_1w row in place:

- name:        115學年度教育部博士生獎學金 (指導教授配合款每月 $5000 元)
- description: 每年配合款經費金額將配合教育部相關規定，採滾動式調整。

The description carries the rolling-adjustment note rather than restating the
name, because the professor review screen now shows it underneath the heading.

For the same reason the sibling nstc description is cleared: it only restated
that row's own name ("國科會博士生獎學金，適用於符合條件的博士生"), so once
descriptions became visible it rendered as a tautological third line that
trained reviewers to skip the very position carrying the moe_1w caveat. The
review screen renders the note only when it is non-empty, so clearing the
column removes the line with no code change.

downgrade() restores the wording shipped by update_moe_1w_label_001 and the
original nstc description.

The UPDATE is scoped to the phd scholarship type: sub_type_code values are
configuration-driven strings, not globally unique, so another scholarship
type could legitimately define its own 'moe_1w' with a different label.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "moe_1w_ay115_label_001"
down_revision: Union[str, Sequence[str], None] = "add_footer_link_section_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE scholarship_sub_type_configs
        SET
            name = '115學年度教育部博士生獎學金 (指導教授配合款每月 $5000 元)',
            name_en = 'AY115 MOE PHD Scholarship (Professor Match NT$5,000/month)',
            description = '每年配合款經費金額將配合教育部相關規定，採滾動式調整。',
            description_en = 'The annual matching fund amount is subject to rolling adjustment in accordance with MOE regulations.'
        WHERE sub_type_code = 'moe_1w'
          AND scholarship_type_id IN (
              SELECT id FROM scholarship_types WHERE code = 'phd'
          )
        """)

    op.execute("""
        UPDATE scholarship_sub_type_configs
        SET
            description = NULL,
            description_en = NULL
        WHERE sub_type_code = 'nstc'
          AND scholarship_type_id IN (
              SELECT id FROM scholarship_types WHERE code = 'phd'
          )
        """)


def downgrade() -> None:
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

    op.execute("""
        UPDATE scholarship_sub_type_configs
        SET
            description = '國科會博士生獎學金，適用於符合條件的博士生',
            description_en = 'NSTC PHD Scholarship for eligible PhD students'
        WHERE sub_type_code = 'nstc'
          AND scholarship_type_id IN (
              SELECT id FROM scholarship_types WHERE code = 'phd'
          )
        """)
