"""Integration test: scrub_pii_from_audit_logs migration (issue #73 follow-up).

Verifies the migration ``20260513_scrub_pii_from_audit_logs.py``:

- redacts ``std_pid`` in ``audit_logs.old_values`` / ``new_values``
  (including when nested inside a ``student_data`` snapshot)
- leaves other keys untouched
- is idempotent: running ``upgrade()`` a second time is a no-op
- leaves rows without ``std_pid`` alone (control row)
- handles ``meta_data`` and ``request_headers`` columns the same way
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# --- helpers -----------------------------------------------------------------


_MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent.parent / "alembic" / "versions" / "20260513_scrub_pii_from_audit_logs.py"
)


def _load_migration_module():
    """Import the migration file as a standalone module.

    We don't go through alembic itself — we just want to call ``upgrade()``
    against a controlled bind. ``op.get_bind()`` is the only alembic surface
    the migration uses; we patch it to return our test engine connection.
    """
    spec = importlib.util.spec_from_file_location(
        "scrub_pii_audit_migration",
        os.fspath(_MIGRATION_PATH),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _create_audit_logs_table(conn):
    """Create a minimal ``audit_logs`` table matching the columns the
    migration touches. We don't import the SQLAlchemy model because that
    drags in the full models package and triggers the StudentDataJSON
    type decorator, which would need real PII keys for the unrelated
    ``applications`` table."""
    conn.execute(text("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action VARCHAR(50) NOT NULL,
                resource_type VARCHAR(50) NOT NULL,
                resource_id VARCHAR(50),
                old_values JSON,
                new_values JSON,
                meta_data JSON,
                request_headers JSON
            )
            """))


def _insert(conn, **cols):
    """Insert one audit_logs row, JSON-encoding any dict values."""
    payload = {
        "user_id": 1,
        "action": "update",
        "resource_type": "application",
        "resource_id": None,
        "old_values": None,
        "new_values": None,
        "meta_data": None,
        "request_headers": None,
    }
    payload.update(cols)
    for k in ("old_values", "new_values", "meta_data", "request_headers"):
        if isinstance(payload[k], (dict, list)):
            payload[k] = json.dumps(payload[k], ensure_ascii=False)
    conn.execute(
        text(
            "INSERT INTO audit_logs "
            "(user_id, action, resource_type, resource_id, old_values, new_values, meta_data, request_headers) "
            "VALUES (:user_id, :action, :resource_type, :resource_id, :old_values, :new_values, "
            ":meta_data, :request_headers)"
        ),
        payload,
    )


def _fetch_json(conn, row_id, col):
    raw = conn.execute(
        text(f"SELECT {col} FROM audit_logs WHERE id = :id"),
        {"id": row_id},
    ).scalar()
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(raw)


# --- fixtures ----------------------------------------------------------------


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with eng.begin() as conn:
        _create_audit_logs_table(conn)
    yield eng
    eng.dispose()


@pytest.fixture
def migration():
    return _load_migration_module()


def _run_upgrade(migration, engine):
    """Invoke ``upgrade()`` with ``op.get_bind()`` patched to our engine.

    The migration calls ``op.get_bind()`` once at the top to grab a bind,
    then issues raw SQL through it. We patch the ``op`` module attribute
    inside the loaded migration so it returns a live connection bound to
    our test engine. Using ``engine.begin()`` ensures changes commit.
    """
    with engine.begin() as conn:
        with patch.object(migration.op, "get_bind", return_value=conn):
            migration.upgrade()


# --- tests -------------------------------------------------------------------


def test_redacts_std_pid_in_old_and_new_values(engine, migration):
    with engine.begin() as conn:
        _insert(
            conn,
            old_values={"std_pid": "A123456789", "other": "ok"},
            new_values={"std_pid": "B987654321", "other": "ok2"},
        )

    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        old = _fetch_json(conn, 1, "old_values")
        new = _fetch_json(conn, 1, "new_values")

    assert old == {"std_pid": "[REDACTED]", "other": "ok"}
    assert new == {"std_pid": "[REDACTED]", "other": "ok2"}


