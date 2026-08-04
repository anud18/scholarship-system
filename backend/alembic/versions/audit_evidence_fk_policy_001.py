"""Explicit FK delete policies for evidence tables (issues #979/#983, gaps G17/G21)

- email_history.application_id / scheduled_emails.application_id → ON DELETE
  SET NULL: emails are delivery EVIDENCE — they must survive the referenced
  application being hard-deleted, and must not make that deletion fail with
  an FK violation (draft hard-delete previously rolled back silently when a
  related email existed).
- audit_logs.user_id → ON DELETE RESTRICT (explicit): audit rows carry no
  independent actor snapshot, so the users row they point at must not be
  deletable while audit history exists. RESTRICT pins what was previously an
  implicit NO ACTION default.

Revision ID: audit_evidence_fk_001
Revises: contact_phone_tw_mobile_001
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "audit_evidence_fk_001"
down_revision: Union[str, None] = "contact_phone_tw_mobile_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_fk_names(inspector, table: str, column: str) -> list:
    return [
        fk["name"]
        for fk in inspector.get_foreign_keys(table)
        if column in fk.get("constrained_columns", []) and fk.get("name")
    ]


def _retarget_fk(table: str, column: str, referred: str, ondelete: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return
    for name in _existing_fk_names(inspector, table, column):
        op.drop_constraint(name, table, type_="foreignkey")
    op.create_foreign_key(
        f"fk_{table}_{column}_{ondelete.replace(' ', '_').lower()}",
        table,
        referred,
        [column],
        ["id"],
        ondelete=ondelete,
    )


def upgrade() -> None:
    _retarget_fk("email_history", "application_id", "applications", "SET NULL")
    _retarget_fk("scheduled_emails", "application_id", "applications", "SET NULL")
    _retarget_fk("audit_logs", "user_id", "users", "RESTRICT")


def downgrade() -> None:
    # Back to unspecified (NO ACTION) delete policies.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table, column, referred in (
        ("email_history", "application_id", "applications"),
        ("scheduled_emails", "application_id", "applications"),
        ("audit_logs", "user_id", "users"),
    ):
        if table not in inspector.get_table_names():
            continue
        for name in _existing_fk_names(inspector, table, column):
            op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(f"fk_{table}_{column}", table, referred, [column], ["id"])
