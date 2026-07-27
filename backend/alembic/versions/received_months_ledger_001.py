"""Imported received-months ledger; retire the ranking-item override columns.

Creates ``received_month_imports`` + ``student_received_month_records``, copies
any existing ``college_ranking_items.received_months_source = 'imported'``
overrides into the new ledger, then drops both columns.

The old override lived on a ranking item, so it could only ever exist for a
student already in a 排名. The ledger is keyed by 學號 alone, so 國科會's file
can be imported for students this system has never seen.

Revision ID: received_months_ledger_001
Revises: cancel_prior_state_001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "received_months_ledger_001"
down_revision = "cancel_prior_state_001"
branch_labels = None
depends_on = None

LEGACY_IMPORT_FILE_NAME = "legacy-migration"


def _json_type(bind):
    return postgresql.JSONB if bind.dialect.name == "postgresql" else sa.JSON


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    json_type = _json_type(bind)

    if "received_month_imports" not in existing_tables:
        op.create_table(
            "received_month_imports",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("importer_id", sa.Integer(), nullable=False),
            sa.Column("scholarship_type_id", sa.Integer(), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("parsed_data", json_type(), nullable=True),
            sa.Column("data_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("warning_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["importer_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["scholarship_type_id"], ["scholarship_types.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_received_month_imports_id", "received_month_imports", ["id"])
        op.create_index("ix_received_month_imports_importer_id", "received_month_imports", ["importer_id"])
        op.create_index(
            "ix_received_month_imports_scholarship_type_id", "received_month_imports", ["scholarship_type_id"]
        )
        op.create_index("ix_received_month_imports_status", "received_month_imports", ["status"])
        op.create_index("ix_received_month_imports_data_expires_at", "received_month_imports", ["data_expires_at"])

    if "student_received_month_records" not in existing_tables:
        op.create_table(
            "student_received_month_records",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("student_number", sa.String(length=20), nullable=False),
            sa.Column("scholarship_type_id", sa.Integer(), nullable=False),
            sa.Column("months", sa.Integer(), nullable=False),
            sa.Column("award_start_month", sa.Integer(), nullable=True),
            sa.Column("award_current_month", sa.Integer(), nullable=True),
            sa.Column("raw_row", json_type(), nullable=True),
            sa.Column("import_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["scholarship_type_id"], ["scholarship_types.id"]),
            sa.ForeignKeyConstraint(["import_id"], ["received_month_imports.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("student_number", "scholarship_type_id", name="uq_received_months_student_type"),
        )
        op.create_index("ix_student_received_month_records_id", "student_received_month_records", ["id"])
        op.create_index(
            "ix_student_received_month_records_student_number", "student_received_month_records", ["student_number"]
        )
        op.create_index("ix_student_received_month_records_import_id", "student_received_month_records", ["import_id"])
        op.create_index(
            "ix_received_months_type_student",
            "student_received_month_records",
            ["scholarship_type_id", "student_number"],
        )

    _migrate_legacy_overrides(bind, inspector)
    _drop_legacy_columns(bind)


def _migrate_legacy_overrides(bind, inspector) -> None:
    """Copy 'imported' ranking-item overrides into the ledger.

    學號 comes from applications.student_data->>'std_stdcode'; the scholarship
    type from the parent college_rankings row. Rows without a resolvable 學號
    are skipped — they cannot be keyed in a ledger that has no application FK.

    Where the same (學號, type) appears on several ranking items (different
    sub_types), the highest month count wins; they should agree, and taking the
    max never understates against the 36-month cap.
    """
    if "college_ranking_items" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("college_ranking_items")}
    if not {"received_months", "received_months_source"} <= columns:
        return

    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        student_number_expr = "a.student_data->>'std_stdcode'"
    else:
        student_number_expr = "json_extract(a.student_data, '$.std_stdcode')"

    legacy_rows = bind.execute(sa.text(f"""
            SELECT {student_number_expr} AS student_number,
                   cr.scholarship_type_id AS scholarship_type_id,
                   MAX(cri.received_months) AS months
            FROM college_ranking_items cri
            JOIN college_rankings cr ON cr.id = cri.ranking_id
            JOIN applications a ON a.id = cri.application_id
            WHERE cri.received_months_source = 'imported'
              AND cri.received_months IS NOT NULL
              AND cr.scholarship_type_id IS NOT NULL
              AND {student_number_expr} IS NOT NULL
              AND {student_number_expr} <> ''
            GROUP BY {student_number_expr}, cr.scholarship_type_id
            """)).fetchall()

    if not legacy_rows:
        return

    # One synthetic import run per scholarship type, attributed to the lowest
    # admin user id so the FK to users is satisfied on any dataset.
    admin_id = bind.execute(sa.text("SELECT MIN(id) FROM users")).scalar()
    if admin_id is None:
        # No users at all (fresh DB) — nothing meaningful to attribute, and by
        # definition there is no real legacy data to preserve.
        return

    run_ids: dict[int, int] = {}
    for row in legacy_rows:
        type_id = row.scholarship_type_id
        if type_id not in run_ids:
            run_ids[type_id] = bind.execute(
                sa.text(
                    """
                    INSERT INTO received_month_imports
                        (importer_id, scholarship_type_id, file_name, status,
                         total_rows, valid_rows, warning_rows, error_rows, confirmed_at)
                    VALUES (:importer_id, :type_id, :file_name, 'completed', 0, 0, 0, 0, NOW())
                    RETURNING id
                    """
                    if bind.dialect.name == "postgresql"
                    else """
                    INSERT INTO received_month_imports
                        (importer_id, scholarship_type_id, file_name, status,
                         total_rows, valid_rows, warning_rows, error_rows, confirmed_at)
                    VALUES (:importer_id, :type_id, :file_name, 'completed', 0, 0, 0, 0, CURRENT_TIMESTAMP)
                    """
                ),
                {"importer_id": admin_id, "type_id": type_id, "file_name": LEGACY_IMPORT_FILE_NAME},
            ).scalar()

        bind.execute(
            sa.text("""
                INSERT INTO student_received_month_records
                    (student_number, scholarship_type_id, months, import_id)
                VALUES (:student_number, :type_id, :months, :import_id)
                """),
            {
                "student_number": str(row.student_number).strip(),
                "type_id": type_id,
                "months": int(row.months),
                "import_id": run_ids[type_id],
            },
        )

    for type_id, run_id in run_ids.items():
        count = bind.execute(
            sa.text("SELECT COUNT(*) FROM student_received_month_records WHERE import_id = :run_id"),
            {"run_id": run_id},
        ).scalar()
        bind.execute(
            sa.text("UPDATE received_month_imports SET total_rows = :n, valid_rows = :n WHERE id = :run_id"),
            {"n": count, "run_id": run_id},
        )


def _drop_legacy_columns(bind) -> None:
    inspector = sa.inspect(bind)
    if "college_ranking_items" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("college_ranking_items")}
    with op.batch_alter_table("college_ranking_items") as batch_op:
        if "received_months" in columns:
            batch_op.drop_column("received_months")
        if "received_months_source" in columns:
            batch_op.drop_column("received_months_source")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "college_ranking_items" in tables:
        columns = {c["name"] for c in inspector.get_columns("college_ranking_items")}
        with op.batch_alter_table("college_ranking_items") as batch_op:
            if "received_months" not in columns:
                batch_op.add_column(sa.Column("received_months", sa.Integer(), nullable=True))
            if "received_months_source" not in columns:
                batch_op.add_column(sa.Column("received_months_source", sa.String(length=20), nullable=True))

    if "student_received_month_records" in tables:
        op.drop_table("student_received_month_records")
    if "received_month_imports" in tables:
        op.drop_table("received_month_imports")