def test_redacts_nested_std_pid_inside_student_data_snapshot(engine, migration):
    nested_old = {
        "student_data": {
            "std_pid": "A123456789",
            "std_cname": "王小明",
            "trm_year": 114,
        },
        "status": "draft",
    }
    nested_new = {
        "student_data": {
            "std_pid": "A123456789",
            "std_cname": "王小明",
            "trm_year": 114,
        },
        "status": "submitted",
    }
    with engine.begin() as conn:
        _insert(conn, old_values=nested_old, new_values=nested_new)

    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        old = _fetch_json(conn, 1, "old_values")
        new = _fetch_json(conn, 1, "new_values")

    assert old["student_data"]["std_pid"] == "[REDACTED]"
    assert old["student_data"]["std_cname"] == "王小明"
    assert old["student_data"]["trm_year"] == 114
    assert old["status"] == "draft"

    assert new["student_data"]["std_pid"] == "[REDACTED]"
    assert new["status"] == "submitted"


def test_control_row_without_std_pid_is_unchanged(engine, migration):
    with engine.begin() as conn:
        _insert(
            conn,
            old_values={"other": "ok", "nested": {"x": 1}},
            new_values={"other": "ok2"},
        )

    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        old = _fetch_json(conn, 1, "old_values")
        new = _fetch_json(conn, 1, "new_values")

    assert old == {"other": "ok", "nested": {"x": 1}}
    assert new == {"other": "ok2"}


def test_redacts_in_meta_data_and_request_headers(engine, migration):
    with engine.begin() as conn:
        _insert(
            conn,
            meta_data={"std_pid": "C111222333", "tag": "audit"},
            request_headers={"X-Forwarded-For": "10.0.0.1", "std_pid": "D444555666"},
        )

    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        md = _fetch_json(conn, 1, "meta_data")
        rh = _fetch_json(conn, 1, "request_headers")

    assert md == {"std_pid": "[REDACTED]", "tag": "audit"}
    assert rh == {"X-Forwarded-For": "10.0.0.1", "std_pid": "[REDACTED]"}


def test_idempotent_rerun_is_noop(engine, migration):
    with engine.begin() as conn:
        _insert(conn, old_values={"std_pid": "A123456789", "other": "ok"})

    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        first = _fetch_json(conn, 1, "old_values")
    assert first == {"std_pid": "[REDACTED]", "other": "ok"}

    # Re-run: should be a no-op (LIKE filter no longer matches; even if it
    # did, recursive walk skips already-[REDACTED] values).
    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        second = _fetch_json(conn, 1, "old_values")
    assert second == first


def test_empty_table_is_safe(engine, migration):
    # No rows at all — the loop should exit immediately without error.
    _run_upgrade(migration, engine)
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM audit_logs")).scalar()
    assert count == 0


def test_null_json_columns_are_left_alone(engine, migration):
    with engine.begin() as conn:
        # All four JSON columns are NULL — the LIKE pre-filter excludes us.
        _insert(conn)

    _run_upgrade(migration, engine)

    with engine.connect() as conn:
        assert _fetch_json(conn, 1, "old_values") is None
        assert _fetch_json(conn, 1, "new_values") is None
        assert _fetch_json(conn, 1, "meta_data") is None
        assert _fetch_json(conn, 1, "request_headers") is None


def test_downgrade_is_noop(engine, migration):
    with engine.begin() as conn:
        _insert(conn, old_values={"std_pid": "A123456789"})
    # Just verify it doesn't raise and doesn't touch data.
    migration.downgrade()
    with engine.connect() as conn:
        assert _fetch_json(conn, 1, "old_values") == {"std_pid": "A123456789"}


def test_missing_audit_logs_table_is_safe(migration):
    """If the audit_logs table doesn't exist (fresh init scenario) the
    migration must return cleanly rather than raise."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        _run_upgrade(migration, eng)  # should be a clean no-op
    finally:
        eng.dispose()
