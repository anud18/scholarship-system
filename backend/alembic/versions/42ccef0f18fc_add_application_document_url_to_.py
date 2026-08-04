"""add_application_document_url_to_applications

Revision ID: 42ccef0f18fc
Revises: a1b2c3d4e5f6
Create Date: 2026-04-21 02:26:05.382961

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42ccef0f18fc'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]
    if "application_document_url" not in columns:
        op.add_column(
            "applications",
            sa.Column("application_document_url", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]
    if "application_document_url" in columns:
        op.drop_column("applications", "application_document_url")
