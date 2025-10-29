"""add batch import tables and fields

Revision ID: 2e7b490e60dc
Revises: c5d8f9a2b3e1
Create Date: 2025-10-05 00:59:48.344483

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e7b490e60dc"
down_revision: Union[str, Sequence[str], None] = "c5d8f9a2b3e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check for existing tables/columns to prevent conflicts
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Create batch_imports table
    if "batch_imports" not in existing_tables:
        op.create_table(
            "batch_imports",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("importer_id", sa.Integer(), nullable=False),
            sa.Column("college_code", sa.String(10), nullable=False),
            sa.Column("scholarship_type_id", sa.Integer(), nullable=True),
            sa.Column("academic_year", sa.Integer(), nullable=False),
            sa.Column("semester", sa.String(20), nullable=True),
            sa.Column("file_name", sa.String(255), nullable=False),
            sa.Column("file_path", sa.String(500), nullable=True),
            sa.Column("total_records", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_summary", postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column("import_status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.ForeignKeyConstraint(
                ["importer_id"],
                ["users.id"],
            ),
            sa.ForeignKeyConstraint(
                ["scholarship_type_id"],
                ["scholarship_types.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_batch_imports_college_code", "batch_imports", ["college_code"])
        op.create_index("ix_batch_imports_importer_id", "batch_imports", ["importer_id"])
        op.create_index("ix_batch_imports_status", "batch_imports", ["import_status"])

    # Add new columns to applications table
    existing_columns = [col["name"] for col in inspector.get_columns("applications")]

    if "imported_by_id" not in existing_columns:
        op.add_column("applications", sa.Column("imported_by_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_applications_imported_by", "applications", "users", ["imported_by_id"], ["id"])

    if "batch_import_id" not in existing_columns:
        op.add_column("applications", sa.Column("batch_import_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_applications_batch_import", "applications", "batch_imports", ["batch_import_id"], ["id"]
        )

    if "import_source" not in existing_columns:
        op.add_column("applications", sa.Column("import_source", sa.String(20), nullable=True, server_default="online"))

    if "document_status" not in existing_columns:
        op.add_column(
            "applications", sa.Column("document_status", sa.String(30), nullable=True, server_default="complete")
        )


def downgrade() -> None:
    # Remove added columns from applications table
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col["name"] for col in inspector.get_columns("applications")]

    if "document_status" in existing_columns:
        op.drop_column("applications", "document_status")

    if "import_source" in existing_columns:
        op.drop_column("applications", "import_source")

    if "batch_import_id" in existing_columns:
        op.drop_constraint("fk_applications_batch_import", "applications", type_="foreignkey")
        op.drop_column("applications", "batch_import_id")

    if "imported_by_id" in existing_columns:
        op.drop_constraint("fk_applications_imported_by", "applications", type_="foreignkey")
        op.drop_column("applications", "imported_by_id")

    # Drop batch_imports table
    existing_tables = inspector.get_table_names()
    if "batch_imports" in existing_tables:
        op.drop_index("ix_batch_imports_status", table_name="batch_imports")
        op.drop_index("ix_batch_imports_importer_id", table_name="batch_imports")
        op.drop_index("ix_batch_imports_college_code", table_name="batch_imports")
        op.drop_table("batch_imports")
