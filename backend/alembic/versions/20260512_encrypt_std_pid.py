"""encrypt existing applications.student_data.std_pid at rest (issue #73)

Walks the ``applications`` table in batches and replaces the plaintext
``std_pid`` inside the JSON ``student_data`` column with an AES-256-GCM
envelope (``pii:v1:...``). Idempotent — re-running is a no-op because
``is_encrypted()`` skips already-enveloped values.

Historical ``audit_logs.old_values`` / ``new_values`` are intentionally
**NOT** rewritten in this migration. Per the design note on issue #73, that
historical scrub is deferred to a follow-up. See ``TODO(#73-followup)``
below.

Revision ID: 20260512_encrypt_std_pid
Revises: seed_phd_college_export_001
Create Date: 2026-05-12
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# TODO(#73-followup): scrub historical std_pid copies inside
# audit_logs.old_values / new_values JSON. Not done here because the user
# explicitly deferred it.


# revision identifiers, used by Alembic.
revision: str = "20260512_encrypt_std_pid"
down_revision: Union[str, None] = "seed_phd_college_export_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BATCH_SIZE = 500


def upgrade() -> None:
    """Encrypt plaintext std_pid in every applications.student_data row."""
    # Lazy import so `alembic show` works even when env keys aren't loaded.
    from app.core.pii_crypto import encrypt_pii_idempotent, is_encrypted

    bind = op.get_bind()

    last_id = 0
    while True:
        rows = bind.execute(
            sa.text(
                "SELECT id, student_data FROM applications "
                "WHERE id > :last_id AND student_data IS NOT NULL "
                "ORDER BY id ASC LIMIT :limit"
            ),
            {"last_id": last_id, "limit": _BATCH_SIZE},
        ).fetchall()

        if not rows:
            break

        for app_id, sd in rows:
            last_id = app_id
            if not isinstance(sd, dict):
                continue
            pid = sd.get("std_pid")
            if pid is None or pid == "":
                continue
            if is_encrypted(pid):
                continue
            new_sd = dict(sd)
            new_sd["std_pid"] = encrypt_pii_idempotent(pid)
            bind.execute(
                sa.text("UPDATE applications SET student_data = CAST(:sd AS JSON) " "WHERE id = :id"),
                {"sd": json.dumps(new_sd, ensure_ascii=False), "id": app_id},
            )


def downgrade() -> None:
    """Intentional no-op.

    Per CLAUDE.md "no backward compatibility" policy, we don't carry the
    decryption surface backwards. Restoring plaintext at downgrade time
    would require the active key plus a one-shot decrypt loop, which would
    also re-expose PII unnecessarily. Operators that truly need to roll
    back should run a separate decryption script offline.
    """
    pass
