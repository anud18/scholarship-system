"""add sub_type, allocation_year, project_number to payment_rosters; add project_numbers to scholarship_configurations

Revision ID: add_roster_sub_type_001
Revises: add_alloc_year_roster_001
Create Date: 2026-03-02

Supports per-allocation-year roster generation for NSTC multi-year supplementary distribution (補發).
Each roster now represents a specific (sub_type, allocation_year) combination.
project_numbers in scholarship_configurations stores admin-entered project codes per sub_type per year.
"""

from alembic import op
import sqlalchemy as sa


revision = "add_roster_sub_type_001"
down_revision = "add_alloc_year_roster_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Add project_numbers to scholarship_configurations
    sc_columns = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "project_numbers" not in sc_columns:
        op.add_column(
            "scholarship_configurations",
            sa.Column("project_numbers", sa.JSON(), nullable=True, comment="計畫編號 per sub_type per year: {'nstc': {'115': '115RXXXXXXX', '114': '114RXXXXXXX'}, 'moe_1w': {'115': '115CXXXXXX'}}"),
        )

    # 2. Add sub_type, allocation_year, project_number to payment_rosters
    pr_columns = [c["name"] for c in inspector.get_columns("payment_rosters")]

    if "sub_type" not in pr_columns:
        op.add_column(
            "payment_rosters",
            sa.Column("sub_type", sa.String(50), nullable=True, comment="獎學金子類型 (e.g. nstc, moe_1w)"),
        )

    if "allocation_year" not in pr_columns:
        op.add_column(
            "payment_rosters",
            sa.Column("allocation_year", sa.Integer(), nullable=True, comment="消耗配額的學年度 (補發時與 academic_year 不同)"),
        )

    if "project_number" not in pr_columns:
        op.add_column(
            "payment_rosters",
            sa.Column("project_number", sa.String(100), nullable=True, comment="計畫編號 e.g. 115RXXXXXXX"),
        )

    # 3. Drop old unique constraint and add new functional unique index
    # Old constraint: (scholarship_configuration_id, period_label)
    # New constraint: (scholarship_configuration_id, period_label, COALESCE(allocation_year, -1), COALESCE(sub_type, ''))
    try:
        existing_constraints = [c["name"] for c in inspector.get_unique_constraints("payment_rosters")]
        if "uq_roster_scholarship_period" in existing_constraints:
            op.drop_constraint("uq_roster_scholarship_period", "payment_rosters", type_="unique")
    except Exception:
        pass  # Constraint may not exist

    # Create functional unique index for PostgreSQL
    try:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
        if "uq_roster_scholarship_period_alloc" not in existing_indexes:
            op.execute(
                """
                CREATE UNIQUE INDEX uq_roster_scholarship_period_alloc
                ON payment_rosters (
                    scholarship_configuration_id,
                    period_label,
                    COALESCE(allocation_year, -1),
                    COALESCE(sub_type, '')
                )
                """
            )
    except Exception:
        pass


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop the functional unique index
    try:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
        if "uq_roster_scholarship_period_alloc" in existing_indexes:
            op.drop_index("uq_roster_scholarship_period_alloc", table_name="payment_rosters")
    except Exception:
        pass

    # Restore old unique constraint
    try:
        existing_constraints = [c["name"] for c in inspector.get_unique_constraints("payment_rosters")]
        if "uq_roster_scholarship_period" not in existing_constraints:
            op.create_unique_constraint(
                "uq_roster_scholarship_period",
                "payment_rosters",
                ["scholarship_configuration_id", "period_label"],
            )
    except Exception:
        pass

    # Drop added columns
    pr_columns = [c["name"] for c in inspector.get_columns("payment_rosters")]
    for col in ["project_number", "allocation_year", "sub_type"]:
        if col in pr_columns:
            op.drop_column("payment_rosters", col)

    sc_columns = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "project_numbers" in sc_columns:
        op.drop_column("scholarship_configurations", "project_numbers")
