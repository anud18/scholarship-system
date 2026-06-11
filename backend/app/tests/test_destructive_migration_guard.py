"""Guard contract for the destructive migration 06e8a66d9437 (issue #963 / audit gap G1).

That revision TRUNCATE CASCADEs every application/review/payment table and its
downgrade() is a documented no-op — replayed against a database that holds real
申請紀錄 it would destroy years of audit-relevant history in one shot. These
tests pin the data-at-risk guard:

  - rows present + no override  -> RuntimeError, NOTHING truncated
  - rows present + ALLOW_DESTRUCTIVE_MIGRATIONS=true -> proceeds
  - fresh/empty database        -> proceeds (truncate is a no-op there)

Sync tests on purpose: they run in the CI `unit` lane.
"""

import importlib.util
import pathlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

MIGRATION_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions" / "06e8a66d9437_cleanup_old_applications.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_06e8a66d9437", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeConnection:
    """Stands in for the alembic bind. Records every executed statement."""

    def __init__(self, application_count: int, applications_table_exists: bool = True):
        self.application_count = application_count
        self.applications_table_exists = applications_table_exists
        self.statements: list[str] = []

    def execute(self, clause):
        sql = str(clause)
        self.statements.append(sql)
        if "to_regclass" in sql:
            return SimpleNamespace(scalar=lambda: ("applications" if self.applications_table_exists else None))
        if "count(*)" in sql.lower():
            return SimpleNamespace(scalar=lambda: self.application_count)
        # SAVEPOINT / TRUNCATE / RELEASE — nothing to return.
        return SimpleNamespace(scalar=lambda: None)

    def truncate_statements(self) -> list[str]:
        return [s for s in self.statements if s.upper().startswith("TRUNCATE")]


def _run_upgrade(connection, monkeypatch, allow: str | None):
    migration = _load_migration()
    if allow is None:
        monkeypatch.delenv("ALLOW_DESTRUCTIVE_MIGRATIONS", raising=False)
    else:
        monkeypatch.setenv("ALLOW_DESTRUCTIVE_MIGRATIONS", allow)
    with patch.object(migration.op, "get_bind", return_value=connection):
        migration.upgrade()


def test_refuses_when_applications_exist_and_no_override(monkeypatch):
    connection = FakeConnection(application_count=137)
    with pytest.raises(RuntimeError) as exc:
        _run_upgrade(connection, monkeypatch, allow=None)
    assert "137" in str(exc.value)
    assert "ALLOW_DESTRUCTIVE_MIGRATIONS" in str(exc.value)
    # The guard must fire BEFORE any destructive statement.
    assert connection.truncate_statements() == []


def test_explicit_override_allows_truncation(monkeypatch):
    connection = FakeConnection(application_count=137)
    _run_upgrade(connection, monkeypatch, allow="true")
    truncated = connection.truncate_statements()
    assert any("applications" in s for s in truncated)
    assert len(truncated) == 11  # all listed tables attempted


def test_fresh_database_proceeds_without_override(monkeypatch):
    # Empty applications table — the truncate is a no-op, first-time setup
    # (alembic upgrade head on a fresh DB) must not be blocked.
    connection = FakeConnection(application_count=0)
    _run_upgrade(connection, monkeypatch, allow=None)
    assert len(connection.truncate_statements()) == 11


def test_missing_applications_table_proceeds(monkeypatch):
    # to_regclass returns NULL on a database created before that table existed.
    connection = FakeConnection(application_count=0, applications_table_exists=False)
    _run_upgrade(connection, monkeypatch, allow=None)
    # No count query should have been issued against a missing table.
    assert not any("count(*)" in s.lower() for s in connection.statements)
    assert len(connection.truncate_statements()) == 11


def test_non_true_override_values_still_refuse(monkeypatch):
    # Only the literal "true" (case-insensitive) opts in — not "1"/"yes".
    for value in ("1", "yes", "false", ""):
        connection = FakeConnection(application_count=5)
        with pytest.raises(RuntimeError):
            _run_upgrade(connection, monkeypatch, allow=value)
        assert connection.truncate_statements() == []


def test_override_is_case_insensitive(monkeypatch):
    connection = FakeConnection(application_count=5)
    _run_upgrade(connection, monkeypatch, allow="TRUE")
    assert len(connection.truncate_statements()) == 11
