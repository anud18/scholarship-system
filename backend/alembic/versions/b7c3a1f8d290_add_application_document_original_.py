"""add_application_document_original_filename_to_applications

Revision ID: b7c3a1f8d290
Revises: 42ccef0f18fc
Create Date: 2026-04-22 09:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c3a1f8d290'
down_revision: Union[str, None] = '42ccef0f18fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]
    if "application_document_original_filename" not in columns:
        op.add_column(
            "applications",
            sa.Column("application_document_original_filename", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]
    if "application_document_original_filename" in columns:
        op.drop_column("applications", "application_document_original_filename")
