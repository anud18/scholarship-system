"""reorganize email templates by sending type and add recipient options

Revision ID: 6b9a429f965b
Revises: 5ac85532364d
Create Date: 2025-09-18 15:55:39.495957

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6b9a429f965b"
down_revision: Union[str, None] = "5ac85532364d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum type for sending_type first
    sending_type_enum = postgresql.ENUM("single", "bulk", name="sending_type")
    sending_type_enum.create(op.get_bind())

    # Add new columns to email_templates table
    op.add_column(
        "email_templates",
        sa.Column(
            "sending_type", sending_type_enum, nullable=False, server_default="single"
        ),
    )
    op.add_column(
        "email_templates",
        sa.Column("recipient_options", postgresql.JSON(), nullable=True),
    )
    op.add_column(
        "email_templates",
        sa.Column(
            "requires_approval", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "email_templates", sa.Column("max_recipients", sa.Integer(), nullable=True)
    )

    # Update existing templates with sending types and recipient options
    connection = op.get_bind()

    # Single email templates (individual notifications)
    single_templates = [
        "application_submitted_student",
        "application_submitted_admin",
        "application_result_approved",
        "application_result_rejected",
        "professor_review_notification",
        "professor_review_submitted_admin",
        "supplement_request_student",
        "award_notification",
        "system_maintenance_notice",
    ]

    # Bulk email templates (mass notifications)
    bulk_templates = [
        "application_deadline_reminder",
        "review_deadline_reminder",
    ]

    # Set single templates
    for template_key in single_templates:
        if "student" in template_key:
            recipient_options = '[{"value": "applicant", "label": "申請人", "description": "獎學金申請人"}, {"value": "student", "label": "學生", "description": "學生本人"}]'
        elif "admin" in template_key:
            recipient_options = '[{"value": "admin", "label": "管理員", "description": "系統管理員"}, {"value": "scholarship_admin", "label": "獎學金管理員", "description": "負責該獎學金的管理員"}]'
        elif "professor" in template_key:
            recipient_options = '[{"value": "professor", "label": "指導教授", "description": "申請人的指導教授"}, {"value": "reviewer", "label": "審查教授", "description": "負責審查的教授"}]'
        else:
            recipient_options = '[{"value": "student", "label": "學生", "description": "學生"}, {"value": "admin", "label": "管理員", "description": "管理員"}]'

        connection.execute(
            sa.text(
                """
                UPDATE email_templates 
                SET sending_type = 'single', 
                    recipient_options = :recipient_options,
                    max_recipients = 1
                WHERE key = :template_key
            """
            ),
            {"template_key": template_key, "recipient_options": recipient_options},
        )

    # Set bulk templates
    for template_key in bulk_templates:
        if "application" in template_key:
            recipient_options = '[{"value": "eligible_students", "label": "符合資格的學生", "description": "符合申請資格的所有學生"}, {"value": "all_students", "label": "所有學生", "description": "系統中的所有學生"}, {"value": "department_students", "label": "特定系所學生", "description": "特定系所的學生"}]'
        else:  # review deadline
            recipient_options = '[{"value": "pending_reviewers", "label": "待審查教授", "description": "尚未完成審查的教授"}, {"value": "all_reviewers", "label": "所有審查教授", "description": "參與審查的所有教授"}]'

        connection.execute(
            sa.text(
                """
                UPDATE email_templates 
                SET sending_type = 'bulk', 
                    recipient_options = :recipient_options,
                    requires_approval = true,
                    max_recipients = 500
                WHERE key = :template_key
            """
            ),
            {"template_key": template_key, "recipient_options": recipient_options},
        )

    # Remove college_notify template
    connection.execute(
        sa.text("DELETE FROM email_templates WHERE key = 'college_notify'")
    )

    # Drop scholarship_email_templates table
    op.drop_table("scholarship_email_templates")


def downgrade() -> None:
    # Recreate scholarship_email_templates table
    op.create_table(
        "scholarship_email_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scholarship_type_id", sa.Integer(), nullable=False),
        sa.Column("email_template_key", sa.String(length=100), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("custom_subject", sa.String(length=255), nullable=True),
        sa.Column("custom_body", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["email_template_key"],
            ["email_templates.key"],
        ),
        sa.ForeignKeyConstraint(
            ["scholarship_type_id"],
            ["scholarship_types.id"],
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "scholarship_type_id",
            "email_template_key",
            name="uq_scholarship_email_template",
        ),
    )

    # Remove new columns from email_templates
    op.drop_column("email_templates", "max_recipients")
    op.drop_column("email_templates", "requires_approval")
    op.drop_column("email_templates", "recipient_options")
    op.drop_column("email_templates", "sending_type")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS sending_type")
