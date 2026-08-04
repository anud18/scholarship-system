"""Enable student and professor automation rules, fix professor condition query

Revision ID: enable_automation_rules_001
Revises: update_master_school_info_001
Create Date: 2026-05-06 00:00:00.000000

Changes:
- Enable '申請提交確認郵件' rule (is_active = true)
- Enable '教授審核通知' rule (is_active = true)
- Fix '教授審核通知' condition_query: use applications.professor_id -> users.email
  with COALESCE fallback to user_profiles.advisor_email
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "enable_automation_rules_001"
down_revision: Union[str, None] = "update_master_school_info_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROFESSOR_CONDITION_QUERY = """
                SELECT COALESCE(u.email, up.advisor_email) AS email
                FROM applications a
                LEFT JOIN users u ON u.id = a.professor_id
                LEFT JOIN user_profiles up ON up.user_id = a.user_id
                WHERE a.id = {application_id}
                AND COALESCE(u.email, up.advisor_email) IS NOT NULL
                AND COALESCE(u.email, up.advisor_email) != ''
            """


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "email_automation_rules" not in inspector.get_table_names():
        return

    op.execute(
        sa.text(
            "UPDATE email_automation_rules SET is_active = true WHERE name = '申請提交確認郵件'"
        )
    )

    op.execute(
        sa.text(
            "UPDATE email_automation_rules "
            "SET is_active = true, condition_query = :cq "
            "WHERE name = '教授審核通知'"
        ).bindparams(cq=PROFESSOR_CONDITION_QUERY)
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "email_automation_rules" not in inspector.get_table_names():
        return

    op.execute(
        sa.text(
            "UPDATE email_automation_rules SET is_active = false WHERE name = '申請提交確認郵件'"
        )
    )

    op.execute(
        sa.text(
            "UPDATE email_automation_rules SET is_active = false WHERE name = '教授審核通知'"
        )
    )
