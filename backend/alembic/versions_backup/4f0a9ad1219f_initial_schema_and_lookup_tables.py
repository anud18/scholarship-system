"""Initial schema and lookup tables

Revision ID: 4f0a9ad1219f
Revises: 6b9a429f965b
Create Date: 2025-09-24 20:27:36.206137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f0a9ad1219f'
down_revision: Union[str, None] = '6b9a429f965b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import text

    conn = op.get_bind()

    # Lookup tables data from init_lookup_tables.py

    # 1. Degrees (學位)
    degrees_data = [
        {"id": 1, "name": "博士"},
        {"id": 2, "name": "碩士"},
        {"id": 3, "name": "學士"},
        {"id": 4, "name": "逕讀博士"},
    ]

    for degree in degrees_data:
        conn.execute(
            text("""
                INSERT INTO degree (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            degree
        )

    # 2. Identities (身份別)
    identities_data = [
        {"id": 1, "name": "國內學生"},
        {"id": 2, "name": "陸生"},
        {"id": 3, "name": "僑生"},
        {"id": 4, "name": "外籍生"},
        {"id": 5, "name": "港澳生"},
    ]

    for identity in identities_data:
        conn.execute(
            text("""
                INSERT INTO identity (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            identity
        )

    # 3. Studying Status (在學狀態)
    studying_status_data = [
        {"id": 1, "name": "在學"},
        {"id": 2, "name": "休學"},
        {"id": 3, "name": "退學"},
        {"id": 4, "name": "畢業"},
    ]

    for status in studying_status_data:
        conn.execute(
            text("""
                INSERT INTO studying_status (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            status
        )

    # 4. Academies (學院)
    academies_data = [
        {"id": 1, "code": "10", "name": "電機學院"},
        {"id": 2, "code": "20", "name": "資訊學院"},
        {"id": 3, "code": "30", "name": "工學院"},
        {"id": 4, "code": "40", "name": "理學院"},
        {"id": 5, "code": "50", "name": "生科學院"},
        {"id": 6, "code": "60", "name": "管理學院"},
        {"id": 7, "code": "70", "name": "人社學院"},
        {"id": 8, "code": "80", "name": "客家學院"},
        {"id": 9, "code": "90", "name": "國際半導體產業學院"},
        {"id": 10, "code": "A0", "name": "智慧科學暨綠能學院"},
        {"id": 11, "code": "B0", "name": "跨領域學程"},
    ]

    for academy in academies_data:
        conn.execute(
            text("""
                INSERT INTO academy (id, code, name)
                VALUES (:id, :code, :name)
                ON CONFLICT (id) DO UPDATE SET code = EXCLUDED.code, name = EXCLUDED.name
            """),
            academy
        )

    # 5. Departments (系所)
    departments_data = [
        {"id": 1, "code": "3311", "name": "電子工程學系", "academy_code": "10"},
        {"id": 2, "code": "3321", "name": "電機工程學系", "academy_code": "10"},
        {"id": 3, "code": "3331", "name": "光電工程學系", "academy_code": "10"},
        {"id": 4, "code": "3411", "name": "電信工程研究所", "academy_code": "10"},
        {"id": 5, "code": "3421", "name": "電子研究所", "academy_code": "10"},
        {"id": 6, "code": "3431", "name": "光電系統研究所", "academy_code": "10"},
        {"id": 7, "code": "3461", "name": "電控工程研究所", "academy_code": "10"},
        {"id": 8, "code": "3471", "name": "電機學院學士班", "academy_code": "10"},
        {"id": 9, "code": "3551", "name": "資訊工程學系", "academy_code": "20"},
        {"id": 10, "code": "3561", "name": "資訊科學與工程研究所", "academy_code": "20"},
        {"id": 11, "code": "3571", "name": "網路工程研究所", "academy_code": "20"},
        {"id": 12, "code": "3581", "name": "多媒體工程研究所", "academy_code": "20"},
        {"id": 13, "code": "3591", "name": "資訊管理與財務金融學系資訊管理組", "academy_code": "20"},
        {"id": 14, "code": "3592", "name": "資訊管理與財務金融學系財務金融組", "academy_code": "20"},
        {"id": 15, "code": "3601", "name": "資訊管理研究所", "academy_code": "20"},
        {"id": 16, "code": "3611", "name": "資訊財金碩士在職專班", "academy_code": "20"},
        {"id": 17, "code": "3621", "name": "資訊學院學士班", "academy_code": "20"},
    ]

    for dept in departments_data:
        conn.execute(
            text("""
                INSERT INTO department (id, code, name, academy_code)
                VALUES (:id, :code, :name, :academy_code)
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code,
                    name = EXCLUDED.name,
                    academy_code = EXCLUDED.academy_code
            """),
            dept
        )

    # 6. Enrollment Types (入學管道)
    enrollment_types_data = [
        {"id": 1, "name": "繁星推薦"},
        {"id": 2, "name": "個人申請"},
        {"id": 3, "name": "考試分發"},
        {"id": 4, "name": "特殊選才"},
        {"id": 5, "name": "其他"},
    ]

    for enrollment_type in enrollment_types_data:
        conn.execute(
            text("""
                INSERT INTO enrollment_type (id, name)
                VALUES (:id, :name)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            enrollment_type
        )


def downgrade() -> None:
    from sqlalchemy import text

    conn = op.get_bind()

    # Delete in reverse order to handle foreign key constraints
    conn.execute(text("DELETE FROM enrollment_type"))
    conn.execute(text("DELETE FROM department"))
    conn.execute(text("DELETE FROM academy"))
    conn.execute(text("DELETE FROM studying_status"))
    conn.execute(text("DELETE FROM identity"))
    conn.execute(text("DELETE FROM degree"))