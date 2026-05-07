"""Add include_in_college_export + export_column_label to application_fields

Revision ID: add_college_export_flag_001
Revises: add_contact_phone_field_001
Create Date: 2026-05-08
"""

import sqlalchemy as sa
from alembic import op

revision = "add_college_export_flag_001"
down_revision = "add_contact_phone_field_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("application_fields")}

    if "include_in_college_export" not in cols:
        op.add_column(
            "application_fields",
            sa.Column(
                "include_in_college_export",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    if "export_column_label" not in cols:
        op.add_column(
            "application_fields",
            sa.Column("export_column_label", sa.String(length=200), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("application_fields")}

    if "export_column_label" in cols:
        op.drop_column("application_fields", "export_column_label")
    if "include_in_college_export" in cols:
        op.drop_column("application_fields", "include_in_college_export")
