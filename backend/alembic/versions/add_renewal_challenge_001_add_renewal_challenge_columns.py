"""Add renewal challenge columns + partial unique indexes + status enum value

Revision ID: add_renewal_challenge_001
Revises: seed_phd_college_export_001
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "add_renewal_challenge_001"
down_revision = "seed_phd_college_export_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("applications")]

    # 1. Add enum value
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'cancelled_by_challenge'")

    # 2. Add new columns (idempotent)
    if "challenges_application_id" not in existing_columns:
        op.add_column(
            "applications",
            sa.Column(
                "challenges_application_id",
                sa.Integer(),
                sa.ForeignKey("applications.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_applications_challenges_application_id",
            "applications",
            ["challenges_application_id"],
        )

    if "cancelled_due_to_application_id" not in existing_columns:
        op.add_column(
            "applications",
            sa.Column(
                "cancelled_due_to_application_id",
                sa.Integer(),
                sa.ForeignKey("applications.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_applications_cancelled_due_to_application_id",
            "applications",
            ["cancelled_due_to_application_id"],
        )

    # 3. Drop old single UNIQUE (was previously "uq_user_scholarship_academic_term"),
    # add three partial unique indexes
    existing_constraints = [c["name"] for c in inspector.get_unique_constraints("applications")]
    if "uq_user_scholarship_academic_term" in existing_constraints:
        op.drop_constraint("uq_user_scholarship_academic_term", "applications", type_="unique")

    op.create_index(
        "uq_user_renewal_app",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
        unique=True,
        postgresql_where=sa.text("is_renewal = true AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_user_challenge_app",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
        unique=True,
        postgresql_where=sa.text("is_renewal = false AND challenges_application_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "uq_user_pure_new_app",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
        unique=True,
        postgresql_where=sa.text("is_renewal = false AND challenges_application_id IS NULL AND deleted_at IS NULL"),
    )

    # 4. Check constraint: cancelled_by_challenge requires cancelled_due_to_application_id
    # NOTE: status::text cast is required because PostgreSQL forbids referencing a
    # newly-added enum value (added in step 1 above) inside the same transaction
    # without explicit casting (psycopg2.errors.UnsafeNewEnumValueUsage).
    # The partial-index predicates above use deleted_at IS NULL (no cast needed).
    op.create_check_constraint(
        "chk_cancelled_by_challenge_link",
        "applications",
        "status::text != 'cancelled_by_challenge' OR cancelled_due_to_application_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("chk_cancelled_by_challenge_link", "applications", type_="check")
    op.drop_index("uq_user_pure_new_app", table_name="applications")
    op.drop_index("uq_user_challenge_app", table_name="applications")
    op.drop_index("uq_user_renewal_app", table_name="applications")
    op.create_unique_constraint(
        "uq_user_scholarship_academic_term",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
    )
    op.drop_index("ix_applications_cancelled_due_to_application_id", table_name="applications")
    op.drop_column("applications", "cancelled_due_to_application_id")
    op.drop_index("ix_applications_challenges_application_id", table_name="applications")
    op.drop_column("applications", "challenges_application_id")
