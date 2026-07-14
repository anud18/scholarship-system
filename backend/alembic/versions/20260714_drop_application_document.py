"""Drop the legacy row-level 申請文件 columns from applications.

The generic single-file application document upload was removed from the
student wizard; application documents are now exclusively the fixed/dynamic
document requirements configured per scholarship (application_documents
table) and uploaded as ApplicationFile records.

Revision ID: drop_app_document_001
Revises: add_renewal_review_flags_001
Create Date: 2026-07-14
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "drop_app_document_001"
down_revision = "add_renewal_review_flags_001"
branch_labels = None
depends_on = None

COLUMNS = ("application_document_url", "application_document_original_filename")


def _existing_columns(bind) -> set:
    inspector = sa.inspect(bind)
    if "applications" not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns("applications")}


def upgrade() -> None:
    existing = _existing_columns(op.get_bind())
    for column in COLUMNS:
        if column in existing:
            op.drop_column("applications", column)


def downgrade() -> None:
    bind = op.get_bind()
    if "applications" not in sa.inspect(bind).get_table_names():
        return
    existing = _existing_columns(bind)
    if "application_document_url" not in existing:
        op.add_column("applications", sa.Column("application_document_url", sa.String(500), nullable=True))
    if "application_document_original_filename" not in existing:
        op.add_column(
            "applications", sa.Column("application_document_original_filename", sa.String(255), nullable=True)
        )
