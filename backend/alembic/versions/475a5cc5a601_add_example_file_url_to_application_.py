"""add_example_file_url_to_application_documents

Revision ID: 475a5cc5a601
Revises: dd2e75101fc4
Create Date: 2025-10-03 02:29:44.545069

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "475a5cc5a601"
down_revision: Union[str, None] = "dd2e75101fc4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column already exists before adding
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("application_documents")]

    if "example_file_url" not in existing_columns:
        op.add_column("application_documents", sa.Column("example_file_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    # Check if column exists before dropping
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("application_documents")]

    if "example_file_url" in existing_columns:
        op.drop_column("application_documents", "example_file_url")
