"""add_condition_query_to_email_automation_rules

Revision ID: 24f4d6ba449b
Revises: e532ef9a7342
Create Date: 2025-10-12 12:24:46.414806

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "24f4d6ba449b"
down_revision: Union[str, None] = "e532ef9a7342"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add condition_query to existing email automation rules"""

    # Update "申請提交確認郵件" rule - sends to both com_email and users.email
    op.execute(
        """
        UPDATE email_automation_rules
        SET condition_query = '
            SELECT email FROM (
                SELECT applications.student_data->>''com_email'' as email
                FROM applications
                WHERE applications.id = {application_id}
                AND applications.student_data->>''com_email'' IS NOT NULL
                AND applications.student_data->>''com_email'' != ''''

                UNION

                SELECT users.email
                FROM applications
                JOIN users ON applications.user_id = users.id
                WHERE applications.id = {application_id}
                AND users.email IS NOT NULL
                AND users.email != ''''
            ) emails
            WHERE email IS NOT NULL
        '
        WHERE template_key = 'application_submitted_student'
    """
    )

    # Update "教授審核通知" rule - sends to advisor_email
    op.execute(
        """
        UPDATE email_automation_rules
        SET condition_query = '
            SELECT user_profiles.advisor_email as email
            FROM applications
            JOIN user_profiles ON applications.user_id = user_profiles.user_id
            WHERE applications.id = {application_id}
            AND user_profiles.advisor_email IS NOT NULL
            AND user_profiles.advisor_email != ''''
        '
        WHERE template_key = 'professor_review_notification'
    """
    )


def downgrade() -> None:
    """Remove condition_query from email automation rules"""

    op.execute(
        """
        UPDATE email_automation_rules
        SET condition_query = NULL
        WHERE template_key IN ('application_submitted_student', 'professor_review_notification')
    """
    )
