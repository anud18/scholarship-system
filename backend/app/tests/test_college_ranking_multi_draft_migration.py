"""Guards for migration college_ranking_multi_draft_001 (several drafts, one finalized).

No live PostgreSQL in the test lanes, so the DDL branches run against a recorded
`op` and a stubbed inspector: the full unique index is swapped for a partial one
(finalized rows only), both steps are existence-checked, and the downgrade never
deletes rankings — it re-creates the old index only when no scope is crowded.
The partial index must also stay identical to the model's declaration, which is
what the SQLite test schema (Base.metadata.create_all) is built from.
"""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.models.college_review import CollegeRanking

_BACKEND = Path(__file__).resolve().parents[2]
_MIGRATION = _BACKEND / "alembic" / "versions" / "college_ranking_multi_draft_001.py"

OLD_INDEX = "uq_college_rankings_single_per_college"
NEW_INDEX = "uq_college_rankings_finalized_per_college"


def _load():
    spec = importlib.util.spec_from_file_location("mig_college_ranking_multi_draft", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def migration():
    return _load()


def _run(migration, monkeypatch, step: str, *, tables=("college_rankings",), indexes=(), crowded_scopes=0):
    """Run upgrade()/downgrade() against a recorded op and a stubbed inspector."""
    bind = MagicMock()
    bind.execute.return_value.scalar.return_value = crowded_scopes
    inspector = SimpleNamespace(
        get_table_names=lambda: list(tables),
        get_indexes=lambda table: [{"name": name} for name in indexes],
    )
    op = MagicMock()
    op.get_bind.return_value = bind
    monkeypatch.setattr(migration, "op", op)
    monkeypatch.setattr(migration, "sa", SimpleNamespace(text=sa.text, inspect=lambda _bind: inspector))
    getattr(migration, step)()
    return op, bind


def _postgres_ddl(create_index_call) -> str:
    """Compile a recorded op.create_index(...) call to PostgreSQL DDL."""
    name, table_name, columns = create_index_call.args
    table = sa.Table(
        table_name,
        sa.MetaData(),
        *(sa.Column(column, sa.String) for column in columns if isinstance(column, str)),
        sa.Column("is_finalized", sa.Boolean),
    )
    index = sa.Index(
        name,
        *(table.c[column] if isinstance(column, str) else column for column in columns),
        **create_index_call.kwargs,
    )
    return str(CreateIndex(index).compile(dialect=postgresql.dialect()))


def _normalise(ddl: str) -> str:
    return re.sub(r"\s+", " ", ddl).lower()


def test_revision_chains_after_the_academy_y_merge(migration):
    # The Y -> E ranking merge must run while one ranking per scope still holds.
    assert migration.revision == "college_ranking_multi_draft_001"
    assert migration.down_revision == "merge_academy_y_into_e_001"
    assert migration.OLD_INDEX_NAME == OLD_INDEX
    assert migration.NEW_INDEX_NAME == NEW_INDEX


def test_alembic_history_has_a_single_head():
    config = Config(str(_BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND / "alembic"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_upgrade_swaps_the_full_index_for_a_partial_one(migration, monkeypatch):
    op, _bind = _run(migration, monkeypatch, "upgrade", indexes=[OLD_INDEX])

    op.drop_index.assert_called_once_with(OLD_INDEX, table_name="college_rankings")
    op.create_index.assert_called_once()
    ddl = _postgres_ddl(op.create_index.call_args)
    assert ddl == (
        f"CREATE UNIQUE INDEX {NEW_INDEX} ON college_rankings (scholarship_type_id, sub_type_code, academic_year, "
        "COALESCE(semester, 'yearly'), COALESCE(college_code, '')) WHERE is_finalized IS TRUE"
    )


def test_partial_index_matches_the_model_declaration(migration, monkeypatch):
    op, _bind = _run(migration, monkeypatch, "upgrade", indexes=[OLD_INDEX])

    [model_index] = [index for index in CollegeRanking.__table__.indexes if index.name == NEW_INDEX]
    assert not [index for index in CollegeRanking.__table__.indexes if index.name == OLD_INDEX]
    model_ddl = str(CreateIndex(model_index).compile(dialect=postgresql.dialect()))
    assert _normalise(model_ddl) == _normalise(_postgres_ddl(op.create_index.call_args))
    # Without sqlite_where the SQLite test schema would get a FULL unique index
    # and reject the second draft.
    assert model_index.dialect_options["sqlite"]["where"] is not None


@pytest.mark.parametrize(
    "indexes, tables",
    [
        ([NEW_INDEX], ("college_rankings",)),  # already upgraded
        ([], ()),  # table missing
    ],
)
def test_upgrade_is_existence_checked(migration, monkeypatch, indexes, tables):
    op, _bind = _run(migration, monkeypatch, "upgrade", indexes=indexes, tables=tables)

    op.drop_index.assert_not_called()
    op.create_index.assert_not_called()


def test_downgrade_restores_the_full_index_when_every_scope_has_one_ranking(migration, monkeypatch):
    op, bind = _run(migration, monkeypatch, "downgrade", indexes=[NEW_INDEX], crowded_scopes=0)

    op.drop_index.assert_called_once_with(NEW_INDEX, table_name="college_rankings")
    bind.execute.assert_called_once()
    assert "HAVING COUNT(*) > 1" in str(bind.execute.call_args.args[0])
    op.create_index.assert_called_once()
    name, table_name, columns = op.create_index.call_args.args
    assert (name, table_name) == (OLD_INDEX, "college_rankings")
    assert op.create_index.call_args.kwargs == {"unique": True}
    assert "WHERE" not in _postgres_ddl(op.create_index.call_args)


def test_downgrade_keeps_every_ranking_when_a_scope_holds_several(migration, monkeypatch):
    logger = MagicMock()
    monkeypatch.setattr(migration, "logger", logger)

    op, _bind = _run(migration, monkeypatch, "downgrade", indexes=[NEW_INDEX], crowded_scopes=2)

    op.drop_index.assert_called_once_with(NEW_INDEX, table_name="college_rankings")
    op.create_index.assert_not_called()
    op.execute.assert_not_called()  # never deletes rankings to make room for the old index
    logger.warning.assert_called_once()
    assert OLD_INDEX in logger.warning.call_args.args


def test_downgrade_is_a_no_op_when_the_old_index_still_exists(migration, monkeypatch):
    op, bind = _run(migration, monkeypatch, "downgrade", indexes=[OLD_INDEX])

    op.drop_index.assert_not_called()
    op.create_index.assert_not_called()
    bind.execute.assert_not_called()
