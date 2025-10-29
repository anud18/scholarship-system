"""add academy name_en and department academy_code

Revision ID: 3453e6861885
Revises: 36976b6fab9f
Create Date: 2025-10-05 01:39:20.965986

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3453e6861885"
down_revision: Union[str, None] = "36976b6fab9f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 確保 academies 表存在
    if "academies" not in existing_tables:
        op.create_table(
            "academies",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("code", sa.String(10), unique=True, nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("name_en", sa.String(200), nullable=True),
        )
        op.create_index("ix_academies_code", "academies", ["code"])
    else:
        # academies 表存在，檢查是否需要新增 name_en
        existing_columns = [col["name"] for col in inspector.get_columns("academies")]
        if "name_en" not in existing_columns:
            op.add_column("academies", sa.Column("name_en", sa.String(200), nullable=True))

    # 新增 departments.academy_code 欄位
    if "departments" in existing_tables:
        existing_columns = [col["name"] for col in inspector.get_columns("departments")]
        if "academy_code" not in existing_columns:
            op.add_column("departments", sa.Column("academy_code", sa.String(10), nullable=True))
            # 建立外鍵
            op.create_foreign_key("fk_departments_academy_code", "departments", "academies", ["academy_code"], ["code"])
            # 建立索引
            op.create_index("ix_departments_academy_code", "departments", ["academy_code"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 移除 departments.academy_code
    if "departments" in inspector.get_table_names():
        existing_columns = [col["name"] for col in inspector.get_columns("departments")]
        if "academy_code" in existing_columns:
            op.drop_constraint("fk_departments_academy_code", "departments", type_="foreignkey")
            op.drop_index("ix_departments_academy_code", "departments")
            op.drop_column("departments", "academy_code")

    # 移除 academies.name_en
    if "academies" in inspector.get_table_names():
        existing_columns = [col["name"] for col in inspector.get_columns("academies")]
        if "name_en" in existing_columns:
            op.drop_column("academies", "name_en")
