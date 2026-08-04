"""scrub historical std_pid plaintext from audit_logs JSON columns (issue #73 follow-up)

PR #202 (``20260512_encrypt_std_pid``) only encrypted live
``applications.student_data``. Historical rows in ``audit_logs.old_values``
and ``audit_logs.new_values`` that snapshotted ``student_data`` still hold
plaintext ``std_pid`` (Taiwan national ID) on disk. This migration walks
``audit_logs`` in batches and replaces every ``std_pid`` value (at any
depth) with ``[REDACTED]``.

Design choices (mirrors ``20260512_encrypt_std_pid``):

- **Batched cursor-based loop** over ``id`` so memory stays bounded even
  on tables with millions of rows.
- **Idempotent**: rows whose JSON columns don't textually contain
  ``"std_pid"`` are skipped via a SQL ``LIKE`` filter; the in-memory walk
  also short-circuits when no redaction was needed. Re-running is a no-op.
- **Recursive walk**: ``redact_dict_pii`` only handles a shallow dict, but
  ``audit_logs.old_values`` typically carries a snapshot of a full
  ``applications`` row whose ``student_data`` is a nested object. We walk
  dicts and lists in-place.
- **Lazy import** of ``redact_dict_pii`` inside ``upgrade()`` so
  ``alembic show`` works without the env / key material being loaded.
- **No-op downgrade**: per CLAUDE.md "no backward compatibility" policy
  and to match PR #202's pattern — we cannot un-redact ``[REDACTED]`` back
  into the original ``std_pid``.

Revision ID: 20260513_scrub_pii_audit
Revises: 20260512_encrypt_std_pid
Create Date: 2026-05-13
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260513_scrub_pii_audit"
down_revision: Union[str, None] = "20260512_encrypt_std_pid"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BATCH_SIZE = 500
# JSON columns on audit_logs that may have captured a student_data snapshot
# containing plaintext std_pid. ``meta_data`` and ``request_headers`` are
# also JSON columns, but historically the writer only ever placed PII into
# ``old_values`` / ``new_values``. We still walk all four for defense in
# depth — the cost is negligible since we LIKE-filter rows up front.
_JSON_COLUMNS = ("old_values", "new_values", "meta_data", "request_headers")
_PII_KEYS = ("std_pid",)
_PLACEHOLDER = "[REDACTED]"


def _redact_recursive(node, redact_dict_pii, pii_keys, placeholder):
    """Walk ``node`` (dict / list / scalar) and redact any value at a
    ``pii_keys`` member key. Returns ``(new_node, changed)``.

    Dict-level redaction is delegated to :func:`app.core.pii_crypto.redact_dict_pii`
    (the shared helper introduced in PR #202) so both the audit-log writer
    and this back-fill use the exact same redaction semantics. We layer
    recursion on top because ``audit_logs.old_values`` typically captures a
    nested snapshot (e.g. ``{"student_data": {"std_pid": ...}}``).

    ``changed`` is ``True`` iff at least one redaction happened. Used by the
    caller to skip the UPDATE when no change is needed (extra idempotency
    layer on top of the SQL LIKE filter; a payload that mentions
    ``std_pid`` somewhere unrelated will still skip this branch).
    """
    if isinstance(node, dict):
        # First recurse into children so nested ``student_data`` blobs get
        # rewritten too.
        rewritten = {}
        changed = False
        for k, v in node.items():
            new_v, sub_changed = _redact_recursive(v, redact_dict_pii, pii_keys, placeholder)
            rewritten[k] = new_v
            changed = changed or sub_changed
        # Then apply the shallow helper at this level so the PR #202
        # ``redact_dict_pii`` semantics own the actual key replacement.
        after = redact_dict_pii(rewritten, keys=pii_keys, placeholder=placeholder)
        if after is not rewritten:
            # Helper returned a copy; detect whether it mutated a target key.
            for k in pii_keys:
                if k in rewritten and rewritten[k] not in (None, "") and after.get(k) == placeholder:
                    if rewritten[k] != placeholder:
                        changed = True
                    break
        return after, changed
    if isinstance(node, list):
        out = []
        changed = False
        for item in node:
            new_item, sub_changed = _redact_recursive(item, redact_dict_pii, pii_keys, placeholder)
            out.append(new_item)
            changed = changed or sub_changed
        return out, changed
    return node, False


def _coerce_json(value):
    """Normalize a JSON column read result into a Python object or ``None``.

    PostgreSQL ``JSON`` columns deserialize into Python ``dict`` / ``list``
    automatically; SQLite ``JSON`` columns hand back a JSON-encoded string.
    Either way, after this function the value is a native Python object or
    ``None``.
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        if value == "":
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # Not valid JSON — leave it alone. We never overwrite a column
            # whose content we can't safely parse.
            return None
    return None


def upgrade() -> None:
    """Redact ``std_pid`` from every audit_logs row's JSON snapshots."""
    # Lazy import so ``alembic show`` works even when env keys aren't loaded.
    from app.core.pii_crypto import redact_dict_pii

    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    # The audit_logs table may not exist on a brand-new minimal test DB.
    inspector = sa.inspect(bind)
    if "audit_logs" not in inspector.get_table_names():
        return

    # Idempotency pre-filter: skip rows whose JSON columns don't textually
    # contain "std_pid". Casting JSON to text is supported on both PG
    # (``::text``) and SQLite (``CAST(... AS TEXT)``).
    like_clauses = " OR ".join(
        [
            (f"CAST({col} AS TEXT) LIKE '%\"std_pid\"%'" if is_sqlite else f"({col})::text LIKE '%\"std_pid\"%'")
            for col in _JSON_COLUMNS
        ]
    )

    last_id = 0
    while True:
        select_sql = sa.text(
            f"SELECT id, {', '.join(_JSON_COLUMNS)} FROM audit_logs "
            f"WHERE id > :last_id AND ({like_clauses}) "
            f"ORDER BY id ASC LIMIT :limit"
        )
        rows = bind.execute(
            select_sql,
            {"last_id": last_id, "limit": _BATCH_SIZE},
        ).fetchall()

        if not rows:
            break

        for row in rows:
            row_id = row[0]
            last_id = row_id

            updates = {}
            for idx, col_name in enumerate(_JSON_COLUMNS, start=1):
                raw = row[idx]
                parsed = _coerce_json(raw)
                if parsed is None:
                    continue
                new_value, changed = _redact_recursive(parsed, redact_dict_pii, _PII_KEYS, _PLACEHOLDER)
                if changed:
                    updates[col_name] = new_value

            if not updates:
                continue

            set_clause = ", ".join(
                [f"{col} = CAST(:{col} AS JSON)" if not is_sqlite else f"{col} = :{col}" for col in updates]
            )
            params = {col: json.dumps(val, ensure_ascii=False) for col, val in updates.items()}
            params["id"] = row_id
            bind.execute(
                sa.text(f"UPDATE audit_logs SET {set_clause} WHERE id = :id"),
                params,
            )


def downgrade() -> None:
    """Intentional no-op.

    Mirrors ``20260512_encrypt_std_pid``'s no-op downgrade. Redaction is
    lossy by design — the original ``std_pid`` plaintext was destroyed on
    purpose and there is no inverse. Per CLAUDE.md's "no backward
    compatibility" policy we do not synthesize fallback data here.
    """
    pass
