"""Make audit_logs append-only at the database level (issue #966 / gap G4)

ISO 27001 A.8.15 / 資通系統防護基準: no privilege level — including the
application's own DB role and administrators — may alter or delete event
logs in place. Until now audit_logs was an ordinary mutable table, so a
compromised credential (or future code) could rewrite history untraceably.

- UPDATE is blocked unconditionally.
- DELETE is blocked unless the session sets the escape-hatch GUC
  `app.audit_purge = 'allowed'` — the hook for a future sanctioned
  destruction workflow (檔案法: 銷毀須經核准造冊), executed deliberately:

      BEGIN;
      SET LOCAL app.audit_purge = 'allowed';
      DELETE FROM audit_logs WHERE created_at < ...;
      COMMIT;

An ORM-level guard in app/models/audit_log.py provides the same property
for non-PostgreSQL test databases and fails faster in app code.

Revision ID: audit_logs_immutability_001
Revises: audit_evidence_fk_001
Create Date: 2026-06-11
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "audit_logs_immutability_001"
down_revision: Union[str, None] = "audit_evidence_fk_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRIGGER_FN = """
CREATE OR REPLACE FUNCTION audit_logs_block_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND current_setting('app.audit_purge', true) = 'allowed' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION
        'audit_logs is append-only: % rejected (set app.audit_purge=allowed inside a sanctioned destruction workflow to purge)',
        TG_OP
        USING ERRCODE = 'raise_exception';
END
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    inspector = sa.inspect(bind)
    if "audit_logs" not in inspector.get_table_names():
        return
    op.execute(TRIGGER_FN)
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("""
        CREATE TRIGGER audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation()
        """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_block_mutation()")
