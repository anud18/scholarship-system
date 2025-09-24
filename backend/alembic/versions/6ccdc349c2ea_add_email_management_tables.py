"""add_email_management_tables

Revision ID: 6ccdc349c2ea
Revises: 4f22265b1968
Create Date: 2025-09-17 05:31:02.226246

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6ccdc349c2ea"
down_revision: Union[str, None] = "4f22265b1968"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create email_history table
    op.create_table(
        "email_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("cc_emails", sa.Text(), nullable=True),
        sa.Column("bcc_emails", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=True),
        sa.Column(
            "email_category",
            sa.Enum(
                "APPLICATION_WHITELIST",
                "APPLICATION_STUDENT",
                "RECOMMENDATION_PROFESSOR",
                "REVIEW_COLLEGE",
                "SUPPLEMENT_STUDENT",
                "RESULT_PROFESSOR",
                "RESULT_COLLEGE",
                "RESULT_STUDENT",
                "ROSTER_STUDENT",
                "SYSTEM",
                "OTHER",
                name="emailcategory",
            ),
            nullable=True,
        ),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("scholarship_type_id", sa.Integer(), nullable=True),
        sa.Column("sent_by_user_id", sa.Integer(), nullable=True),
        sa.Column("sent_by_system", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "status",
            sa.Enum("SENT", "FAILED", "BOUNCED", "PENDING", name="emailstatus"),
            nullable=False,
            default="SENT",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column("email_size_bytes", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["template_key"],
            ["email_templates.key"],
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["scholarship_type_id"],
            ["scholarship_types.id"],
        ),
        sa.ForeignKeyConstraint(
            ["sent_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for email_history
    op.create_index(
        "idx_email_history_recipient_date",
        "email_history",
        ["recipient_email", "sent_at"],
    )
    op.create_index(
        "idx_email_history_category_date",
        "email_history",
        ["email_category", "sent_at"],
    )
    op.create_index(
        "idx_email_history_scholarship_date",
        "email_history",
        ["scholarship_type_id", "sent_at"],
    )
    op.create_index(
        "idx_email_history_status_date", "email_history", ["status", "sent_at"]
    )
    op.create_index(op.f("ix_email_history_id"), "email_history", ["id"])
    op.create_index(
        op.f("ix_email_history_recipient_email"), "email_history", ["recipient_email"]
    )
    op.create_index(
        op.f("ix_email_history_email_category"), "email_history", ["email_category"]
    )
    op.create_index(
        op.f("ix_email_history_application_id"), "email_history", ["application_id"]
    )
    op.create_index(
        op.f("ix_email_history_scholarship_type_id"),
        "email_history",
        ["scholarship_type_id"],
    )
    op.create_index(op.f("ix_email_history_status"), "email_history", ["status"])
    op.create_index(op.f("ix_email_history_sent_at"), "email_history", ["sent_at"])

    # Create scheduled_emails table
    op.create_table(
        "scheduled_emails",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("cc_emails", sa.Text(), nullable=True),
        sa.Column("bcc_emails", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("template_key", sa.String(length=100), nullable=True),
        sa.Column(
            "email_category",
            sa.Enum(
                "APPLICATION_WHITELIST",
                "APPLICATION_STUDENT",
                "RECOMMENDATION_PROFESSOR",
                "REVIEW_COLLEGE",
                "SUPPLEMENT_STUDENT",
                "RESULT_PROFESSOR",
                "RESULT_COLLEGE",
                "RESULT_STUDENT",
                "ROSTER_STUDENT",
                "SYSTEM",
                "OTHER",
                name="emailcategory",
            ),
            nullable=True,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "SENT", "CANCELLED", "FAILED", name="schedulestatus"),
            nullable=False,
            default="PENDING",
        ),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("scholarship_type_id", sa.Integer(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=False, default=False),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
        ),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), default=5),
        sa.ForeignKeyConstraint(
            ["template_key"],
            ["email_templates.key"],
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["scholarship_type_id"],
            ["scholarship_types.id"],
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for scheduled_emails
    op.create_index(
        "idx_scheduled_email_due", "scheduled_emails", ["scheduled_for", "status"]
    )
    op.create_index(
        "idx_scheduled_email_approval",
        "scheduled_emails",
        ["requires_approval", "approved_by_user_id"],
    )
    op.create_index(
        "idx_scheduled_email_scholarship",
        "scheduled_emails",
        ["scholarship_type_id", "status"],
    )
    op.create_index(
        "idx_scheduled_email_priority",
        "scheduled_emails",
        ["priority", "scheduled_for"],
    )
    op.create_index(op.f("ix_scheduled_emails_id"), "scheduled_emails", ["id"])
    op.create_index(
        op.f("ix_scheduled_emails_recipient_email"),
        "scheduled_emails",
        ["recipient_email"],
    )
    op.create_index(
        op.f("ix_scheduled_emails_scheduled_for"), "scheduled_emails", ["scheduled_for"]
    )
    op.create_index(op.f("ix_scheduled_emails_status"), "scheduled_emails", ["status"])
    op.create_index(
        op.f("ix_scheduled_emails_application_id"),
        "scheduled_emails",
        ["application_id"],
    )
    op.create_index(
        op.f("ix_scheduled_emails_scholarship_type_id"),
        "scheduled_emails",
        ["scholarship_type_id"],
    )


def downgrade() -> None:
    # Drop tables
    op.drop_table("scheduled_emails")
    op.drop_table("email_history")
