"""clear the phd nstc sub-type description (it only restated its own name)

Revision ID: drop_nstc_subtype_desc_001
Revises: moe_1w_ay115_label_001
Create Date: 2026-09-04 00:00:00.000000

moe_1w_ay115_label_001 made scholarship_sub_type_configs.description visible:
the professor review screen now renders it as a note under the sub-type
heading. That surfaced a line on the nstc card which only restated that row's
own name — "國科會博士生獎學金，適用於符合條件的博士生" under the heading
"國科會博士生獎學金" — so reviewers were trained to skip the very position
that carries the moe_1w matching-fund caveat.

Clearing the column removes the line with no code change, because the review
screen renders the note only when it is non-empty.

This is a separate revision rather than an edit to moe_1w_ay115_label_001:
that revision is already merged and may already be applied, and an applied
migration is never re-run, so an in-place edit would silently skip every
deployed database.

The UPDATE is scoped to the phd scholarship type: sub_type_code values are
configuration-driven strings, not globally unique, so another scholarship
type could legitimately define its own 'nstc' with a description worth keeping.

The revision id is kept at 26 characters: alembic_version.version_num is
VARCHAR(32), and the first cut of this migration used a 33-character id, which
applied the UPDATE and then blew up writing the version row (staging rolled
back cleanly). Existing ids in this repo top out at exactly 32.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "drop_nstc_subtype_desc_001"
down_revision: Union[str, Sequence[str], None] = "moe_1w_ay115_label_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
            description = '國科會博士生獎學金，適用於符合條件的博士生',
            description_en = 'NSTC PHD Scholarship for eligible PhD students'
        WHERE sub_type_code = 'nstc'
          AND scholarship_type_id IN (
              SELECT id FROM scholarship_types WHERE code = 'phd'
          )
        """)
