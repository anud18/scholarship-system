"""Create scholarship_rules table

Revision ID: create_scholarship_rules_table
Revises: ea5d2bc75b8b
Create Date: 2025-01-05 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "create_scholarship_rules_table"
down_revision: Union[str, None] = "ea5d2bc75b8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if tables already exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Create scholarship_types table first if it doesn't exist
    if "scholarship_types" not in existing_tables:
        # Create required enums
        op.execute(
            """
            DO $$ BEGIN
                CREATE TYPE subtypeselectionmode AS ENUM ('SINGLE', 'MULTIPLE');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """
        )

        op.execute(
            """
            DO $$ BEGIN
                CREATE TYPE applicationcycle AS ENUM ('SEMESTER', 'ANNUAL');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """
        )

        # Create scholarship_types table
        op.create_table(
            "scholarship_types",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("name_en", sa.String(200), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("description_en", sa.Text(), nullable=True),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("sub_type_list", postgresql.JSON(astext_type=sa.Text()), nullable=True),
            sa.Column(
                "sub_type_selection_mode",
                sa.Enum("SINGLE", "MULTIPLE", name="subtypeselectionmode"),
                nullable=False,
                server_default="SINGLE",
            ),
            sa.Column(
                "application_cycle",
                sa.Enum("SEMESTER", "ANNUAL", name="applicationcycle"),
                nullable=False,
                server_default="SEMESTER",
            ),
            sa.Column("whitelist_enabled", sa.Boolean(), nullable=True, server_default=sa.text("false")),
            sa.Column("status", sa.String(20), nullable=True, server_default="active"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code"),
        )
        op.create_index("ix_scholarship_types_id", "scholarship_types", ["id"])
        op.create_index("ix_scholarship_types_code", "scholarship_types", ["code"])

    if "scholarship_rules" in existing_tables:
        # Table already exists, skip creation
        return

    # Create scholarship_rules table
    op.create_table(
        "scholarship_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scholarship_type_id", sa.Integer(), nullable=False),
        sa.Column("sub_type", sa.String(50), nullable=True),
        sa.Column("academic_year", sa.Integer(), nullable=True),
        sa.Column("semester", sa.Enum("FIRST", "SECOND", "SUMMER", "ANNUAL", name="semester"), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("template_name", sa.String(100), nullable=True),
        sa.Column("template_description", sa.Text(), nullable=True),
        sa.Column("rule_name", sa.String(100), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("tag", sa.String(20), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("condition_field", sa.String(100), nullable=True),
        sa.Column("operator", sa.String(20), nullable=True),
        sa.Column("expected_value", sa.String(500), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("message_en", sa.Text(), nullable=True),
        sa.Column("is_hard_rule", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("is_warning", sa.Boolean(), nullable=True, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["scholarship_type_id"],
            ["scholarship_types.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_scholarship_rules_id", "scholarship_rules", ["id"])
    op.create_index("ix_scholarship_rules_academic_year", "scholarship_rules", ["academic_year"])
    op.create_index("ix_scholarship_rules_semester", "scholarship_rules", ["semester"])


def downgrade() -> None:
    # Drop scholarship_rules indexes first
    op.drop_index("ix_scholarship_rules_semester", table_name="scholarship_rules")
    op.drop_index("ix_scholarship_rules_academic_year", table_name="scholarship_rules")
    op.drop_index("ix_scholarship_rules_id", table_name="scholarship_rules")

    # Drop scholarship_rules table
    op.drop_table("scholarship_rules")

    # Drop scholarship_types indexes
    op.drop_index("ix_scholarship_types_code", table_name="scholarship_types")
    op.drop_index("ix_scholarship_types_id", table_name="scholarship_types")

    # Drop scholarship_types table
    op.drop_table("scholarship_types")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS applicationcycle CASCADE")
    op.execute("DROP TYPE IF EXISTS subtypeselectionmode CASCADE")
