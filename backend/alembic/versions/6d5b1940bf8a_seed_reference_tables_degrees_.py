"""seed_reference_tables_degrees_identities_schoolidentities_studyingstatuses

Revision ID: 6d5b1940bf8a
Revises: 05a291e3cca0
Create Date: 2025-10-18 17:02:02.892019

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6d5b1940bf8a"
down_revision: Union[str, None] = "05a291e3cca0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Initialize reference data tables with lookup values"""

    conn = op.get_bind()

    # === Degrees (學位) ===
    print("  📖 Seeding degrees...")
    degrees_data = [
        {"id": 1, "name": "博士"},
        {"id": 2, "name": "碩士"},
        {"id": 3, "name": "學士"},
    ]

    for degree in degrees_data:
        conn.execute(
            sa.text(
                """
                INSERT INTO degrees (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO NOTHING
            """
            ),
            degree,
        )

    # === Studying Statuses (學籍狀態) ===
    print("  📊 Seeding studying statuses...")
    studying_statuses_data = [
        {"id": 1, "name": "在學"},
        {"id": 2, "name": "應畢"},
        {"id": 3, "name": "延畢"},
        {"id": 4, "name": "休學"},
        {"id": 5, "name": "期中退學"},
        {"id": 6, "name": "期末退學"},
        {"id": 7, "name": "開除學籍"},
        {"id": 8, "name": "死亡"},
        {"id": 9, "name": "保留學籍"},
        {"id": 10, "name": "放棄入學"},
        {"id": 11, "name": "畢業"},
    ]

    for status in studying_statuses_data:
        conn.execute(
            sa.text(
                """
                INSERT INTO studying_statuses (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO NOTHING
            """
            ),
            status,
        )

    # === School Identities (學校身份 std_schoolid) ===
    print("  🎓 Seeding school identities...")
    school_identities_data = [
        {"id": 1, "name": "一般生"},
        {"id": 2, "name": "在職生"},
        {"id": 3, "name": "選讀學分"},
        {"id": 4, "name": "交換學生"},
        {"id": 5, "name": "外校生"},
        {"id": 6, "name": "提早選讀生"},
        {"id": 7, "name": "跨校生"},
        {"id": 8, "name": "專案選讀生"},
    ]

    for school_identity in school_identities_data:
        conn.execute(
            sa.text(
                """
                INSERT INTO school_identities (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO NOTHING
            """
            ),
            school_identity,
        )

    # === Student Identities (學生身份 std_identity) ===
    print("  👥 Seeding student identities...")
    identities_data = [
        {"id": 1, "name": "一般生"},
        {"id": 2, "name": "原住民"},
        {"id": 3, "name": "僑生"},
        {"id": 4, "name": "外籍生"},
        {"id": 5, "name": "外交子女"},
        {"id": 6, "name": "身心障礙生"},
        {"id": 7, "name": "運動成績優良甄試學生"},
        {"id": 8, "name": "離島"},
        {"id": 9, "name": "退伍軍人"},
        {"id": 10, "name": "一般公費生"},
        {"id": 11, "name": "原住民公費生"},
        {"id": 12, "name": "離島公費生"},
        {"id": 13, "name": "退伍軍人公費生"},
        {"id": 14, "name": "願景計畫生"},
        {"id": 17, "name": "陸生"},
        {"id": 30, "name": "其他"},
    ]

    for identity in identities_data:
        conn.execute(
            sa.text(
                """
                INSERT INTO identities (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO NOTHING
            """
            ),
            identity,
        )

    print("  ✓ Reference tables seeded successfully!")


def downgrade() -> None:
    """Clear seeded reference data"""

    conn = op.get_bind()

    print("  🗑️ Clearing reference data...")

    # Clear data in reverse order of insertion (respecting foreign keys if any)
    conn.execute(sa.text("DELETE FROM identities WHERE id IN (1,2,3,4,5,6,7,8,9,10,11,12,13,14,17,30)"))
    conn.execute(sa.text("DELETE FROM school_identities WHERE id IN (1,2,3,4,5,6,7,8)"))
    conn.execute(sa.text("DELETE FROM studying_statuses WHERE id IN (1,2,3,4,5,6,7,8,9,10,11)"))
    conn.execute(sa.text("DELETE FROM degrees WHERE id IN (1,2,3)"))

    print("  ✓ Reference data cleared!")
