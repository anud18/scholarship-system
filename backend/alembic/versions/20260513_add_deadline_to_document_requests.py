"""Add deadline column to document_requests

Revision ID: 20260513_doc_req_deadline
Revises: 20260513_scrub_pii_audit, b7c3a1f8d290, add_college_rejected_001
Create Date: 2026-05-13

Closes issue #215: the deadline-checker task (backend/app/tasks/deadline_checker.py)
needs a deadline column on document_requests to send reminder notifications.

This migration also folds the three open alembic heads on main into a single
head so future migrations can append cleanly without `alembic upgrade head`
choking on ambiguous lineage.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260513_doc_req_deadline"
down_revision = (
    "20260513_scrub_pii_audit",
    "b7c3a1f8d290",
    "add_college_rejected_001",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "document_requests" not in inspector.get_table_names():
        # The table was renamed or dropped — nothing to do.
        return

    columns = {col["name"] for col in inspector.get_columns("document_requests")}
    if "deadline" in columns:
        return

    op.add_column(
        "document_requests",
        sa.Column(
            "deadline",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When the student must fulfill this request by; null = no hard deadline.",
        ),
    )
    op.create_index(
        "ix_document_requests_deadline",
        "document_requests",
        ["deadline"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "document_requests" not in inspector.get_table_names():
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("document_requests")}
    if "ix_document_requests_deadline" in indexes:
        op.drop_index("ix_document_requests_deadline", table_name="document_requests")

    columns = {col["name"] for col in inspector.get_columns("document_requests")}
    if "deadline" in columns:
        op.drop_column("document_requests", "deadline")
