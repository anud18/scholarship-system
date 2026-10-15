"""Record which profile object an application's cloned fixed document came from

`ApplicationService._clone_user_profile_documents` copies the student's profile
bank document into the application. It must copy again when the student later
replaces the profile document, so each copy remembers its source object.
Copies made before this column existed have NULL and are refreshed once.

Revision ID: app_file_source_object_001
Revises: clear_unsafe_notif_links_001
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "app_file_source_object_001"
down_revision: Union[str, None] = "clear_unsafe_notif_links_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "application_files" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("application_files")}
    if "source_object_name" not in columns:
        op.add_column("application_files", sa.Column("source_object_name", sa.String(length=500), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "application_files" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("application_files")}
    if "source_object_name" in columns:
        op.drop_column("application_files", "source_object_name")
