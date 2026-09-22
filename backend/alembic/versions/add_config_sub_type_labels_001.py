"""per-configuration sub-type display names (scholarship_configurations.sub_type_labels)

Revision ID: add_config_sub_type_labels_001
Revises: drop_nstc_subtype_desc_001
Create Date: 2026-09-09 00:00:00.000000

Sub-type display names used to live only on scholarship_sub_type_configs,
which is keyed by scholarship type — so a year-specific wording such as
「115學年度教育部博士生獎學金 (...)」 (moe_1w_ay115_label_001) leaked into every
academic year at once. Admins now edit each year's MOE / NSTC wording on that
year's ScholarshipConfiguration:

    sub_type_labels = {"moe_1w": {"name": "...", "name_en": "..."}, "nstc": {...}}

Resolution (app/services/sub_type_labels.py): a configuration's override wins,
otherwise the base scholarship_sub_type_configs.name applies.

Data migration keeps every deployed screen showing exactly what it shows today:

1. Snapshot the current 115學年度-prefixed phd moe_1w wording onto every phd
   configuration that has no override yet, so existing years keep their label.
2. Reset the base phd moe_1w row to the year-agnostic wording, so a newly
   created configuration (e.g. 116) starts from a label without a stale year.

Both statements are scoped to the phd scholarship type: sub_type_code values
are configuration-driven strings, not globally unique.

Revision id is 30 characters (alembic_version.version_num is VARCHAR(32)).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "add_config_sub_type_labels_001"
down_revision: Union[str, Sequence[str], None] = "drop_nstc_subtype_desc_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

AY115_MOE_1W_NAME = "115學年度教育部博士生獎學金 (指導教授配合款每月 $5000 元)"
AY115_MOE_1W_NAME_EN = "AY115 MOE PHD Scholarship (Professor Match NT$5,000/month)"
BASE_MOE_1W_NAME = "教育部博士生獎學金 (指導教授配合款每月 $5000 元)"
BASE_MOE_1W_NAME_EN = "MOE PHD Scholarship (Professor Match NT$5,000/month)"


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("scholarship_configurations", "sub_type_labels"):
        op.add_column("scholarship_configurations", sa.Column("sub_type_labels", sa.JSON(), nullable=True))

    # 1. Snapshot the year-specific wording onto existing phd configurations.
    op.execute(sa.text("""
            UPDATE scholarship_configurations AS c
            SET sub_type_labels = jsonb_build_object(
                    'moe_1w', jsonb_build_object('name', s.name, 'name_en', s.name_en)
                )::json
            FROM scholarship_sub_type_configs AS s
            JOIN scholarship_types AS t ON t.id = s.scholarship_type_id
            WHERE t.code = 'phd'
              AND s.sub_type_code = 'moe_1w'
              AND s.name = :ay115_name
              AND c.scholarship_type_id = t.id
              AND c.sub_type_labels IS NULL
            """).bindparams(ay115_name=AY115_MOE_1W_NAME))

    # 2. Make the base row year-agnostic again.
    op.execute(sa.text("""
            UPDATE scholarship_sub_type_configs
            SET name = :base_name, name_en = :base_name_en
            WHERE sub_type_code = 'moe_1w'
              AND name = :ay115_name
              AND scholarship_type_id IN (SELECT id FROM scholarship_types WHERE code = 'phd')
            """).bindparams(base_name=BASE_MOE_1W_NAME, base_name_en=BASE_MOE_1W_NAME_EN, ay115_name=AY115_MOE_1W_NAME))


def downgrade() -> None:
    op.execute(
        sa.text("""
            UPDATE scholarship_sub_type_configs
            SET name = :ay115_name, name_en = :ay115_name_en
            WHERE sub_type_code = 'moe_1w'
              AND name = :base_name
              AND scholarship_type_id IN (SELECT id FROM scholarship_types WHERE code = 'phd')
            """).bindparams(
            ay115_name=AY115_MOE_1W_NAME, ay115_name_en=AY115_MOE_1W_NAME_EN, base_name=BASE_MOE_1W_NAME
        )
    )
    if _has_column("scholarship_configurations", "sub_type_labels"):
        op.drop_column("scholarship_configurations", "sub_type_labels")
