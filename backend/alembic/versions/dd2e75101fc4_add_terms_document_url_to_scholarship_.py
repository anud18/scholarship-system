"""add_terms_document_url_to_scholarship_types

Revision ID: dd2e75101fc4
Revises: f333214c4735
Create Date: 2025-10-02 21:35:36.397255

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dd2e75101fc4"
down_revision: Union[str, None] = "f333214c4735"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add terms_document_url column to scholarship_types table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("scholarship_types")]

    if "terms_document_url" not in existing_columns:
        op.add_column("scholarship_types", sa.Column("terms_document_url", sa.String(500), nullable=True))


def downgrade() -> None:
    # Remove terms_document_url column from scholarship_types table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("scholarship_types")]

    if "terms_document_url" in existing_columns:
        op.drop_column("scholarship_types", "terms_document_url")
